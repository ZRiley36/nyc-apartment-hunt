from __future__ import annotations
import os
from pathlib import Path
from jinja2 import Environment, PackageLoader, select_autoescape
from .slug import report_slug

_env = Environment(loader=PackageLoader("apthunt", "templates"),
                   autoescape=select_autoescape(["html"]))


def render_report(ctx) -> str:
    return _env.get_template("report.html.j2").render(ctx=ctx)


def report_path(profile_name: str, salt: str | None = None, root: Path = Path("site")) -> Path:
    salt = salt if salt is not None else os.environ.get("REPORT_SLUG_SALT", "dev-salt")
    slug = report_slug(profile_name, salt)
    return Path(root) / "r" / f"{profile_name}-{slug}.html"
