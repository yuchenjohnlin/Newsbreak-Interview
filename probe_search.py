#!/usr/bin/env python3
"""Probe web-search / research APIs with the example event sentences.

Exploratory tool, NOT part of the generation pipeline. Goal: hit Brave,
SerpAPI, Tavily, and Perplexity with the same one-sentence inputs and dump
their raw + normalized results so we can compare quality/shape and decide
which provider(s) to build on.

Usage:
    python probe_search.py [input_file] [--providers brave serpapi tavily perplexity]
                           [--max-results 5] [--outdir data/probe]

Only providers whose API key is present in the environment (.env) are run;
the rest are skipped with a note. Raw JSON for every (provider, query) pair
is written under --outdir for later inspection.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

# Each provider: env var holding its key, and a human label.
PROVIDERS = {
    "brave": "BRAVE_API_KEY",
    "serpapi": "SERPAPI_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
}

TIMEOUT = 30


def slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:n]


# --- Provider calls -------------------------------------------------------
# Each returns (raw_json, normalized) where normalized is a list of
# {title, url, snippet} dicts. Perplexity also stashes an "answer".


def call_brave(query: str, key: str, max_results: int):
    r = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
        params={"q": query, "count": max_results},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    raw = r.json()
    results = (raw.get("web") or {}).get("results", [])[:max_results]
    norm = [
        {
            "title": x.get("title"),
            "url": x.get("url"),
            "snippet": x.get("description"),
            "thumbnail": (x.get("thumbnail") or {}).get("src"),
        }
        for x in results
    ]
    return raw, norm


def call_serpapi(query: str, key: str, max_results: int):
    r = requests.get(
        "https://serpapi.com/search.json",
        params={"q": query, "api_key": key, "num": max_results, "engine": "google"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    raw = r.json()
    results = raw.get("organic_results", [])[:max_results]
    norm = [
        {"title": x.get("title"), "url": x.get("link"), "snippet": x.get("snippet")}
        for x in results
    ]
    return raw, norm


def call_tavily(query: str, key: str, max_results: int):
    r = requests.post(
        "https://api.tavily.com/search",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "query": query,
            "max_results": max_results,
            "include_answer": True,
            "search_depth": "advanced",
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    raw = r.json()
    results = raw.get("results", [])[:max_results]
    norm = [
        {"title": x.get("title"), "url": x.get("url"), "snippet": x.get("content")}
        for x in results
    ]
    if raw.get("answer"):
        norm = [{"title": "[tavily answer]", "url": None, "snippet": raw["answer"]}] + norm
    return raw, norm


def call_perplexity(query: str, key: str, max_results: int):
    r = requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": "sonar",
            "messages": [
                {"role": "system", "content": "Be concise and factual. Cite sources."},
                {"role": "user", "content": query},
            ],
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    raw = r.json()
    answer = raw["choices"][0]["message"]["content"] if raw.get("choices") else None
    citations = raw.get("citations", [])
    norm = []
    if answer:
        norm.append({"title": "[perplexity answer]", "url": None, "snippet": answer})
    for c in citations[:max_results]:
        norm.append({"title": None, "url": c, "snippet": None})
    return raw, norm


CALLERS = {
    "brave": call_brave,
    "serpapi": call_serpapi,
    "tavily": call_tavily,
    "perplexity": call_perplexity,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input_file", nargs="?", default="input", help="Text file, one event sentence per line (default: input)")
    ap.add_argument("--providers", nargs="+", choices=list(PROVIDERS), default=list(PROVIDERS))
    ap.add_argument("--max-results", type=int, default=5)
    ap.add_argument("--outdir", default="data/probe")
    args = ap.parse_args()

    load_dotenv()

    path = Path(args.input_file)
    if not path.exists():
        print(f"error: input file not found: {path}", file=sys.stderr)
        return 1
    queries = [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]
    if not queries:
        print(f"error: no non-empty lines in {path}", file=sys.stderr)
        return 1

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Resolve which providers actually have keys.
    active, skipped = [], []
    for p in args.providers:
        if os.getenv(PROVIDERS[p]):
            active.append(p)
        else:
            skipped.append(p)
    if skipped:
        print(f"skipping (no key set): {', '.join(f'{p} ({PROVIDERS[p]})' for p in skipped)}\n")
    if not active:
        print("error: no providers have keys set; nothing to do.", file=sys.stderr)
        return 1

    for q in queries:
        print("=" * 100)
        print(f"QUERY: {q}")
        print("=" * 100)
        for p in active:
            key = os.getenv(PROVIDERS[p])
            t0 = time.time()
            try:
                raw, norm = CALLERS[p](q, key, args.max_results)
                dt = time.time() - t0
                (outdir / f"{p}__{slug(q)}.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False))
                print(f"\n--- {p.upper()}  ({dt:.2f}s, {len(norm)} items) ---")
                for i, item in enumerate(norm, 1):
                    title = (item.get("title") or "").strip()
                    url = item.get("url") or ""
                    snippet = (item.get("snippet") or "").strip().replace("\n", " ")
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "…"
                    print(f"  {i}. {title}")
                    if url:
                        print(f"     {url}")
                    if snippet:
                        print(f"     {snippet}")
            except requests.HTTPError as e:
                print(f"\n--- {p.upper()}  HTTP ERROR: {e} ---")
                print(f"     body: {e.response.text[:300] if e.response is not None else ''}")
            except Exception as e:  # noqa: BLE001 - probe tool, surface everything
                print(f"\n--- {p.upper()}  ERROR: {type(e).__name__}: {e} ---")
        print()

    print(f"raw JSON written to {outdir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
