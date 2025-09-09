from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markdown import markdown


def write_outputs(week: int, md: str, out_dir: str = "build") -> tuple[str, str]:
    """
    Writes the given Markdown string to a file and returns the paths of the Markdown
    and HTML outputs. Always writes both Markdown and HTML to disk.
    """
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"NPFFL_Week_{week:02d}.md")
    html_path = os.path.join(out_dir, f"NPFFL_Week_{week:02d}.html")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    # Always generate HTML using markdown library
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(markdown(md))
    return md_path, html_path


# Default template used if no external Jinja2 template is found.
DEFAULT_MD_TEMPLATE = """# {{ title }}

Week **{{ week }}** · {{ timezone }}

{% if standings %}
## Standings (Top 5)
{% for row in standings[:5] -%}
- {{ loop.index }}. {{ row.team }} — {{ row.w }}-{{ row.l }} ({{ row.pct }})
{% endfor %}
{% endif %}

{% if top_values %}
## Top Values (Pts per $1K)
{% for p in top_values -%}
- {{ p.player }} ({{ p.pos }} {{ p.nfl_team }}) — {{ "%.2f"|format(p.pts_per_k) }} ({{ p.points }} pts, ${{ p.salary|int }})
{% endfor %}
{% endif %}

{% if top_busts %}
## Top Busts (Overpriced)
{% for p in top_busts -%}
- {{ p.player }} ({{ p.pos }} {{ p.nfl_team }}) — {{ p.points }} pts on ${{ p.salary|int }}
{% endfor %}
{% endif %}

{% if team_roasts %}
## Roastbook
{% for team, lines in team_roasts.items() -%}
**{{ team }}**
{% for line in lines -%}
- {{ line }}
{% endfor %}

{% endfor %}
{% endif %}

*Generated automatically.*
"""


def _env_for_templates(template_dir: str | None):
    """
    Returns a Jinja2 environment and a template for rendering the newsletter.
    If template_dir is provided and exists, attempts to load 'newsletter.md.j2' from it;
    otherwise uses the DEFAULT_MD_TEMPLATE.
    """
    if template_dir and os.path.isdir(template_dir):
        env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(disabled_extensions=("md",), default=False),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template("newsletter.md.j2")
    else:
        env = Environment(autoescape=False, trim_blocks=True, lstrip_blocks=True)
        template = env.from_string(DEFAULT_MD_TEMPLATE)
    return env, template



def render_newsletter(context: Dict[str, Any], output_dir: str, week: int) -> str:
    """
    Renders the weekly newsletter using the provided context and writes it to disk.
    Returns the path to the Markdown output.
    The context should include keys like:
      - title: str
      - timezone: str
      - standings: list of dicts
      - top_values: list of dicts with pts_per_k, points, salary, etc.
      - top_busts: list of dicts
      - team_roasts: mapping of team name -> list of roast strings
      - outputs.make_html: bool (optional; ignored for now)
      - template_dir: optional path containing a Jinja2 template 'newsletter.md.j2'
    """
    template_dir = context.get("template_dir")
    _, template = _env_for_templates(template_dir)
    # Render Markdown using safe defaults
    md_text = template.render(
        title=context.get("title") or "NPFFL Weekly Roast",
        week=week,
        timezone=context.get("timezone") or "America/New_York",
        standings=context.get("standings") or [],
        top_values=context.get("top_values") or [],
        top_busts=context.get("top_busts") or [],
        team_roasts=context.get("team_roasts") or {},
    )
    # Write outputs (always writes both md and html)
    md_path, _ = write_outputs(week, md_text, out_dir=output_dir)
    return md_path
