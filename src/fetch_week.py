from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List
import requests


def _get_api_key() -> str:
    return os.environ.get("MFL_API_KEY", "").strip()


def _host() -> str:
    # Your league uses www46; allow override via env if needed.
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


def _players_directory(year: int, league_id: str) -> Dict[str, Dict[str, str]]:
    """
    Canonical players directory (names/pos/team) so we can enrich weekly data.
    """
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


def fetch_week_data(client, week: int) -> Dict[str, Any]:
    year = getattr(client, "year", None)
    league_id = getattr(client, "league_id", None)
    if not year or not league_id:
        raise ValueError("fetch_week_data: client must expose .year and .league_id")

    # Pull core payloads
    weekly_results = _weekly_results(year, league_id, week)   # RAW weeklyResults JSON
    standings_json = _standings(year, league_id)
    pool_nfl = _pool(year, league_id)
    survivor_pool = _survivor(year, league_id)
    players_dir = _players_directory(year, league_id)

    # Dump raw weeklyResults for debugging so we can tailor the extractor
    try:
        out_dir = Path(os.environ.get("NPFFL_OUTDIR", "build"))
        out_dir.mkdir(parents=True, exist_ok=True)
        dump_path = out_dir / f"wr_week_{int(week):02d}.json"
        dump_path.write_text(json.dumps(weekly_results, indent=2), encoding="utf-8")
        print(f"[fetch_week] dumped raw weeklyResults -> {dump_path}")
    except Exception as e:
        print(f"[fetch_week] failed to dump weeklyResults: {e}")

    # Franchise name map + quick standings rows
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

    print(f"[fetch_week] players_dir size: {len(players_dir)}")

    return {
        # Keep the RAW weeklyResults so main.py can parse your shard’s exact shape.
        "weekly_results": weekly_results,
        "standings_rows": standings_rows,
        "pool_nfl": pool_nfl,
        "survivor_pool": survivor_pool,
        "players_map": players_dir,
        "franchise_names": fmap,
    }
