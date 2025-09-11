from __future__ import annotations
import html
from pathlib import Path
from typing import Any, Dict, List

try:
    import markdown as _md
    def _render_markdown(md_text: str) -> str:
        return _md.markdown(md_text, extensions=["tables"])
except Exception:
    def _render_markdown(md_text: str) -> str:
        return "<p>" + md_text.replace("\n", "<br/>") + "</p>"

def _fmt2(x: Any) -> str:
    try: return f"{float(x):.2f}"
    except Exception: return "0.00"

def _mini_table(headers: List[str], rows: List[List[str]]) -> str:
    if not headers or not rows: return ""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for r in rows: lines.append("| " + " | ".join(r) + " |")
    lines.append("")
    return "\n".join(lines)

def _banners_cell(name: str, fid: str, banners_dir: str) -> str:
    from pathlib import Path
    p = Path(banners_dir) / f"{fid}.png"
    return f"![{name}]({banners_dir}/{fid}.png)" if p.exists() else name

def _mk_md(payload: Dict[str, Any]) -> str:
    title = payload.get("title", "NPFFL Weekly Newsletter")
    week_label = payload.get("week_label", "00")

    standings = payload.get("standings_rows") or []
    values = payload.get("top_values") or []
    busts = payload.get("top_busts") or []
    eff = payload.get("team_efficiency") or []
    scores = payload.get("scores_info") or {}
    headliners = payload.get("headliners") or []
    starters_idx = payload.get("starters_by_franchise")
    f_map = payload.get("franchise_names") or {}
    season_rank = payload.get("season_rankings") or []

    conf3 = payload.get("confidence_top3") or []
    team_prob = payload.get("team_prob") or {}  # expect this in payload from main when odds built
    conf_no = (payload.get("confidence_meta") or {}).get("no_picks", [])
    surv = payload.get("survivor_list") or []
    surv_no = (payload.get("survivor_meta") or {}).get("no_picks", [])

    banners_dir = (payload.get("assets") or {}).get("banners_dir", "assets/banners")

    from . import roastbook as rb

    out: List[str] = []
    out.append(f"# {title} — Week {week_label}\n")

    # Weekly Results (long prose)
    out.append("## Weekly Results")
    out.append(rb.weekly_results_blurb(scores) + "\n")

    # VP Drama (expanded)
    if payload.get("vp_drama"):
        out.append("## VP Drama")
        out.append(rb.vp_drama_blurb(payload["vp_drama"]) + "\n")

    # Headliners (team-centric prose)
    if headliners:
        out.append("## Headliners")
        out.append(rb.headliners_blurb(headliners) + "\n")

    # Values & Busts (prose only)
    out.append("## Value vs. Busts")
    out.append(rb.values_blurb(values))
    out.append(rb.busts_blurb(busts) + "\n")

    # Power Vibes (season table stays)
    out.append("## Power Vibes (Season-to-Date)")
    out.append(rb.power_vibes_blurb(season_rank) + "\n")
    if season_rank:
        headers = ["#", "Team", "Pts (YTD)", "Avg", "Consistency (σ)", "Luck (Σ)", "Salary Burn"]
        rows = []
        for r in season_rank:
            rows.append([
                str(r["rank"]),
                _banners_cell(r["team"], r["id"], banners_dir),
                _fmt2(r["pts_sum"]),
                _fmt2(r["avg"]),
                _fmt2(r["stdev"]),
                _fmt2(r["luck_sum"]),
                f"{r['burn_rate_pct']:+.1f}%"
            ])
        out.append(_mini_table(headers, rows))

    # Confidence Pick’em — odds narrative ONLY (no tables/bullets)
    if conf3:
        out.append("## Confidence Pick’em")
        out.append(rb.confidence_story(conf3, team_prob, conf_no) + "\n")

    # Survivor Pool — odds narrative ONLY (no table)
    if surv or surv_no:
        out.append("## Survivor Pool")
        out.append(rb.survivor_story(surv, team_prob, surv_no) + "\n")

    # Rotating segments
    fw = rb.fraud_watch_blurb(eff)
    if fw: out.append(fw + "\n")
    jail = rb.fantasy_jail_blurb(starters_idx, f_map)
    if jail: out.append(jail + "\n")
    dd = rb.dumpster_division_blurb(standings)
    if dd: out.append(dd + "\n")

    # Standings (tiny table at end)
    if standings:
        out.append("## Standings (Week-to-date)")
        hdr = ["Team", "PF", "VP"]
        body = []
        for r in standings:
            fid = str(r.get("id") or "").zfill(4)
            name = r.get("name","Team")
            body.append([_banners_cell(name, fid, banners_dir), _fmt2(r.get("pf")), _fmt2(r.get("vp",0))])
        out.append(_mini_table(hdr, body))

    return "\n".join(out)

def render_newsletter(payload: Dict[str, Any], output_dir: str, week: int) -> Dict[str, str]:
    md_text = _mk_md(payload) or "# NPFFL Weekly Newsletter\n\n_No content._"
    html_body = _render_markdown(md_text)
    html_doc = f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"/><title>{html.escape(payload.get('title','NPFFL Weekly Newsletter'))} — Week {html.escape(payload.get('week_label','00'))}</title>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
:root{{--fg:#111;--muted:#555;--bg:#fff;--accent:#0b5fff;--line:#e5e7eb}}
html,body{{margin:0;padding:0;background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,Apple Color Emoji,Segoe UI Emoji}}
.page{{max-width:880px;margin:2rem auto;padding:0 1rem 3rem}}
header h1{{margin:0 0 .25rem;font-size:2rem;line-height:1.2}}
header .meta{{color:var(--muted);margin-bottom:1rem}}
h2{{margin-top:2rem}}
table{{width:100%;border-collapse:collapse;margin:.75rem 0 1.25rem}}
th,td{{padding:.5rem .6rem;border-bottom:1px solid var(--line);vertical-align:middle}}
thead th{{text-align:left}}
img{{max-height:26px;vertical-align:middle}}
.footer{{margin-top:2rem;color:var(--muted);font-size:.95rem}}
a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}
</style></head>
<body><div class="page">
<header><h1>{html.escape(payload.get('title','NPFFL Weekly Newsletter'))}</h1>
<div class="meta"><strong>Week {html.escape(payload.get('week_label','00'))}</strong> · {html.escape(payload.get('timezone','America/New_York'))}</div>
</header>
<main>{html_body}</main>
<div class="footer">Generated automatically — DFS blog vibe</div>
</div></body></html>"""
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    md_path = out / f"NPFFL_Week_{payload.get('week_label','00')}.md"
    html_path = out / f"NPFFL_Week_{payload.get('week_label','00')}.html"
    md_path.write_text(md_text, encoding="utf-8")
    html_path.write_text(html_doc, encoding="utf-8")
    print(f"[newsletter] Wrote markdown: {md_path}")
    print(f"[newsletter] Wrote HTML:     {html_path}")
    return {"md_path": str(md_path), "html_path": str(html_path)}
