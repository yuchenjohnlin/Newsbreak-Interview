"""Stage 6 — Render (deterministic).

Pure function: valid page data in -> self-contained HTML string out.
Jinja2 templates + CSS. No LLM here. Handles empty / error states per module.
"""
from __future__ import annotations


def run(page_data: dict) -> str:
    raise NotImplementedError("TODO: Jinja2 render schema -> HTML")
