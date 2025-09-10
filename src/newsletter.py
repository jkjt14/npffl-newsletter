from __future__ import annotations
from typing import Any, Dict, List
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
import markdown as md

def render_newsletter(context: Dict[str, Any], templates_dir: str, out_dir: str, make_html: bool=True) -> Dict[str,str]:
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape()
    )
    tpl = env.get_template("newsletter.md.j2")
    markdown_text = tpl.render(**context)
    outp = {}
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    md_path = Path(out_dir)/f"week_{context['week']:02d}.md"
    md_path.write_text(markdown_text, encoding="utf-8")
    outp["md"] = str(md_path)
    if make_html:
        html_text = md.markdown(markdown_text, extensions=["tables"])
        html_path = Path(out_dir)/f"week_{context['week']:02d}.html"
        html_path.write_text(html_text, encoding="utf-8")
        outp["html"] = str(html_path)
    return outp
