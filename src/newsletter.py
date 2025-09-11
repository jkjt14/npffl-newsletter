from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List
import markdown

from . import roastbook as rb


def _fmt_money(x: float | int) -> str:
    try:
        return f"${int(x):,}"
    except Exception:
        return "$0"


def _fmt2(x: Any) -> str:
    try:
        f = float(x)
        return f"{f:.2f}"
    except Exception:
        return "0.00"


def _render_markdown(md: str) -> str:
    return markdown.markdown(md, extensions=["tables"])


def _md_table(headers: List[str], rows: List[List[str]]) -> List[str]:
    if not headers:
        return []
    out = []
    out.append("| " + " | ".join(headers) + " |")
    aligns = []
    for h in headers:
        aligns.append("---:" if h.strip().lower() in {"pf","vp","pts","score","salary","pts/$1k"} else "---")
    out.append("| " + " | ".join(aligns) + " |")
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    out.append("")
    return out


def _build_confidence_section(payload: Dict[str, Any]) -> List[str]:
    conf3 = payload.get("confidence_top3") or []
    lines: List[str] = []
    if not conf3:
        return lines
    # Optional future fields if odds are added later:
    boring = (payload.get("confidence_summary") or {}).get("boring_pick")
    bold = (payload.get("confidence_summary") or {}).get("boldest_pick")
    lines.append("## Confidence Pick’em")
    blurb = rb.confidence_blurb(conf3, boring_pick=boring, bold_pick=bold)
    if blurb:
        lines.append(blurb + "\n")
    for row in conf3:
        team = row["team"]
        top3 = ", ".join(f"{g['pick']}({g['rank']})" for g in row["top3"])
        lines.append(f"- **{team}** — {top3}")
    lines.append("")
    return lines


def _build_survivor_section(payload: Dict[str, Any]) -> List[str]:
    surv = payload.get("survivor_list") or []
    if not surv:
        return []
    lines: List[str] = []
    lines.append("## Survivor Pool")
    summ = payload.get("survivor_summary") or {}
    blurb = rb.survivor_blurb(
        surv,
        lifeline=summ.get("boldest_lifeline"),
        consensus=summ.get("boring_consensus"),
        no_picks=summ.get("no_picks"),
    )
    if blurb:
        lines.append(blurb + "\n")
    rows = [["Team", "Pick"]]
    for r in surv:
        rows.append([r.get("team",""), r.get("pick","—") or "—"])
    lines.extend(_md_table(rows[0], rows[1:]))
    return lines


