"""Stage 4 — Synthesize (LLM).

Turn raw sources into structured page data that conforms to the schema:
extract facts, resolve conflicts, attach a citation to every factual claim.
Output is DATA (JSON), never HTML.
"""
from __future__ import annotations


def run(sources: dict, understanding: dict) -> dict:
    raise NotImplementedError("TODO: LLM source -> structured page data + citations")
