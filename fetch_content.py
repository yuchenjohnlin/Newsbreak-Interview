#!/usr/bin/env python3
"""Fetch and extract article content for Brave search results.

Pipeline step 2 (retrieval). For each event sentence we:
  1. get the top Brave web results (live, or reused from data/probe/),
  2. download each result URL,
  3. extract the main article text + metadata (title, sitename, publish
     date) with trafilatura, dropping nav/ads/boilerplate.

Output: one manifest per query at data/pages/{slug}.json, holding the
extracted documents. This is the clean text we'll later feed to the LLM.

Usage:
    python fetch_content.py [input_file] [--max-results 5]
                            [--from-probe] [--outdir data/pages] [--delay 0.5]

--from-probe reuses the raw Brave JSON already saved under data/probe/
(no Brave API call); otherwise Brave is queried live.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import trafilatura
from dotenv import load_dotenv
import os

from probe_search import call_brave, slug  # reuse the search + slug helpers

# A real browser UA — many news sites 403 the python-requests default.
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
FETCH_TIMEOUT = 20


def brave_urls_live(query: str, key: str, max_results: int):
    """(title, url) pairs from a live Brave query."""
    _raw, norm = call_brave(query, key, max_results)
    return [(x.get("title"), x.get("url")) for x in norm if x.get("url")]


def brave_urls_from_probe(query: str, probedir: Path, max_results: int):
    """(title, url) pairs from a previously-saved Brave probe JSON."""
    path = probedir / f"brave__{slug(query)}.json"
    if not path.exists():
        raise FileNotFoundError(f"no saved Brave probe at {path} (run probe_search.py first)")
    raw = json.loads(path.read_text())
    results = (raw.get("web") or {}).get("results", [])[:max_results]
    return [(x.get("title"), x.get("url")) for x in results if x.get("url")]


def fetch_and_extract(url: str) -> dict:
    """Download one URL and pull out the main article text + metadata.

    Returns a record dict; on failure it carries an `error` and empty text
    rather than raising, so one bad URL never sinks the whole query.
    """
    rec = {
        "url": url,
        "http_status": None,
        "title": None,
        "author": None,
        "sitename": None,
        "date": None,
        "char_len": 0,
        "text": None,
        "error": None,
    }
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=FETCH_TIMEOUT)
        rec["http_status"] = resp.status_code
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype and "xml" not in ctype:
            rec["error"] = f"non-html content-type: {ctype!r}"
            return rec
        js = trafilatura.extract(
            resp.text,
            url=url,
            output_format="json",
            with_metadata=True,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )
        if not js:
            rec["error"] = "trafilatura extracted nothing"
            return rec
        data = json.loads(js)
        text = (data.get("text") or "").strip()
        rec.update(
            title=data.get("title"),
            author=data.get("author"),
            sitename=data.get("sitename") or data.get("hostname"),
            date=data.get("date"),
            text=text,
            char_len=len(text),
        )
    except requests.HTTPError as e:
        rec["error"] = f"HTTP {rec['http_status']}"
    except requests.RequestException as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001 - surface any extraction issue
        rec["error"] = f"{type(e).__name__}: {e}"
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_file", nargs="?", default="input")
    ap.add_argument("--max-results", type=int, default=5, help="Number of successfully-extracted docs to keep per query")
    ap.add_argument("--pool", type=int, default=0, help="How many Brave results to consider (default: 2x max-results, capped at 20). We over-fetch because bot-hostile sites fail.")
    ap.add_argument("--from-probe", action="store_true", help="Reuse saved Brave JSON in --probedir instead of calling Brave")
    ap.add_argument("--probedir", default="data/probe")
    ap.add_argument("--outdir", default="data/pages")
    ap.add_argument("--delay", type=float, default=0.5, help="Seconds to wait between URL fetches")
    args = ap.parse_args()

    load_dotenv()
    key = os.getenv("BRAVE_API_KEY")
    if not args.from_probe and not key:
        print("error: BRAVE_API_KEY not set (or use --from-probe)", file=sys.stderr)
        return 1

    path = Path(args.input_file)
    if not path.exists():
        print(f"error: input file not found: {path}", file=sys.stderr)
        return 1
    queries = [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    probedir = Path(args.probedir)

    target = args.max_results
    pool = args.pool or min(max(target * 2, target + 3), 20)

    for q in queries:
        print("=" * 100)
        print(f"QUERY: {q}")
        print("=" * 100)
        try:
            if args.from_probe:
                pairs = brave_urls_from_probe(q, probedir, pool)
            else:
                pairs = brave_urls_live(q, key, pool)
        except Exception as e:  # noqa: BLE001
            print(f"  failed to get Brave results: {e}")
            continue

        # Dedup URLs while preserving Brave's ranking order.
        seen, ordered = set(), []
        for title, url in pairs:
            if url not in seen:
                seen.add(url)
                ordered.append((title, url))

        # Over-fetch: walk the pool in rank order, keep going until we have
        # `target` successful extractions (or the pool runs out).
        documents = []
        n_ok = 0
        for i, (brave_title, url) in enumerate(ordered, 1):
            rec = fetch_and_extract(url)
            rec["brave_title"] = brave_title
            rec["rank"] = i
            documents.append(rec)
            if rec["error"] is None:
                n_ok += 1
            status = "OK " if rec["error"] is None else "ERR"
            print(f"  [{status}] {i}. {rec['sitename'] or ''} | {rec['char_len']} chars | date={rec['date']}")
            print(f"        {url}")
            if rec["error"]:
                print(f"        -> {rec['error']}")
            time.sleep(args.delay)
            if n_ok >= target:
                break

        manifest = {
            "query": q,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "brave",
            "n_documents": len(documents),
            "n_ok": sum(1 for d in documents if d["error"] is None),
            "documents": documents,
        }
        out_path = outdir / f"{slug(q)}.json"
        out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        ok = manifest["n_ok"]
        total_chars = sum(d["char_len"] for d in documents)
        print(f"  -> {out_path}  ({ok}/{len(documents)} ok, {total_chars} chars total)\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
