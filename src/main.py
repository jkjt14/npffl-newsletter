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
    """
    Prefer a pre-normalized table from fetch_week (standings_rows).
    Otherwise, try to build from a few known shapes.
    """
    # 0) If fetch_week already supplied normalized rows, use them verbatim.
    rows = week_data.get("standings_rows")
    if isinstance(rows, list) and rows and all(isinstance(r, dict) for r in rows):
        return rows

    # 1) try a generic 'standings' node with common fields
    rows = []
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

    # 2) Fallback: synthesize PF from weekly_results (various shapes)
    if not rows:
        pf_map: Dict[str, float] = {}
        wr = week_data.get("weekly_results") or {}
        # (a) already flattened: {'matchups': [...]}
        matchups = wr.get("matchups") if isinstance(wr, dict) else None

        # (b) common MFL: {'weeklyResults': {'matchup': [...]}}
        if not matchups and isinstance(wr, dict) and "weeklyResults" in wr:
            wrn = wr.get("weeklyResults") or {}
            matchups = wrn.get("matchup")

        # normalize to list
        if isinstance(matchups, dict):
            matchups = [matchups]
        if not isinstance(matchups, list):
            matchups = []

        for m in matchups:
            # MFL shape: m['franchise'] may be a list or single dict
            franchises = m.get("franchise") or []
            if isinstance(franchises, dict):
                franchises = [franchises]
            for s in franchises:
                fid = str(s.get("id") or s.get("franchise_id") or "").zfill(4)
                pts = _safe_float(s.get("score") or s.get("pf") or s.get("points"), 0.0)
                pf_map[fid] = pf_map.get(fid, 0.0) + pts

        for fid, pf in pf_map.items():
            rows.append({"id": fid, "name": f_map.get(fid, f"Team {fid}"), "pf": pf, "vp": 0.0})

    rows.sort(key=lambda r: (-_safe_float(r["pf"]), r["name"]))
    return rows


# ----------------------
# Starters extraction for value engine
# ----------------------

