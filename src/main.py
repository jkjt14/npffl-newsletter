from __future__ import annotations

import argparse, glob, json, os, sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml
from .mfl_client import MFLClient
from .fetch_week import fetch_week_data
from .load_salary import load_salary_file
from .value_engine import compute_values
from .newsletter import render_newsletter
from .odds_client import fetch_week_moneylines, build_team_prob_index, TEAM_MAP
from .history import load_history, save_history, update_history, build_season_rankings

# ---------- utils ----------
def _read_config(path: str | Path = "config.yaml") -> Dict[str, Any]:
    p = Path(path); 
    if not p.exists(): return {}
    with p.open("r", encoding="utf-8") as f: return yaml.safe_load(f) or {}

def _week_label(week: int | None) -> str: return f"{int(week):02d}" if week is not None else "01"
def _safe_float(x: Any, default: float = 0.0) -> float:
    try: return float(x)
    except Exception: return default

def _merge_franchise_names(*maps: Dict[str, str] | None) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for mp in maps or []:
        if not mp: continue
        for k,v in mp.items():
            if k is None: continue
            out[str(k).zfill(4)] = str(v)
    return out


def _history_weeks(history: Dict[str, Any]) -> set[int]:
    weeks: set[int] = set()
    teams = history.get("teams") or {}
    if isinstance(teams, dict):
        for team in teams.values():
            for wk in (team.get("weeks") or []):
                try:
                    weeks.add(int(wk.get("week")))
                except (TypeError, ValueError):
                    continue
    return weeks

