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
    Signature required by your repo:
      render_newsletter(payload, output_dir=None, week=None) -> Dict[str, str]
    Writes NPFFL_Week_XX.md and NPFFL_Week_XX.html in output_dir and returns their paths.
    """
    out_dir = Path(output_dir or "build")
    out_dir.mkdir(parents=True, exist_ok=True)

    # templates expected next to this file
    templates_dir = Path(__file__).parent / "templates"
    env = _env(templates_dir)

    md_tmpl = env.get_template("newsletter.md.j2")
    html_tmpl = env.get_template("newsletter.html.j2")

    week_int = int(week) if week is not None else int(payload.get("week") or payload.get("week_label") or 1)
    week_label = f"{week_int:02d}"

    # render markdown first
    md_text = md_tmpl.render(**payload)

    # convert MD→HTML and drop it into the HTML shell
    content_html = markdown.markdown(md_text, extensions=["tables", "smarty"])
    html_text = html_tmpl.render(content_html=content_html, **payload)

    md_path = out_dir / f"NPFFL_Week_{week_label}.md"
    html_path = out_dir / f"NPFFL_Week_{week_label}.html"
    md_path.write_text(md_text, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")

    return {"md_path": str(md_path), "html_path": str(html_path)}
