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
# Derivers for extra sections
# ----------------------

def _derive_weekly_scores(week_data: Dict[str, Any], f_map: Dict[str, str]) -> Dict[str, Any]:
    """Return {'rows': [(name, score)], 'min': .., 'max': .., 'avg': ..} from weeklyResults.franchise[]."""
    out_rows: List[Tuple[str, float]] = []
    wr = week_data.get("weekly_results") or {}
    node = wr.get("weeklyResults") if isinstance(wr, dict) else {}
    franchises = (node or {}).get("franchise") or []
    if isinstance(franchises, dict):
        franchises = [franchises]
    for fr in (franchises or []):
        fid = str(fr.get("id") or "").zfill(4)
        name = f_map.get(fid, f"Team {fid}")
        score = _safe_float(fr.get("score"), 0.0)
        out_rows.append((name, score))
    if not out_rows:
        return {"rows": [], "min": None, "max": None, "avg": None}

    scores = [s for _, s in out_rows]
    mn, mx = min(scores), max(scores)
    avg = round(sum(scores) / len(scores), 2)
    out_rows.sort(key=lambda t: -t[1])
    return {"rows": out_rows, "min": mn, "max": mx, "avg": avg}


def _derive_vp_drama(standings_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Figure out the 2.5 VP cut line drama (last-in vs first-out) if your league tiers are 5/2.5/0."""
    if not standings_rows:
        return {}
    # Sort by VP desc, then PF desc (how your table comes in)
    rows = sorted(standings_rows, key=lambda r: (-_safe_float(r.get("vp")), -_safe_float(r.get("pf"))))
    # Find boundary between mid-tier (2.5) and bottom (0)
    mids = [r for r in rows if _safe_float(r.get("vp")) == 2.5]
    lows = [r for r in rows if _safe_float(r.get("vp")) == 0.0]
    if not mids or not lows:
        return {}
    last_in = mids[-1]
    first_out = lows[0]
    gap = round(_safe_float(last_in["pf"]) - _safe_float(first_out["pf"]), 2)
    return {"villain": last_in["name"], "bubble": first_out["name"], "gap_pf": gap}


def _derive_headliners(starters_by_franchise: Dict[str, List[Dict[str, Any]]],
                       players_map: Dict[str, Dict[str, Any]],
                       f_map: Dict[str, str],
                       top_n: int = 10) -> List[Dict[str, Any]]:
    """
    Aggregate best player scores across the league: who scored, how much, and who rostered them.
    Uses starters_by_franchise plus players_map for names/pos/team.
    """
    use_map: Dict[str, Dict[str, Any]] = {}
    for fid, rows in (starters_by_franchise or {}).items():
        manager = f_map.get(fid, f"Team {fid}")
        for r in rows:
            pid = str(r.get("player_id") or "").strip()
            if not pid:
                continue
            pts = _safe_float(r.get("pts"), 0.0)
            meta = players_map.get(pid, {})
            name = (r.get("player") or meta.get("first_last") or meta.get("raw") or pid).strip()
            pos = (r.get("pos") or meta.get("pos") or "").strip()
            team = (r.get("team") or meta.get("team") or "").strip()
            bucket = use_map.setdefault(pid, {"pid": pid, "name": name, "pos": pos, "team": team, "pts": pts, "managers": set()})
            bucket["pts"] = max(bucket["pts"], pts)  # same player may appear on multiple teams; keep top score
            bucket["managers"].add(manager)
    rows = []
    for v in use_map.values():
        rows.append({
            "player": v["name"],
            "pos": v["pos"],
            "team": v["team"],
            "pts": v["pts"],
            "managers": sorted(v["managers"]),
        })
    rows.sort(key=lambda x: -x["pts"])
    return rows[:top_n]


def _derive_confidence_top3(pool_nfl: Dict[str, Any], f_map: Dict[str, str], week: int) -> List[Dict[str, Any]]:
    """
    For each franchise: pull the top-3 confidence picks (highest rank) for the given week.
    """
    picks = []
    node = (pool_nfl or {}).get("poolPicks") or {}
    franchises = node.get("franchise") or []
    if isinstance(franchises, dict):
        franchises = [franchises]
    for fr in franchises:
        fid = str(fr.get("id") or "").zfill(4)
        name = f_map.get(fid, f"Team {fid}")
        week_blocks = fr.get("week") or []
        if isinstance(week_blocks, dict):
            week_blocks = [week_blocks]
        target = None
        for w in week_blocks:
            if str(w.get("week") or "") == str(week):
                target = w
                break
        if not target:
            continue
        games = target.get("game") or []
        if isinstance(games, dict):
            games = [games]
        rows = []
        for g in games:
            try:
                rank = int(str(g.get("rank") or "0"))
            except Exception:
                rank = 0
            rows.append({"rank": rank, "pick": str(g.get("pick") or "").strip(), "matchup": str(g.get("matchup") or "").strip()})
        rows.sort(key=lambda r: -r["rank"])
        top3 = rows[:3]
        if top3:
            picks.append({"team": name, "top3": top3})
    return picks


def _derive_survivor_picks(survivor_pool: Dict[str, Any], f_map: Dict[str, str], week: int) -> List[Dict[str, Any]]:
    """
    Best-effort survivor list: franchise->pick for the week, if present.
    (Your artifacts sometimes omit survivor; this will just return [].)
    """
    node = (survivor_pool or {}).get("survivorPool") or survivor_pool or {}
    franchises = node.get("franchise") or []
    if isinstance(franchises, dict):
        franchises = [franchises]
    out = []
    for fr in franchises:
        fid = str(fr.get("id") or "").zfill(4)
        name = f_map.get(fid, f"Team {fid}")
        week_blocks = fr.get("week") or []
        if isinstance(week_blocks, dict):
            week_blocks = [week_blocks]
        pick = ""
        for w in week_blocks:
            if str(w.get("week") or "") == str(week):
                pick = str(w.get("pick") or "").strip()
                break
        if pick:
            out.append({"team": name, "pick": pick})
    return out


def _compose_opening_blurb(scores_info: Dict[str, Any]) -> str:
    rows = scores_info.get("rows") or []
    if not rows:
        return ""
    top = rows[0]
    bottom = rows[-1]
    return (f"{top[0]} blasted off with {top[1]:.2f}, "
            f"while {bottom[0]} brought up the rear with {bottom[1]:.2f}. "
            "Some of you built rocket ships; others built IKEA furniture without the instructions.")


# ----------------------
# Standings + Starters helpers
# ----------------------

def _build_standings_rows(week_data: Dict[str, Any], f_map: Dict[str, str]) -> List[Dict[str, Any]]:
    rows = week_data.get("standings_rows")
    if isinstance(rows, list) and all(isinstance(r, dict) for r in rows) and rows:
        return rows

    rows = []
    wr = week_data.get("weekly_results") or {}
    wrn = wr.get("weeklyResults") if isinstance(wr, dict) else {}
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

    if not rows:
        franchises = (wrn or {}).get("franchise") or []
        if isinstance(franchises, dict):
            franchises = [franchises]
        if isinstance(franchises, list) and franchises:
            for fr in franchises:
                fid = str(fr.get("id") or fr.get("franchise_id") or "").zfill(4)
                pf = _safe_float(fr.get("score") or fr.get("pf") or fr.get("points"), 0.0)
                rows.append({"id": fid, "name": f_map.get(fid, f"Team {fid}"), "pf": pf, "vp": 0.0})

    rows.sort(key=lambda r: (-_safe_float(r["vp"]), -_safe_float(r["pf"]), r["name"]))
    return rows


def _extract_starters_by_franchise(week_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    wr = week_data.get("weekly_results") or {}
    wrn = wr.get("weeklyResults") if isinstance(wr, dict) else None
    if not isinstance(wrn, dict):
        return out

    players_map: Dict[str, Dict[str, Any]] = week_data.get("players_map") or {}

    def enrich(pid: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        pm = players_map.get(pid, {})
        name = (meta.get("name") or pm.get("first_last") or pm.get("raw") or "").strip()
        pos = (meta.get("pos") or pm.get("pos") or "").strip()
        team = (meta.get("team") or pm.get("team") or None)
        return {"player_id": pid, "player": name, "pos": pos, "team": team, "pts": _safe_float(meta.get("pts"), 0.0)}

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

    # Root-level weeklyResults.franchise[] (present in your Week 1 artifacts)
    franchises = wrn.get("franchise") or []
    if isinstance(franchises, dict):
        franchises = [franchises]
    if isinstance(franchises, list) and franchises:
        for fr in franchises:
            fid = str(fr.get("id") or "").zfill(4)
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

    # tolerant ctor
    try:
        client = MFLClient(league_id=league_id, year=year, tz=tz)
    except TypeError:
        try:
            client = MFLClient(league_id=league_id, year=year, timezone=tz)
        except TypeError:
            client = MFLClient(league_id=league_id, year=year)
            setattr(client, "tz", tz)
            setattr(client, "timezone", tz)

    # Fetch week data
    week_data: Dict[str, Any] = fetch_week_data(client, week=week) or {}

    # Franchise names
    f_names = _merge_franchise_names(
        week_data.get("franchise_names"),
        getattr(client, "franchise_names", None),
        cfg.get("franchise_names"),
    )

    # Standings + starters + players
    standings_rows = _build_standings_rows(week_data, f_names)
    starters_by_franchise = _extract_starters_by_franchise(week_data)
    players_map = week_data.get("players_map") or week_data.get("players") or {}

    # REQUIRED salaries
    salary_glob = _resolve_required_salaries_glob(cfg)
    salaries_df = load_salary_file(salary_glob)

    # Value metrics (ordering that matched your earlier success)
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

    # NEW: other sections
    scores_info = _derive_weekly_scores(week_data, f_names)
    opener = _compose_opening_blurb(scores_info)
    vp_drama = _derive_vp_drama(standings_rows)
    headliners = _derive_headliners(starters_by_franchise, players_map, f_names, top_n=10)
    confidence_top3 = _derive_confidence_top3(week_data.get("pool_nfl") or {}, f_names, week=week)
    survivor_list = _derive_survivor_picks(week_data.get("survivor_pool") or {}, f_names, week=week)

    # Simple trophies
    sr_rows = list(scores_info.get("rows") or [])
    trophies = {}
    if sr_rows:
        trophies = {
            "banana_peel": sr_rows[0][0],
            "walk_of_shame": sr_rows[-1][0],
        }

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
        "pool_nfl": week_data.get("pool_nfl") or {},
        "survivor_pool": week_data.get("survivor_pool") or {},
        "scores_info": scores_info,
        "opener": opener,
        "vp_drama": vp_drama,
        "headliners": headliners,
        "confidence_top3": confidence_top3,
        "survivor_list": survivor_list,
        "trophies": trophies,
        "roasts": [],
    }

    # Debug context (so we can see what rendered)
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
