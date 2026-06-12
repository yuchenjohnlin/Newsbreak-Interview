"""Deterministic render: validated TopicPage -> self-contained HTML file.

Jinja with StrictUndefined so any schema/template drift fails loudly at
build time instead of shipping a silently broken page. The output is a
single file with inline CSS — reviewers open it via file://, offline.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from schemas import TopicPage

TEMPLATE_DIR = Path(__file__).parent / "templates"


def fmt_date(value: str | None) -> str:
    """ISO-ish date -> 'Jun 11, 2026'; anything unparseable passes through."""
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y").replace(" 0", " ")
    except ValueError:
        return value


def domain(url: str) -> str:
    return url.split("//")[-1].split("/")[0].removeprefix("www.")


_env: Environment | None = None


def env() -> Environment:
    global _env
    if _env is None:
        _env = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            undefined=StrictUndefined,
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        _env.filters["fmt_date"] = fmt_date
        _env.filters["domain"] = domain
    return _env


def render_page(page: TopicPage, out_path: Path, template_name: str = "page.html.j2") -> Path:
    html = env().get_template(template_name).render(page=page)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return out_path


def render_error_page(sentence: str, status: str, message: str, slug: str, out_path: Path) -> Path:
    """User-facing error state: rendered when a run rejects or fails."""
    html = env().get_template("error.html.j2").render(
        sentence=sentence, status=status, message=message, slug=slug,
        generated_at=datetime.now().strftime("%b %d, %Y %H:%M"),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return out_path


def write_report(rundir: Path, payload: dict) -> Path:
    """Machine-readable run outcome for engineers: data/runs/{slug}/report.json."""
    import json

    rundir.mkdir(parents=True, exist_ok=True)
    path = rundir / "report.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return path
