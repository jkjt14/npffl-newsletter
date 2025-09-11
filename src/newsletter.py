from __future__ import annotations
import html
from pathlib import Path
from typing import Any, Dict, List
import markdown
from . import roastbook as rb

def _fmt2(x: Any) -> str:
    try:
        f = float(x); return f"{f:.2f}"
    except Exception:
        return "0.00"

def _render_markdown(md: str) -> str:
    return markdown.markdown(md, extensions=["tables"])

def _tiny_table(headers: List[str], rows: List[List[str]]) -> List[str]:
    if not headers or not rows: return []
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for r in rows: out.append("| " + " | ".join(r) + " |")
    out.append("")
    return out

def _mk_md(payload: Dict[str, Any]) -> str:
    title = payload.get("title", "NPFFL Weekly Roast")
    week_label = payload.get("week_label", "00")
    tz = payload.get("timezone", "America/New_York")

    standings = payload.get("standings_rows") or []
    values = payload.get("top_values") or []
    busts = payload.get("top_busts") or []
    eff = payload.get("team_efficiency") or []
    scores = payload.get("scores_info") or {}
    f_map = payload.get("franchise_names") or {}
    headliners = payload.get("headliners") or []

    starters_idx = payload.get("starters_by_franchise")  # optional
    conf3 = payload.get("confidence_top3") or []
    conf_summary = payload.get("confidence_summary") or {}
    conf_no = (payload.get("confidence_meta") or {}).get("no_picks", [])
    surv = payload.get("survivor_list") or []
    surv_summary = payload.get("survivor_summary") or {}
    surv_no = (payload.get("survivor_meta") or {}).get("no_picks", [])

    vp_drama = payload.get("vp_drama") or {}
    # --- Order: Opener -> Weekly Wrap -> VP Drama -> Headliners -> Values -> Busts -> Power Ranks -> Confidence -> Survivor -> Fraud/FantasyJail/Dumpster -> Standings ---
    lines: List[str] = []
    lines.append(f"# {title} — Week {week_label}\n")

    # Opener (spicy)
    opener = payload.get("opener") or rb.opener(scores)
    if opener: lines.append(opener + "\n")

    # Weekly Wrap (no table)
    ww = rb.weekly_wrap(scores)
    if ww:
        lines.append("## Weekly Results")
        lines.append(ww + "\n")

    # VP drama
    drama = rb.vp_drama_blurb(vp_drama)
    if drama:
        lines.append("## VP Drama")
        lines.append(drama + "\n")

    # Headliners (prose only + brief list)
    if headliners:
        lines.append("## Headliners")
        lines.append(rb.headliners_blurb(headliners) + "\n")

    # Values & Busts (pure prose)
    lines.append("## Value vs. Busts")
    lines.append(rb.values_blurb(values))
    lines.append(rb.busts_blurb(busts) + "\n")

    # Power ranks (commentary only; no salary/pp$ columns)
    lines.append("## Power Vibes")
    lines.append(rb.power_ranks_blurb(eff) + "\n")

    # Confidence (Vegas odds labels + roast no-picks; short bullets for top-3)
    if conf3:
        lines.append("## Confidence Pick’em")
        lines.append(rb.confidence_blurb(conf_summary, conf_no) + "\n")
        for row in conf3:
            team = row["team"]
            top3 = ", ".join(f"{g['pick']}({g['rank']})" for g in row["top3"])
            lines.append(f"- **{team}** — {top3}")
        lines.append("")

    # Survivor (odds labels + roast no-picks; tiny table)
    if surv:
        lines.append("## Survivor Pool")
        lines.append(rb.survivor_blurb(surv_summary, surv_no) + "\n")
        rows = [["Team", "Pick"]] + [[r["team"], r.get("pick","—") or "—"] for r in surv]
        lines += _tiny_table(rows[0], rows[1:])

    # Rotating segments (DFS tone)
    fw = rb.fraud_watch_blurb(eff)
    if fw: lines.append(fw + "\n")
    jail = rb.fantasy_jail_blurb(starters_idx, f_map)
    if jail: lines.append(jail + "\n")
    dd = rb.dumpster_division_blurb(standings)
    if dd: lines.append(dd + "\n")

    # Standings (tiny table at END)
    if standings:
        lines.append("## Standings (Week-to-date)")
        hdr = ["Team", "PF", "VP"]
        rows = [[r["name"], _fmt2(r.get("pf")), _fmt2(r.get("vp", 0))] for r in standings]
        lines += _tiny_table(hdr, rows)

    return "\n".join(lines)

def render_newsletter(payload: Dict[str, Any], output_dir: str, week: int) -> Dict[str, str]:
    md = _mk_md(payload)
    html_body = _render_markdown(md)
    html = f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/><title>{html.escape(payload.get('title','NPFFL Weekly Roast'))} — Week {html.escape(payload.get('week_label','00'))}</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
:root{{--fg:#111;--muted:#555;--bg:#fff;--accent:#0b5fff;--table:#e5e7eb}}
html,body{{margin:0;padding:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,Apple Color Emoji,Segoe UI Emoji}}
.page{{max-width:860px;margin:2rem auto;padding:0 1rem 3rem}}
header{{margin-bottom:1.25rem}} header h1{{margin:0 0 .25rem;font-size:2rem;line-height:1.2}} header .meta{{color:var(--muted)}}
h2{{margin-top:2rem}} h3{{margin-top:1.25rem}}
table{{width:100%;border-collapse:collapse;margin:.75rem 0 1.25rem}}
th,td{{padding:.5rem .6rem;border-bottom:1px solid var(--table)}}
thead th{{text-align:left}} .footer{{margin-top:2rem;color:var(--muted);font-size:.95rem}}
a{{color:var(--accent);text-decoration:none}} a:hover{{text-decoration:underline}}
</style></head>
<body><div class="page">
<header><h1>{html.escape(payload.get('title','NPFFL Weekly Roast'))}</h1>
<div class="meta"><strong>Week {html.escape(payload.get('week_label','00'))}</strong> · {html.escape(payload.get('timezone','America/New_York'))}</div>
</header>
<main>{html_body}</main>
<div class="footer">Generated automatically (DFS style).</div>
</div></body></html>"""
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"NPFFL_Week_{payload.get('week_label','00')}.md"
    html_path = out / f"NPFFL_Week_{payload.get('week_label','00')}.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return {"md_path": str(md_path), "html_path": str(html_path)}
