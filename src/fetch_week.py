from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple
import requests


def _get_api_key() -> str:
    return os.environ.get("MFL_API_KEY", "").strip()


def _base_url(year: int) -> str:
    # e.g. https://www46.myfantasyleague.com/2025
    # Your league lives on www46; if MFL redirects, requests will follow.
    return f"https://www46.myfantasyleague.com/{year}"


def _get_json(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure JSON=1 is present
    params = dict(params or {})
    params["JSON"] = 1
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {}


def _players_map(year: int) -> Dict[str, Dict[str, str]]:
    """
    Return {player_id: {name, pos, team}}
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
            out[pid] = {
                "name": str(p.get("name") or "").strip(),
                "pos": str(p.get("position") or p.get("pos") or "").strip(),
                "team": str(p.get("team") or "").strip(),
            }
    return out


def _franchise_names_from_standings(standings_json: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract {franchise_id: franchise_name} from leagueStandings payload.
    """
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
    """
    Normalize standings into a list of rows: [{id, name, pf, vp}, ...]
    """
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
    """
    Fetch all week-level inputs needed by the pipeline.

    Returns a dict with:
      - weekly_results: raw weeklyResults JSON
      - standings_rows: normalized standings [{id,name,pf,vp}]
      - pool_nfl: confidence pool JSON (if configured)
      - survivor_pool: survivor pool JSON (if configured)
      - players_map: {player_id: {name,pos,team}}
      - franchise_names: {franchise_id: franchise_name}
    """
    # Pull year/league_id off the provided client object when possible.
    year = getattr(client, "year", None)
    league_id = getattr(client, "league_id", None)

    if not year or not league_id:
        raise ValueError("fetch_week_data: client must expose .year and .league_id")

    base = _base_url(year)
    apikey = _get_api_key()

    # --- Weekly Results (starters & scores) ---
    weekly_url = f"{base}/export"
    weekly_params = {
        "TYPE": "weeklyResults",
        "L": str(league_id),
        "W": str(week),
    }
    if apikey:
        weekly_params["APIKEY"] = apikey
    weekly_results = _get_json(weekly_url, weekly_params)

    # --- Standings (season-to-date, includes VP/PF per franchise) ---
    standings_url = f"{base}/export"
    standings_params = {
        "TYPE": "leagueStandings",
        "L": str(league_id),
        "COLUMN_NAMES": "",
        "ALL": "",
        "WEB": "",
    }
    if apikey:
        standings_params["APIKEY"] = apikey
    standings_json = _get_json(standings_url, standings_params)
    standings_rows = _standings_rows(standings_json)
    franchise_names = _franchise_names_from_standings(standings_json)

    # --- Confidence Pool (POOLTYPE=NFL for pick’em) ---
    pool_url = f"{base}/export"
    pool_params = {
        "TYPE": "pool",
        "L": str(league_id),
        "POOLTYPE": "NFL",
    }
    if apikey:
        pool_params["APIKEY"] = apikey
    pool_nfl = _get_json(pool_url, pool_params)

    # --- Survivor Pool ---
    survivor_url = f"{base}/export"
    survivor_params = {
        "TYPE": "survivorPool",
        "L": str(league_id),
    }
    if apikey:
        survivor_params["APIKEY"] = apikey
    survivor_pool = _get_json(survivor_url, survivor_params)

    # --- Players map (id -> name/pos/team) ---
    pmap = _players_map(year)

    # Package
    return {
        "weekly_results": weekly_results,
        "standings_rows": standings_rows,
        "pool_nfl": pool_nfl,
        "survivor_pool": survivor_pool,
        "players_map": pmap,
        "franchise_names": franchise_names,
    }
