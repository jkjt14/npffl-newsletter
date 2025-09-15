from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List
import json
import os

from .mfl_client import MFLClient


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


def _players_directory(client: MFLClient) -> Dict[str, Dict[str, str]]:
    """Canonical players directory (names/pos/team) to enrich weekly data."""
    data = client.get_players(details=1)
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


def fetch_week_data(client: MFLClient, week: int) -> Dict[str, Any]:
    year = getattr(client, "year", None)
    league_id = getattr(client, "league_id", None)
    if not year or not league_id:
        raise ValueError("fetch_week_data: client must expose .year and .league_id")

    weekly_results = client.get_weekly_results(week=week)
    standings_json = client.get_league_standings()
    pool_nfl = client.get_pool(pooltype="NFL")
    survivor_pool = client.get_survivor()
    players_dir = _players_directory(client)

    # Dump raw weeklyResults for debugging so we can tailor the extractor
    try:
        out_dir = Path(os.environ.get("NPFFL_OUTDIR", "build"))
        out_dir.mkdir(parents=True, exist_ok=True)
        dump_path = out_dir / f"wr_week_{int(week):02d}.json"
        dump_path.write_text(json.dumps(weekly_results, indent=2), encoding="utf-8")
        print(f"[fetch_week] dumped raw weeklyResults -> {dump_path}")
    except Exception as e:
        print(f"[fetch_week] failed to dump weeklyResults: {e}")

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
        "weekly_results": weekly_results,
        "standings_rows": standings_rows,
        "pool_nfl": pool_nfl,
        "survivor_pool": survivor_pool,
        "players_map": players_dir,
        "franchise_names": fmap,
    }
