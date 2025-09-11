from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List

import markdown


def _fmt_money(x: float | int) -> str:
    try:
        return f"${int(x):,}"
    except Exception:
        return "$0"


def _render_markdown(md: str) -> str:
    return markdown.markdown(md, extensions=["tables"])


def _mk_md(payload: Dict[str, Any]) -> str:
    title = payload.get("title", "NPFFL Weekly Roast")
    week_label = payload.get("week_label", "00")
    tz = payload.get("timezone", "America/New_York")
    standings = payload.get("standings_rows") or []
    values = payload.get("top_values") or []
    busts = payload.get("top_busts") or []
    eff = payload.get("team_efficiency") or []
    opener = payload.get("opener") or ""
    scores_info = payload.get("scores_info") or {}
    vp_drama = payload.get("vp_drama") or {}
    headliners = payload.get("headliners") or []
    conf3 = payload.get("confidence_top3") or []
    survivor = payload.get("survivor_list") or []
    trophies = payload.get("trophies") or {}

    lines: List[str] = []
    lines.append(f"# {title} — Week {week_label}\n")

    if opener:
        lines.append(opener + "\n")

    # Standings
    if standings:
        lines.append("## Standings Snapshot")
        lines.append("| Team | PF | VP |")
        lines.append("|---|---:|---:|")
        for r in standings:
            lines.append(f"| {r['name']} | {round(float(r['pf']),2)} | {r.get('vp',0)} |")
        lines.append("")

    # Weekly Scores
    if scores_info.get("rows"):
        rows = scores_info["rows"]
        lines.append("## Weekly Scores")
        lines.append(f"Range **{rows[-1][1]:.2f} → {rows[0][1]:.2f}** (avg {scores_info.get('avg')}).")
        lines.append("")
        lines.append("| Team | Score |")
        lines.append("|---|---:|")
        for name, sc in rows:
            lines.append(f"| {name} | {sc:.2f} |")
        lines.append("")

    # VP Drama
    if vp_drama:
        villain = vp_drama.get("villain")
        bubble = vp_drama.get("bubble")
        gap = vp_drama.get("gap_pf")
        lines.append("## VP Drama")
        lines.append(f"League Villain: **{villain}** grabbed the last chair in the 2.5 VP lounge and locked the door. ")
        lines.append(f"**{bubble}** missed by **{gap}** PF. That’s a bad beat and a worse lineup.\n")

    # Headliners
    if headliners:
        lines.append("## Headliners")
        tops = []
        for h in headliners:
            mgrs = ", ".join(h["managers"])
            nm = h["player"] or h.get("pos") or "Unknown"
            tops.append(f"{nm} dropped **{h['pts']:.2f}** ({mgrs})")
        lines.append("; ".join(tops) + ".\n")

        lines.append("| Player | Pos | Team | Pts | Managers |")
        lines.append("|---|---|---|---:|---|")
        for h in headliners:
            mgrs = ", ".join(h["managers"])
            lines.append(f"| {h['player']} | {h['pos']} | {h['team']} | {h['pts']:.2f} | {mgrs} |")
        lines.append("")

    # Values vs Busts summary
    lines.append("## Value vs. Busts")
    if values or busts:
        lines.append("Values vs. Busts: receipts delivered below.")
    else:
        lines.append("Values vs. Busts: receipts pending, excuses loading.")
    lines.append("")

    # Biggest Steals
    lines.append("### Biggest Steals")
    if values:
        lines.append("| Player | Pos | Team | Pts | Salary | Pts/$1K | Manager |")
        lines.append("|---|---|---|---:|---:|---:|---|")
        for v in values:
            lines.append(
                f"| {v.get('player')} | {v.get('pos','')} | {v.get('team','')} | "
                f"{_safe(v.get('pts'))} | {_fmt_money(v.get('salary',0))} | {_safe(v.get('ppk'))} | "
                f"{v.get('franchise','')} |"
            )
    else:
        lines.append("No value standouts this week.")
    lines.append("")

    # Overpriced Misfires
    lines.append("### Overpriced Misfires")
    if busts:
        lines.append("| Player | Pos | Team | Pts | Salary | Pts/$1K | Manager |")
        lines.append("|---|---|---|---:|---:|---:|---|")
        for b in busts:
            lines.append(
                f"| {b.get('player')} | {b.get('pos','')} | {b.get('team','')} | "
                f"{_safe(b.get('pts'))} | {_fmt_money(b.get('salary',0))} | {_safe(b.get('ppk'))} | "
                f"{b.get('franchise','')} |"
            )
    else:
        lines.append("No notable misfires this week.")
    lines.append("")

    # Efficiency board
    lines.append("## Power Rankings — Efficiency Vibes")
    if eff:
        lines.append("| Team | Pts | Salary |")
        lines.append("|---|---:|---:|")
        for r in eff:
            lines.append(f"| {r.get('name')} | {_safe(r.get('total_pts'))} | {_fmt_money(r.get('total_sal',0))} |")
    else:
        lines.append("Efficiency board wouldn’t snitch this week.")
    lines.append("")

    # Confidence Pick'em (top-3)
    if conf3:
        lines.append("## Confidence Pick’em")
        for row in conf3:
            team = row["team"]
            top3 = ", ".join(f"{g['pick']}({g['rank']})" for g in row["top3"])
            lines.append(f"**{team}** — {top3}")
        lines.append("")

    # Survivor
    if survivor:
        lines.append("## Survivor Pool")
        lines.append("| Team | Pick |")
        lines.append("|---|---|")
        for r in survivor:
            lines.append(f"| {r['team']} | {r['pick']} |")
        lines.append("")

    # Trophies
    if trophies:
        lines.append("## Trophies")
        if trophies.get("banana_peel"):
            lines.append(f"**Banana Peel:** {trophies['banana_peel']} stacked the biggest numbers.")
        if trophies.get("walk_of_shame"):
            lines.append(f"**Walk Of Shame:** {trophies['walk_of_shame']} tripped over the lowest score.")
        lines.append("")

    return "\n".join(lines)


