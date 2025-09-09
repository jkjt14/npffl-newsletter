from __future__ import annotations

from typing import Any, Dict, List, Set


def _as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x]
    return []


def _normalize_standings(st: Any):
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


def _collect_starter_ids(weekly_results: Dict[str, Any]) -> List[str]:
    ids: Set[str] = set()
    wr = weekly_results.get("weeklyResults") if isinstance(weekly_results, dict) else None
    for fr in _as_list(wr.get("franchise") if isinstance(wr, dict) else None):
        for p in _as_list(fr.get("player")):
            st = str(p.get("status") or "").lower()
            if st and st not in ("starter", "s"):
                continue
            pid = str(p.get("id") or "").strip()
            if pid:
                ids.add(pid)
    return sorted(ids)


def _build_players_map(players_json: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """
    players_json shape (common):
      {"players": {"player": [ {"id":"13589","name":"Allen, Josh","position":"QB","team":"BUF"}, ... ]}}
    Returns { id: {name, pos, team} }
    """
    out: Dict[str, Dict[str, str]] = {}
    if not isinstance(players_json, dict):
        return out
    root = players_json.get("players")
    if not isinstance(root, dict):
        return out
    arr = root.get("player")
    if isinstance(arr, dict):
        arr = [arr]
    if isinstance(arr, list):
        for p in arr:
            pid = str(p.get("id") or "").strip()
            if not pid:
                continue
            nm = str(p.get("name") or "").strip()
            pos = str(p.get("position") or "").strip()
            tm = str(p.get("team") or "").strip()
            out[pid] = {"name": nm, "pos": pos, "team": tm}
    return out


def _build_map_from_league(league_json: Any) -> Dict[str, str]:
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
    m: Dict[str, str] = {}
    for row in standings_list:
        fid = str(row.get("id") or "").strip()
        nm = str(row.get("fname") or row.get("name") or "").strip()
        if fid and nm:
            m[fid] = nm
    return m


def fetch_week_data(league_id: str | int, week: int, client) -> Dict[str, Any]:
    """
    Pull core week data and resolve player ids -> names/pos/team for starters.
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

    # Player scores for the week (optional)
    try:
        out["player_scores"] = client.get_export("playerScores", W=week)
    except Exception as e:
        out["player_scores_error"] = str(e)

    # Pools
    try:
        out["pool_nfl"] = client.get_export("pool", POOLTYPE="NFL")
    except Exception as e:
        out["pool_nfl_error"] = str(e)
    try:
        out["survivor_pool"] = client.get_export("survivorPool")
    except Exception as e:
        out["survivor_pool_error"] = str(e)

    # League info (for franchise names)
    try:
        out["league"] = client.get_export("league")
    except Exception as e:
        out["league_error"] = str(e)

    # Franchise map (detected) from league + standings
    fm = {}
    fm.update(_build_map_from_league(out.get("league")))
    fm.update(_build_map_from_standings(standings_list))
    out["franchise_map_detected"] = fm

    # ---- Resolve starter ids to names via targeted players call ----
    try:
        wr = out.get("weekly_results") or {}
        starter_ids = _collect_starter_ids(wr)
        players_map: Dict[str, Dict[str, str]] = {}
        # MFL supports querying specific players: PLAYERS=comma_sep_ids
        # chunk to be safe (in case of >100 ids)
        CHUNK = 100
        for i in range(0, len(starter_ids), CHUNK):
            chunk = ",".join(starter_ids[i:i+CHUNK])
            pj = client.get_export("players", PLAYERS=chunk, DETAILS="1")
            players_map.update(_build_players_map(pj))
        out["players_map"] = players_map
    except Exception as e:
        out["players_map_error"] = str(e)

    return out
