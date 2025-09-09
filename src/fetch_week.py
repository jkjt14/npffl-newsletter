from __future__ import annotations

from typing import Any, Dict


def fetch_week_data(league_id: str | int, week: int, client) -> Dict[str, Any]:
    """
    Pulls the core data the newsletter needs.
    Requires an authenticated client (cookie on the session).
    Returns a normalized dict with keys we use in the renderer.
    """
    if client is None:
        # No client means no cookie → league likely private → return empty
        return {}

    out: Dict[str, Any] = {}

    # Weekly results (starters, scores, etc.)
    try:
        wr = client.get_export("weeklyResults", W=week)
        out["weekly_results"] = wr
    except Exception as e:
        out["weekly_results_error"] = str(e)

    # Standings (season-to-date)
    try:
        st = client.get_export("leagueStandings")
        # Normalize to a simple list we can render. Shape varies by league,
        # but many responses contain { "leagueStandings": { "franchise": [ {...}, ... ] } }
        standings = None
        if isinstance(st, dict):
            ls = st.get("leagueStandings") or st.get("standings") or {}
            if isinstance(ls, dict):
                standings = ls.get("franchise") or ls.get("team")
        out["standings"] = standings
    except Exception as e:
        out["standings_error"] = str(e)

    # Optional: playerScores if you want to compute values from raw scoring
    try:
        ps = client.get_export("playerScores", W=week)
        out["player_scores"] = ps
    except Exception as e:
        out["player_scores_error"] = str(e)

    return out
