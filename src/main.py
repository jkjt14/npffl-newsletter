from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from .mfl_client import MFLClient
from .fetch_week import fetch_week_data  # must return weekly data dict
from .load_salary import load_salary_file  # must return pandas DataFrame
from .value_engine import compute_values   # returns dict with value/busts & team efficiency
from .newsletter import render_newsletter


def _read_config(path: str | Path = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _week_label(week: int | None) -> str:
    return f"{int(week):02d}" if week is not None else "01"


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _merge_franchise_names(*maps: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for mp in maps:
        for k, v in (mp or {}).items():
            if k is None:
                continue
            out[str(k).zfill(4)] = str(v)
    return out


def _build_standings_rows(week_data: Dict[str, Any], f_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Expected output rows: {id, name, pf, vp}
    Tries multiple shapes from fetch_week payloads.
    """
    rows: List[Dict[str, Any]] = []

    # Option A: explicit standings array with pf/vp
    st = week_data.get("standings") or week_data.get("standings_rows")
    if isinstance(st, list) and st:
        for r in st:
            fid = str(r.get("id") or r.get("franchise_id") or r.get("franchiseId") or "").zfill(4)
            if not fid:
                continue
            name = f_map.get(fid, r.get("name") or fid)
            pf = _safe_float(r.get("pf") or r.get("points_for") or r.get("points") or 0)
            vp = _safe_float(r.get("vp") or r.get("victory_points") or 0)
            rows.append({"id": fid, "name": name, "pf": pf, "vp": vp})
        if rows:
            return rows

    # Option B: derive from weekly scores (most common)
    # Look under week_data["weekly_results"]["franchise"] or week_data["scores"]
    scores = week_data.get("scores") or week_data.get("weekly_results") or {}
    fr = scores.get("franchise") if isinstance(scores, dict) else None
    if fr is None and isinstance(scores, list):
        fr = scores
    if isinstance(fr, dict):
        fr = [fr]
    if isinstance(fr, list):
        for r in fr:
            fid = str(r.get("id") or r.get("franchise_id") or "").zfill(4)
            if not fid:
                continue
            name = f_map.get(fid, fid)
            pf = _safe_float(r.get("score") or r.get("pf") or r.get("points") or 0)
            # If your league uses weekly VP tiers, try week_data['vp_map'] else compute later
            vp = _safe_float(r.get("vp") or 0)
            rows.append({"id": fid, "name": name, "pf": pf, "vp": vp})
    return rows


def _index_starters_by_franchise(week_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Returns { '0001': [ {player, pos, team, pts}, ... ], ... }
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    starters = week_data.get("starters") or week_data.get("lineups") or {}
    if isinstance(starters, dict) and starters.get("franchise"):
        fr = starters["franchise"]
        if isinstance(fr, dict):
            fr = [fr]
        for row in fr:
            fid = str(row.get("id") or row.get("franchise_id") or "").zfill(4)
            if not fid:
                continue
            ps = row.get("players") or row.get("starter") or row.get("players_started") or []
            if isinstance(ps, dict):
                ps = [ps]
            items: List[Dict[str, Any]] = []
            for p in ps:
                items.append({
                    "player": p.get("name") or p.get("player") or p.get("id") or "",
                    "pos": p.get("position") or p.get("pos") or "",
                    "team": p.get("team") or p.get("nflteam") or "",
                    "pts": _safe_float(p.get("points") or p.get("pts") or 0.0),
                    "player_id": str(p.get("id") or p.get("player_id") or ""),
                })
            out[fid] = items
    return out


def _build_top_performers(week_data: Dict[str, Any],
                          starters_by_f: Dict[str, List[Dict[str, Any]]],
                          players_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Returns list of {player, pos, team, pts, franchise_ids}
    We dedupe by (name,pos,team,pts) and aggregate which franchises started them.
    """
    perf: List[Dict[str, Any]] = []
    raw = week_data.get("performers") or week_data.get("top_performers") or []
    # If not present, derive performers from starters combined:
    if not raw and starters_by_f:
        pool = []
        for fid, items in starters_by_f.items():
            for it in items:
                pool.append(it)
        # pick top N by pts
        pool.sort(key=lambda x: x.get("pts", 0), reverse=True)
        raw = pool[:20]

    # Build map: signature -> entry
    seen: Dict[Tuple[str, str, str, float], Dict[str, Any]] = {}
    for item in raw:
        name = item.get("player") or item.get("name") or ""
        pid = str(item.get("player_id") or item.get("id") or "")
        if not name and pid and pid in players_map:
            name = players_map[pid].get("name") or pid
        # enforce First Last
        if "," in name:
            parts = [p.strip() for p in name.split(",", 1)]
            name = f"{parts[1]} {parts[0]}".strip()
        pos = item.get("pos") or item.get("position") or ""
        team = item.get("team") or item.get("nflteam") or ""
        pts = _safe_float(item.get("pts") or item.get("points") or 0)
        sig = (name, pos, team, pts)
        entry = seen.get(sig)
        if not entry:
            entry = {"player": name, "pos": pos, "team": team, "pts": pts, "franchise_ids": []}
            seen[sig] = entry

    # figure out which franchises started them
    for fid, items in starters_by_f.items():
        for it in items:
            nm = it.get("player") or ""
            pid = str(it.get("player_id") or "")
            if not nm and pid and pid in players_map:
                nm = players_map[pid].get("name") or pid
            if "," in nm:
                pp = [p.strip() for p in nm.split(",", 1)]
                nm = f"{pp[1]} {pp[0]}".strip()
            pos = it.get("pos") or ""
            team = it.get("team") or ""
            pts = _safe_float(it.get("pts") or 0)
            sig = (nm, pos, team, pts)
            if sig in seen:
                if fid not in seen[sig]["franchise_ids"]:
                    seen[sig]["franchise_ids"].append(fid)

    perf = sorted(seen.values(), key=lambda x: x["pts"], reverse=True)[:20]
    return perf


def _build_team_efficiency(values_out: Dict[str, Any], f_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    value_engine should provide team totals. Expect either:
      values_out["team_efficiency"] = [{franchise_id, total_pts, total_sal, ppk}, ...]
    or we’ll attempt to aggregate from per-starter rows in values_out["starters_with_salary"].
    """
    rows = values_out.get("team_efficiency")
    if isinstance(rows, list) and rows:
        # normalize id and ensure ints
        out = []
        for r in rows:
            fid = str(r.get("franchise_id") or r.get("id") or "").zfill(4)
            out.append({
                "franchise_id": fid,
                "total_pts": _safe_float(r.get("total_pts")),
                "total_sal": int(float(r.get("total_sal") or 0)),
                "ppk": _safe_float(r.get("ppk")),
                "name": f_map.get(fid, fid),
            })
        return out

    starters = values_out.get("starters_with_salary") or []
    agg: Dict[str, Dict[str, Any]] = {}
    for s in starters:
        fid = str(s.get("franchise_id") or "").zfill(4)
        if not fid:
            continue
        rec = agg.setdefault(fid, {"franchise_id": fid, "total_pts": 0.0, "total_sal": 0})
        rec["total_pts"] += _safe_float(s.get("pts"))
        rec["total_sal"] += int(float(s.get("salary") or 0))
    out = []
    for fid, rec in agg.items():
        sal = rec["total_sal"] if rec["total_sal"] else 0
        ppk = (rec["total_pts"] / (sal / 1000.0)) if sal else 0.0
        out.append({
            "franchise_id": fid,
            "total_pts": rec["total_pts"],
            "total_sal": sal,
            "ppk": ppk,
            "name": f_map.get(fid, fid),
        })
    return sorted(out, key=lambda x: x["ppk"], reverse=True)


def _build_values_tables(values_out: Dict[str, Any], players_map: Dict[str, Dict[str, Any]], f_map: Dict[str, str]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns (top_values, top_busts)
    Each list entry: {player, pos, team, pts, salary, franchise_id, ppk}
    """
    def normalize(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in (items or []):
            pid = str(r.get("player_id") or "")
            name = r.get("player") or ""
            if not name and pid and pid in players_map:
                name = players_map[pid].get("name") or pid
            if "," in name:
                parts = [p.strip() for p in name.split(",", 1)]
                name = f"{parts[1]} {parts[0]}".strip()
            out.append({
                "player": name,
                "pos": r.get("pos") or r.get("position") or "",
                "team": r.get("team") or r.get("nflteam") or "",
                "pts": _safe_float(r.get("pts") or r.get("points")),
                "salary": int(float(r.get("salary") or 0)),
                "franchise_id": str(r.get("franchise_id") or "").zfill(4),
                "ppk": _safe_float(r.get("ppk") or 0),
            })
        return out

    top_vals = normalize(values_out.get("top_values") or values_out.get("values") or [])
    top_busts = normalize(values_out.get("top_busts") or values_out.get("busts") or [])
    return top_vals, top_busts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week", default=os.environ.get("WEEK", "").strip())
    args = parser.parse_args()

    cfg = _read_config()
    year = int(cfg.get("year", 2025))
    league_id = str(cfg.get("league_id", os.environ.get("MFL_LEAGUE_ID", "35410")))
    tz = str(cfg.get("timezone", "America/New_York"))
    out_dir = Path(cfg.get("outputs", {}).get("dir", "build"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # Determine target week
    week = None
    if args.week and str(args.week).isdigit():
        week = int(args.week)
    elif str(cfg.get("inputs", {}).get("week", "")).isdigit():
        week = int(cfg["inputs"]["week"])
    # Else None → your fetcher should pick latest completed

    wl = _week_label(week)

    # Instantiate client (API key or user/pass already in env)
    client = MFLClient(
        league_id=league_id,
        year=year,
        username=os.environ.get("MFL_USERNAME", "") or None,
        password=os.environ.get("MFL_PASSWORD", "") or None,
        api_key=os.environ.get("MFL_API_KEY", "") or None,
        cache_dir="data/cache",
    )

    # Fetch weekly data
    week_data = fetch_week_data(client, week=week)

    # Franchise names map: prefer week_data’s mapping; merge with any hardcoded dicts
    f_map = _merge_franchise_names(
        week_data.get("franchise_names") or week_data.get("franchises") or {},
        # You can hardcode fallbacks here if desired
        {
            "0001": "Freaks",
            "0002": "GBHDJ14",
            "0003": "Injury Inc",
            "0004": "Circle the Wagons",
            "0005": "Swamp Rabbits",
            "0006": "Mike's Misery",
            "0007": "Femmes",
            "0008": "The Mayor",
            "0009": "Taint Touchers",
            "0010": "FlatFootWorks",
            "0011": "The Whack Pack",
            "0012": "Dominators",
            "0013": "Fast & Ferocious",
            "0014": "Bubba Fell In The Creek",
            "0015": "Bang",
            "0016": "Politically Incorrect",
            "0017": "Polish Pounders",
        },
    )

    # Players map from fetch_week (ID -> {name, pos, team})
    players_map: Dict[str, Dict[str, Any]] = week_data.get("players_map") or week_data.get("players") or {}

    # Load salary file(s)
    salary_glob = cfg.get("inputs", {}).get("salary_glob", "data/salaries/2025_*_Salary.xlsx")
    salary_df = load_salary_file(salary_glob)

    # Starters by franchise (needed for performer ownership + value math)
    starters_by_f = _index_starters_by_franchise(week_data)

    # Compute value metrics
values_out = compute_values(
    salary_df=salary_df,
    players_map=players_map,
    starters_by_franchise=starters_by_f,
    franchise_names=f_map,
    week=week,
    year=year,
)

    # Build sections for template
    standings_rows = _build_standings_rows(week_data, f_map)
    team_efficiency = _build_team_efficiency(values_out, f_map)
    top_values, top_busts = _build_values_tables(values_out, players_map, f_map)
    top_performers = _build_top_performers(week_data, starters_by_f, players_map)

    # Pools (raw) for newsletter to summarize
    pools = week_data.get("pools") or {}
    pool_nfl = pools.get("nfl") or pools.get("confidence") or {}
    survivor_pool = pools.get("survivor") or pools.get("survivor_pool") or {}

    # Optional roasts from roastbook (safe default if missing)
    roasts = week_data.get("roasts") or {}

    # Assemble payload
    payload = {
        "title": cfg.get("newsletter", {}).get("title", "NPFFL Weekly Roast"),
        "week_label": wl,
        "timezone": tz,
        "standings_rows": standings_rows,
        "team_efficiency": team_efficiency,
        "top_performers": top_performers,
        "top_values": top_values,
        "top_busts": top_busts,
        "pool_nfl": pool_nfl,
        "survivor_pool": survivor_pool,
        "franchise_names": f_map,
        "roasts": roasts,
    }

    # Debug snapshot to inspect in artifacts if anything looks empty
    dbg_dir = out_dir / "debug"
    dbg_dir.mkdir(parents=True, exist_ok=True)
    (dbg_dir / "debug_context.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Render & write
    out = render_newsletter(payload, output_dir=out_dir, week=week)

    print(f"[out] Wrote: {out['md_path']}")
    print(f"[out] Wrote: {out['html_path']}")
    # Also list dir for the Actions log
    print(f"[out] Contents of {out_dir}/:")
    os.system(f"ls -lah {out_dir}")


if __name__ == "__main__":
    main()
