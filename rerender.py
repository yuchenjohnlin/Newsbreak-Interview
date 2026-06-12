#!/usr/bin/env python3
"""Re-render topic pages from stored artifacts — no API calls.

This is the template iteration loop: edit templates/, run this, refresh the
browser. Reads the validated page JSON from data/runs/{slug}/page.json,
migrates older schema versions where needed, and renders with the current
template.

Usage:
    python rerender.py                      # re-render every run that has a page.json
    python rerender.py --slug <slug>        # just one
    python rerender.py --template page_featured.html.j2 --suffix -featured
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from render import render_page
from schemas import TopicPage


def migrate(data: dict) -> dict:
    """Older page.json shims: reactions used to live in TechExtras."""
    extras = data.get("extras") or {}
    if "reactions" in extras:
        data.setdefault("reactions", [])
        data["reactions"].extend(extras.pop("reactions"))
    data.setdefault("reactions", [])
    data.setdefault("hero_image", None)
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slug", help="Single run slug under data/runs/ (default: all with a page.json)")
    ap.add_argument("--runsdir", default="data/runs")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--template", default="page.html.j2")
    ap.add_argument("--suffix", default="", help="Filename suffix, e.g. -featured")
    args = ap.parse_args()

    runs = [Path(args.runsdir) / args.slug] if args.slug else sorted(Path(args.runsdir).iterdir())
    outdir = Path(args.outdir)
    n = 0
    for rundir in runs:
        src = rundir / "page.json"
        if not src.exists():
            continue
        page = TopicPage.model_validate(migrate(json.loads(src.read_text())))
        out = render_page(page, outdir / f"{rundir.name}{args.suffix}.html", template_name=args.template)
        print(f"  {out}  <- {src}")
        n += 1
    print(f"re-rendered {n} page(s) with {args.template}")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
