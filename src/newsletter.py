from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import markdown as mdlib


def _as_list(x):
    # Normalize a single dict to [dict], or pass through list, else []
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


def _render_standings(standings: Any) -> str:
    """
    standings is expected to be a list of dicts with:
      id, fname (team name), pf (points for), vp (victory points)
    JSON sample matched from your artifact.
    """
    rows: List[Tuple[str, float, float]] = []
    for row in _as_list(standings):
        name = row.get("fname") or row.get("name") or row.get("id") or "Unknown"
        try:
            pf = float(row.get("pf") or 0)
        except Exception:
            pf = 0.0
        try:
            vp = float(row.get("vp") or 0)
        except Exception:
            vp = 0.0
        rows.append((name, pf, vp))

    # Sort by VP, then PF desc — tweak to your league’s preference
    rows.sort(key=lambda t: (t[2], t[1]), reverse=True)

    out = _h2("Standings (Week-to-date)")
    if not rows:
        return out + _p("_No standings data available._")

    # Compact table (no long prose in tables)
    out += "Team | PF | VP\n"
    out += "---|---:|---:\n"
    for name, pf, vp in rows:
        out += f"{name} | {pf:.2f} | {vp:g}\n"
    out += "\n"
    return out


def _render_weekly_scores(weekly_results: Any) -> str:
    """
    weekly_results structure from artifact:
      {"weeklyResults": {"franchise": [ { "id": "...", "score": "96.2", "player":[...], ... }, ...]}}
    """
    if not isinstance(weekly_results, dict):
        return _h2("Weekly Scores") + _p("_No weekly results found._")

    wr = weekly_results.get("weeklyResults") or {}
    franchises = _as_list(wr.get("franchise"))
    if not franchises:
        return _h2("Weekly Scores") + _p("_No weekly results found._")

    # Build list of (team_id, score) plus optional best performers from players
    team_rows: List[Tuple[str, float]] = []
    for f in franchises:
        team_id = f.get("id") or "unknown"
        try:
            score = float(f.get("score") or 0)
        except Exception:
            score = 0.0
        team_rows.append((team_id, score))

    # Sort by score desc
    team_rows.sort(key=lambda t: t[1], reverse=True)

    out = _h2("Weekly Scores (Starter Lineups)")
    out += "Team ID | Score\n"
    out += "---|---:\n"
    for tid, sc in team_rows:
        out += f"{tid} | {sc:.2f}\n"
    out += "\n"

    # Optional: top performers per team (from 'player' lists)
    # Keep it lightweight for now: list each team’s top scoring starter
    bullets: List[str] = []
    for f in franchises:
        tid = f.get("id") or "unknown"
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


def _render_pool_confidence(pool_nfl: Any, week: int) -> str:
    """
    pool JSON shape from artifact shows:
      {"poolPicks":{"use_weights":"Confidence","franchise":[
          {"id":"0001","week":[{"week":"1","game":[{"rank":"16","pick":"PHI","matchup":"DAL,PHI"}, ...]}, ...]},
          ...
      ]}}
    We’ll render for the given week: show each franchise’s top 3 ranks & picks.
    """
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
        week_list = _as_list(fr.get("week"))
        # find matching week entry
        wnode = None
        for w in week_list:
            if str(w.get("week") or "") == str(week):
                wnode = w
                break
        if not wnode:
            continue
        games = _as_list(wnode.get("game"))
        # pick top-3 ranks for the week
        try:
            sorted_games = sorted(
                games,
                key=lambda g: int(g.get("rank") or 0),
                reverse=True
            )
        except Exception:
            sorted_games = games
        top_n = sorted_games[:3]
        short = ", ".join([f"{g.get('pick','?')}({g.get('rank','-')})" for g in top_n]) if top_n else "—"
        bullets.append(f"**{fid}** — {short}")

    if bullets:
        out += _bullet(bullets)
    else:
        out += _p("_No confidence picks available for this week._")

    return out


def _render_survivor(survivor_pool: Any, week: int) -> str:
    """
    survivor JSON shape from artifact shows:
      {"survivorPool":{"franchise":[{"id":"0001","week":[{"week":"1","pick":"ARI"}, ...]}, ...]}}
    """
    if not isinstance(survivor_pool, dict):
        return ""

    sp = survivor_pool.get("survivorPool")
    if not isinstance(sp, dict):
        return ""

    franchises = _as_list(sp.get("franchise"))
    if not franchises:
        return ""

    out = _h2("Survivor Pool — Week Picks")
    rows: List[Tuple[str, str]] = []
    for fr in franchises:
        fid = fr.get("id", "unknown")
        week_list = _as_list(fr.get("week"))
        pick = None
        for w in week_list:
            if str(w.get("week") or "") == str(week):
                pick = w.get("pick")
                break
        rows.append((fid, pick or "—"))

    # Compact table
    out += "Team ID | Pick\n"
    out += "---|---\n"
    for fid, pk in rows:
        out += f"{fid} | {pk}\n"
    out += "\n"
    return out


def render_newsletter(context: Dict[str, Any], output_dir: str, week: int) -> str:
    """
    Generate Markdown + (optional) HTML.
    Writes:
      build/NPFFL_Week_XX.md
      build/NPFFL_Week_XX.html (if make_html: true)
    """
    nl = context.get("newsletter") or {}
    title = nl.get("title", "NPFFL Weekly Roast")
    tz = context.get("timezone", "America/New_York")
    outputs = context.get("outputs") or {}
    make_html = bool(outputs.get("make_html", True))

    data = context.get("data") or {}
    standings = data.get("standings") or []                      # normalized list
    weekly_results = data.get("week") or {}                      # raw weeklyResults payload holder
    # If the fetcher stored weekly results at top-level key:
    if not weekly_results:
        weekly_results = (data.get("week") or {}).get("weekly_results") or data.get("weekly_results") or {}
    if not weekly_results:
        # Some contexts store the entire fetch dict in data["week"]
        weekly_results = data.get("week", {})

    pools_conf = data.get("week", {}).get("pool_nfl") or data.get("pool_nfl") or {}
    survivor = data.get("week", {}).get("survivor_pool") or data.get("survivor_pool") or {}

    # Header
    md = []
    md.append(_h1(title))
    md.append(_p(f"**Week {week} · {tz}**"))
    md.append(_p("_Generated automatically._"))

    # Sections
    md.append(_render_standings(standings))
    md.append(_render_weekly_scores(data.get('weekly_results') or weekly_results))
    md.append(_render_pool_confidence(pools_conf, week))
    md.append(_render_survivor(survivor, week))

    md_text = "".join(md)

    # Write files
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    md_path = Path(output_dir) / f"NPFFL_Week_{int(week):02d}.md"
    md_path.write_text(md_text, encoding="utf-8")

    if make_html:
        html_text = mdlib.markdown(md_text, extensions=["tables", "fenced_code"])
        html_path = Path(output_dir) / f"NPFFL_Week_{int(week):02d}.html"
        html_path.write_text(html_text, encoding="utf-8")

    return str(md_path)
