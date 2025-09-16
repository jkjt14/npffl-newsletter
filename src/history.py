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
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"history.json is invalid JSON: {p}") from e

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
    metrics: List[Dict[str, float]] = []
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
        ceiling = max(pts_list) if pts_list else 0.0
        max_week_sal = max([float(w.get("sal", 0.0)) for w in weeks] or [0.0])
        ceiling_ppk_val: float | None = None
        if max_week_sal > 0:
            ceiling_ppk_val = ceiling / (max_week_sal / 1000.0)

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
            "ceiling": round(ceiling, 2),
            "ceiling_ppk": round(ceiling_ppk_val, 4) if ceiling_ppk_val is not None else None,
        })

        metrics.append({
            "ppk": float(ppk),
            "avg": float(avg),
            "stdev": float(stdev),
            "ceiling": float(ceiling),
            "ceiling_ppk": float(ceiling_ppk_val) if ceiling_ppk_val is not None else 0.0,
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

    if not out:
        return out

    def _norm(val: float, low: float, high: float) -> float:
        if high - low <= 1e-9:
            return 0.0
        return (val - low) / (high - low)

    ppk_vals = [m["ppk"] for m in metrics]
    avg_vals = [m["avg"] for m in metrics]
    ceil_vals = [m["ceiling"] for m in metrics]
    ceil_ppk_vals = [m["ceiling_ppk"] for m in metrics]
    stdev_vals = [m["stdev"] for m in metrics]

    ppk_low, ppk_high = (min(ppk_vals), max(ppk_vals)) if ppk_vals else (0.0, 0.0)
    avg_low, avg_high = (min(avg_vals), max(avg_vals)) if avg_vals else (0.0, 0.0)
    ceil_low, ceil_high = (min(ceil_vals), max(ceil_vals)) if ceil_vals else (0.0, 0.0)
    ceil_ppk_low, ceil_ppk_high = (min(ceil_ppk_vals), max(ceil_ppk_vals)) if ceil_ppk_vals else (0.0, 0.0)
    stdev_low, stdev_high = (min(stdev_vals), max(stdev_vals)) if stdev_vals else (0.0, 0.0)

    for r, m in zip(out, metrics):
        norm_ppk = _norm(m["ppk"], ppk_low, ppk_high)
        norm_avg = _norm(m["avg"], avg_low, avg_high)
        norm_ceiling = _norm(m["ceiling"], ceil_low, ceil_high)
        norm_ceiling_ppk = _norm(m["ceiling_ppk"], ceil_ppk_low, ceil_ppk_high)
        consistency = 1.0 - _norm(m["stdev"], stdev_low, stdev_high)
        consistency = max(0.0, min(1.0, consistency))
        power_score = (
            0.35 * norm_ppk
            + 0.25 * norm_avg
            + 0.2 * norm_ceiling
            + 0.1 * norm_ceiling_ppk
            + 0.1 * consistency
        )
        r["power_score"] = round(power_score, 4)

    # rank by composite power score (ppk, avg, ceiling, and consistency)
    out.sort(
        key=lambda x: (
            -x.get("power_score", 0.0),
            -x.get("ppk", 0.0),
            -x.get("avg", 0.0),
            -x.get("ceiling", 0.0),
            x.get("stdev", 0.0),
        )
    )
    # assign rank
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out
