"""Stage 2 — Understand (LLM).

Turn the fuzzy one sentence into a structured plan:
classify event type, extract entities + time hint, decide the module plan,
and generate the search queries that `retrieve` will run.
"""
from __future__ import annotations


def run(intake_result: dict) -> dict:
    raise NotImplementedError("TODO: LLM classification + query planning")
