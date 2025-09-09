from __future__ import annotations

import os
from typing import Any, Dict, List, Set
import requests


def _get_api_key() -> str:
    return os.environ.get("MFL_API_KEY", "").strip()


def _base_url(year: int) -> str:
    # You’re on www46; keep it stable to your league’s shard.
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


def _first_last_from_fields(p: Dict[str, Any]) -> str:
    """
    Normalize to 'First Last'. MFL may give:
      - name: 'Last, First'
      - firstName/lastName
      - name: 'First Last'
    """
    name = (p.get("name") or "").strip()
    if name and "," in name:
        last, first = [t.strip() for t in name.split(",", 1)]
        return f"{first} {last}".strip()
    if name:
        return name
    first = (p.get("firstName") or p.get("fname") or "").strip()
    last = (p.get("lastName") or p.get("lname") or "").strip()
    if first or last:
        return f"{first} {last}".strip()
    return ""


def _players_map(year: int) -> Dict[str, Dict[str, str]]:
    """
    Base map from TYPE=players. Not always complete for every ID
    showing up in weeklyResults, so we will enrich it later.
    """
    url = f"{_base_url(year)}/export"
    data = _get_json(url, {"TYPE": "players"})
    out: Dict[str, Dict[str, str]] = {}
    players = (data or {}).get("players")
    if isinstance(players, dict):
        for p in players.get("player", []) or []:
            pid = str(p.get("id") or "").strip()
            if not pid:
                continue
            nm = _first_last_from_fields(p)
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
    """
    Fill in names for any missing IDs using TYPE=playerInfo&P=...
    Batched to avoid long URLs.
    """
    if not ids:
        return
    url = f"{_base_url(year)}/export"
    BATCH = 150
    for i in range(0, len(ids), BATCH):
        chunk = ids[i:i + BATCH]
        data = _get_json(url, {"TYPE": "playerInfo", "P": ",".join(chunk)})
        pi = (data or {}).get("players") or (data or {}).get("playerInfo")
        # Some MFL variants return under .players.player, others under .playerInfo.player
        rows = []
        if isinstance(pi, dict):
            if isinstance(pi.get("player"), list):
                rows = pi.get("player") or []
            elif isinstance(pi.get("players"), list):
                rows = pi.get("players") or []
        for p in rows:
            pid = str(p.get("id") or "").strip()
            if not pid:
                continue
            nm = _first_last_from_fields(p)
            pos = str(p.get("position") or p.get("pos") or "").strip()
            team = str(p.get("team") or "").strip()
            if pid not in players_map or not players_map[pid].get("name"):
                players_map[pid] = {"name": nm or pid, "pos": pos, "team": team}
            else:
                # patch holes
                if not players_map[pid].get("name"):
                    players_map[pid]["name"] = nm or pid
                if not players_map[pid].get("pos") and pos:
                    players_map[pid]["pos"] = pos
                if not players_map[pid].get("team") and team:
                    players_map[pid]["team"] = team


def fetch_week_data(client, week: int) -> Dict[str, Any]:
    year = getattr(client, "year", None)
    league_id = getattr(client, "league_id", None)
    if not year or not league_id:
        raise ValueError("fetch_week_data: client must expose .year and .league_id")

    base = _base_url(year)
    apikey = _get_api_key()

    # Weekly results (includes actual starters and scores)
    wr_params = {"TYPE": "weeklyResults", "L": str(league_id), "W": str(week)}
    if apikey: wr_params["APIKEY"] = apikey
    weekly_results = _get_json(f"{base}/export", wr_params)

    # Standings (used for VP narrative & team names)
    st_params = {"TYPE": "leagueStandings", "L": str(league_id), "COLUMN_NAMES": "", "ALL": "", "WEB": ""}
    if apikey: st_params["APIKEY"] = apikey
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

    # Confidence pool
    pool_params = {"TYPE": "pool", "L": str(league_id), "POOLTYPE": "NFL"}
    if apikey: pool_params["APIKEY"] = apikey
    pool_nfl = _get_json(f"{base}/export", pool_params)

    # Survivor pool
    sv_params = {"TYPE": "survivorPool", "L": str(league_id)}
    if apikey: sv_params["APIKEY"] = apikey
    survivor_pool = _get_json(f"{base}/export", sv_params)

    # Players (base map)
    players_map = _players_map(year)

    # Enrich: make sure every player ID in weekly_results has a real name
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
        # odds_map is filled in odds_client (already wired in your tree)
    }
