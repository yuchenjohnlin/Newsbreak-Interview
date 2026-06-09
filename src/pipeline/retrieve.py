"""Stage 3 — Retrieve (deterministic).

Run the search queries against the search API, fetch, dedupe
(source diversity != source count), and cache raw results to data/raw/.
This is where the SPIKE starts — first thing to build once we have a key.
"""
from __future__ import annotations


def run(understanding: dict) -> dict:
    raise NotImplementedError("TODO: call search API, dedupe, cache to data/raw/")