def _extract_starters_by_franchise(week_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Produce: { franchise_id: [ {player_id, player, pos, team, pts}, ... ] }
    Handles several MFL shapes:
      - {'matchups': [ { 'home':{...}, 'away':{...} }, ... ]}   (custom flatten)
      - {'weeklyResults': { 'matchup': [ { 'franchise':[ {...}, {...} ] }, ... ] } }
      - fallback to team totals if no per-player breakdown found
    """
    result: Dict[str, List[Dict[str, Any]]] = {}
    wr = week_data.get("weekly_results") or {}

    # Variant A: already flattened to {'matchups': [...]}
    matchups = wr.get("matchups") if isinstance(wr, dict) else None

    # Variant B: MFL canonical: {'weeklyResults': {'matchup': [...]}}
    if not matchups and isinstance(wr, dict) and "weeklyResults" in wr:
        wrn = wr.get("weeklyResults") or {}
        matchups = wrn.get("matchup")

    # normalize matchups to a list
    if isinstance(matchups, dict):
        matchups = [matchups]
    if not isinstance(matchups, list):
        matchups = []

    def _add(fid: str, row: Dict[str, Any]) -> None:
        if not fid:
            return
        result.setdefault(fid, []).append(row)

    for m in matchups:
        # Common MFL: a list of two franchise dicts per matchup
        franchises = m.get("franchise") or []
        if isinstance(franchises, dict):
            franchises = [franchises]

        if franchises:
            for fr in franchises:
                fid = str(fr.get("id") or fr.get("franchise_id") or "").zfill(4)

                # Try rich per-player structures first
                # Some shards embed {'players': {'player': [ {id, score, name?, position?, team?}, ... ]}}
                players = fr.get("players") or {}
                if isinstance(players, dict):
                    pl = players.get("player") or []
                    if isinstance(pl, dict):
                        pl = [pl]
                else:
                    pl = []

                if pl:
                    for p in pl:
                        row = {
                            "player_id": str(p.get("id") or p.get("player_id") or "").strip(),
                            "player": str(p.get("name") or "").strip(),
                            "pos": str(p.get("position") or p.get("pos") or "").strip(),
                            "team": (str(p.get("team") or "").strip() or None),
                            "pts": _safe_float(p.get("score") or p.get("points"), 0.0),
                        }
                        _add(fid, row)
                    continue  # done with this franchise, next

                # Next: some exports provide a comma-separated starters string, with
                # per-player points in a sibling 'player' list or not at all.
                starters = fr.get("starters")
                pl2 = fr.get("player") or []
                if isinstance(pl2, dict):
                    pl2 = [pl2]
                points_by_id: Dict[str, float] = {}
                meta_by_id: Dict[str, Dict[str, Any]] = {}
                for p in pl2:
                    pid = str(p.get("id") or "").strip()
                    if pid:
                        points_by_id[pid] = _safe_float(p.get("score") or p.get("points"), 0.0)
                        meta_by_id[pid] = {
                            "name": str(p.get("name") or "").strip(),
                            "pos": str(p.get("position") or p.get("pos") or "").strip(),
                            "team": (str(p.get("team") or "").strip() or None),
                        }
                if isinstance(starters, str) and starters.strip():
                    for pid in [t for t in starters.split(",") if t]:
                        pid = pid.strip()
                        meta = meta_by_id.get(pid, {})
                        row = {
                            "player_id": pid,
                            "player": str(meta.get("name") or "").strip(),
                            "pos": str(meta.get("pos") or "").strip(),
                            "team": meta.get("team"),
                            "pts": points_by_id.get(pid, 0.0),
                        }
                        _add(fid, row)
                    if result.get(fid):
                        continue  # we got something

                # Last fallback: at least capture team total so downstream can compute something
                score = _safe_float(fr.get("score") or fr.get("pf") or fr.get("points") or 0.0)
                _add(fid, {"player_id": "", "player": "Team Total", "pos": "", "team": None, "pts": score})

        else:
            # Alternate shapes (e.g., 'home'/'away' dicts already flattened)
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

                    if isinstance(starters, list) and starters:
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

    v = _cfg_get(cfg, "inputs.salary_glob")
    if v:
        candidates.append(str(v))

    for k in ("salaries_path", "salaries_file", "salary_file"):
        v = cfg.get(k)
        if v:
            candidates.append(str(v))

    env_glob = os.environ.get("SALARY_GLOB")
    if env_glob:
        candidates.append(env_glob)

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
    ap.add_argument("--week", type=_int_or_none, default=None)
    ap.add_argument("--out-dir", default=os.environ.get("NPFFL_OUTDIR", "build"))
    return ap.parse_args()


def main() -> Tuple[Path, Path] | Tuple[Path] | Tuple[()]:
    args = _parse_args()
    cfg = _read_config(args.config)

    league_id = str(cfg.get("league_id") or os.environ.get("MFL_LEAGUE_ID") or "").strip()
    year = int(cfg.get("year") or os.environ.get("MFL_YEAR") or 2025)
    tz = cfg.get("timezone") or cfg.get("tz") or "America/New_York"
    week = args.week if args.week is not None else int(cfg.get("week") or 1)

    cfg_out_dir = _cfg_get(cfg, "outputs.dir")
    out_dir = Path(cfg_out_dir or args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # MFL client ctor tolerance
    try:
        client = MFLClient(league_id=league_id, year=year, tz=tz)
    except TypeError:
        try:
            client = MFLClient(league_id=league_id, year=year, timezone=tz)
        except TypeError:
            client = MFLClient(league_id=league_id, year=year)
            setattr(client, "tz", tz)
            setattr(client, "timezone", tz)

    # Pull week data
    week_data: Dict[str, Any] = fetch_week_data(client, week=week) or {}

    # Franchise names
    f_names = _merge_franchise_names(
        week_data.get("franchise_names"),
        getattr(client, "franchise_names", None),
        cfg.get("franchise_names"),
    )

    # Standings + starters (robust to your current fetch_week shapes)
    standings_rows = _build_standings_rows(week_data, f_names)
    starters_by_franchise = _extract_starters_by_franchise(week_data)

    # Players map (for salary match)
    players_map = week_data.get("players_map") or week_data.get("players") or {}

    # Salaries (required)
    salary_glob = _resolve_required_salaries_glob(cfg)
    salaries_df = load_salary_file(salary_glob)

    # Value engine — your repo's signature:
    # compute_values(salary_df, players_map, starters_by_franchise, franchise_names, week=None, year=None)
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

    # Optional pools/lines
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

    # --- sanity checks (fail fast if there's no data) ---
    problems = []
    if not standings_rows:
        problems.append("standings_rows is empty (no standings/boxscores found)")
    if not starters_by_franchise:
        problems.append("starters_by_franchise is empty (no weekly_results/boxscores found)")
    if not (top_values or top_busts or team_efficiency):
        problems.append("no value metrics (likely because starters or salaries didn’t join)")

    if problems:
        print("[sanity] Week", week, "had issues:")
        for p in problems:
            print(" -", p)
        wk_keys = sorted((week_data or {}).keys())
        print("[sanity] week_data keys:", wk_keys)
        # hard stop to avoid producing empty artifacts
        raise SystemExit(3)

    # Debug dump
    try:
        (out_dir / f"context_week_{_week_label(week)}.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
    except Exception:
        pass

    # Render newsletter
    outputs_dict = render_newsletter(payload, output_dir=str(out_dir), week=week)

    md_path = outputs_dict.get("md_path")
    html_path = outputs_dict.get("html_path")
    paths: List[Path] = []
    if md_path:
        print(f"Wrote: {md_path}")
        paths.append(Path(md_path))
    if html_path:
        print(f"Wrote: {html_path}")
        paths.append(Path(html_path))

    if paths:
        return tuple(paths)  # type: ignore[return-value]

    stub_md = out_dir / f"week_{_week_label(week)}.md"
    stub_md.write_text("# Newsletter\n\n_No content produced._\n", encoding="utf-8")
    print(f"Wrote: {stub_md}")
    return (stub_md,)


if __name__ == "__main__":
    main()
