from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from .mfl_client import MFLClient
from .fetch_week import fetch_week_data           # returns a dict of week data
from .load_salary import load_salary_file         # returns a pandas DataFrame (or empty)
from .value_engine import compute_values          # returns dict: top_values, top_busts, team_efficiency, starters_with_salary
from .newsletter import render_newsletter


# ----------------------
# Utilities
# ----------------------

def _read_config(path: str | Path = "config.yaml") -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _week_label(week: int | None) -> str:
    return f"{int(week):02d}" if week is not None else "01"


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _merge_franchise_names(*maps: Dict[str, str] | None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for mp in maps:
        if not mp:
            continue
        for k, v in mp.items():
            if k is None:
                continue
            out[str(k).zfill(4)] = str(v)
    return out


# ----------------------
# Standings helpers
# ----------------------

def _build_standings_rows(week_data: Dict[str, Any], f_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Normalize standings to rows: {id, name, pf, vp}
    Accepts multiple source shapes from fetch_week payloads.
    """
    rows: List[Dict[str, Any]] = []

    # Shape A: week_data["standings"] already normalized
    st = week_data.get("standings")
    if isinstance(st, list) and st and all(isinstance(r, dict) for r in st):
        # Try to coerce keys
        for r in st:
            fid = str(r.get("id") or r.get("franchise_id") or r.get("fid") or "").zfill(4)
            rows.append({
                "id": fid,
                "name": f_map.get(fid, r.get("name") or f"Team {fid}"),
                "pf": _safe_float(r.get("pf") or r.get("points_for") or r.get("points") or 0),
                "vp": _safe_float(r.get("vp") or r.get("victory_points") or 0),
            })

    # Shape B: standings like {"franchises":[{"id": "...", "pf":..., "vp":...}, ...]}
    elif isinstance(st, dict) and "franchises" in st:
        for r in st["franchises"] or []:
            fid = str(r.get("id") or r.get("franchise_id") or "").zfill(4)
            rows.append({
                "id": fid,
                "name": f_map.get(fid, r.get("name") or f"Team {fid}"),
                "pf": _safe_float(r.get("pf") or r.get("points_for") or r.get("points") or 0),
                "vp": _safe_float(r.get("vp") or r.get("victory_points") or 0),
            })

    # Fallback: synthesize PF from weekly_results boxscores
    if not rows:
        pf_map: Dict[str, float] = {}
        wr = week_data.get("weekly_results") or {}
        # tolerate shapes: {"matchups": [...] } or already flattened
        matchups = wr.get("matchups") if isinstance(wr, dict) else wr
        matchups = matchups or []
        for m in matchups:
            for side_key in ("home", "away", "franchise", "franchises"):
                side = m.get(side_key)
                if not side:
                    continue
                # side may be list or single dict
                if isinstance(side, list):
                    side_list = side
                else:
                    side_list = [side]
                for s in side_list:
                    fid = str(s.get("id") or s.get("franchise_id") or "").zfill(4)
                    pts = _safe_float(s.get("score") or s.get("points") or 0)
                    pf_map[fid] = pf_map.get(fid, 0.0) + pts

        for fid, pf in pf_map.items():
            rows.append({
                "id": fid,
                "name": f_map.get(fid, f"Team {fid}"),
                "pf": pf,
                "vp": 0.0,
            })

    # Stable order by PF desc, then name
    rows.sort(key=lambda r: (-_safe_float(r["pf"]), r["name"]))
    return rows


# ----------------------
# Starters extraction for value engine
# ----------------------

def _extract_starters_by_franchise(week_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Produce: { franchise_id: [ {player_id, player, pos, team, pts}, ... ] }
    Tolerates multiple shapes from fetch_week payloads.
    """
    result: Dict[str, List[Dict[str, Any]]] = {}
    wr = week_data.get("weekly_results") or {}
    matchups = wr.get("matchups") if isinstance(wr, dict) else wr
    matchups = matchups or []

    def _add(fid: str, row: Dict[str, Any]) -> None:
        if not fid:
            return
        result.setdefault(fid, []).append(row)

    for m in matchups:
        # try typical MFL shapes
        for side_key in ("home", "away", "franchise", "franchises"):
            side = m.get(side_key)
            if not side:
                continue
            side_list = side if isinstance(side, list) else [side]
            for s in side_list:
                fid = str(s.get("id") or s.get("franchise_id") or "").zfill(4)

                starters = s.get("starters") or s.get("players") or []
                # starters sometimes a list of dicts {id,name,pos,nfl_team,points}
                # or {"player":[{...}, ...]}
                if isinstance(starters, dict) and "player" in starters:
                    starters = starters["player"]

                if isinstance(starters, list):
                    for p in starters:
                        # tolerate both snake/camel, string/float
                        _pid = p.get("id") or p.get("player_id") or p.get("pid")
                        _name = p.get("name") or p.get("player") or p.get("Player")
                        _pos = p.get("position") or p.get("pos")
                        _team = p.get("nfl_team") or p.get("team") or p.get("Team")
                        _pts = p.get("points") or p.get("score") or p.get("Pts")

                        row = {
                            "player_id": str(_pid or "").strip(),
                            "player": str(_name or "").strip(),
                            "pos": str(_pos or "").strip(),
                            "team": (str(_team or "").strip() or None),
                            "pts": _safe_float(_pts, 0.0),
                        }
                        _add(fid, row)
                else:
                    # if no starters shape, at least put QB/placeholder so value engine has something
                    score = _safe_float(s.get("score") or s.get("points") or 0.0)
                    _add(fid, {"player_id": "", "player": "Team Total", "pos": "", "team": None, "pts": score})

    return result


# ----------------------
# CLI + Main
# ----------------------

def _int_or_none(s: str | None) -> int | None:
    """Convert '', '  ', None -> None; otherwise int(s)."""
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    return int(s)

def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="NPFFL Weekly Roast generator")
    ap.add_argument("--config", default=os.environ.get("NPFFL_CONFIG", "config.yaml"))
    ap.add_argument("--week", type=_int_or_none, default=None)  # tolerant of empty string
    ap.add_argument("--out-dir", default=os.environ.get("NPFFL_OUTDIR", "build"))
    ap.add_argument("--make-html", action="store_true", default=True)
    return ap.parse_args()


def main() -> Tuple[Path, Path] | Tuple[Path] | Tuple[()]:
    args = _parse_args()
    cfg = _read_config(args.config)

    league_id = str(cfg.get("league_id") or os.environ.get("MFL_LEAGUE_ID") or "").strip()
    year = int(cfg.get("year") or os.environ.get("MFL_YEAR") or 2025)
    tz = cfg.get("timezone") or cfg.get("tz") or "America/New_York"
    week = args.week if args.week is not None else int(cfg.get("week") or 1)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Instantiate client
# Instantiate client (tolerate different constructor signatures)
try:
    client = MFLClient(league_id=league_id, year=year, tz=tz)
except TypeError:
    try:
        client = MFLClient(league_id=league_id, year=year, timezone=tz)
    except TypeError:
        client = MFLClient(league_id=league_id, year=year)
        # expose tz on the instance for any downstream code that expects it
        setattr(client, "tz", tz)
        setattr(client, "timezone", tz)


    # Pull everything for the requested week
    week_data: Dict[str, Any] = fetch_week_data(client, week=week) or {}

    # Franchise names, from any source we can get
    f_names = _merge_franchise_names(
        week_data.get("franchise_names"),
        getattr(client, "franchise_names", None),
        cfg.get("franchise_names"),
    )

    # Standings table
    standings_rows = _build_standings_rows(week_data, f_names)

    # Starters by franchise for the value engine
    starters_by_franchise = _extract_starters_by_franchise(week_data)

    # Load salaries (path from config if provided)
    salaries_path = cfg.get("salaries_path") or cfg.get("salaries_file") or cfg.get("salary_file")
    salaries_df = load_salary_file(salaries_path) if salaries_path else load_salary_file(None)

    # Compute value metrics, try multiple signatures defensively
    values_out: Dict[str, Any] = {}
    try:
        values_out = compute_values(starters_by_franchise, salaries_df, f_names)
    except TypeError:
        try:
            values_out = compute_values(starters_by_franchise, salaries_df)
        except TypeError:
            values_out = compute_values(starters_by_franchise)  # last resort

    top_values = values_out.get("top_values", [])
    top_busts = values_out.get("top_busts", [])
    team_efficiency = values_out.get("team_efficiency", [])

    # Pools (optional)
    pool_nfl = week_data.get("pool_nfl") or {}
    survivor_pool = week_data.get("survivor_pool") or {}

    # Lines (optional – from odds API integration if present in week_data)
    lines = week_data.get("lines") or week_data.get("odds") or []

    payload: Dict[str, Any] = {
        "title": cfg.get("title") or "NPFFL Weekly Roast",
        "week_label": _week_label(week),
        "timezone": tz,
        "year": year,
        "league_id": league_id,
        "franchise_names": f_names,
        "standings_rows": standings_rows,
        "team_efficiency": team_efficiency,
        "top_values": top_values,
        "top_busts": top_busts,
        "pool_nfl": pool_nfl,
        "survivor_pool": survivor_pool,
        "lines": lines,
        # Leave roasts empty unless you have a generator
        "roasts": [],
    }

    # Debug dump to help with template issues (non-fatal)
    try:
        (out_dir / f"context_week_{_week_label(week)}.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
    except Exception:
        pass

    # Render newsletter
    templates_dir = str(Path(__file__).parent / "templates")
    outputs = render_newsletter(
        payload,
        templates_dir=templates_dir,
        out_dir=str(out_dir),
        make_html=bool(args.make_html),
    )

    # Ensure CI has something to upload even in degenerate cases
    if isinstance(outputs, (list, tuple)) and outputs:
        for p in outputs:
            print(f"Wrote: {p}")
        return tuple(Path(p) for p in outputs)  # type: ignore[return-value]
    else:
        # write a minimal stub file
        stub_md = out_dir / f"week_{_week_label(week)}.md"
        stub_md.write_text("# Newsletter\n\n_No content produced._\n", encoding="utf-8")
        print(f"Wrote: {stub_md}")
        return (stub_md,)


if __name__ == "__main__":
    main()
