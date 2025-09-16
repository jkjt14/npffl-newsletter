from __future__ import annotations
import base64, mimetypes, html, traceback
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

def _embed_logo_html(fid: str, alt_text: str, dirpath: str) -> str:
    p_png = Path(dirpath) / f"{fid}.png"
    p_jpg = Path(dirpath) / f"{fid}.jpg"
    p = p_png if p_png.exists() else (p_jpg if p_jpg.exists() else None)
    if not p:
        return alt_text
    mime, _ = mimetypes.guess_type(p.name)
    mime = mime or ("image/png" if p.suffix.lower()==".png" else "image/jpeg")
    try:
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        return f'<img src="data:{mime};base64,{b64}" alt="{html.escape(alt_text)}" style="height:26px;vertical-align:middle;border-radius:4px;" />'
    except Exception:
        return alt_text

def _clean_title(t: str) -> str:
    """Ensure a usable newsletter title."""
    t = (t or "").strip() or "NPFFL Weekly Newsletter"
    return t

def _resolve_tone(payload: Dict[str, Any]) -> str:
    """Pick a tone from payload/config, defaulting to the hottest setting."""

    def _normalize(raw: Any) -> str | None:
        if raw is None:
            return None
        if isinstance(raw, str):
            raw = raw.strip()
            return raw or None
        return str(raw)

    tone = _normalize(payload.get("tone"))
    if tone:
        return tone

    tone = _normalize((payload.get("config") or {}).get("tone"))
    if tone:
        return tone

    return "inferno"

