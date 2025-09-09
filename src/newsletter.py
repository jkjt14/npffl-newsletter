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


def _h1(text: str) -> str:
    return f"# {text}\n\n"


def _h2(text: str) -> str:
    return f"## {text}\n\n"


def _h3(text: str) -> str:
    return f"### {text}\n\n"


def _p(text: str) -> str:
    return f"{text}\n\n"


def _bullet(items: List[str]) -> str:
    if not items:
        return ""
    return "".join([f"- {i}\n" for i in items]) + "\n"


def _name_for(fid: str, fmap: Dict[str, str]) -> str:
    if not fid:
        return "unknown"
    return fmap.get(str(fid), str(fid))


def _render_standings(standings: Any, fmap: Dict[str, str]) -> str:
    rows: List[Tuple[str, float, float]] = []
    for row in _as_list(standings):
        fid = row.get("id") or ""
        # prefer API's provided name (fname); fallback to our map
        name = (row.get("fname") or row.get("name")) or _name_for(fid, fmap)
        try:
            pf = float(row.get("pf") or 0)
        except Exception:
            pf = 0.0
        try:
            vp = float(row.get("vp") or 0)
        except Exception:
            vp = 0.0
        rows.append((name, pf, vp))
    rows.sort(key=lambda t: (t[2], t[1]), reverse=True)

    out = _h2("Standings (Week-to-date)")
    if not rows:
        return out + _p("_No standings data available._")
    out += "Team | PF | VP\n---|---:|---:\n"
    for name, pf, vp in rows:
        out += f"{name} | {pf:.2f} | {vp:g}\n"
    out += "\n"
    return out


def _render_weekly_scores(weekly_results: Any, fmap: Dict[str, str]) -> str:
    if not isinstance(weekly_results, dict):
        return _h2("Weekly Scores") + _p("_No weekly results found._")
    wr = weekly_results.get("weeklyResults") or {}
    franchises = _as_list(wr.get("franchise"))
    if not franchises:
        return _h2("Weekly Scores") + _p("_No weekly results found._")

    team_rows: List[Tuple[str, float]] = []
    for f in franchises:
        fid = f.get("id") or "unknown"
        try:
            score = float(f.get("score") or 0)
        except Exception:
            score = 0.0
        team_rows.append((_name_for(fid, fmap), score))
    team_rows.sort(key=lambda t: t[1], reverse=True)

    out = _h2("Weekly Scores (Starter Lineups)")
    out += "Team | Score\n---|---:\n"
    for name, sc in team_rows:
        out += f"{name} | {sc:.2f}\n"
    out += "\n"

    bullets: List[str] = []
    for f in franchises:
        fid = f.get("id") or "unknown"
        tid = _name_for(fid, fmap)
        best = None
        top_score = -1e9
        for p in _as_list(f.get("player")):
            try:
                ps = float(p.get("score") or 0)
            except Exception:
                ps = 0.0
            if ps > top_score:
                top_score = ps
                best = p
        if best is not None and top_score > 0:
            bullets.append(f"**{tid}** — top starter scored {top_score:.2f} pts (player id {best.get('id')}).")
    if bullets:
        out += _h3("Team Highlights")
        out += _bullet(bullets)
    return out


def _render_values(values: Dict[str, Any], fmap: Dict[str, str]) -> str:
    if not values:
        return ""
    top_vals = values.get("top_values") or []
    top_busts = values.get("top_busts") or []

    def _mk_rows(items):
        out = "Player | Pts | Salary | P/$1K | Team | Pos | Manager\n---|---:|---:|---:|---|---|---\n"
        for it in items:
            who = str(it.get("player") or "Unknown")
            pts = it.get("pts")
            sal = it.get("salary")
            ppk = it.get("ppk")
            team = it.get("team") or ""
            pos = it.get("pos") or ""
            mgr = _name_for(it.get("franchise_id") or "", fmap)
            pts_s = f"{pts:.2f}" if isinstance(pts, (int, float)) else str(pts)
            sal_s = f"${int(sal):,}" if isinstance(sal, (int, float)) else "-"
            ppk_s = f"{ppk:.3f}" if isinstance(ppk, (int, float)) else "-"
            out += f"{who} | {pts_s} | {sal_s} | {ppk_s} | {team} | {pos} | {mgr}\n"
        out += "\n"
        return out

    out = _h2("Top Values")
    out += _mk_rows(top_vals) if top_vals else _p("_No value data available._")
    out += _h2("Top Busts")
    out += _mk_rows(top_busts) if top_busts else _p("_No bust data available._")

    by_pos = values.get("by_pos") or {}
    if by_pos:
        out += _h2("Best Values by Position")
        for pos, rows in by_pos.items():
            out += _h3(pos)
            out += _mk_rows(rows[:5])
    return out


