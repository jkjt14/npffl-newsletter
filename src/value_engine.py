from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

try:
    import pandas as pd
except Exception:
    pd = None


def _as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x]
    return []


def _clean_name(n: str) -> str:
    n = (n or "").strip()
    n = re.sub(r"[!·•]+", "", n)
    n = re.sub(r"\s+", " ", n)
    return n.lower()


def _ppk(points: float, salary: float) -> Optional[float]:
    if salary and salary > 0:
        return round(points / (salary / 1000.0), 4)
    return None


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _salary_index_from_df(df: "pd.DataFrame") -> Tuple[Dict[str, float], Dict[str, str], Dict[str, str]]:
    name_col = "Name"
    pos_col = "Pos"
    team_col = "Team"
    sal_col = "Salary"

    out_salary: Dict[str, float] = {}
    out_pos: Dict[str, str] = {}
    out_team: Dict[str, str] = {}

    df2 = df.copy()
    if sal_col in df2.columns:
        df2[sal_col] = pd.to_numeric(df2[sal_col], errors="coerce")

    for _, r in df2.iterrows():
        nm = str(r.get(name_col) or "").strip()
        if not nm:
            continue
        key = _clean_name(nm)
        sal = r.get(sal_col)
        if sal is not None and pd.notna(sal):
            out_salary[key] = float(sal)
        pos = str(r.get(pos_col) or "").strip()
        team = str(r.get(team_col) or "").strip()
        if pos:
            out_pos[key] = pos
        if team:
            out_team[key] = team

    return out_salary, out_pos, out_team


def _resolve_name_for_id(pid: str, players_map: Dict[str, Dict[str, str]]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not isinstance(players_map, dict):
        return None, None, None
    node = players_map.get(pid)
    if not isinstance(node, dict):
        return None, None, None
    nm = node.get("name")
    pos = node.get("pos") or node.get("position")
    team = node.get("team")
    return nm, pos, team


def compute_values(salary_df, week_data: Dict[str, Any]) -> Dict[str, Any]:
    if pd is None:
        return {}

    # Salary lookups
    name_to_salary: Dict[str, float] = {}
    name_to_pos: Dict[str, str] = {}
    name_to_team: Dict[str, str] = {}

    if salary_df is not None and not getattr(salary_df, "empty", True):
        name_to_salary, name_to_pos, name_to_team = _salary_index_from_df(salary_df)

    players_map = week_data.get("players_map") or {}  # id -> {name,pos,team}
    wr = week_data.get("weekly_results") or {}
    wr_root = wr.get("weeklyResults") if isinstance(wr, dict) else None
    franchises = _as_list(wr_root.get("franchise") if isinstance(wr_root, dict) else None)

    enriched_starters: List[Dict[str, Any]] = []
    for fr in franchises:
        fid = fr.get("id") or "unknown"
        for p in _as_list(fr.get("player")):
            st = str(p.get("status") or "").lower()
            if st and st not in ("starter", "s"):
                continue
            pid = str(p.get("id") or "").strip()
            pts = _safe_float(p.get("score"), 0.0)

            nm, pos_hint, team_hint = _resolve_name_for_id(pid, players_map)

            salary = None
            pos = pos_hint
            team = team_hint
            if nm:
                key = _clean_name(nm)
                salary = name_to_salary.get(key)
                if not pos:
                    pos = name_to_pos.get(key)
                if not team:
                    team = name_to_team.get(key)

            enriched_starters.append({
                "player_id": pid,
                "player": nm or pid,
                "pos": pos,
                "team": team,
                "salary": salary,
                "pts": pts,
                "franchise_id": fid,
                "ppk": _ppk(pts, salary) if (salary is not None) else None,
            })

    # Top performers
    top_performers = sorted(enriched_starters, key=lambda r: r["pts"], reverse=True)[:10]

    # Value rankings
    with_ppk = [r for r in enriched_starters if r.get("ppk") is not None]
    top_values = sorted(with_ppk, key=lambda r: (r["ppk"], r["pts"]), reverse=True)[:10]
    top_busts = sorted(with_ppk, key=lambda r: (r["ppk"], -r["pts"]))[:10]

    # Per-position
    by_pos: Dict[str, List[Dict[str, Any]]] = {}
    for r in with_ppk:
        pos = (r.get("pos") or "UNK").upper()
        by_pos.setdefault(pos, []).append(r)
    for pos, rows in list(by_pos.items()):
        by_pos[pos] = sorted(rows, key=lambda r: r["ppk"], reverse=True)[:10]

    # Team efficiency
    team_stats: Dict[str, Dict[str, float]] = {}
    for r in enriched_starters:
        fid = r["franchise_id"]
        pts = _safe_float(r["pts"], 0.0)
        sal = r.get("salary")
        if fid not in team_stats:
            team_stats[fid] = {"pts": 0.0, "sal": 0.0}
        team_stats[fid]["pts"] += pts
        if sal is not None:
            team_stats[fid]["sal"] += float(sal)
    team_efficiency = []
    for fid, agg in team_stats.items():
        total_pts = agg["pts"]
        total_sal = agg["sal"]
        ppk_team = _ppk(total_pts, total_sal) if total_sal > 0 else None
        team_efficiency.append({
            "franchise_id": fid,
            "total_pts": round(total_pts, 2),
            "total_sal": int(total_sal) if total_sal else 0,
            "ppk": ppk_team,
        })
    team_efficiency.sort(key=lambda r: (r["ppk"] or 0.0, r["total_pts"]), reverse=True)

    return {
        "top_values": top_values,
        "top_busts": top_busts,
        "by_pos": by_pos,
        "team_efficiency": team_efficiency,
        "top_performers": top_performers,
        "samples": {
            "starters": len(enriched_starters),
            "with_ppk": len(with_ppk),
        },
    }
