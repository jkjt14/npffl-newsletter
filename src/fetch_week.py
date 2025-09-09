from __future__ import annotations

from typing import Any, Dict, List


def _normalize_standings(st: Any):
    """
    Reduce common MFL shapes to a simple list of teams.
    Expected patterns:
      {"leagueStandings":{"franchise":[{...}, ...]}}  OR  {"standings":[...]}
    """
    if not isinstance(st, dict):
        return []
    ls = st.get("leagueStandings") or st.get("standings") or {}
    if isinstance(ls, dict):
        fr_list = ls.get("franchise") or ls.get("team")
        if isinstance(fr_list, list):
            return fr_list
    if isinstance(st, list):
        return st
    return []


def _build_map_from_league(league_json: Any) -> Dict[str, str]:
    """
    league_json shape commonly:
      {"league": {"franchises": {"franchise":[{"id":"0001","name":"Team Name"}, ...]}}}
    """
    m: Dict[str, str] = {}
    if not isinstance(league_json, dict):
        return m
    lg = league_json.get("league")
    if not isinstance(lg, dict):
        return m
    frs = lg.get("franchises")
    if isinstance(frs, dict):
        arr = frs.get("franchise")
        if isinstance(arr, dict):
            arr = [arr]
        if isinstance(arr, list):
            for f in arr:
                fid = str(f.get("id") or "").strip()
                nm = str(f.get("name") or "").strip()
                if fid and nm:
                    m[fid] = nm
    return m


def _build_map_from_standings(standings_list: List[dict]) -> Dict[str, str]:
    """
    Use 'id' + 'fname' from the normalized standings list.
    """
    m: Dict[str, str] = {}
    for row in standings_list:
        fid = str(row.get("id") or "").strip()
        nm = str(row.get("fname") or row.get("name") or "").strip()
        if fid and nm:
            m[fid] = nm
    return m


def fetch_week_data(league_id: str | int, week: int, client) -> Dict[str, Any]:
    """
    Pulls weekly results, standings, player scores, pools, and a franchise name map.
    Works with API key or cookie (client handles both).
    """
    out: Dict[str, Any] = {}

    if client is None:
        return out

    # Weekly results (week required)
    try:
        out["weekly_results"] = client.get_export("weeklyResults", W=week)
    except Exception as e:
        out["weekly_results_error"] = str(e)

    # Standings (season-to-date)
    standings_list = []
    try:
        st = client.get_export("leagueStandings")
        standings_list = _normalize_standings(st)
        out["standings"] = standings_list
    except Exception as e:
        out["standings_error"] = str(e)
        out["standings"] = []

    # Player scores for the week (optional, helps value calc)
    try:
        out["player_scores"] = client.get_export("playerScores", W=week)
    except Exception as e:
        out["player_scores_error"] = str(e)

    # Confidence / NFL pool (optional)
    try:
        out["pool_nfl"] = client.get_export("pool", POOLTYPE="NFL")
    except Exception as e:
        out["pool_nfl_error"] = str(e)

    # Survivor pool (optional)
    try:
        out["survivor_pool"] = client.get_export("survivorPool")
    except Exception as e:
        out["survivor_pool_error"] = str(e)

    # League info (for franchise names)
    try:
        league_json = client.get_export("league")
        out["league"] = league_json
    except Exception as e:
        out["league_error"] = str(e)

    # Build a franchise map from league + standings; user overrides are merged in main.py
    m = {}
    m.update(_build_map_from_league(out.get("league")))
    m.update(_build_map_from_standings(standings_list))
    out["franchise_map_detected"] = m  # preliminary map; main.py will merge with overrides

    return out
