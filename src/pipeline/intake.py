"""Stage 1 — Intake & validation (deterministic).

Cheap gate that rejects obvious junk before we spend LLM / API calls:
empty / whitespace, length bounds, junk chars, (language), prompt-injection scan.

NOTE: "is this a real, sensible event?" is NOT decided here — that's the LLM in
`understand`, and "does it actually exist?" is decided after `retrieve`.
"""
from __future__ import annotations


def run(sentence: str) -> dict:
    raise NotImplementedError("TODO: deterministic input validation gate")
