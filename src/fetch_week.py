from __future__ import annotations

import os
from typing import Any, Dict, List, Set
import requests


def _get_api_key() -> str:
    return os.environ.get("MFL_API_KEY", "").strip()


def _base_url(year: int) -> str:
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


def _last_first_from_fl(fl: str) -> str:
    toks = [t for t in (fl or "").split(" ") if t]
    if len(toks) >= 2:
        return f"{toks[-1]}, {' '.join(toks[:-1])}"
    return fl


def _players_directory(year: int, league_id: str) -> Dict[str, Dict[str, str]]:
    """
    Pull the full players directory so we get canonical MFL names.
    Works even if weekly endpoints omit a 'name' field in some shards.
    """
    url = f"{_base_url(year)}/export"
    params = {"TYPE": "players", "L": str(league_id), "DETAILS": 1}
    apikey = _get_api_key()
    if apikey:
        params["APIKEY"] = apikey
    data = _get_json(url, params)

    out: Dict[str, Dict[str, str]] = {}
    node = (data or {}).get("players") or {}
    rows = node.get("player") or []
    if isinstance(rows, dict):
        rows = [rows]

    for p in rows:
        pid = str(p.get("id") or "").strip()
        if not pid:
            continue
        raw = (p.get("name") or "").strip()
        fl = _first_last(raw)
        lf = _last_first_from_fl(fl)
        pos = str(p.get("position") or p.get("pos") or "").strip()
        team = str(p.get("team") or "").strip()
        out[pid] = {
            "raw": raw,          # e.g., "Allen, Josh"
            "first_last": fl,    # "Josh Allen"
            "last_first": lf,    # "Allen, Josh"
            "pos": pos,
            "team": team,
        }
    return out


def _weekly_results(year: int, league_id: str, week: int) -> Dict[str, Any]:
    url = f"{_base_url(year)}/export"
    params = {"TYPE": "weeklyResults", "L": str(league_id), "W": str(week)}
    apikey = _get_api_key()
    if apikey:
        params["APIKEY"] = apikey
    return _get_json(url, params)


def _standings(year: int, league_id: str) -> Dict[str, Any]:
    url = f"{_base_url(year)}/export"
    params = {"TYPE": "leagueStandings", "L": str(league_id), "COLUMN_NAMES": "", "ALL": "", "WEB": ""}
    apikey = _get_api_key()
    if apikey:
        params["APIKEY"] = apikey
    return _get_json(url, params)


def _pool(year: int, league_id: str) -> Dict[str, Any]:
    url = f"{_base_url(year)}/export"
    params = {"TYPE": "pool", "L": str(league_id), "POOLTYPE": "NFL"}
    apikey = _get_api_key()
    if apikey:
        params["APIKEY"] = apikey
    return _get_json(url, params)


def _survivor(year: int, league_id: str) -> Dict[str, Any]:
    url = f"{_base_url(year)}/export"
    params = {"TYPE": "survivorPool", "L": str(league_id)}
    apikey = _get_api_key()
    if apikey:
        params["APIKEY"] = apikey
    return _get_json(url, params)


def fetch_week_data(client, week: int) -> Dict[str, Any]:
    year = getattr(client, "year", None)
    league_id = getattr(client, "league_id", None)
    if not year or not league_id:
        raise ValueError("fetch_week_data: client must expose .year and .league_id")

    # Pull all primary data
    weekly_results = _weekly_results(year, league_id, week)
    standings_json = _standings(year, league_id)
    pool_nfl = _pool(year, league_id)
    survivor_pool = _survivor(year, league_id)
    players_dir = _players_directory(year, league_id)

    # franchise name map for pretty printing
    fmap: Dict[str, str] = {}
    standings_rows: List[Dict[str, Any]] = []
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

    print(f"[fetch_week] players_dir size: {len(players_dir)}")

    return {
        "weekly_results": weekly_results,
        "standings_rows": standings_rows,
        "pool_nfl": pool_nfl,
        "survivor_pool": survivor_pool,
        "players_map": players_dir,   # id -> {raw, first_last, last_first, pos, team}
        "franchise_names": fmap,
    }