def _render_pool_confidence(pool_nfl: Any, week: int, fmap: Dict[str, str]) -> str:
    if not isinstance(pool_nfl, dict):
        return ""
    picks_root = pool_nfl.get("poolPicks")
    if not isinstance(picks_root, dict):
        return ""
    franchises = _as_list(picks_root.get("franchise"))
    if not franchises:
        return ""

    out = _h2("Confidence Pool — Highlights")
    bullets: List[str] = []
    for fr in franchises:
        fid = fr.get("id", "unknown")
        tid = _name_for(fid, fmap)
        wnode = None
        for w in _as_list(fr.get("week")):
            if str(w.get("week") or "") == str(week):
                wnode = w
                break
        if not wnode:
            continue
        games = _as_list(wnode.get("game"))
        try:
            sorted_games = sorted(games, key=lambda g: int(g.get("rank") or 0), reverse=True)
        except Exception:
            sorted_games = games
        top_n = sorted_games[:3]
        short = ", ".join([f"{g.get('pick','?')}({g.get('rank','-')})" for g in top_n]) if top_n else "—"
        bullets.append(f"**{tid}** — {short}")
    if bullets:
        out += _bullet(bullets)
    else:
        out += _p("_No confidence picks available for this week._")
    return out


def _render_survivor(survivor_pool: Any, week: int, fmap: Dict[str, str]) -> str:
    if not isinstance(survivor_pool, dict):
        return ""
    sp = survivor_pool.get("survivorPool")
    if not isinstance(sp, dict):
        return ""
    franchises = _as_list(sp.get("franchise"))
    if not franchises:
        return ""

    out = _h2("Survivor Pool — Week Picks")
    out += "Team | Pick\n---|---\n"
    for fr in franchises:
        fid = fr.get("id", "unknown")
        tid = _name_for(fid, fmap)
        pick = "—"
        for w in _as_list(fr.get("week")):
            if str(w.get("week") or "") == str(week):
                pick = w.get("pick") or "—"
                break
        out += f"{tid} | {pick}\n"
    out += "\n"
    return out


def _render_roasts(roasts: Dict[str, Any], fmap: Dict[str, str]) -> str:
    if not roasts:
        return ""
    out = _h2("Trophies & Roasts")
    for k, v in roasts.items():
        out += f"- **{k.replace('_',' ').title()}**: {v}\n"
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
    pool_nfl = data.get("pool_nfl") or (data.get("week") or {}).get("pool_nfl") or {}
    survivor = data.get("survivor_pool") or (data.get("week") or {}).get("survivor_pool") or {}
    values = data.get("values") or {}

    md = []
    md.append(_h1(title))
    md.append(_p(f"**Week {week} · {tz}**"))

    md.append(_render_standings(standings, fmap))
    md.append(_render_weekly_scores(weekly_results, fmap))
    md.append(_render_values(values, fmap))
    md.append(_render_pool_confidence(pool_nfl, week, fmap))
    md.append(_render_survivor(survivor, week, fmap))
    md.append(_render_roasts(data.get("roasts") or {}, fmap))

    md.append(_p("_Generated automatically._"))

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    md_path = Path(output_dir) / f"NPFFL_Week_{int(week):02d}.md"
    md_path.write_text("".join(md), encoding="utf-8")

    if make_html:
        html_text = mdlib.markdown("".join(md), extensions=["tables", "fenced_code"])
        (Path(output_dir) / f"NPFFL_Week_{int(week):02d}.html").write_text(html_text, encoding="utf-8")

    return str(md_path)
