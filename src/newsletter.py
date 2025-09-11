from __future__ import annotations
import html, os
from pathlib import Path
from typing import Any, Dict, List

# Optional markdown; fall back to plain HTML if unavailable
try:
    import markdown as _md
    def _render_markdown(md_text: str) -> str:
        return _md.markdown(md_text, extensions=["tables"])
except Exception:  # pragma: no cover
    def _render_markdown(md_text: str) -> str:
        # ultra-minimal fallback: paragraphs + line breaks
        parts = []
        for block in md_text.split("\n\n"):
            parts.append("<p>" + "<br/>".join(html.escape(line) for line in block.splitlines()) + "</p>")
        return "\n".join(parts)

# ---------- helpers ----------
def _fmt2(x: Any) -> str:
    try:
        f = float(x); return f"{f:.2f}"
    except Exception:
        return "0.00"

def _tiny_table(headers: List[str], rows: List[List[str]]) -> str:
    if not headers or not rows: return ""
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join("---" for _ in headers) + " |")
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    out.append("")
    return "\n".join(out)

# ---------- prose engine (uses roastbook tone) ----------
def _mk_md(payload: Dict[str, Any]) -> str:
    # Pull pre-computed bits (your main.py builds these)
    title = payload.get("title", "NPFFL Weekly Roast")
    week_label = payload.get("week_label", "00")
    tz = payload.get("timezone", "America/New_York")

    standings = payload.get("standings_rows") or []
    values = payload.get("top_values") or []
    busts = payload.get("top_busts") or []
    eff = payload.get("team_efficiency") or []
    scores = payload.get("scores_info") or {}
    headliners = payload.get("headliners") or []

    starters_idx = payload.get("starters_by_franchise")  # optional
    f_map = payload.get("franchise_names") or {}

    conf3 = payload.get("confidence_top3") or []
    conf_summary = payload.get("confidence_summary") or {}
    conf_no = (payload.get("confidence_meta") or {}).get("no_picks", [])
    surv = payload.get("survivor_list") or []
    surv_summary = payload.get("survivor_summary") or {}
    surv_no = (payload.get("survivor_meta") or {}).get("no_picks", [])

    # Roastbook is optional; if not present we still write files
    try:
        from . import roastbook as rb
    except Exception:
        rb = None

    lines: List[str] = []
    lines.append(f"# {title} — Week {week_label}\n")

    # Opener
    if rb:
        op = payload.get("opener") or rb.opener(scores)
        if op: lines.append(op + "\n")

    # Weekly Results (prose)
    if rb:
        ww = rb.weekly_wrap(scores)
        if ww:
            lines.append("## Weekly Results")
            lines.append(ww + "\n")

    # VP drama
    if rb and payload.get("vp_drama"):
        vd = rb.vp_drama_blurb(payload["vp_drama"])
        if vd:
            lines.append("## VP Drama")
            lines.append(vd + "\n")

    # Headliners (prose only)
    if rb and headliners:
        lines.append("## Headliners")
        lines.append(rb.headliners_blurb(headliners) + "\n")

    # Values & Busts (prose only)
    if rb:
        lines.append("## Value vs. Busts")
        lines.append(rb.values_blurb(values))
        lines.append(rb.busts_blurb(busts) + "\n")

    # Power vibes (commentary only)
    if rb:
        lines.append("## Power Vibes")
        lines.append(rb.power_ranks_blurb(eff) + "\n")

    # Confidence (odds labels + roast no-picks; short bullets for top-3)
    if rb and conf3:
        lines.append("## Confidence Pick’em")
        lines.append(rb.confidence_blurb(conf_summary, conf_no) + "\n")
        for row in conf3:
            team = row["team"]
            top3 = ", ".join(f"{g['pick']}({g['rank']})" for g in row["top3"])
            lines.append(f"- **{team}** — {top3}")
        lines.append("")

    # Survivor (odds labels + roast no-picks)
    if rb and surv:
        lines.append("## Survivor Pool")
        lines.append(rb.survivor_blurb(surv_summary, surv_no) + "\n")
        # Tiny table (Team banners supported here too if desired)

        rows = [["Team", "Pick"]]
        for r in surv:
            rows.append([r.get("team",""), r.get("pick","—") or "—"])
        lines.append(_tiny_table(rows[0], rows[1:]))

    # Rotating segments
    if rb:
        fw = rb.fraud_watch_blurb(eff)
        if fw: lines.append(fw + "\n")
        jail = rb.fantasy_jail_blurb(starters_idx, f_map)
        if jail: lines.append(jail + "\n")
        dd = rb.dumpster_division_blurb(standings)
        if dd: lines.append(dd + "\n")

    # Standings — minimal table with optional team banners instead of names
    if standings:
        lines.append("## Standings (Week-to-date)")
        # Team banner support:
        # Place images at: assets/banners/<franchise_id>.png  (e.g., assets/banners/0010.png)
        # If present, we render an image markdown instead of team name; fallback to name if missing.
        banner_dir = payload.get("assets", {}).get("banners_dir", "assets/banners")
        hdr = ["Team", "PF", "VP"]
        body: List[List[str]] = []
        for r in standings:
            fid = str(r.get("id") or "").zfill(4)
            name = r.get("name","Team")
            pf = _fmt2(r.get("pf"))
            vp = _fmt2(r.get("vp", 0))
            banner_path = f"{banner_dir}/{fid}.png"
            if Path(banner_path).exists():
                # Markdown image; alt text = name
                label = f"![{name}]({banner_path})"
            else:
                label = name
            body.append([label, pf, vp])
        lines.append(_tiny_table(hdr, body))

    return "\n".join(lines)

