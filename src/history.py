from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
import statistics

History = Dict[str, Any]

def _z4(x: str | int) -> str:
    return str(x).zfill(4)

def load_history(dirpath: str | Path) -> History:
    p = Path(dirpath) / "history.json"
    if not p.exists():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"history.json is invalid JSON: {p}") from e

def save_history(history: History, dirpath: str | Path) -> None:
    Path(dirpath).mkdir(parents=True, exist_ok=True)
    p = Path(dirpath) / "history.json"
    p.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")

def _ensure_team(history: History, fid: str, name: str) -> Dict[str, Any]:
    t = history["teams"].setdefault(fid, {"name": name, "weeks": []})
    # keep latest name
    t["name"] = name
    return t

def update_history(
    history: History,
    *,
    year: int,
    week: int,
    franchise_names: Dict[str, str],
    weekly_scores: List[Tuple[str, float]],  # [(fid, pts)]
    team_efficiency: List[Dict[str, Any]],  # [{"id"|"franchise_id": fid, "total_pts":..., "total_sal":...}]
) -> None:
    history["meta"]["year"] = year

    # median PF for luck calc
    scores_only = [s for _, s in weekly_scores]
    median_pf = statistics.median(scores_only) if scores_only else 0.0

    # league average cost-per-point for burn rate
    league_pts = 0.0
    league_sal = 0.0
    eff_idx: Dict[str, Dict[str, Any]] = {}
    for row in team_efficiency:
        fid_raw = (
            row.get("id")
            or row.get("franchise_id")
            or row.get("franchiseId")
            or row.get("franchiseID")
            or row.get("team_id")
            or row.get("teamId")
            or row.get("fid")
        )
        fid4 = _z4(fid_raw or "") if fid_raw is not None else ""
        if not fid4:
            continue
        eff_idx[fid4] = row
        league_pts += float(row.get("total_pts") or 0.0)
        league_sal += float(row.get("total_sal") or row.get("salary") or row.get("total_salary") or 0.0)

    league_cpp = (league_sal / league_pts) if league_pts > 0 else 0.0

    # push a week row per team
    for fid, pts in weekly_scores:
        fid4 = _z4(fid)
        name = franchise_names.get(fid4, f"Team {fid4}")
        eff = eff_idx.get(fid4, {})

        sal = float(
            eff.get("total_sal")
            or eff.get("salary")
            or eff.get("total_salary")
            or 0.0
        )
        eff_pts = float(eff.get("total_pts") or eff.get("pts") or eff.get("points") or pts)
        cpp = (sal / eff_pts) if eff_pts > 0 else 0.0
        ppk = float(eff.get("ppk") or ((eff_pts / (sal / 1000.0)) if sal else 0.0))
        luck = float(pts) - float(median_pf)

        week_row = {
            "week": int(week),
            "pts": float(pts),
            "sal": float(sal),
            "cpp": float(cpp),
            "ppk": float(ppk),
            "luck": float(luck),
        }
        if league_cpp > 0 and cpp > 0:
            week_row["burn_rate_pct"] = float((cpp / league_cpp - 1.0) * 100.0)

        team = _ensure_team(history, fid4, name)
        # avoid double-writing if re-running same week (idempotent)
        team["weeks"] = [w for w in team["weeks"] if int(w.get("week", 0)) != int(week)]
        team["weeks"].append(week_row)
        team["weeks"].sort(key=lambda w: int(w.get("week", 0)))

