# src/newsletter.py
from __future__ import annotations
import os
from markdown import markdown

def write_outputs(week: int, md: str, out_dir: str = "build") -> tuple[str,str]:
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"NPFFL_Week_{week:02d}.md")
    html_path = os.path.join(out_dir, f"NPFFL_Week_{week:02d}.html")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(markdown(md))
    return md_path, html_path
