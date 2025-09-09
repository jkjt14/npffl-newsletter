from __future__ import annotations

import os
from typing import Any, Dict, List
import requests

from .odds_client import fetch_week_win_probs_nfl


def _get_api_key() -> str:
    return os.environ.get("MFL_API_KEY", "").strip()


def _base_url(year: int) -> str:
    return f"https://www46.myfantasyleague.com/{year}"


def _get_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    params = dict(params or {})
    params["JSON"] = 1
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {}


def _first_last_from_any(p: Dict[str, Any]) -> str:
    """
    MFL sometimes returns 'name' as 'Last, First' or separate 'firstName'/'lastName'.
    Normalize to 'First Last'.
    """
    name = (p.get("name") or "").strip()
    first = (p.get("firstName") or p.get("fname") or "").strip()
    last = (p.get("lastName") or p.get("lname") or "").strip()

    if name:
        # If "Last, First", flip
        if "," in name:
            parts = [x.strip() for x in name.split(",", 1)]
            if len(parts) == 2:
                return f"{parts[1]} {parts[0]}".strip()
        return name

    if first or last:
        return f"{first} {last}".strip()

    return ""


def _players_map(year: int) -> Dict[str, Dict[str, str]]:
    """
    Return {player_id: {name (First Last), pos, team}}
    Tries TYPE=players with as many fields as available.
    """
    url = f"{_base_url(year)}/export"
    params = {"TYPE": "players"}
    data = _get_json(url, params)
    out: Dict[str, Dict[str, str]] = {}
    players = (data or {}).get("players")
    if isinstance(players, dict):
        for p in players.get("player", []) or []:
            pid = str(p.get("id") or "").strip()
            if not pid:
                continue
            disp = _first_last_from_any(p) or (p.get("name") or "").strip()
            pos = str(p.get("position") or p.get("pos") or "").strip()
            team = str(p.get("team") or "").strip()
            if not disp:
                # fallback to raw 'name' if present
                disp = (p.get("name") or "").strip()
            out[pid] = {"name": disp, "pos": pos, "team": team}
    return out


def _franchise_names_from_standings(standings_json: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    ls = (standings_json or {}).get("leagueStandings")
    if not isinstance(ls, dict):
        return out
    for fr in (ls.get("franchise") or []):
        fid = str(fr.get("id") or "").strip()
        name = (fr.get("name") or fr.get("fname") or "").strip()
        if fid:
            out[fid] = name or fid
    return out


def _standings_rows(standings_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    ls = (standings_json or {}).get("leagueStandings")
    if not isinstance(ls, dict):
        return rows
    for fr in (ls.get("franchise") or []):
        fid = str(fr.get("id") or "").strip()
        name = (fr.get("name") or fr.get("fname") or "").strip()
        try:
            pf = float(fr.get("pf") or 0.0)
        except Exception:
            pf = 0.0
        try:
            vp = float(fr.get("vp") or 0.0)
        except Exception:
            vp = 0.0
        rows.append({"id": fid, "name": name, "pf": pf, "vp": vp})
    return rows


def fetch_week_data(client, week: int) -> Dict[str, Any]:
    year = getattr(client, "year", None)
    league_id = getattr(client, "league_id", None)
    if not year or not league_id:
        raise ValueError("fetch_week_data: client must expose .year and .league_id")

    base = _base_url(year)
    apikey = _get_api_key()

    # Weekly results
    weekly_params = {"TYPE": "weeklyResults", "L": str(league_id), "W": str(week)}
    if apikey: weekly_params["APIKEY"] = apikey
    weekly_results = _get_json(f"{base}/export", weekly_params)

    # Standings
    standings_params = {"TYPE": "leagueStandings", "L": str(league_id), "COLUMN_NAMES": "", "ALL": "", "WEB": ""}
    if apikey: standings_params["APIKEY"] = apikey
    standings_json = _get_json(f"{base}/export", standings_params)
    standings_rows = _standings_rows(standings_json)
    franchise_names = _franchise_names_from_standings(standings_json)

    # Confidence pool
    pool_params = {"TYPE": "pool", "L": str(league_id), "POOLTYPE": "NFL"}
    if apikey: pool_params["APIKEY"] = apikey
    pool_nfl = _get_json(f"{base}/export", pool_params)

    # Survivor pool
    survivor_params = {"TYPE": "survivorPool", "L": str(league_id)}
    if apikey: survivor_params["APIKEY"] = apikey
    survivor_pool = _get_json(f"{base}/export", survivor_params)

    # Players (names/pos/team)
    pmap = _players_map(year)

    # Real win probs
    odds_map = fetch_week_win_probs_nfl(week=week, season_year=year) or {}

    return {
        "weekly_results": weekly_results,
        "standings_rows": standings_rows,
        "pool_nfl": pool_nfl,
        "survivor_pool": survivor_pool,
        "players_map": pmap,
        "franchise_names": franchise_names,
        "odds": odds_map,
    }