def _cfg_get(cfg: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur: return default
        cur = cur[part]
    return cur

def _int_or_none(s: str | None) -> int | None:
    if s is None: return None
    s = str(s).strip()
    return None if s == "" else int(s)

def _resolve_required_salaries_glob(cfg: Dict[str, Any]) -> str:
    cand: List[str] = []
    v = _cfg_get(cfg, "inputs.salary_glob");  cand += [str(v)] if v else []
    for k in ("salaries_path","salaries_file","salary_file"):
        v = cfg.get(k);  cand += [str(v)] if v else []
    env_glob = os.environ.get("SALARY_GLOB"); cand += [env_glob] if env_glob else []
    cand += ["data/salaries/*.xlsx", "salaries/*.xlsx"]
    tried = []
    for pat in cand:
        pat = str(pat).strip(); 
        if not pat: continue
        tried.append(pat)
        if glob.glob(pat): return pat
    print("[salary] No salary files found. Looked for:"); 
    for t in tried: print(" -", t)
    print("Set inputs.salary_glob in config.yaml or SALARY_GLOB env.", file=sys.stderr)
    sys.exit(2)

# ---------- derivations ----------
def _derive_weekly_scores(week_data: Dict[str, Any]) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    wr = week_data.get("weekly_results") or {}
    node = wr.get("weeklyResults") if isinstance(wr, dict) else {}
    franchises = (node or {}).get("franchise") or []
    if isinstance(franchises, dict): franchises = [franchises]
    for fr in (franchises or []):
        fid = str(fr.get("id") or "").zfill(4)
        out.append((fid, _safe_float(fr.get("score"), 0.0)))
    return out

def _build_standings_rows(week_data: Dict[str, Any], f_map: Dict[str, str]) -> List[Dict[str, Any]]:
    rows = week_data.get("standings_rows")
    if isinstance(rows, list) and rows: return rows
    # fallback from weekly scores
    out = []
    for fid, pts in _derive_weekly_scores(week_data):
        out.append({"id": fid, "name": f_map.get(fid, f"Team {fid}"), "pf": pts, "vp": 0.0})
    out.sort(key=lambda r: (-_safe_float(r["vp"]), -_safe_float(r["pf"]), r["name"]))
    return out

def _extract_starters_by_franchise(week_data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    wr = week_data.get("weekly_results") or {}
    wrn = wr.get("weeklyResults") if isinstance(wr, dict) else {}
    players_map: Dict[str, Dict[str, Any]] = week_data.get("players_map") or {}
    franchises = (wrn or {}).get("franchise") or []
    if isinstance(franchises, dict): franchises = [franchises]
    for fr in franchises or []:
        fid = str(fr.get("id") or "").zfill(4)
        # per-team player index
        f_pl = fr.get("players") or fr.get("player") or []
        if isinstance(f_pl, dict): f_pl = f_pl.get("player") or f_pl
        if isinstance(f_pl, dict): f_pl = [f_pl]
        fp_idx: Dict[str, Dict[str, Any]] = {}
        for p in (f_pl or []):
            pid = str(p.get("id") or "").strip()
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
                meta = fp_idx.get(pid) or {}
                pm = players_map.get(pid, {})
                rows.append({
                    "player_id": pid,
                    "player": (meta.get("name") or pm.get("first_last") or pm.get("raw") or "").strip(),
                    "pos": (meta.get("pos") or pm.get("pos") or "").strip(),
                    "team": (meta.get("team") or pm.get("team") or None),
                    "pts": _safe_float(meta.get("pts"), 0.0),
                })
        if not rows:
            score = _safe_float(fr.get("score") or 0.0)
            rows.append({"player_id": "", "player": "Team Total", "pos": "", "team": None, "pts": score})
        out.setdefault(fid, []).extend(rows)
    return out

def _derive_vp_drama(standings: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not standings: return {}
    rows = sorted(standings, key=lambda r: (-_safe_float(r.get("vp")), -_safe_float(r.get("pf"))))
    mids = [r for r in rows if _safe_float(r.get("vp")) == 2.5]
    lows = [r for r in rows if _safe_float(r.get("vp")) == 0.0]
    if not mids or not lows: return {}
    last_in = mids[-1]; first_out = lows[0]
    gap = round(_safe_float(last_in["pf"]) - _safe_float(first_out["pf"]), 2)
    return {"villain": last_in["name"], "bubble": first_out["name"], "gap_pf": gap, "top5": rows[:5], "sixth": rows[5] if len(rows) > 5 else None}

def _derive_headliners(starters_by_franchise: Dict[str, List[Dict[str, Any]]],
                       players_map: Dict[str, Dict[str, Any]],
                       f_map: Dict[str, str],
                       top_n: int = 10) -> List[Dict[str, Any]]:
    use: Dict[str, Dict[str, Any]] = {}
    for fid, rows in (starters_by_franchise or {}).items():
        who = f_map.get(fid, f"Team {fid}")
        for r in rows:
            pid = str(r.get("player_id") or "").strip()
            if not pid: continue
            pts = _safe_float(r.get("pts"), 0.0)
            pm = players_map.get(pid, {})
            name = (r.get("player") or pm.get("first_last") or pm.get("raw") or pid).strip()
            pos = (r.get("pos") or pm.get("pos") or "").strip()
            team = (r.get("team") or pm.get("team") or "").strip()
            bucket = use.setdefault(pid, {"player": name, "pos": pos, "team": team, "pts": pts, "managers": set()})
            bucket["pts"] = max(bucket["pts"], pts)
            bucket["managers"].add(who)
    rows = [{"player": v["player"], "pos": v["pos"], "team": v["team"], "pts": v["pts"], "managers": sorted(v["managers"])} for v in use.values()]
    rows.sort(key=lambda x: -x["pts"])
    return rows[:top_n]

# ---------- odds summaries ----------
def _mfl_code_to_odds(team_code: str) -> str:
    return TEAM_MAP.get(team_code.upper().strip(), team_code.upper().strip())

def _confidence_summary(conf3: List[Dict[str, Any]], team_prob: Dict[str, float]) -> Dict[str, Any]:
    all_picks: List[str] = []
    scored: List[Tuple[str, float]] = []
    for row in conf3:
        for g in row.get("top3", []):
            t = _mfl_code_to_odds(str(g.get("pick","")))
            if not t: continue
            all_picks.append(t)
            prob = float(team_prob.get(t, 0.5))
            scored.append((t, prob))
    boring = None
    if all_picks:
        from collections import Counter
        c = Counter(all_picks)
        boring = sorted(c.items(), key=lambda x: (-x[1], x[0]))[0][0]
    boldest = None
    if scored:
        scored.sort(key=lambda x: x[1])  # lowest prob first
        boldest = scored[0][0]
    return {"boring_pick": boring, "boldest_pick": boldest}

def _survivor_summary(surv: List[Dict[str, Any]], team_prob: Dict[str, float]) -> Dict[str, Any]:
    if not surv: return {}
    picks = [ _mfl_code_to_odds(r.get("pick","")) for r in surv if r.get("pick") ]
    if not picks: return {"boring_consensus": None, "boldest_lifeline": None}
    from collections import Counter
    c = Counter(picks)
    boring = sorted(c.items(), key=lambda x: (-x[1], x[0]))[0][0]
    boldest = sorted(picks, key=lambda t: team_prob.get(t, 0.5))[0]
    return {"boring_consensus": boring, "boldest_lifeline": boldest}

# ---------- CLI ----------
def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="NPFFL Weekly Newsletter generator")
    ap.add_argument("--config", default=os.environ.get("NPFFL_CONFIG", "config.yaml"))
    ap.add_argument("--week", type=_int_or_none, default=None)
    ap.add_argument("--out-dir", default=os.environ.get("NPFFL_OUTDIR", "build"))
    return ap.parse_args()

def generate_newsletter(cfg: Dict[str, Any], week: int, out_dir: Path) -> Tuple[Path, Path] | Tuple[Path] | Tuple[()]:
    league_id = str(cfg.get("league_id") or os.environ.get("MFL_LEAGUE_ID") or "").strip()
    year = int(cfg.get("year") or os.environ.get("MFL_YEAR") or 2025)
    tz = cfg.get("timezone") or cfg.get("tz") or "America/New_York"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    history_dir_cfg = (
        _cfg_get(cfg, "history.dir")
        or _cfg_get(cfg, "history.path")
        or _cfg_get(cfg, "history_dir")
    )
    history_dir = Path(history_dir_cfg) if history_dir_cfg else Path("data") / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    # client
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
    f_names = _merge_franchise_names(week_data.get("franchise_names"), getattr(client, "franchise_names", None), cfg.get("franchise_names"))

    # Weekly bits
    standings_rows = _build_standings_rows(week_data, f_names)
    starters_by_franchise = _extract_starters_by_franchise(week_data)
    players_map = week_data.get("players_map") or week_data.get("players") or {}

    # Salaries (required)
    salary_glob = _resolve_required_salaries_glob(cfg)
    salaries_df = load_salary_file(salary_glob, week=week)

    # Values/Efficiency
    values_out: Dict[str, Any] = compute_values(
        salaries_df, players_map, starters_by_franchise, f_names, week=week, year=year
    )
    top_values = values_out.get("top_values", [])
    top_busts = values_out.get("top_busts", [])
    team_efficiency = values_out.get("team_efficiency", [])

    # Scores list for history + narrative
    weekly_scores_pairs = _derive_weekly_scores(week_data)  # [(fid, pts)]
    scores_info = {
        "rows": sorted([(f_names.get(fid, f"Team {fid}"), pts) for fid, pts in weekly_scores_pairs], key=lambda t:-t[1]),
        "avg": round(sum(pts for _, pts in weekly_scores_pairs)/len(weekly_scores_pairs), 2) if weekly_scores_pairs else None,
    }

    # VP drama (also include 5th vs 6th)
    vp_drama = _derive_vp_drama(standings_rows)

    # Headliners
    headliners = _derive_headliners(starters_by_franchise, players_map, f_names, top_n=10)

    # Pools + odds
    pool_nfl = week_data.get("pool_nfl") or {}
    survivor_pool = week_data.get("survivor_pool") or {}

    conf3 = []
    node = (pool_nfl.get("poolPicks") or {})
    franchises = node.get("franchise") or []
    if isinstance(franchises, dict): franchises = [franchises]
    for fr in franchises:
        fid = str(fr.get("id") or "").zfill(4)
        name = f_names.get(fid, f"Team {fid}")
        wk_blocks = fr.get("week") or []
        if isinstance(wk_blocks, dict): wk_blocks = [wk_blocks]
        target = None
        for w in wk_blocks:
            if str(w.get("week") or "") == str(week):
                target = w; break
        if not target: continue
        games = target.get("game") or []
        if isinstance(games, dict): games = [games]
        picks = []
        for g in games:
            try: rank = int(str(g.get("rank") or "0"))
            except Exception: rank = 0
            picks.append({"rank": rank, "pick": str(g.get("pick") or "").strip()})
        picks.sort(key=lambda r: -r["rank"])
        conf3.append({"team": name, "top3": picks[:3]})

    # Survivor list
    survivor_list = []
    node = (survivor_pool.get("survivorPool") or survivor_pool or {})
    franchises = node.get("franchise") or []
    if isinstance(franchises, dict): franchises = [franchises]
    surv_no = []
    for fr in franchises:
        fid = str(fr.get("id") or "").zfill(4)
        name = f_names.get(fid, f"Team {fid}")
        wk_blocks = fr.get("week") or []
        if isinstance(wk_blocks, dict): wk_blocks = [wk_blocks]
        pick = ""
        for w in wk_blocks:
            if str(w.get("week") or "") == str(week):
                pick = str(w.get("pick") or "").strip(); break
        if pick:
            survivor_list.append({"team": name, "pick": pick})
        else:
            surv_no.append(name)

    # Odds → implied probabilities → summaries
    api_key = os.environ.get("THE_ODDS_API_KEY")
    games = fetch_week_moneylines(api_key)
    team_prob = build_team_prob_index(games)
    conf_summary = _confidence_summary(conf3, team_prob)
    conf_no = [t["team"] for t in conf3 if not t.get("top3")]
    surv_summary = _survivor_summary(survivor_list, team_prob)

    # ---- Season history (consistency / luck / salary burn / rankings) ----
    try:
        history = load_history(history_dir)
    except (FileNotFoundError, ValueError) as e:
        print(f"[history] {e}; starting fresh")
        history = {"teams": {}, "meta": {}}

    present_weeks = _history_weeks(history)
    missing_weeks = [w for w in range(1, int(week)) if w not in present_weeks]
    if missing_weeks:
        print(f"[history] Backfilling weeks: {missing_weeks}")
    for wk in missing_weeks:
        try:
            wk_data = fetch_week_data(client, week=wk) or {}
        except Exception as exc:
            print(f"[history] Failed to fetch week {wk}: {exc}")
            continue

        wk_fnames = _merge_franchise_names(
            wk_data.get("franchise_names"),
            getattr(client, "franchise_names", None),
            cfg.get("franchise_names"),
        )
        wk_scores = _derive_weekly_scores(wk_data)
        if not wk_scores:
            print(f"[history] No scores found for week {wk}; skipping")
            continue

        wk_starters = _extract_starters_by_franchise(wk_data)
        wk_players = wk_data.get("players_map") or wk_data.get("players") or {}
        try:
            wk_salary_df = load_salary_file(salary_glob, week=wk)
        except Exception as exc:
            print(f"[history] Salary load failed for week {wk}: {exc}; reusing current sheet")
            wk_salary_df = salaries_df

        wk_values = compute_values(
            wk_salary_df,
            wk_players,
            wk_starters,
            wk_fnames,
            week=wk,
            year=year,
        )
        wk_eff = wk_values.get("team_efficiency", [])

        update_history(
            history,
            year=year,
            week=wk,
            franchise_names=wk_fnames,
            weekly_scores=wk_scores,
            team_efficiency=wk_eff,
        )

    salary_cap = _safe_float(_cfg_get(cfg, "salary_cap"), 0.0)
    if salary_cap > 0:
        history.setdefault("meta", {})["salary_cap"] = salary_cap

    # convert weekly_scores_pairs (fid, pts) to ensure all fids present
    update_history(
        history,
        year=year,
        week=week,
        franchise_names=f_names,
        weekly_scores=weekly_scores_pairs,
        team_efficiency=team_efficiency,
    )
    save_history(history, history_dir)
    season_table = build_season_rankings(history)  # list of dicts with rank, pts_sum, avg, stdev, luck_sum, burn_rate_pct, ppk

    assets_cfg = cfg.get("assets") or {}
    logos_dir_cfg = assets_cfg.get("logos_dir") or "assets/franchises"
    assets_payload: Dict[str, Any] = {"logos_dir": str(logos_dir_cfg)}
    if assets_cfg.get("banners_dir"):
        assets_payload["banners_dir"] = str(assets_cfg.get("banners_dir"))
    if assets_cfg.get("logo_width_px"):
        assets_payload["logo_width_px"] = assets_cfg.get("logo_width_px")
    if "use_franchise_logos" in assets_cfg:
        assets_payload["use_franchise_logos"] = assets_cfg.get("use_franchise_logos")

    payload: Dict[str, Any] = {
        "title": _cfg_get(cfg, "newsletter.title") or "NPFFL Weekly Newsletter",
        "week_label": _week_label(week),
        "timezone": tz,
        "year": year,
        "league_id": league_id,
        "franchise_names": f_names,
        "standings_rows": standings_rows,
        "team_efficiency": team_efficiency,
        "top_values": top_values,
        "top_busts": top_busts,
        "scores_info": scores_info,
        "vp_drama": vp_drama,
        "headliners": headliners,
        "starters_by_franchise": starters_by_franchise,  # for Fantasy Jail
        # pools
        "confidence_top3": conf3,
        "team_prob": team_prob,
        "confidence_summary": conf_summary,
        "confidence_meta": {"no_picks": conf_no},
        "survivor_list": survivor_list,
        "survivor_summary": surv_summary,
        "survivor_meta": {"no_picks": surv_no},
        # season power rankings (mini table)
        "season_rankings": season_table,
        # assets (optional banners)
        "assets": assets_payload,
    }

    try:
        (out_dir / f"context_week_{_week_label(week)}.json").write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
    except Exception:
        pass

    outputs = render_newsletter(payload, output_dir=str(out_dir), week=week)
    paths = [p for p in (outputs.get("md_path"), outputs.get("html_path")) if p]
    if paths:
        for p in paths: print(f"Wrote: {p}")
        return tuple(Path(p) for p in paths)  # type: ignore[return-value]

    stub = out_dir / f"week_{_week_label(week)}.md"
    stub.write_text("# Newsletter\n\n_No content produced._\n", encoding="utf-8")
    print(f"Wrote: {stub}")
    return (stub,)


def main() -> Tuple[Path, Path] | Tuple[Path] | Tuple[()]:
    args = _parse_args()
    cfg = _read_config(args.config)
    week = args.week if args.week is not None else int(cfg.get("week") or 1)
    out_dir = Path(_cfg_get(cfg, "outputs.dir") or args.out_dir)
    return generate_newsletter(cfg, week, out_dir)

if __name__ == "__main__":
    main()