def _mk_md(payload: Dict[str, Any]) -> str:
    raw_title = payload.get("title", "") or (payload.get("config", {}) or {}).get("title", "")
    title = _clean_title(raw_title)
    week_label = payload.get("week_label", "00")
    week_num = int(str(week_label).lstrip("0") or "0") or payload.get("week", 0)
    tone_name = _resolve_tone(payload)

    # Data
    values = payload.get("top_values") or []
    busts = payload.get("top_busts") or []
    eff = payload.get("team_efficiency") or []
    scores = payload.get("scores_info") or {}
    headliners = payload.get("headliners") or []
    starters_idx = payload.get("starters_by_franchise")
    f_map = payload.get("franchise_names") or {}
    season_rank = payload.get("season_rankings") or []
    conf3 = payload.get("confidence_top3") or []
    team_prob = payload.get("team_prob") or {}
    conf_no = (payload.get("confidence_meta") or {}).get("no_picks", [])
    surv = payload.get("survivor_list") or []
    surv_no = (payload.get("survivor_meta") or {}).get("no_picks", [])
    logos_dir = (payload.get("assets") or {}).get("banners_dir") or "assets/franchises"

    # Feature flags (Around the League OFF by default this week)
    features = payload.get("features") or {}
    include_around_league = bool(features.get("around_league", False))

    from . import roastbook as rb
    from .prose import ProseBuilder

    tone = rb.Tone(tone_name)
    pb_intro = ProseBuilder(tone)

    def _safe_float(val: Any) -> float | None:
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _join_names(names: List[str]) -> str:
        clean = [str(n).strip() for n in names if n and str(n).strip()]
        if not clean:
            return ""
        if len(clean) == 1:
            return clean[0]
        if len(clean) == 2:
            return f"{clean[0]} and {clean[1]}"
        return f"{clean[0]}, {clean[1]}, and {clean[2]}"

    score_rows = []
    for row in scores.get("rows") or []:
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            team = str(row[0]).strip()
            score_rows.append((team, row[1]))
        elif isinstance(row, dict):
            team = (row.get("team") or row.get("name") or "").strip()
            pts = row.get("pts") or row.get("points")
            if team and pts is not None:
                score_rows.append((team, pts))
    def _score_sort_key(row: Any) -> float:
        val = _safe_float(row[1])
        return val if val is not None else float("-inf")

    score_rows.sort(key=_score_sort_key, reverse=True)

    avg_score = _safe_float(scores.get("avg"))
    top_score_line = ""
    bottom_score_line = ""
    if score_rows:
        top_team, top_pts_raw = score_rows[0]
        if top_team:
            avg_clause = f" on a league average of **{_fmt2(avg_score)}**" if avg_score is not None else ""
            try:
                top_pts = _fmt2(top_pts_raw)
            except Exception:
                top_pts = str(top_pts_raw)
            top_score_line = pb_intro.sentence(
                f"**{top_team}** lit the slate at **{top_pts}**{avg_clause}"
            )
        if len(score_rows) > 1:
            bottom_team, bottom_raw = score_rows[-1]
            if bottom_team and _safe_float(bottom_raw) is not None:
                bottom_score_line = pb_intro.sentence(
                    f"**{bottom_team}** is nursing that **{_fmt2(bottom_raw)}** finish"
                )

    leaders_line = ""
    if season_rank:
        leaders = [r.get("team") for r in season_rank[:3] if isinstance(r, dict) and r.get("team")]
        joined = _join_names(leaders)
        if joined:
            leaders_line = pb_intro.sentence(
                f"Power Vibes still run through **{joined}**"
            )

    headliner_line = ""
    for h in headliners:
        if not isinstance(h, dict):
            continue
        player = (h.get("player") or "").strip()
        managers = h.get("managers") or []
        manager = ""
        if isinstance(managers, list) and managers:
            manager = str(managers[0]).strip()
        elif isinstance(managers, str):
            manager = managers.strip()
        pts_val = _safe_float(h.get("pts"))
        if player and manager and pts_val is not None:
            headliner_line = pb_intro.sentence(
                f"**{player}** handed **{manager}** **{_fmt2(pts_val)}** fantasy points to flex"
            )
            break

    closer_options = [
        pb_intro.sentence("Drop hits every Tuesday at noon ET"),
        pb_intro.sentence("We publish every Tuesday at noon ET"),
        pb_intro.sentence("Circle Tuesday at noon ET for the drop"),
    ]
    closer_line = pb_intro.choose(closer_options)

    intro_templates: List[str] = [
        "> **New format!** Same DFS chaos, tighter recap, louder voice. This one’s late because the editor tried to stream All-22 from an airport lounge. We’ll be on time going forward — posting **every Tuesday at noon ET**.",
    ]

    if top_score_line:
        score_lines = [
            pb_intro.sentence("Same DFS chaos, louder mic."),
            top_score_line,
        ]
        if bottom_score_line:
            score_lines.append(bottom_score_line)
        score_lines.append(closer_line)
        intro_templates.append("> " + pb_intro.paragraph(*score_lines))

    if leaders_line:
        leader_lines = [
            pb_intro.sentence("New wrapper, same obsession with scoreboard flexes."),
            leaders_line,
            closer_line,
        ]
        intro_templates.append("> " + pb_intro.paragraph(*leader_lines))

    if headliner_line:
        headliner_lines = [
            pb_intro.sentence("DFS degenerates, this one’s for you."),
            headliner_line,
            closer_line,
        ]
        intro_templates.append("> " + pb_intro.paragraph(*headliner_lines))

    intro_templates = list(dict.fromkeys(tpl for tpl in intro_templates if tpl.strip()))
    intro_pick = pb_intro.choose(intro_templates)

    out: List[str] = []
    # Intro blurb (new)
    out.append(f"# {title} — Week {week_label}\n")
    if intro_pick:
        intro_pick = intro_pick.rstrip()
        if not intro_pick.endswith("\n"):
            intro_pick += "\n"
        out.append(intro_pick)

    # 1) Weekly Results  (intro → mini visual: Chalk&Leverage → roast)
    try:
        out.append("## Weekly Results")
        out.append(rb.weekly_results_blurb(scores, tone))
        chlv = rb.chalk_leverage_blurb(starters_idx, tone)
        if chlv:
            out.append("")
            out.append(chlv)
        out.append("")
        out.append(f"*{rb.weekly_results_roast(tone)}*")
        out.append("")
    except Exception:
        out.append("_Weekly Results unavailable._")

    # 2) VP Drama
    try:
        if payload.get("vp_drama"):
            out.append("## VP Drama")
            out.append(rb.vp_drama_blurb(payload["vp_drama"], tone))
            out.append("")
            out.append(f"*{rb.vp_drama_roast(tone)}*")
            out.append("")
    except Exception:
        out.append("_VP Drama unavailable._")

    # 3) Headliners
    try:
        if headliners:
            out.append("## Headliners")
            out.append(rb.headliners_blurb(headliners, tone))
            out.append("")
            out.append(f"*{rb.headliners_roast(tone)}*")
            out.append("")
    except Exception:
        out.append("_Headliners unavailable._")

    # 4) Value vs. Busts
    try:
        out.append("## Value vs. Busts")
        out.append(rb.values_blurb(values, tone))
        out.append(rb.busts_blurb(busts, tone))
        out.append("")
        out.append(f"*{rb.values_roast(tone)} {rb.busts_roast(tone)}*")
        out.append("")
    except Exception:
        out.append("_Value vs. Busts unavailable._")

    # 5) Power Vibes
    try:
        out.append("## Power Vibes (Season-to-Date)")
        out.append("We rank teams by what actually wins weeks: **points stacked**, a touch of **consistency**, and how cleanly salary turns into output. No spreadsheet lecture—just results.")
        out.append("")
        out.append(rb.power_vibes_blurb(season_rank, tone))
        out.append("")
        if season_rank:
            headers = ["#", "Team", "Pts (YTD)", "Avg"]
            rows = []
            for r in season_rank:
                fid = str(r["id"]).zfill(4)
                logo_html = _embed_logo_html(fid, r["team"], logos_dir)
                rows.append([str(r["rank"]), logo_html, _fmt2(r["pts_sum"]), _fmt2(r["avg"])])
            out.append(_mini_table(headers, rows))
        out.append(f"*{rb.power_vibes_roast(tone)}*")
        out.append("")
    except Exception:
        out.append("_Power Vibes unavailable._")

    # 6) Confidence
    try:
        if conf3 or conf_no:
            out.append("## Confidence Pick’em")
            out.append(rb.confidence_story(conf3, team_prob, conf_no, tone))
            out.append("")
            out.append(f"*{rb.confidence_roast(tone)}*")
            out.append("")
    except Exception:
        out.append("_Confidence section unavailable._")

    # 7) Survivor
    try:
        if surv or surv_no:
            out.append("## Survivor Pool")
            out.append(rb.survivor_story(surv, team_prob, surv_no, tone))
            out.append("")
            out.append(f"*{rb.survivor_roast(tone)}*")
            out.append("")
    except Exception:
        out.append("_Survivor section unavailable._")

    # 8) Around the League — DISABLED for this issue (opt-in later via features.around_league: true)
    if include_around_league:
        try:
            lines = rb.around_the_league_lines(f_map, scores, week=week_num, tone=tone, n=7)
            if lines:
                out.append("## Around the League")
                out.extend([f"- {ln}" for ln in lines])
                out.append("")
        except Exception:
            out.append("_Around the League unavailable._")

    return "\n".join(out)

