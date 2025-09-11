from __future__ import annotations

import os
from typing import Any, Dict, List
import requests


def _get_api_key() -> str:
    return os.environ.get("MFL_API_KEY", "").strip()


def _host() -> str:
    return os.environ.get("MFL_HOST", "www46.myfantasyleague.com")


def _base_url(year: int) -> str:
    return f"https://{_host()}/{year}"


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


# -----------------------------
# MFL endpoints
# -----------------------------

def _players_directory(year: int, league_id: str) -> Dict[str, Dict[str, str]]:
    url = f"{_base_url(year)}/export"
    params = {"TYPE": "players", "L": str(league_id), "DETAILS": 1}
    apikey = _get_api_key()
    if apikey:
        params["APIKEY"] = apikey
    data = _get_json(url, params)

    out: Dict[str, Dict[str, str]] = {}
    rows = (data or {}).get("players", {}).get("player", []) or []
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
        out[pid] = {"raw": raw, "first_last": fl, "last_first": lf, "pos": pos, "team": team}
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


# -----------------------------
# Normalization (optional)
# -----------------------------

def _key_for_matchup(m: Dict[str, Any]) -> str:
    f = m.get("franchise") or []
    if isinstance(f, dict):
        f = [f]
    ids = [str(x.get("id") or x.get("franchise_id") or "").zfill(4) for x in f]
    return ",".join(sorted(ids))


def _normalize_from_weekly_results(wr_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Produce a matchups list compatible with main.py’s 'normalized' path,
    using only weeklyResults (no liveScoring).
    """
    wrn = (wr_json or {}).get("weeklyResults") or {}
    mlist = wrn.get("matchup") or []
    if isinstance(mlist, dict):
        mlist = [mlist]

    out: List[Dict[str, Any]] = []
    for m in mlist:
        frs = m.get("franchise") or []
        if isinstance(frs, dict):
            frs = [frs]

        # collect franchise-level players if present
        norm_frs = []
        for fr in frs:
            fid = str(fr.get("id") or fr.get("franchise_id") or "").zfill(4)
            score = fr.get("score") or fr.get("pf") or fr.get("points") or 0.0

            # try to lift players if franchise node has them
            f_pl = fr.get("players") or fr.get("player") or []
            if isinstance(f_pl, dict):
                f_pl = f_pl.get("player") or f_pl
            if isinstance(f_pl, dict):
                f_pl = [f_pl]
            players = []
            for p in f_pl or []:
                players.append({
                    "id": str(p.get("id") or "").strip(),
                    "name": (p.get("name") or "").strip(),
                    "position": (p.get("position") or p.get("pos") or "").strip(),
                    "team": (p.get("team") or "").strip(),
                    "score": float(p.get("score") or p.get("points") or 0.0),
                })

            norm_frs.append({
                "id": fid,
                "score": score,
                "players": {"player": players} if players else {},
            })

        out.append({"franchise": norm_frs})
    return out


# -----------------------------
# Entry point
# -----------------------------

def fetch_week_data(client, week: int) -> Dict[str, Any]:
    year = getattr(client, "year", None)
    league_id = getattr(client, "league_id", None)
    if not year or not league_id:
        raise ValueError("fetch_week_data: client must expose .year and .league_id")

    weekly_results_raw = _weekly_results(year, league_id, week)   # RAW weeklyResults JSON
    standings_json = _standings(year, league_id)
    pool_nfl = _pool(year, league_id)
    survivor_pool = _survivor(year, league_id)
    players_dir = _players_directory(year, league_id)

    # Franchise names + simple standings table
    fmap: Dict[str, str] = {}
    standings_rows: List[Dict[str, Any]] = []
    ls = (standings_json or {}).get("leagueStandings")
    if isinstance(ls, dict):
        fr_list = ls.get("franchise") or []
        if isinstance(fr_list, dict):
            fr_list = [fr_list]
        for fr in fr_list:
            fid = str(fr.get("id") or "").strip()
            nm = (fr.get("name") or fr.get("fname") or fid).strip()
            fmap[fid] = nm
            pf = float(fr.get("pf") or 0.0)
            vp = float(fr.get("vp") or 0.0)
            standings_rows.append({"id": fid, "name": nm, "pf": pf, "vp": vp})

    # Build a best-effort normalized view from weeklyResults only (may lack per-player)
    normalized_matchups = _normalize_from_weekly_results(weekly_results_raw)

    # Debug
    num_matchups = len(normalized_matchups)
    num_players = sum(len((fr.get("players") or {}).get("player") or [])
                      for m in normalized_matchups for fr in (m.get("franchise") or []))
    print(f"[fetch_week] players_dir size: {len(players_dir)}")
    print(f"[fetch_week] matchups: {num_matchups}, per-player rows: {num_players}")

    return {
        # IMPORTANT: expose BOTH normalized and RAW weeklyResults so main.py can fall back
        "weekly_results": {
            "matchups": normalized_matchups,
            "weeklyResults": weekly_results_raw.get("weeklyResults") or {}
        },
        "standings_rows": standings_rows,
        "pool_nfl": pool_nfl,
        "survivor_pool": survivor_pool,
        "players_map": players_dir,
        "franchise_names": fmap,
    }
