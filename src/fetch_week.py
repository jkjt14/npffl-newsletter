from __future__ import annotations

import os
from typing import Any, Dict, List, Set
import requests


def _get_api_key() -> str:
    return os.environ.get("MFL_API_KEY", "").strip()


def _base_url(year: int) -> str:
    # Stick to your shard
    return f"https://www46.myfantasyleague.com/{year}"


def _get_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    q = dict(params or {})
    q["JSON"] = 1
    r = requests.get(url, params=q, timeout=30)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {}


def _first_last(name: str) -> str:
    name = (name or "").strip()
    if "," in name:
        last, first = [t.strip() for t in name.split(",", 1)]
        return f"{first} {last}".strip()
    return name


def _players_map_from_player_scores(year: int, league_id: str, week: int) -> Dict[str, Dict[str, str]]:
    """
    Build player map from this week's playerScores, which reliably includes names.
    """
    url = f"{_base_url(year)}/export"
    params = {"TYPE": "playerScores", "L": str(league_id), "W": str(week)}
    apikey = _get_api_key()
    if apikey:
        params["APIKEY"] = apikey
    data = _get_json(url, params)
    out: Dict[str, Dict[str, str]] = {}
    ps = (data or {}).get("playerScores")
    if not isinstance(ps, dict):
        return out
    for p in ps.get("player", []) or []:
        pid = str(p.get("id") or "").strip()
        if not pid:
            continue
        nm = _first_last(p.get("name") or "")
        pos = str(p.get("position") or p.get("pos") or "").strip()
        team = str(p.get("team") or "").strip()
        out[pid] = {"name": nm or pid, "pos": pos, "team": team}
    return out


def _collect_missing_ids(weekly_results: Dict[str, Any], players_map: Dict[str, Any]) -> List[str]:
    wr = weekly_results.get("weeklyResults") if isinstance(weekly_results, dict) else None
    fr = (wr.get("franchise") if isinstance(wr, dict) else None) or []
    if isinstance(fr, dict):
        fr = [fr]
    missing: Set[str] = set()
    for f in fr:
        for p in (f.get("player") or []):
            pid = str(p.get("id") or "").strip()
            if not pid:
                continue
            pm = players_map.get(pid)
            if not pm or not (pm.get("name") and pm.get("name") != pid):
                missing.add(pid)
    return sorted(list(missing))


def _enrich_player_info(year: int, ids: List[str], players_map: Dict[str, Any]) -> None:
    if not ids:
        return
    url = f"{_base_url(year)}/export"
    BATCH = 150
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        data = _get_json(url, {"TYPE": "playerInfo", "P": ",".join(chunk)})
        # Some shards return under "players.player", some under "playerInfo.player"
        node = (data.get("players") or data.get("playerInfo")) if isinstance(data, dict) else None
        rows = []
        if isinstance(node, dict):
            if isinstance(node.get("player"), list):
                rows = node["player"]
        for p in rows:
            pid = str(p.get("id") or "").strip()
            if not pid:
                continue
            nm = _first_last(p.get("name") or "")
            pos = str(p.get("position") or p.get("pos") or "").strip()
            team = str(p.get("team") or "").strip()
            base = players_map.get(pid) or {}
            players_map[pid] = {
                "name": nm or base.get("name") or pid,
                "pos": base.get("pos") or pos,
                "team": base.get("team") or team,
            }


def fetch_week_data(client, week: int) -> Dict[str, Any]:
    year = getattr(client, "year", None)
    league_id = getattr(client, "league_id", None)
    if not year or not league_id:
        raise ValueError("fetch_week_data: client must expose .year and .league_id")

    base = _base_url(year)
    apikey = _get_api_key()

    # Weekly results (starter lineups + scores)
    wr_params = {"TYPE": "weeklyResults", "L": str(league_id), "W": str(week)}
    if apikey:
        wr_params["APIKEY"] = apikey
    weekly_results = _get_json(f"{base}/export", wr_params)

    # Standings (for names + VP)
    st_params = {"TYPE": "leagueStandings", "L": str(league_id), "COLUMN_NAMES": "", "ALL": "", "WEB": ""}
    if apikey:
        st_params["APIKEY"] = apikey
    standings_json = _get_json(f"{base}/export", st_params)
    standings_rows = []
    fmap: Dict[str, str] = {}
    ls = (standings_json or {}).get("leagueStandings")
    if isinstance(ls, dict):
        for fr in (ls.get("franchise") or []):
            fid = str(fr.get("id") or "").strip()
            nm = (fr.get("name") or fr.get("fname") or fid).strip()
            fmap[fid] = nm
            try:
                pf = float(fr.get("pf") or 0.0)
            except Exception:
                pf = 0.0
            try:
                vp = float(fr.get("vp") or 0.0)
            except Exception:
                vp = 0.0
            standings_rows.append({"id": fid, "name": nm, "pf": pf, "vp": vp})

    # Pools
    pool_params = {"TYPE": "pool", "L": str(league_id), "POOLTYPE": "NFL"}
    if apikey:
        pool_params["APIKEY"] = apikey
    pool_nfl = _get_json(f"{base}/export", pool_params)

    sv_params = {"TYPE": "survivorPool", "L": str(league_id)}
    if apikey:
        sv_params["APIKEY"] = apikey
    survivor_pool = _get_json(f"{base}/export", sv_params)

    # ✅ Player map from *this week's* playerScores (names included)
    players_map = _players_map_from_player_scores(year, str(league_id), week)

    # Enrich any stragglers with playerInfo (rare)
    missing_ids = _collect_missing_ids(weekly_results, players_map)
    if missing_ids:
        _enrich_player_info(year, missing_ids, players_map)

    return {
        "weekly_results": weekly_results,
        "standings_rows": standings_rows,
        "pool_nfl": pool_nfl,
        "survivor_pool": survivor_pool,
        "players_map": players_map,
        "franchise_names": fmap,
        # odds handled elsewhere if configured
    }
