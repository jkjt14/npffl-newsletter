from __future__ import annotations

from typing import Any, Dict


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


def fetch_week_data(league_id: str | int, week: int, client) -> Dict[str, Any]:
    """
    Pulls weekly results, standings, player scores, and pools.
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
    try:
        st = client.get_export("leagueStandings")
        out["standings"] = _normalize_standings(st)
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

    return out