def _safe(x: Any) -> str:
    try:
        f = float(x)
        if f.is_integer():
            return f"{int(f)}"
        return f"{f:.2f}"
    except Exception:
        return "0"


def render_newsletter(payload: Dict[str, Any], output_dir: str, week: int) -> Dict[str, str]:
    md = _mk_md(payload)
    html_body = _render_markdown(md)
    html_wrapper = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{html.escape(payload.get('title','NPFFL Weekly Roast'))} — Week {payload.get('week_label','00')}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {{
        --fg: #111;
        --muted: #555;
        --bg: #fff;
        --accent: #0b5fff;
        --table-border: #e5e7eb;
      }}
      html, body {{ margin:0; padding:0; background:var(--bg); color:var(--fg); font: 16px/1.6 system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, Apple Color Emoji, Segoe UI Emoji; }}
      .page {{ max-width: 860px; margin: 2rem auto; padding: 0 1rem 3rem; }}
      header {{ margin-bottom: 1.25rem; }}
      header h1 {{ margin: 0 0 .25rem; font-size: 2rem; line-height: 1.2; }}
      header .meta {{ color: var(--muted); }}
      h2 {{ margin-top: 2rem; }}
      h3 {{ margin-top: 1.25rem; }}
      table {{ width:100%; border-collapse: collapse; margin: .75rem 0 1.25rem; }}
      th, td {{ padding: .5rem .6rem; border-bottom: 1px solid var(--table-border); vertical-align: top; }}
      thead th {{ text-align: left; }}
      code, pre {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; }}
      .footer {{ margin-top: 2rem; color: var(--muted); font-size: .95rem; }}
      a {{ color: var(--accent); text-decoration: none; }}
      a:hover {{ text-decoration: underline; }}
    </style>
  </head>
  <body>
    <div class="page">
      <header>
        <h1>{html.escape(payload.get('title','NPFFL Weekly Roast'))}</h1>
        <div class="meta">
          <strong>Week {payload.get('week_label','00')}</strong>
 · {html.escape(payload.get('timezone','America/New_York'))}
        </div>
      </header>

      <!-- Inject the rendered Markdown as HTML -->
      <main>
        {html_body}
      </main>

      <div class="footer">
        Generated automatically.
      </div>
    </div>
  </body>
</html>"""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"NPFFL_Week_{payload.get('week_label','00')}.md"
    html_path = out_dir / f"NPFFL_Week_{payload.get('week_label','00')}.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html_wrapper, encoding="utf-8")
    return {"md_path": str(md_path), "html_path": str(html_path)}