def render_newsletter(payload: Dict[str, Any], output_dir: str, week: int) -> Dict[str, str]:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    title = _clean_title(payload.get("title") or (payload.get("config", {}) or {}).get("title", ""))
    payload = dict(payload)  # don’t mutate caller
    payload["title"] = title

    md_path = out / f"NPFFL_Week_{payload.get('week_label','00')}.md"
    html_path = out / f"NPFFL_Week_{payload.get('week_label','00')}.html"

    try:
        md_text = _mk_md(payload) or "# NPFFL Weekly Newsletter\n\n_No content._"
    except Exception:
        err = f"**Render error**:\n\n```\n{traceback.format_exc()}\n```"
        md_text = f"# {payload.get('title','NPFFL Weekly Newsletter')}\n\n{err}\n"

    try:
        import markdown as _md
        html_body = _md.markdown(md_text, extensions=["tables"])
    except Exception:
        html_body = "<p>" + md_text.replace("\n", "<br/>") + "</p>"

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
img{{max-height:28px;vertical-align:middle}}
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

    md_path.write_text(md_text, encoding="utf-8")
    html_path.write_text(html_doc, encoding="utf-8")
    print(f"[newsletter] Wrote markdown: {md_path}")
    print(f"[newsletter] Wrote HTML:     {html_path}")
    return {"md_path": str(md_path), "html_path": str(html_path)}
