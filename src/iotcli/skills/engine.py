"""Template rendering engine for AI skill files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _get_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape([]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render(template_name: str, **context: Any) -> str:
    """Render a Jinja2 template from the templates/ directory."""
    env = _get_env()
    tmpl = env.get_template(template_name)
    return tmpl.render(**context)
