from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
import statistics

History = Dict[str, Any]

def _z4(x: str | int) -> str:
    return str(x).zfill(4)

def load_history(dirpath: str) -> History:
    p = Path(dirpath) / "history.json"
    if not p.exists():
        return {"teams": {}, "meta": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"teams": {}, "meta": {}}

def save_history(history: History, dirpath: str) -> None:
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
    team_efficiency: List[Dict[str, Any]],    # [{"id": fid, "total_pts":..., "total_sal":...}]
) -> None:
    history["meta"]["year"] = year
    # median PF for luck calc
    scores_only = [s for _, s in weekly_scores]
    median_pf = statistics.median(scores_only) if scores_only else 0.0

    # league average cost-per-point for burn rate
    league_pts = sum(x.get("total_pts", 0.0) for x in team_efficiency)
    league_sal = sum(x.get("total_sal", 0.0) for x in team_efficiency)
    league_cpp = (league_sal / league_pts) if (league_pts > 0) else 0.0

    # index efficiency by fid for salary & ppk
    eff_idx = {str(x.get("id") or "").zfill(4): x for x in team_efficiency}

    # push a week row per team
    for fid, pts in weekly_scores:
        fid4 = _z4(fid)
        name = franchise_names.get(fid4, f"Team {fid4}")
        eff = eff_idx.get(fid4, {})
        sal = float(eff.get("total_sal") or 0.0)
        # if your efficiency rows are only per-week sums, sal here is weekly salary; if season-summed, it's okay—we show season table anyway
        cpp = (sal / pts) if pts > 0 else 0.0
        luck = float(pts) - float(median_pf)

        team = _ensure_team(history, fid4, name)
        # avoid double-writing if re-running same week (idempotent)
        team["weeks"] = [w for w in team["weeks"] if int(w.get("week", 0)) != int(week)]
        team["weeks"].append({
            "week": int(week),
            "pts": float(pts),
            "sal": float(sal),
            "cpp": float(cpp),
            "luck": float(luck),
        })

def build_season_rankings(history: History) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for fid, t in (history.get("teams") or {}).items():
        weeks = sorted(t.get("weeks", []), key=lambda w: int(w.get("week", 0)))
        if not weeks:
            continue
        pts_list = [float(w.get("pts", 0.0)) for w in weeks]
        sal_sum = sum(float(w.get("sal", 0.0)) for w in weeks)
        pts_sum = sum(pts_list)
        cpp_list = [float(w.get("cpp", 0.0)) for w in weeks if float(w.get("cpp", 0.0)) > 0]
        luck_sum = sum(float(w.get("luck", 0.0)) for w in weeks)
        stdev = statistics.pstdev(pts_list) if len(pts_list) > 1 else 0.0
        avg = (pts_sum / len(pts_list)) if pts_list else 0.0
        avg_cpp = (sum(cpp_list)/len(cpp_list)) if cpp_list else 0.0
        ppk = (pts_sum / (sal_sum/1000)) if sal_sum > 0 else 0.0  # hidden efficiency

        out.append({
            "id": fid,
            "team": t.get("name", fid),
            "weeks": len(weeks),
            "pts_sum": round(pts_sum, 2),
            "avg": round(avg, 2),
            "stdev": round(stdev, 2),
            "luck_sum": round(luck_sum, 2),
            "avg_cpp": round(avg_cpp, 4),
            "ppk": round(ppk, 4),
        })

    # compute league avg cpp for relative “salary burn rate”
    league_avg_cpp = 0.0
    cpp_vals = [r["avg_cpp"] for r in out if r["avg_cpp"] > 0]
    if cpp_vals:
        league_avg_cpp = sum(cpp_vals) / len(cpp_vals)

    for r in out:
        if r["avg_cpp"] > 0 and league_avg_cpp > 0:
            # burn rate: (team cpp / league avg cpp - 1) * 100 (%)
            r["burn_rate_pct"] = round((r["avg_cpp"]/league_avg_cpp - 1.0) * 100.0, 1)
        else:
            r["burn_rate_pct"] = 0.0

    # rank by hidden efficiency (ppk), tie-break avg then stdev (lower stdev = more consistent)
    out.sort(key=lambda x: (-x["ppk"], -x["avg"], x["stdev"]))
    # assign rank
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out
