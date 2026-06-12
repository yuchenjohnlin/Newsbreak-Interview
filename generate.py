#!/usr/bin/env python3
"""One-sentence event description -> topic page HTML.

Orchestrates the whole pipeline; every stage is observable via artifacts
written to data/runs/{slug}/:

  1. intake gate (deterministic)        schemas.validate_intake
  2. intake plan (LLM #1, bounded)      synthesize.plan_intake -> category + facet queries
  3. search + fetch (deterministic)     Brave (headline + facet queries) -> trafilatura
  4. evidence pack (deterministic)      dedup, freshness sort, clip to budget, gate
  5. synthesis (LLM #2)                 synthesize.synthesize_page -> TopicPage JSON
  6. render (deterministic)             render.render_page -> out/{slug}.html

Usage:
    python generate.py [input_file] [--sentence "..."] [--model claude-...]
                       [--max-docs 6] [--outdir out]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
import os

from fetch_content import fetch_and_extract
from probe_search import call_brave, slug
from render import render_error_page, render_page, write_report
from schemas import Document, EvidencePack, GateError, validate_evidence, validate_intake
from synthesize import SYNTH_MODEL, plan_intake, synthesize_page

PER_DOC_CHAR_CAP = 6000
TOTAL_CHAR_BUDGET = 30000
SEARCH_POOL = 8          # results per query to consider (over-fetch headroom)
BRAVE_DELAY = 1.1        # free tier: 1 request/second


def clip_text(text: str, cap: int = PER_DOC_CHAR_CAP) -> str:
    """Clip to cap at the nearest paragraph (or sentence) boundary."""
    if len(text) <= cap:
        return text
    cut = text[:cap]
    for sep in ("\n", ". "):
        i = cut.rfind(sep)
        if i > cap // 2:
            return cut[: i + len(sep)].rstrip()
    return cut


def freshness_key(rec: dict) -> tuple:
    """Sort key: dated docs first (newest first), then undated by rank.
    Wikipedia dates are unreliable -> treated as undated."""
    date = rec.get("date")
    site = (rec.get("sitename") or "").lower()
    if date and "wikipedia" not in site:
        return (0, date and -int(date.replace("-", "")[:8] or 0), rec["rank"])
    return (1, 0, rec["rank"])


def gather_evidence(sentence: str, queries: list[str], key: str, max_docs: int) -> list[dict]:
    """Deterministic retrieval: candidate URLs from all queries (headline
    first), walk down fetching until max_docs successful extractions."""
    candidates: list[tuple[str, str, str | None]] = []  # (title, url, thumbnail)
    seen: set[str] = set()
    for q in [sentence] + queries:
        try:
            _raw, norm = call_brave(q, key, SEARCH_POOL)
        except Exception as e:  # noqa: BLE001 - one bad query shouldn't sink the run
            print(f"  [search] query failed ({e}): {q[:60]}")
            norm = []
        n_new = 0
        for hit in norm:
            url = hit.get("url")
            if url and url not in seen:
                seen.add(url)
                candidates.append((hit.get("title"), url, hit.get("thumbnail")))
                n_new += 1
        print(f"  [search] {n_new} new urls <- {q[:70]}")
        time.sleep(BRAVE_DELAY)

    docs, n_ok = [], 0
    seen_text: set[str] = set()  # same article via amp/mirror URLs
    for rank, (title, url, thumb) in enumerate(candidates, 1):
        rec = fetch_and_extract(url)
        rec["brave_title"], rec["rank"], rec["thumbnail_url"] = title, rank, thumb
        if rec["error"] is None and rec["char_len"] >= 300:
            fingerprint = rec["text"][:500]
            if fingerprint in seen_text:
                print(f"  [fetch] DUP {url[:70]} (same content as earlier doc)")
                continue
            seen_text.add(fingerprint)
            docs.append(rec)
            n_ok += 1
            print(f"  [fetch] OK  {rec['sitename'] or url[:40]} ({rec['char_len']} chars, date={rec['date']})")
        else:
            print(f"  [fetch] ERR {url[:70]} -> {rec['error'] or 'too short'}")
        if n_ok >= max_docs:
            break
        time.sleep(0.3)
    return docs


def build_pack(sentence: str, category: str, canonical: str, raw_docs: list[dict],
               total_budget: int = TOTAL_CHAR_BUDGET) -> EvidencePack:
    """Freshness-sort, clip to budgets, assign source_ids."""
    ordered = sorted(raw_docs, key=freshness_key)
    documents, used = [], 0
    for rec in ordered:
        if used >= total_budget:
            break
        text = clip_text(rec["text"], min(PER_DOC_CHAR_CAP, total_budget - used))
        used += len(text)
        documents.append(
            Document(
                source_id=len(documents) + 1,
                url=rec["url"],
                title=rec.get("title") or rec.get("brave_title"),
                sitename=rec.get("sitename"),
                author=rec.get("author"),
                date=rec.get("date"),
                thumbnail_url=rec.get("thumbnail_url"),
                text=text,
                char_len=len(text),
            )
        )
    return EvidencePack(
        sentence=sentence,
        category=category,
        canonical_name=canonical,
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        documents=documents,
    )


def run_one(sentence: str, key: str, model: str, max_docs: int, outdir: Path,
            template_name: str = "page.html.j2") -> Path:
    sentence = validate_intake(sentence)
    s = slug(sentence)
    rundir = Path("data/runs") / s
    rundir.mkdir(parents=True, exist_ok=True)

    plan, raw_plan = plan_intake(sentence)
    (rundir / "intake.json").write_text(json.dumps(raw_plan, indent=2, ensure_ascii=False))
    if not plan.is_real_event:
        raise GateError(f"input rejected by intake gate: {plan.reject_reason}")
    print(f"  [intake] category={plan.category} | {plan.canonical_name}")
    for q in plan.facet_queries:
        print(f"  [intake] facet query: {q}")

    raw_docs = gather_evidence(sentence, plan.facet_queries, key, max_docs)
    pack = build_pack(sentence, plan.category, plan.canonical_name or sentence, raw_docs)
    pack.documents = validate_evidence(pack.documents)
    (rundir / "evidence.json").write_text(pack.model_dump_json(indent=2))
    total = sum(d.char_len for d in pack.documents)
    print(f"  [evidence] {len(pack.documents)} docs, {total} chars after clipping")

    page, raw_page = synthesize_page(pack, model=model)
    (rundir / "page_raw.json").write_text(json.dumps(raw_page, indent=2, ensure_ascii=False))
    (rundir / "page.json").write_text(page.model_dump_json(indent=2))
    print(f"  [synth] ok: {page.headline!r} | {len(page.key_facts)} facts, {len(page.timeline)} timeline items")

    out_path = outdir / f"{s}.html"
    render_page(page, out_path, template_name=template_name)
    print(f"  [render] -> {out_path}")
    write_report(rundir, {
        "sentence": sentence, "orchestrator": "deterministic", "status": "success",
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "headline": page.headline, "n_documents": len(pack.documents),
        "template": template_name,
        "out_path": str(out_path),
    })
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_file", nargs="?", default="input")
    ap.add_argument("--sentence", help="Generate for a single sentence instead of the input file")
    ap.add_argument("--model", default=SYNTH_MODEL)
    ap.add_argument("--max-docs", type=int, default=6)
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--template", default="page.html.j2",
                    help="Jinja template in templates/ (default: page.html.j2; alternate: page_featured.html.j2)")
    args = ap.parse_args()

    load_dotenv()
    key = os.getenv("BRAVE_API_KEY")
    if not key:
        print("error: BRAVE_API_KEY not set", file=sys.stderr)
        return 1
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 1

    if args.sentence:
        sentences = [args.sentence]
    else:
        path = Path(args.input_file)
        if not path.exists():
            print(f"error: input file not found: {path}", file=sys.stderr)
            return 1
        sentences = [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    failures = 0
    for sent in sentences:
        print(f"\n=== {sent}")
        try:
            run_one(sent, key, args.model, args.max_docs, outdir, args.template)
        except (GateError, Exception) as e:  # noqa: BLE001
            failures += 1
            status = "rejected" if isinstance(e, GateError) else "failed"
            print(f"  {status.upper()}: {e}")
            s = slug(sent)
            write_report(Path("data/runs") / s, {"sentence": sent, "orchestrator": "deterministic",
                                                 "status": status, "message": str(e)})
            render_error_page(sent, status, str(e), s, outdir / f"{s}.html")
            print(f"  [error-page] -> {outdir / (s + '.html')}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
