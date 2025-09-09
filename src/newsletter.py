from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import markdown as mdlib


def _as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x]
    return []


def _name_for(fid: str, fmap: Dict[str, str]) -> str:
    if not fid:
        return "unknown"
    return fmap.get(str(fid), str(fid))


def _h1(t: str): return f"# {t}\n\n"
def _h2(t: str): return f"## {t}\n\n"
def _h3(t: str): return f"### {t}\n\n"
def _p(t: str):  return f"{t}\n\n"


def _render_standings(standings: Any, fmap: Dict[str, str], note: str) -> str:
    rows: List[Tuple[str, float, float]] = []
    for row in _as_list(standings):
        fid = row.get("id") or ""
        name = (row.get("fname") or row.get("name")) or _name_for(fid, fmap)
        pf = float(row.get("pf") or 0)
        vp = float(row.get("vp") or 0)
        rows.append((name, pf, vp))
    rows.sort(key=lambda t: (t[2], t[1]), reverse=True)
    out = _h2("Standings (Week-to-date)")
    if note: out += _p(note)
    if not rows:
        return out + _p("_No standings data available._")
    out += "Team | PF | VP\n---|---:|---:\n"
    for name, pf, vp in rows:
        out += f"{name} | {pf:.2f} | {vp:g}\n"
    out += "\n"
    return out


def _render_weekly_scores(weekly_results: Any, fmap: Dict[str, str], note: str) -> str:
    out = _h2("Weekly Scores")
    if note: out += _p(note)
    if not isinstance(weekly_results, dict):
        return out + _p("_No weekly results found._")
    wr = weekly_results.get("weeklyResults") or {}
    franchises = _as_list(wr.get("franchise"))
    if not franchises:
        return out + _p("_No weekly results found._")
    team_rows: List[Tuple[str, float]] = []
    for f in franchises:
        fid = f.get("id") or "unknown"
        score = float(f.get("score") or 0)
        team_rows.append((_name_for(fid, fmap), score))
    team_rows.sort(key=lambda t: t[1], reverse=True)
    out += "Team | Score\n---|---:\n"
    for name, sc in team_rows:
        out += f"{name} | {sc:.2f}\n"
    out += "\n"
    return out


def _render_top_performers(values: Dict[str, Any], fmap: Dict[str, str], note: str) -> str:
    tp = values.get("top_performers") or []
    out = _h2("Headliners")
    if note: out += _p(note)
    if not tp:
        return out + _p("_No headliners this week._")
    out += "Player | Pos | Team | Pts | Managers\n---|---|---|---:|---\n"
    for r in tp:
        nm = r.get("player") or "Unknown"
        pos = r.get("pos") or ""
        tm = r.get("team") or ""
        pts = r.get("pts") or 0
        mgrs = ", ".join(_name_for(fid, fmap) for fid in (r.get("franchise_ids") or []))
        out += f"{nm} | {pos} | {tm} | {pts:.2f} | {mgrs}\n"
    out += "\n"
    return out


def _render_values(values: Dict[str, Any], fmap: Dict[str, str], note: str) -> str:
    # We hide the technical metric; still rank by it internally
    top_vals = values.get("top_values") or []
    top_busts = values.get("top_busts") or []
    out = _h2("Value vs. Busts")
    if note: out += _p(note)

    def _mk_rows(items):
        out = "Player | Pts | Salary | Team | Pos | Manager\n---|---:|---:|---|---|---\n"
        for it in items:
            who = str(it.get("player") or "Unknown")
            pts = it.get("pts") or 0
            sal = it.get("salary")
            tm = it.get("team") or ""
            pos = it.get("pos") or ""
            mgr = _name_for(it.get("franchise_id") or "", fmap)
            sal_s = f\"${int(sal):,}\" if isinstance(sal, (int, float)) else "-"
            out += f\"{who} | {pts:.2f} | {sal_s} | {tm} | {pos} | {mgr}\n\"
        out += "\n"
        return out

    out += _h3("Biggest Steals")
    out += _mk_rows(top_vals[:10]) if top_vals else _p("_No value standouts this week._")
    out += _h3("Overpriced Misfires")
    out += _mk_rows(top_busts[:10]) if top_busts else _p("_No notable misfires this week._")
    return out


def _render_power_rankings(values: Dict[str, Any], fmap: Dict[str, str], note: str) -> str:
    te = values.get("team_efficiency") or []
    out = _h2("Power Rankings — Efficiency Vibes")
    if note: out += _p(note)
    if not te:
        return out + _p("_No efficiency data available._")
    # Order already sorted by our internal metric. We just show team, pts, salary.
    out += "Team | Pts | Salary\n---|---:|---:\n"
    for row in te:
        nm = _name_for(row.get("franchise_id",""), fmap)
        pts = row.get("total_pts", 0.0)
        sal = row.get("total_sal", 0)
        out += f"{nm} | {pts:.2f} | ${int(sal):,}\n"
    out += "\n"
    return out


