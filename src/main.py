from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from .mfl_client import MFLClient
from .fetch_week import fetch_week_data
from .load_salary import load_salary_file
from .value_engine import compute_values
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
    rows: List[Dict[str, Any]] = []

    st = week_data.get("standings")
    if isinstance(st, list) and st and all(isinstance(r, dict) for r in st):
        for r in st:
            fid = str(r.get("id") or r.get("franchise_id") or r.get("fid") or "").zfill(4)
            rows.append({
                "id": fid,
                "name": f_map.get(fid, r.get("name") or f"Team {fid}"),
                "pf": _safe_float(r.get("pf") or r.get("points_for") or r.get("points") or 0),
                "vp": _safe_float(r.get("vp") or r.get("victory_points") or 0),
            })
    elif isinstance(st, dict) and "franchises" in st:
        for r in st["franchises"] or []:
            fid = str(r.get("id") or r.get("franchise_id") or "").zfill(4)
            rows.append({
                "id": fid,
                "name": f_map.get(fid, r.get("name") or f"Team {fid}"),
                "pf": _safe_float(r.get("pf") or r.get("points_for") or r.get("points") or 0),
                "vp": _safe_float(r.get("vp") or r.get("victory_points") or 0),
            })

    if not rows:
        pf_map: Dict[str, float] = {}
        wr = week_data.get("weekly_results") or {}
        matchups = wr.get("matchups") if isinstance(wr, dict) else wr
        matchups = matchups or []
        for m in matchups:
            for side_key in ("home", "away", "franchise", "franchises"):
                side = m.get(side_key)
                if not side:
                    continue
                side_list = side if isinstance(side, list) else [side]
                for s in side_list:
                    fid = str(s.get("id") or s.get("franchise_id") or "").zfill(4)
                    pts = _safe_float(s.get("score") or s.get("points") or 0)
                    pf_map[fid] = pf_map.get(fid, 0.0) + pts
        for fid, pf in pf_map.items():
            rows.append({"id": fid, "name": f_map.get(fid, f"Team {fid}"), "pf": pf, "vp": 0.0})

    rows.sort(key=lambda r: (-_safe_float(r["pf"]), r["name"]))
    return rows


# ----------------------
# Starters extraction for value engine
# ----------------------

