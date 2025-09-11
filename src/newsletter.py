# src/newsletter.py

from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
import markdown


def _env(templates_dir: Path) -> Environment:
    return Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_newsletter(payload: Dict[str, Any], output_dir: str | None = None, week: int | None = None) -> Dict[str, str]:
    """
    Renders markdown + html using Jinja templates.
    Signature matches your repo usage: render_newsletter(payload, output_dir=None, week=None) -> Dict[str, str]
    Returns a dict like {"md_path": "...", "html_path": "..."}.
    """
    # resolve paths
    out_dir = Path(output_dir or "build")
    out_dir.mkdir(parents=True, exist_ok=True)

    # templates live in src/templates next to this file
    templates_dir = Path(__file__).parent / "templates"
    env = _env(templates_dir)

    # Required templates: newsletter.md.j2 -> markdown, newsletter.html.j2 -> html wrapper
    md_tmpl = env.get_template("newsletter.md.j2")
    html_tmpl = env.get_template("newsletter.html.j2")

    # derive week label for filenames
    week_int = int(week) if week is not None else int(payload.get("week") or payload.get("week_label") or 1)
    week_label = f"{week_int:02d}"

    # render markdown first
    md_text = md_tmpl.render(**payload)

    # render HTML either via template or by converting MD then inserting into HTML template
    # (Your templates likely expect 'content_html' if you do MD->HTML)
    content_html = markdown.markdown(md_text, extensions=["tables", "smarty"])
    html_text = html_tmpl.render(content_html=content_html, **payload)

    # file names consistent with past artifacts: NPFFL_Week_XX.*
    md_path = out_dir / f"NPFFL_Week_{week_label}.md"
    html_path = out_dir / f"NPFFL_Week_{week_label}.html"

    md_path.write_text(md_text, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")

    return {"md_path": str(md_path), "html_path": str(html_path)}