def _mk_md(payload: Dict[str, Any]) -> str:
    title = payload.get("title", "NPFFL Weekly Roast")
    week_label = payload.get("week_label", "00")
    tz = payload.get("timezone", "America/New_York")

    standings = payload.get("standings_rows") or []
    values = payload.get("top_values") or []
    busts = payload.get("top_busts") or []
    eff = payload.get("team_efficiency") or []
    scores_info = payload.get("scores_info") or {}
    opener = payload.get("opener") or rb.opener_blurb(scores_info)
    vp_drama = payload.get("vp_drama") or {}
    headliners = payload.get("headliners") or []
    trophies = payload.get("trophies") or {}
    starters_index = payload.get("starters_by_franchise")  # optional if you pass it
    f_map = payload.get("franchise_names") or {}

    lines: List[str] = []
    lines.append(f"# {title} — Week {week_label}\n")
    if opener:
        lines.append(opener + "\n")

    # --- Standings ---
    if standings:
        lines.append("## Standings (Week-to-date)")
        hdr = ["Team", "PF", "VP"]
        rows = [[r["name"], _fmt2(r.get("pf")), _fmt2(r.get("vp", 0))] for r in standings]
        lines.extend(_md_table(hdr, rows))

    # --- Weekly Scores ---
    if scores_info.get("rows"):
        rows = scores_info["rows"]
        lines.append("## Weekly Scores")
        lines.append(f"Range **{rows[-1][1]:.2f} → {rows[0][1]:.2f}** (avg {scores_info.get('avg')}).\n")
        hdr = ["Team", "Score"]
        trows = [[name, f"{score:.2f}"] for name, score in rows]
        lines.extend(_md_table(hdr, trows))

    # --- VP Drama ---
    drama = rb.vp_drama_blurb(vp_drama)
    if drama:
        lines.append("## VP Drama")
        lines.append(drama + "\n")

    # --- Headliners ---
    if headliners:
        lines.append("## Headliners")
        lines.append(rb.headliners_blurb(headliners) + "\n")
        hdr = ["Player", "Pos", "Team", "Pts", "Managers"]
        trows = []
        for h in headliners:
            trows.append([
                h.get("player",""),
                h.get("pos",""),
                h.get("team",""),
                _fmt2(h.get("pts")),
                ", ".join(h.get("managers",[]))
            ])
        lines.extend(_md_table(hdr, trows))

    # --- Values vs Busts ---
    lines.append("## Value vs. Busts")
    if values or busts:
        lines.append("Receipts delivered below.\n")
    else:
        lines.append("Receipts pending, excuses loading.\n")

    lines.append("### Biggest Steals")
    if values:
        hdr = ["Player", "Pos", "Team", "Pts", "Salary", "Pts/$1K", "Manager"]
        vrows = []
        for v in values:
            vrows.append([
                v.get("player",""),
                v.get("pos",""),
                v.get("team",""),
                _fmt2(v.get("pts")),
                _fmt_money(v.get("salary", 0)),
                _fmt2(v.get("ppk")),
                v.get("franchise","")
            ])
        lines.extend(_md_table(hdr, vrows))
    else:
        lines.append("No value standouts this week.\n")

    lines.append("### Overpriced Misfires")
    if busts:
        hdr = ["Player", "Pos", "Team", "Pts", "Salary", "Pts/$1K", "Manager"]
        brows = []
        for b in busts:
            brows.append([
                b.get("player",""),
                b.get("pos",""),
                b.get("team",""),
                _fmt2(b.get("pts")),
                _fmt_money(b.get("salary", 0)),
                _fmt2(b.get("ppk")),
                b.get("franchise","")
            ])
        lines.extend(_md_table(hdr, brows))
    else:
        lines.append("No notable misfires this week.\n")

    # --- Efficiency Board ---
    lines.append("## Power Rankings — Efficiency Vibes")
    if eff:
        hdr = ["Team", "Pts", "Salary", "Pts/$1K"]
        erows = []
        for r in eff:
            pts = float(r.get("total_pts") or 0.0)
            sal = float(r.get("total_sal") or 0.0)
            ppk = (pts / (sal/1000)) if sal > 0 else 0.0
            erows.append([r.get("name",""), _fmt2(pts), _fmt_money(sal), _fmt2(ppk)])
        # sort by Pts per $1K desc
        erows.sort(key=lambda x: -float(x[3]))
        lines.extend(_md_table(hdr, erows))
    else:
        lines.append("Efficiency board wouldn’t snitch this week.\n")

    # --- Confidence Pick'em (top-3 per team; odds labels added later) ---
    lines.extend(_build_confidence_section(payload))

    # --- Survivor Pool (boldest lifeline / consensus labels added later) ---
    lines.extend(_build_survivor_section(payload))

    # --- Rotating segments ---
    # Fraud Watch (DFS edition) — rely on efficiency to find fancy spend / low ppk
    fw = rb.fraud_watch_blurb(payload.get("team_efficiency") or [])
    if fw:
        lines.append(fw + "\n")

    # Fantasy Jail — requires starters_by_franchise; safe no-op otherwise
    jail = rb.fantasy_jail_blurb(payload.get("starters_by_franchise"), f_map)
    if jail:
        lines.append(jail + "\n")

    # Dumpster Division — bottom third of standings
    dd = rb.dumpster_division_blurb(standings)
    if dd:
        lines.append(dd + "\n")

    # --- Trophies ---
    if scores_info.get("rows"):
        lines.append("## Trophies")
        t = rb.trophies_blurb(scores_info)
        if t.get("banana"):
            lines.append(t["banana"])
        if t.get("trombone"):
            lines.append(t["trombone"])
        lines.append("")

    return "\n".join(lines)


def render_newsletter(payload: Dict[str, Any], output_dir: str, week: int) -> Dict[str, str]:
    md = _mk_md(payload)
    html_body = _render_markdown(md)
    html_wrapper = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{html.escape(payload.get('title','NPFFL Weekly Roast'))} — Week {html.escape(payload.get('week_label','00'))}</title>
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
          <strong>Week {html.escape(payload.get('week_label','00'))}</strong>
 · {html.escape(payload.get('timezone','America/New_York'))}
        </div>
      </header>
      <main>
        {html_body}
      </main>
      <div class="footer">
        Generated automatically (DFS style).
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
