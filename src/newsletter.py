from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
from jinja2 import Environment, FileSystemLoader, select_autoescape
import markdown

def _mk_env() -> Environment:
    tpl_dir = Path("templates")
    tpl_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(tpl_dir)),
        autoescape=select_autoescape(enabled_extensions=("html",))
    )
    return env

def _fmt_top3_conf(pool_nfl: Dict[str, Any], franchise_names: Dict[str, str]) -> List[Dict[str, str]]:
    out = []
    # Expect your existing structure; fall back gently
    picks = (pool_nfl or {}).get("pool") or {}
    fr = picks.get("franchise") or []
    if isinstance(fr, dict):
        fr = [fr]
    for row in fr:
        fid = str(row.get("id") or "")
        name = franchise_names.get(fid, fid)
        top3 = []
        # assumes children like [{"team":"PHI","points":"16"}, ...] or similar
        for p in (row.get("pick") or []):
            try:
                t = p.get("nflteam") or p.get("team") or ""
                c = int(p.get("points") or p.get("value") or 0)
                top3.append((t, c))
            except Exception:
                pass
        top3 = sorted(top3, key=lambda x: x[1], reverse=True)[:3]
        if top3:
            line = ", ".join([f"{t}({c})" for t, c in top3])
            out.append({"manager": name, "line": line})
    return out

def _mk_pool_summary(pool_nfl: Dict[str, Any], franchise_names: Dict[str, str]) -> Dict[str, Any]:
    # Dumb but safe defaults. You can enhance with the-odds-api later.
    top3 = _fmt_top3_conf(pool_nfl, franchise_names)
    # naive freq for “most common”
    all_firsts = []
    no_picks = []
    picks = (pool_nfl or {}).get("pool") or {}
    fr = picks.get("franchise") or []
    if isinstance(fr, dict):
        fr = [fr]
    for row in fr:
        fid = str(row.get("id") or "")
        name = franchise_names.get(fid, fid)
        px = row.get("pick") or []
        if not px:
            no_picks.append(name)
        else:
            try:
                first = max(px, key=lambda p: int(p.get("points") or p.get("value") or 0))
                t = first.get("nflteam") or first.get("team") or ""
                all_firsts.append(t)
            except Exception:
                pass
    most_common = {"team": "—", "count": 0}
    if all_firsts:
        from collections import Counter
        t, cnt = Counter(all_firsts).most_common(1)[0]
        most_common = {"team": t, "count": cnt}
    # placeholders for boldest/faceplant until odds are wired
    boldest = {"manager": (top3[0]["manager"] if top3 else "—"), "team": "—", "conf": "—"}
    faceplant = {"manager": "—", "team": "—", "conf": "—"}

    return {
        "top3": top3,
        "no_picks": no_picks,
        "most_common": most_common,
        "boldest": boldest,
        "faceplant": faceplant,
    }

def _mk_survivor_summary(survivor_pool: Dict[str, Any], franchise_names: Dict[str, str]) -> Dict[str, Any]:
    rows = []
    no_picks = []
    eliminated = []  # stub; can be derived if API supplies result flags
    surv = (survivor_pool or {}).get("survivorPool") or {}
    fr = surv.get("franchise") or []
    if isinstance(fr, dict):
        fr = [fr]
    for row in fr:
        fid = str(row.get("id") or "")
        name = franchise_names.get(fid, fid)
        pick = row.get("pick") or ""
        if not pick:
            no_picks.append(name)
        rows.append({"manager": name, "pick": pick or "—"})
    # most common
    from collections import Counter
    picks = [r["pick"] for r in rows if r["pick"] and r["pick"] != "—"]
    mc = {"team": "—", "count": 0}
    if picks:
        t, cnt = Counter(picks).most_common(1)[0]
        mc = {"team": t, "count": cnt}
    boldest = {"manager": rows[0]["manager"] if rows else "—", "team": rows[0]["pick"] if rows else "—"}  # placeholder
    return {
        "rows": rows,
        "no_picks": no_picks,
        "eliminated": eliminated,
        "most_common": mc,
        "boldest": boldest,
    }

def render_newsletter(payload: Dict[str, Any]) -> Dict[str, str]:
    """
    Returns {'md': markdown_text, 'html': html_text}
    """
    title = payload.get("title", "NPFFL Weekly Roast")
    week_label = payload.get("week_label", "01")
    timezone = payload.get("timezone", "America/New_York")
    standings_rows = payload.get("standings_rows", [])
    team_efficiency = payload.get("team_efficiency", [])
    top_performers = payload.get("top_performers", [])
    top_values = payload.get("top_values", [])
    top_busts = payload.get("top_busts", [])
    franchise_names = payload.get("franchise_names", {})
    roasts = payload.get("roasts", {})  # from roastbook.py (narrative strings)

    # Summaries for pick’em & survivor (safe defaults if not provided)
    pool_nfl_summary = payload.get("pool_nfl_summary")
    if pool_nfl_summary is None:
        pool_nfl_summary = _mk_pool_summary(payload.get("pool_nfl", {}), franchise_names)

    survivor_summary = payload.get("survivor_summary")
    if survivor_summary is None:
        survivor_summary = _mk_survivor_summary(payload.get("survivor_pool", {}), franchise_names)

    env = _mk_env()
    tpl = env.get_template("newsletter.md.j2")

    md = tpl.render(
        title=title,
        week_label=week_label,
        timezone=timezone,
        standings_rows=standings_rows,
        team_efficiency=team_efficiency,
        top_performers=top_performers,
        top_values=top_values,
        top_busts=top_busts,
        pool_nfl_summary=pool_nfl_summary,
        survivor_summary=survivor_summary,
        franchise_names=franchise_names,
        roasts=roasts,
        manager_traits=payload.get("manager_traits", {}),
    )

    html = markdown.markdown(md, extensions=["tables", "fenced_code"])
    return {"md": md, "html": html}
