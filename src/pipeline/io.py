"""Filesystem helpers.

Two jobs:
  - dump every stage's output as JSON so the pipeline is debuggable/observable.
  - a simple disk cache keyed by input so search-API calls are cheap & reproducible.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = ROOT / "out"


def slug(text: str) -> str:
    """Stable short id for an input sentence (used to name artifacts)."""
    return hashlib.sha1(text.strip().lower().encode()).hexdigest()[:12]


def dump_json(obj: Any, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))
