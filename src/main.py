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


def _cfg_get(cfg: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _int_or_none(s: str | None) -> int | None:
    if s is None:
        return None
    s = str(s).strip()
    if s == "":
        return None
    return int(s)


def _resolve_required_salaries_glob(cfg: Dict[str, Any]) -> str:
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

    msg = ["[salary] No salary files found.", "Looked for:"]
    msg.extend([f"  - {p}" for p in tried] if tried else ["  - (no patterns)"])
    msg.extend(["", "Set inputs.salary_glob in config.yaml or SALARY_GLOB env."])
    print("\n".join(msg), file=sys.stderr)
    sys.exit(2)


# ----------------------
# Standings helpers
# ----------------------

def _build_standings_rows(week_data: Dict[str, Any], f_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Prefer prebuilt rows from fetch_week (leagueStandings).
    Fallback to week-only PF from weeklyResults when needed.
    Supports:
      - weeklyResults.matchup[].franchise[]
      - weeklyResults.franchise[] (root-level)
    """
    rows = week_data.get("standings_rows")
    if isinstance(rows, list) and all(isinstance(r, dict) for r in rows) and rows:
        return rows

    rows = []
    wr = week_data.get("weekly_results") or {}
    wrn = wr.get("weeklyResults") if isinstance(wr, dict) else {}
    # A: matchup franchises
    matchups = (wrn or {}).get("matchup")
    if isinstance(matchups, dict):
        matchups = [matchups]
    if isinstance(matchups, list) and matchups:
        pf_map: Dict[str, float] = {}
        for m in matchups:
            franchises = m.get("franchise") or []
            if isinstance(franchises, dict):
                franchises = [franchises]
            for fr in franchises:
                fid = str(fr.get("id") or fr.get("franchise_id") or "").zfill(4)
                pts = _safe_float(fr.get("score") or fr.get("pf") or fr.get("points"), 0.0)
                pf_map[fid] = pf_map.get(fid, 0.0) + pts
        for fid, pf in pf_map.items():
            rows.append({"id": fid, "name": f_map.get(fid, f"Team {fid}"), "pf": pf, "vp": 0.0})

    # B: root-level weeklyResults.franchise[]
    if not rows:
        franchises = (wrn or {}).get("franchise") or []
        if isinstance(franchises, dict):
            franchises = [franchises]
        if isinstance(franchises, list) and franchises:
            for fr in franchises:
                fid = str(fr.get("id") or fr.get("franchise_id") or "").zfill(4)
                pf = _safe_float(fr.get("score") or fr.get("pf") or fr.get("points"), 0.0)
                rows.append({"id": fid, "name": f_map.get(fid, f"Team {fid}"), "pf": pf, "vp": 0.0})

    rows.sort(key=lambda r: (-_safe_float(r["pf"]), r["name"]))
    return rows


# ----------------------
# Starters extraction (now enriched from players_map)
# ----------------------

def _extract_starters_by_franchise(week_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Produce: { franchise_id: [ {player_id, player, pos, team, pts}, ... ] }

    Supports:
      - weeklyResults.matchup[].franchise[].players.player[] or .player[]
      - weeklyResults.matchup[].player[] (matchup-level)
      - weeklyResults.player[] (global)
      - weeklyResults.franchise[] (root-level) ← your Week 1 payload

    NEW: If weeklyResults lacks name/pos/team, we backfill from players_map.
    """
    out: Dict[str, List[Dict[str, Any]]] = {}
    wr = week_data.get("weekly_results") or {}
    wrn = wr.get("weeklyResults") if isinstance(wr, dict) else None
    if not isinstance(wrn, dict):
        return out

    # players_map for enrichment
    players_map: Dict[str, Dict[str, str]] = week_data.get("players_map") or {}

    def enrich(pid: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure name/pos/team exist by merging from players_map."""
        pm = players_map.get(pid, {})
        name = (meta.get("name") or pm.get("first_last") or pm.get("raw") or "").strip()
        pos = (meta.get("pos") or pm.get("pos") or "").strip()
        team = (meta.get("team") or pm.get("team") or None)
        return {
            "player_id": pid,
            "player": name,
            "pos": pos,
            "team": team,
            "pts": _safe_float(meta.get("pts"), 0.0),
        }

    # Global player table (rare)
    global_players = wrn.get("player") or []
    if isinstance(global_players, dict):
        global_players = [global_players]
    gp_idx: Dict[str, Dict[str, Any]] = {}
    for p in global_players:
        pid = str(p.get("id") or "").strip()
        if not pid:
            continue
        gp_idx[pid] = {
            "pts": _safe_float(p.get("score") or p.get("points") or 0.0),
            "name": str(p.get("name") or "").strip(),
            "pos": str(p.get("position") or p.get("pos") or "").strip(),
            "team": (str(p.get("team") or "").strip() or None),
        }

    # Path 1: matchup-based structure
    matchups = wrn.get("matchup") or []
    if isinstance(matchups, dict):
        matchups = [matchups]
    if isinstance(matchups, list) and matchups:
        for m in matchups:
            # matchup index
            match_players = m.get("player") or []
            if isinstance(match_players, dict):
                match_players = [match_players]
            mp_idx: Dict[str, Dict[str, Any]] = {}
            for p in match_players:
                pid = str(p.get("id") or "").strip()
                if not pid:
                    continue
                mp_idx[pid] = {
                    "pts": _safe_float(p.get("score") or p.get("points") or 0.0),
                    "name": str(p.get("name") or "").strip(),
                    "pos": str(p.get("position") or p.get("pos") or "").strip(),
                    "team": (str(p.get("team") or "").strip() or None),
                }

            franchises = m.get("franchise") or []
            if isinstance(franchises, dict):
                franchises = [franchises]
            for fr in franchises:
                fid = str(fr.get("id") or fr.get("franchise_id") or "").zfill(4)

                # franchise player index
                f_pl = fr.get("players") or fr.get("player") or []
                if isinstance(f_pl, dict):
                    f_pl = f_pl.get("player") or f_pl
                if isinstance(f_pl, dict):
                    f_pl = [f_pl]
                fp_idx: Dict[str, Dict[str, Any]] = {}
                for p in (f_pl or []):
                    pid = str(p.get("id") or "").strip()
                    if not pid:
                        continue
                    fp_idx[pid] = {
                        "pts": _safe_float(p.get("score") or p.get("points") or 0.0),
                        "name": str(p.get("name") or "").strip(),
                        "pos": str(p.get("position") or p.get("pos") or "").strip(),
                        "team": (str(p.get("team") or "").strip() or None),
                    }

                starters = fr.get("starters")
                rows: List[Dict[str, Any]] = []
                if isinstance(starters, str) and starters.strip():
                    for pid in [t.strip() for t in starters.split(",") if t.strip()]:
                        meta = fp_idx.get(pid) or mp_idx.get(pid) or gp_idx.get(pid) or {}
                        rows.append(enrich(pid, {
                            "pts": meta.get("pts"),
                            "name": meta.get("name"),
                            "pos": meta.get("pos"),
                            "team": meta.get("team"),
                        }))
                if not rows:
                    score = _safe_float(fr.get("score") or fr.get("pf") or fr.get("points") or 0.0)
                    rows.append({"player_id": "", "player": "Team Total", "pos": "", "team": None, "pts": score})

                out.setdefault(fid, []).extend(rows)

        return out

    # Path 2: root-level weeklyResults.franchise[]  ← Week 1 payload
    franchises = wrn.get("franchise") or []
    if isinstance(franchises, dict):
        franchises = [franchises]
    if isinstance(franchises, list) and franchises:
        for fr in franchises:
            fid = str(fr.get("id") or fr.get("franchise_id") or "").zfill(4)

            # franchise-level player index (id -> pts/name/pos/team if present)
            f_pl = fr.get("players") or fr.get("player") or []
            if isinstance(f_pl, dict):
                f_pl = f_pl.get("player") or f_pl
            if isinstance(f_pl, dict):
                f_pl = [f_pl]
            fp_idx: Dict[str, Dict[str, Any]] = {}
            for p in (f_pl or []):
                pid = str(p.get("id") or "").strip()
                if not pid:
                    continue
                fp_idx[pid] = {
                    "pts": _safe_float(p.get("score") or p.get("points") or 0.0),
                    "name": str(p.get("name") or "").strip(),   # usually missing
                    "pos": str(p.get("position") or p.get("pos") or "").strip(),
                    "team": (str(p.get("team") or "").strip() or None),
                }

            starters = fr.get("starters")
            rows: List[Dict[str, Any]] = []
            if isinstance(starters, str) and starters.strip():
                for pid in [t.strip() for t in starters.split(",") if t.strip()]:
                    meta = fp_idx.get(pid) or gp_idx.get(pid) or {}
                    rows.append(enrich(pid, {
                        "pts": meta.get("pts"),
                        "name": meta.get("name"),
                        "pos": meta.get("pos"),
                        "team": meta.get("team"),
                    }))
            if not rows:
                score = _safe_float(fr.get("score") or fr.get("pf") or fr.get("points") or 0.0)
                rows.append({"player_id": "", "player": "Team Total", "pos": "", "team": None, "pts": score})

            out.setdefault(fid, []).extend(rows)

    # simple visibility log
    total_rows = sum(len(v) for v in out.values())
    print(f"[starters] franchises={len(out)} rows={total_rows}")
    return out


# ----------------------
# CLI + Main
# ----------------------

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

    try:
        client = MFLClient(league_id=league_id, year=year, tz=tz)
    except TypeError:
        try:
            client = MFLClient(league_id=league_id, year=year, timezone=tz)
        except TypeError:
            client = MFLClient(league_id=league_id, year=year)
            setattr(client, "tz", tz)
            setattr(client, "timezone", tz)

    week_data: Dict[str, Any] = fetch_week_data(client, week=week) or {}

    f_names = _merge_franchise_names(
        week_data.get("franchise_names"),
        getattr(client, "franchise_names", None),
        cfg.get("franchise_names"),
    )

    standings_rows = _build_standings_rows(week_data, f_names)
    starters_by_franchise = _extract_starters_by_franchise(week_data)

    players_map = week_data.get("players_map") or week_data.get("players") or {}

    # Salaries are REQUIRED
    salary_glob = _resolve_required_salaries_glob(cfg)
    salaries_df = load_salary_file(salary_glob)

    # Compute values/busts/efficiency — this is the ordering that worked before
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

    # Log issues but don't hard-fail
    problems = []
    if not standings_rows:
        problems.append("standings_rows is empty (derived from weeklyResults if possible)")
    if not starters_by_franchise:
        problems.append("starters_by_franchise is empty (no weeklyResults starters parsed)")
    if not (top_values or top_busts or team_efficiency):
        problems.append("no value metrics (likely starters/salaries mismatch)")
    if problems:
        print("[sanity] Week", week, "notes:")
        for p in problems:
            print(" -", p)
        wk_keys = sorted((week_data or {}).keys())
        print("[sanity] week_data keys:", wk_keys)
        print("[sanity] proceeding to write outputs anyway for debugging…")

    try:
        (out_dir / f"context_week_{_week_label(week)}.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
    except Exception:
        pass

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
