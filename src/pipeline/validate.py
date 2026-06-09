"""Stage 5 — Validate & repair (deterministic).

Guards before rendering:
  - schema conformance (Pydantic)
  - citation integrity: every claim points to a real retrieved URL
  - required-module presence (no empty shells)
  - freshness (stale data is a visible failure)
On failure, optionally feed errors back to the LLM for a repair pass.
"""
from __future__ import annotations


def run(page_data: dict) -> dict:
    raise NotImplementedError("TODO: schema + citation + freshness validation")