# ---------- public API ----------
def render_newsletter(payload: Dict[str, Any], output_dir: str, week: int) -> Dict[str, str]:
    """
    Always writes both .md and .html. Never returns without creating artifacts.
    """
    try:
        md_text = _mk_md(payload)
    except Exception as e:  # harden: even if prose fails, we still write a stub
        md_text = f"# {html.escape(payload.get('title','NPFFL Weekly Roast'))} — Week {html.escape(payload.get('week_label','00'))}\n\n" \
                  f"_Renderer fallback due to error: {html.escape(str(e))}_\n"

    # Ensure non-empty
    if not md_text.strip():
        md_text = f"# {payload.get('title','NPFFL Weekly Roast')} — Week {payload.get('week_label','00')}\n\n" \
                  f"_No content this week, but we still ship._\n"

    html_body = _render_markdown(md_text)
    # Lightweight blog wrapper with emojis support
    html_doc = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>{html.escape(payload.get('title','NPFFL Weekly Roast'))} — Week {html.escape(payload.get('week_label','00'))}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      :root {{
        --fg:#111; --muted:#555; --bg:#fff; --accent:#0b5fff; --line:#e5e7eb;
      }}
      html,body {{ margin:0; padding:0; background:var(--bg); color:var(--fg); font:16px/1.6 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,Apple Color Emoji,Segoe UI Emoji; }}
      .page {{ max-width: 880px; margin: 2rem auto; padding: 0 1rem 3rem; }}
      header h1 {{ margin: 0 0 .25rem; font-size: 2rem; line-height: 1.2; }}
      header .meta {{ color: var(--muted); margin-bottom: 1rem; }}
      h2 {{ margin-top: 2rem; }}
      table {{ width:100%; border-collapse: collapse; margin: .75rem 0 1.25rem; }}
      th, td {{ padding: .5rem .6rem; border-bottom: 1px solid var(--line); vertical-align: middle; }}
      thead th {{ text-align: left; }}
      img {{ max-height: 26px; vertical-align: middle; }}
      .footer {{ margin-top: 2rem; color: var(--muted); font-size: .95rem; }}
      a {{ color: var(--accent); text-decoration: none; }}
      a:hover {{ text-decoration: underline; }}
    </style>
  </head>
  <body>
    <div class="page">
      <header>
        <h1>{html.escape(payload.get('title','NPFFL Weekly Roast'))}</h1>
        <div class="meta"><strong>Week {html.escape(payload.get('week_label','00'))}</strong> · {html.escape(payload.get('timezone','America/New_York'))}</div>
      </header>
      <main>
        {html_body}
      </main>
      <div class="footer">Generated automatically — DFS spice 🌶️</div>
    </div>
  </body>
</html>"""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = out_dir / f"NPFFL_Week_{payload.get('week_label','00')}.md"
    html_path = out_dir / f"NPFFL_Week_{payload.get('week_label','00')}.html"

    # Always write artifacts (no early returns)
    md_path.write_text(md_text, encoding="utf-8")
    html_path.write_text(html_doc, encoding="utf-8")

    # Explicit console logs so you’ll see them in Actions
    print(f"[newsletter] Wrote markdown: {md_path}")
    print(f"[newsletter] Wrote HTML:     {html_path}")

    return {"md_path": str(md_path), "html_path": str(html_path)}