def _render_confidence(pool_nfl: Any, week: int, fmap: Dict[str, str], note: str) -> str:
    out = _h2("Confidence Pick’em")
    if note: out += _p(note)
    pr = pool_nfl.get("poolPicks") if isinstance(pool_nfl, dict) else None
    if not isinstance(pr, dict):
        return out + _p("_No data._")
    franchises = _as_list(pr.get("franchise"))
    if not franchises:
        return out + _p("_No data._")

    # Show each team’s top-3 stated ranks (just like before), this is readable
    out += "Team | Top-3 Confidence\n---|---\n"
    for fr in franchises:
        fid = fr.get("id","unknown")
        nm = _name_for(fid, fmap)
        wnode = None
        for w in _as_list(fr.get("week")):
            if str(w.get("week") or "") == str(week):
                wnode = w; break
        if not wnode:
            out += f"{nm} | —\n"; continue
        games = _as_list(wnode.get("game"))
        try:
            games = sorted(games, key=lambda g: int(g.get("rank") or 0), reverse=True)
        except Exception:
            pass
        short = ", ".join([f"{g.get('pick','?')}({g.get('rank','-')})" for g in games[:3]]) if games else "—"
        out += f"{nm} | {short}\n"
    out += "\n"
    return out


def _render_survivor(survivor_pool: Any, week: int, fmap: Dict[str, str], note: str) -> str:
    out = _h2("Survivor Pool")
    if note: out += _p(note)
    sp = survivor_pool.get("survivorPool") if isinstance(survivor_pool, dict) else None
    if not isinstance(sp, dict):
        return out + _p("_No data._")
    franchises = _as_list(sp.get("franchise"))
    if not franchises:
        return out + _p("_No data._")
    out += "Team | Pick\n---|---\n"
    for fr in franchises:
        fid = fr.get("id","unknown")
        nm = _name_for(fid, fmap)
        pick = "—"
        for w in _as_list(fr.get("week")):
            if str(w.get("week") or "") == str(week):
                pick = w.get("pick") or "—"; break
        out += f"{nm} | {pick}\n"
    out += "\n"
    return out


def render_newsletter(context: Dict[str, Any], output_dir: str, week: int) -> str:
    nl = context.get("newsletter") or {}
    title = nl.get("title", "NPFFL Weekly Roast")
    tz = context.get("timezone", "America/New_York")
    outputs = context.get("outputs") or {}
    make_html = bool(outputs.get("make_html", True))

    data = context.get("data") or {}
    fmap = context.get("franchise_map") or {}

    standings = data.get("standings") or []
    weekly_results = data.get("weekly_results") or data.get("week") or {}
    values = data.get("values") or {}
    pool_nfl = data.get("pool_nfl") or (data.get("week") or {}).get("pool_nfl") or {}
    survivor = data.get("survivor_pool") or (data.get("week") or {}).get("survivor_pool") or {}
    notes = (data.get("roasts") or {}).get("notes") or {}

    md = []
    md.append(_h1(title))
    md.append(_p(f"**Week {week} · {tz}**"))
    if notes.get("opener"):
        md.append(_p(notes["opener"]))

    md.append(_render_standings(standings, fmap, notes.get("standings","")))
    md.append(_render_weekly_scores(weekly_results, fmap, notes.get("scores","")))
    md.append(_render_top_performers(values, fmap, notes.get("performers","")))
    md.append(_render_values(values, fmap, notes.get("values","")))
    md.append(_render_power_rankings(values, fmap, notes.get("efficiency","")))
    md.append(_render_confidence(pool_nfl, week, fmap, notes.get("confidence","")))
    md.append(_render_survivor(survivor, week, fmap, notes.get("survivor","")))

    # Trophies—keep concise
    roasts = data.get("roasts") or {}
    has_trophies = any(k in roasts for k in ("coupon_clipper","dumpster_fire","galaxy_brain","banana_peel","walk_of_shame"))
    if has_trophies:
        md.append(_h2("Trophies"))
        for key in ("coupon_clipper","dumpster_fire","galaxy_brain","banana_peel","walk_of_shame"):
            if key in roasts:
                md.append(f"- **{key.replace('_',' ').title()}**: {roasts[key]}\n")
        md.append("\n")

    md.append(_p("_Generated automatically._"))

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    md_path = Path(output_dir) / f"NPFFL_Week_{int(week):02d}.md"
    text = "".join(md)
    md_path.write_text(text, encoding="utf-8")

    if make_html:
        html_text = mdlib.markdown(text, extensions=["tables", "fenced_code"])
        (Path(output_dir) / f"NPFFL_Week_{int(week):02d}.html").write_text(html_text, encoding="utf-8")

    return str(md_path)
