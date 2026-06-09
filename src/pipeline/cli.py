"""CLI entry point.

`run` chains all stages end-to-end and dumps each stage's output to data/
so the pipeline is observable. Each stage is also importable and runnable on
its own (file in -> file out) for fast iteration.

Usage:
    python -m pipeline.cli run "OpenAI rolled out GPT-5.5 Instant in May 2026."
"""
from __future__ import annotations

import argparse

from . import intake, understand, retrieve, synthesize, validate, render
from .io import DATA, OUT, dump_json, slug


def cmd_run(sentence: str) -> None:
    sid = slug(sentence)

    intake_res = intake.run(sentence)
    dump_json(intake_res, DATA / "raw" / f"{sid}.intake.json")

    understanding = understand.run(intake_res)
    dump_json(understanding, DATA / "raw" / f"{sid}.understand.json")

    sources = retrieve.run(understanding)
    dump_json(sources, DATA / "raw" / f"{sid}.sources.json")

    page = synthesize.run(sources, understanding)
    page = validate.run(page)
    dump_json(page, DATA / "pages" / f"{sid}.json")

    html = render.run(page)
    out_path = OUT / f"{sid}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"Wrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="generate a topic page from one sentence")
    p_run.add_argument("sentence", help="one-sentence event description")

    args = parser.parse_args()
    if args.command == "run":
        cmd_run(args.sentence)


if __name__ == "__main__":
    main()