def build_season_rankings(history: History) -> List[Dict[str, Any]]:
    meta = history.get("meta") or {}
    try:
        salary_cap = float(meta.get("salary_cap", 0.0) or 0.0)
    except (TypeError, ValueError):
        salary_cap = 0.0

    rows: List[Dict[str, Any]] = []
    for fid, t in (history.get("teams") or {}).items():
        weeks = sorted(t.get("weeks", []), key=lambda w: int(w.get("week", 0)))
        if not weeks:
            continue

        pts_list = [float(w.get("pts", 0.0)) for w in weeks]
        sal_list = [float(w.get("sal", 0.0)) for w in weeks]
        cpp_list = [float(w.get("cpp", 0.0)) for w in weeks if float(w.get("cpp", 0.0)) > 0]
        ppk_list = [float(w.get("ppk", 0.0)) for w in weeks if float(w.get("ppk", 0.0)) > 0]
        luck_sum = sum(float(w.get("luck", 0.0)) for w in weeks)

        pts_sum = sum(pts_list)
        sal_sum = sum(sal_list)
        weeks_played = len(weeks)
        avg = (pts_sum / weeks_played) if weeks_played else 0.0
        stdev = statistics.pstdev(pts_list) if len(pts_list) > 1 else 0.0
        avg_cpp = (sum(cpp_list) / len(cpp_list)) if cpp_list else 0.0
        ppk = (pts_sum / (sal_sum / 1000.0)) if sal_sum > 0 else 0.0
        if not ppk and ppk_list:
            ppk = sum(ppk_list) / len(ppk_list)
        ceiling = max(pts_list) if pts_list else 0.0
        cv = (stdev / avg) if avg else 0.0

        boom_rate = 0.0
        bust_rate = 0.0
        if pts_list and stdev > 0:
            boom_cutoff = avg + stdev
            bust_cutoff = avg - stdev
            boom_rate = sum(1 for pts in pts_list if pts >= boom_cutoff) / len(pts_list)
            bust_rate = sum(1 for pts in pts_list if pts <= bust_cutoff) / len(pts_list)

        avg_cap_pct = 0.0
        if salary_cap > 0 and weeks_played > 0:
            avg_salary = sal_sum / weeks_played
            avg_cap_pct = (avg_salary / salary_cap) * 100.0

        rows.append(
            {
                "id": fid,
                "team": t.get("name", fid),
                "weeks": weeks_played,
                "pts_sum": pts_sum,
                "avg": avg,
                "stdev": stdev,
                "luck_sum": luck_sum,
                "avg_cpp": avg_cpp,
                "ppk": ppk,
                "sal_sum": sal_sum,
                "boom_rate": boom_rate,
                "bust_rate": bust_rate,
                "avg_cap_pct": avg_cap_pct,
                "cv": cv,
                "ceiling": ceiling,
            }
        )

    league_avg_cpp = 0.0
    cpp_vals = [r["avg_cpp"] for r in rows if r["avg_cpp"] > 0]
    if cpp_vals:
        league_avg_cpp = sum(cpp_vals) / len(cpp_vals)

    out: List[Dict[str, Any]] = []
    for r in rows:
        expected_pts = (r["sal_sum"] / league_avg_cpp) if league_avg_cpp > 0 else 0.0
        value_over_baseline = r["pts_sum"] - expected_pts
        out.append(
            {
                "id": r["id"],
                "team": r["team"],
                "weeks": r["weeks"],
                "pts_sum": round(r["pts_sum"], 2),
                "avg": round(r["avg"], 2),
                "stdev": round(r["stdev"], 2),
                "luck_sum": round(r["luck_sum"], 2),
                "avg_cpp": round(r["avg_cpp"], 4),
                "ppk": round(r["ppk"], 4),
                "vob": round(value_over_baseline, 2),
                "value_over_baseline": round(value_over_baseline, 2),
                "boom_rate": round(r["boom_rate"], 3),
                "bust_rate": round(r["bust_rate"], 3),
                "avg_cap_pct": round(r["avg_cap_pct"], 1),
                "cv": round(r["cv"], 3),
                "ceiling": round(r["ceiling"], 2),
            }
        )

    for r in out:
        if r["avg_cpp"] > 0 and league_avg_cpp > 0:
            r["burn_rate_pct"] = round((r["avg_cpp"] / league_avg_cpp - 1.0) * 100.0, 1)
        else:
            r["burn_rate_pct"] = 0.0

    out.sort(key=lambda x: (-x["ppk"], -x["vob"], -x["avg"], x["stdev"]))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out
