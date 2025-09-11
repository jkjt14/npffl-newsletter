from __future__ import annotations

import os
from typing import Any, Dict, List, Set
import requests


# -----------------------------
# Config / helpers
# -----------------------------

def _get_api_key() -> str:
    return os.environ.get("MFL_API_KEY", "").strip()


def _host() -> str:
    # Allow override via env if your league isn’t on www46
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
    """
    Canonical players directory (names/pos/team) so we can fill missing fields
    from weekly endpoints.
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
            "raw": raw,          # "Allen, Josh"
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


def _live_scoring(year: int, league_id: str, week: int) -> Dict[str, Any]:
    """
    liveScoring typically contains per-player scoring:
      {'liveScoring': {'matchup': [{'franchise': [{'players': {'player': [...]}}]}]}}
    """
    url = f"{_base_url(year)}/export"
    params = {"TYPE": "liveScoring", "L": str(league_id), "W": str(week), "DETAILS": 1}
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
# Normalization
# -----------------------------

def _key_for_matchup(m: Dict[str, Any]) -> str:
    """Key a matchup by sorted franchise IDs to align WR↔LS."""
    f = m.get("franchise") or []
    if isinstance(f, dict):
        f = [f]
    ids = []
    for x in f:
        ids.append(str(x.get("id") or x.get("franchise_id") or "").zfill(4))
    return ",".join(sorted(ids))


def _normalize_matchups(weekly_results_json: Dict[str, Any], live_scoring_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build a list like:
      {
        'franchise': [
          { 'id': '0001', 'score': 93.3, 'players': { 'player': [ {id,name,position,team,score}, ... ] } },
          { 'id': '0002', 'score': 88.1, 'players': { 'player': [...] } }
        ]
      }
    Prefer liveScoring for per-player data; use weeklyResults for team totals if missing.
    """
    # Live scoring source
    ls = (live_scoring_json or {}).get("liveScoring") or {}
    ls_matchups = ls.get("matchup") or []
    if isinstance(ls_matchups, dict):
        ls_matchups = [ls_matchups]

    # Weekly results source (team totals)
    wr = (weekly_results_json or {}).get("weeklyResults") or {}
    wr_matchups = wr.get("matchup") or []
    if isinstance(wr_matchups, dict):
        wr_matchups = [wr_matchups]
    wr_by_key: Dict[str, Dict[str, Any]] = { _key_for_matchup(m): m for m in wr_matchups }

    out: List[Dict[str, Any]] = []

    if ls_matchups:
        for m in ls_matchups:
            frs = m.get("franchise") or []
            if isinstance(frs, dict):
                frs = [frs]
            norm_frs: List[Dict[str, Any]] = []
            for fr in frs:
                fid = str(fr.get("id") or fr.get("franchise_id") or "").zfill(4)

                # Score: prefer liveScoring, else supplement from weeklyResults
                score = fr.get("score")
                if score is None:
                    k = _key_for_matchup(m)
                    wr_m = wr_by_key.get(k) or {}
                    wr_frs = wr_m.get("franchise") or []
                    if isinstance(wr_frs, dict):
                        wr_frs = [wr_frs]
                    for _fr in wr_frs:
                        if str(_fr.get("id") or "").zfill(4) == fid:
                            score = _fr.get("score") or _fr.get("pf") or _fr.get("points")
                            break

                # Players
                players_node = fr.get("players") or {}
                players = players_node.get("player") or []
                if isinstance(players, dict):
                    players = [players]

                norm_players: List[Dict[str, Any]] = []
                for p in players:
                    pid = str(p.get("id") or "").strip()
                    nm = (p.get("name") or "").strip()
                    pos = (p.get("position") or p.get("pos") or "").strip()
                    team = (p.get("team") or "").strip()
                    pts = p.get("score") or p.get("points") or 0.0
                    try:
                        pts = float(pts)
                    except Exception:
                        pts = 0.0
                    norm_players.append({
                        "id": pid,
                        "name": nm,
                        "position": pos,
                        "team": team,
                        "score": pts,
                    })

                norm_frs.append({
                    "id": fid,
                    "score": score,
                    "players": {"player": norm_players} if norm_players else {},
                })

            out.append({"franchise": norm_frs})

        return out

    # Fallback: only weeklyResults available → still emit totals
    for m in wr_matchups:
        frs = m.get("franchise") or []
        if isinstance(frs, dict):
            frs = [frs]
        norm_frs = []
        for fr in frs:
            fid = str(fr.get("id") or fr.get("franchise_id") or "").zfill(4)
            score = fr.get("score") or fr.get("pf") or fr.get("points") or 0.0
            norm_frs.append({"id": fid, "score": score, "players": {}})
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

    # Pull everything
    weekly_results_json = _weekly_results(year, league_id, week)
    live_scoring_json = _live_scoring(year, league_id, week)
    standings_json = _standings(year, league_id)
    pool_nfl = _pool(year, league_id)
    survivor_pool = _survivor(year, league_id)
    players_dir = _players_directory(year, league_id)

    # Franchise names + standings_rows (your existing behavior)
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
            try:
                pf = float(fr.get("pf") or 0.0)
            except Exception:
                pf = 0.0
            try:
                vp = float(fr.get("vp") or 0.0)
            except Exception:
                vp = 0.0
            standings_rows.append({"id": fid, "name": nm, "pf": pf, "vp": vp})

    # Merge/normalize matchups from both sources
    matchups = _normalize_matchups(weekly_results_json, live_scoring_json)

    # Debug so we can see what's happening in CI logs
    num_matchups = len(matchups)
    num_players = sum(len((fr.get("players") or {}).get("player") or [])
                      for m in matchups for fr in (m.get("franchise") or []))
    print(f"[fetch_week] players_dir size: {len(players_dir)}")
    print(f"[fetch_week] matchups: {num_matchups}, per-player rows: {num_players}")

    return {
        "weekly_results": { "matchups": matchups },
        "standings_rows": standings_rows,
        "pool_nfl": pool_nfl,
        "survivor_pool": survivor_pool,
        "players_map": players_dir,   # id -> {raw, first_last, last_first, pos, team}
        "franchise_names": fmap,
    }