def _extract_starters_by_franchise(week_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = {}
    wr = week_data.get("weekly_results") or {}
    matchups = wr.get("matchups") if isinstance(wr, dict) else wr
    matchups = matchups or []

    def _add(fid: str, row: Dict[str, Any]) -> None:
        if not fid:
            return
        result.setdefault(fid, []).append(row)

    for m in matchups:
        for side_key in ("home", "away", "franchise", "franchises"):
            side = m.get(side_key)
            if not side:
                continue
            side_list = side if isinstance(side, list) else [side]
            for s in side_list:
                fid = str(s.get("id") or s.get("franchise_id") or "").zfill(4)
                starters = s.get("starters") or s.get("players") or []
                if isinstance(starters, dict) and "player" in starters:
                    starters = starters["player"]
                if isinstance(starters, list):
                    for p in starters:
                        row = {
                            "player_id": str(p.get("id") or p.get("player_id") or p.get("pid") or "").strip(),
                            "player": str(p.get("name") or p.get("player") or p.get("Player") or "").strip(),
                            "pos": str(p.get("position") or p.get("pos") or "").strip(),
                            "team": (str(p.get("nfl_team") or p.get("team") or p.get("Team") or "").strip() or None),
                            "pts": _safe_float(p.get("points") or p.get("score") or p.get("Pts"), 0.0),
                        }
                        _add(fid, row)
                else:
                    score = _safe_float(s.get("score") or s.get("points") or 0.0)
                    _add(fid, {"player_id": "", "player": "Team Total", "pos": "", "team": None, "pts": score})

    return result


# ----------------------
# CLI + Main
# ----------------------

def _int_or_none(s: str | None) -> int | None:
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    return int(s)


def _cfg_get(cfg: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _resolve_required_salaries_glob(cfg: Dict[str, Any]) -> str:
    """
    Resolve a salary file glob that matches at least one file.
    Prefers config inputs.salary_glob, then top-level keys, then sensible defaults.
    """
    candidates: List[str] = []
    # config: nested first (your config.yaml uses this)
    v = _cfg_get(cfg, "inputs.salary_glob")
    if v:
        candidates.append(str(v))
    # config: top-level variants
    for k in ("salaries_path", "salaries_file", "salary_file"):
        v = cfg.get(k)
        if v:
            candidates.append(str(v))
    # env override (optional)
    env_glob = os.environ.get("SALARY_GLOB")
    if env_glob:
        candidates.append(env_glob)
    # sensible defaults
    candidates.extend(["data/salaries/*.xlsx", "salaries/*.xlsx"])

    tried: List[str] = []
    for pat in candidates:
        pat = str(pat).strip()
        if not pat:
            continue
        tried.append(pat)
        if glob.glob(pat):
            return pat

    msg = [
        "[salary] No salary files found.",
        "Looked for a file or glob in the following locations:",
    ]
    if tried:
        msg.extend([f"  - {p}" for p in tried])
    else:
        msg.append("  - (no patterns to try)")
    msg.extend([
        "",
        "Set inputs.salary_glob in config.yaml (e.g., data/salaries/2025_*_Salary.xlsx),",
        "or set SALARY_GLOB env, or define salaries_path/salaries_file/salary_file.",
    ])
    print("\n".join(msg), file=sys.stderr)
    sys.exit(2)


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

    # Output dir: prefer config override if present
    cfg_out_dir = _cfg_get(cfg, "outputs.dir")
    out_dir = Path(cfg_out_dir or args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Instantiate client (tolerate older/newer ctor signatures)
    try:
        client = MFLClient(league_id=league_id, year=year, tz=tz)
    except TypeError:
        try:
            client = MFLClient(league_id=league_id, year=year, timezone=tz)
        except TypeError:
            client = MFLClient(league_id=league_id, year=year)
            setattr(client, "tz", tz)
            setattr(client, "timezone", tz)

    # Fetch all week data
    week_data: Dict[str, Any] = fetch_week_data(client, week=week) or {}

    # Franchise names
    f_names = _merge_franchise_names(
        week_data.get("franchise_names"),
        getattr(client, "franchise_names", None),
        cfg.get("franchise_names"),
    )

    # Standings + starters
    standings_rows = _build_standings_rows(week_data, f_names)
    starters_by_franchise = _extract_starters_by_franchise(week_data)

    # Players map for value engine (from fetch_week)
    players_map = week_data.get("players_map") or week_data.get("players") or {}

    # REQUIRED salaries
    salary_glob = _resolve_required_salaries_glob(cfg)
    salaries_df = load_salary_file(salary_glob)

    # ---- Call value engine with your repo's expected ordering ----
    #   compute_values(salary_df, players_map, starters_by_franchise, franchise_names, week=None, year=None)
    values_out: Dict[str, Any] = compute_values(
        salaries_df,
        players_map,
        starters_by_franchise,
        f_names,
        week=week,
        year=year,
    )

    top_values = values_out.get("top_values", [])
    top_busts = values_out.get("top_busts", [])
    team_efficiency = values_out.get("team_efficiency", [])

    # Optional pools/lines (if present in week_data)
    pool_nfl = week_data.get("pool_nfl") or {}
    survivor_pool = week_data.get("survivor_pool") or {}
    lines = week_data.get("lines") or week_data.get("odds") or []

    payload: Dict[str, Any] = {
        "title": _cfg_get(cfg, "newsletter.title") or cfg.get("title") or "NPFFL Weekly Roast",
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
        "roasts": [],
    }

    # Debug dump to help with template issues
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

    # Ensure CI has something to upload
    if isinstance(outputs, (list, tuple)) and outputs:
        for p in outputs:
            print(f"Wrote: {p}")
        return tuple(Path(p) for p in outputs)  # type: ignore[return-value]
    else:
        stub_md = out_dir / f"week_{_week_label(week)}.md"
        stub_md.write_text("# Newsletter\n\n_No content produced._\n", encoding="utf-8")
        print(f"Wrote: {stub_md}")
        return (stub_md,)


if __name__ == "__main__":
    main()
