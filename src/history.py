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
    t["name"] = name                     # keep latest name
    return t

def update_history(
    history: History,
    *,
    year: int,
    week: int,
    franchise_names: Dict[str, str],
    weekly_scores: List[Tuple[str, float]],  # [(fid, pts)]
    team_efficiency: List[Dict[str, Any]],   # [{"id": fid, "total_pts":..., "total_sal":...}]
) -> None:
    history["meta"]["year"] = year

    # median PF for luck calc
    scores_only = [s for _, s in weekly_scores]
    median_pf = statistics.median(scores_only) if scores_only else 0.0

    # league average cost-per-point for burn rate
    eff_idx: Dict[str, Dict[str, Any]] = {}
    league_pts = 0.0
    league_sal = 0.0
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
        fid4 = _z4(fid_raw or "")
        eff_idx[fid4] = row
        league_pts += float(row.get("total_pts") or 0.0)
        league_sal += float(row.get("total_sal") or row.get("salary") or row.get("total_salary") or 0.0)

    league_cpp = (league_sal / league_pts) if league_pts else 0.0

    # push a week row per team
    for fid, pts in weekly_scores:
        fid4 = _z4(fid)
        name = franchise_names.get(fid4, f"Team {fid4}")
        eff = eff_idx.get(fid4, {})
        sal = float(eff.get("total_sal") or eff.get("salary") or eff.get("total_salary") or 0.0)
        pts_val = float(pts)
        cpp = (sal / pts_val) if pts_val > 0 else 0.0
        ppk = (pts_val / (sal / 1000.0)) if sal > 0 else 0.0
        luck = pts_val - median_pf

        week_row = {
            "week": int(week),
            "pts": pts_val,
            "sal": sal,
            "cpp": cpp,
            "ppk": ppk,
            "luck": luck,
        }
        if league_cpp > 0 and cpp > 0:
            week_row["burn_rate_pct"] = (cpp / league_cpp - 1.0) * 100.0

        team = _ensure_team(history, fid4, name)
        team["weeks"] = [w for w in team["weeks"] if int(w.get("week", 0)) != int(week)]
        team["weeks"].append(week_row)
        team["weeks"].sort(key=lambda w: int(w.get("week", 0)))

def build_season_rankings(history: History) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for fid, t in (history.get("teams") or {}).items():
        weeks = sorted(t.get("weeks", []), key=lambda w: int(w.get("week", 0)))
        if not weeks:
            continue

        pts_list = [float(w.get("pts", 0.0)) for w in weeks]
        sal_list = [float(w.get("sal", 0.0)) for w in weeks]
        cpp_list = [float(w.get("cpp", 0.0)) for w in weeks if float(w.get("cpp", 0.0)) > 0]
        weekly_ppk = [float(w.get("ppk") or 0.0) for w in weeks]
        luck_sum = sum(float(w.get("luck", 0.0)) for w in weeks)

        pts_sum = sum(pts_list)
        sal_sum = sum(sal_list)
        weeks_played = len(weeks)
        avg = pts_sum / weeks_played if weeks_played else 0.0
        stdev = statistics.pstdev(pts_list) if len(pts_list) > 1 else 0.0
        avg_cpp = sum(cpp_list) / len(cpp_list) if cpp_list else 0.0
        ppk = pts_sum / (sal_sum / 1000.0) if sal_sum > 0 else 0.0
        boom_count = sum(1 for x in weekly_ppk if x >= 3.0)
        bust_count = sum(1 for x in weekly_ppk if x <= 1.5)
        boom_rate = boom_count / weeks_played if weeks_played else 0.0
        bust_rate = bust_count / weeks_played if weeks_played else 0.0

        rows.append(
            {
                "id": fid,
                "team": t.get("name", fid),
                "weeks": weeks_played,
                "pts_sum": round(pts_sum, 2),
                "avg": round(avg, 2),
                "stdev": round(stdev, 2),
                "luck_sum": round(luck_sum, 2),
                "avg_cpp": round(avg_cpp, 4),
                "ppk": round(ppk, 4),
                "boom_rate": round(boom_rate, 3),
                "bust_rate": round(bust_rate, 3),
            }
        )

    league_avg_cpp = 0.0
    cpp_vals = [r["avg_cpp"] for r in rows if r["avg_cpp"] > 0]
    if cpp_vals:
        league_avg_cpp = sum(cpp_vals) / len(cpp_vals)

    out: List[Dict[str, Any]] = []
    for r in rows:
        if r["avg_cpp"] > 0 and league_avg_cpp > 0:
            r["burn_rate_pct"] = round((r["avg_cpp"] / league_avg_cpp - 1.0) * 100.0, 1)
        else:
            r["burn_rate_pct"] = 0.0
        out.append(r)

    # rank by hidden efficiency (ppk), then boom/bust rates, then avg/stdev
    out.sort(key=lambda x: (-x["ppk"], -x["boom_rate"], x["bust_rate"], -x["avg"], x["stdev"]))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out
