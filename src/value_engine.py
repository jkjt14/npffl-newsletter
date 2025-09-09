from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

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


def _clean_key(n: str) -> str:
    n = (n or "").strip()
    n = re.sub(r"\s+", " ", n)
    return n.lower()


def _first_last(name: str) -> str:
    if not name:
        return name
    parts = [p.strip() for p in name.split(",")]
    if len(parts) == 2:
        last, first = parts[0], parts[1]
        return f"{first} {last}"
    return name


def _ppk(points: float, salary: float):
    if salary and salary > 0:
        return round(points / (salary / 1000.0), 4)
    return None


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _salary_index_from_df(df: "pd.DataFrame"):
    if df is None or getattr(df, "empty", True):
        return {}, {}, {}
    name_to_salary, name_to_pos, name_to_team = {}, {}, {}
    df2 = df.copy()
    if "Salary" in df2.columns:
        df2["Salary"] = pd.to_numeric(df2["Salary"], errors="coerce")
    for _, r in df2.iterrows():
        nm = str(r.get("Name") or "").strip()
        if not nm: continue
        key = _clean_key(nm)
        sal = r.get("Salary")
        if sal is not None and pd.notna(sal):
            name_to_salary[key] = float(sal)
        pos = str(r.get("Pos") or "").strip()
        team = str(r.get("Team") or "").strip()
        if pos:
            name_to_pos[key] = pos
        if team:
            name_to_team[key] = team
    return name_to_salary, name_to_pos, name_to_team


def compute_values(salary_df, week_data: Dict[str, Any]) -> Dict[str, Any]:
    if pd is None:
        return {}

    name_to_salary, name_to_pos, name_to_team = _salary_index_from_df(salary_df)
    players_map = week_data.get("players_map") or {}
    wr = week_data.get("weekly_results") or {}
    wr_root = wr.get("weeklyResults") if isinstance(wr, dict) else None
    franchises = _as_list(wr_root.get("franchise") if isinstance(wr_root, dict) else None)

    starters: List[Dict[str, Any]] = []
    for fr in franchises:
        fid = fr.get("id") or "unknown"
        for p in _as_list(fr.get("player")):
            st = str(p.get("status") or "").lower()
            if st and st not in ("starter", "s"):
                continue
            pid = str(p.get("id") or "").strip()
            pts = _safe_float(p.get("score"), 0.0)

            # Resolve names: players_map → weekly node name → id
            pm = players_map.get(pid) or {}
            nm = pm.get("name") or p.get("name") or pid
            pos_hint = pm.get("pos") or p.get("position")
            team_hint = pm.get("team") or p.get("team")

            # Salary lookup by "Last, First" key
            key = _clean_key(pm.get("name") or "")
            salary = name_to_salary.get(key)
            pos = pos_hint or name_to_pos.get(key)
            team = team_hint or name_to_team.get(key)

            display_name = _first_last(nm)
            starters.append({
                "player_id": pid,
                "player": display_name,
                "pos": pos,
                "team": team,
                "salary": salary,
                "pts": pts,
                "franchise_id": fid,
                "ppk": _ppk(pts, salary) if salary else None,
            })

    # Dedupe top performers by player key
    perf: Dict[str, Dict[str, Any]] = {}
    for r in starters:
        key = (r.get("player") or "").lower() + "|" + (r.get("pos") or "")
        node = perf.setdefault(key, {
            "player": r.get("player"),
            "pos": r.get("pos"),
            "team": r.get("team"),
            "pts": 0.0,
            "franchise_ids": set(),
        })
        node["pts"] = max(node["pts"], r.get("pts") or 0.0)
        node["franchise_ids"].add(r.get("franchise_id"))

    top_performers = sorted(
        [{"player": v["player"], "pos": v["pos"], "team": v["team"], "pts": v["pts"], "franchise_ids": sorted(list(v["franchise_ids"]))}
         for v in perf.values()],
        key=lambda r: r["pts"],
        reverse=True
    )[:10]

    with_ppk = [r for r in starters if r.get("ppk") is not None]
    top_values = sorted(with_ppk, key=lambda r: (r["ppk"], r["pts"]), reverse=True)[:10]
    top_busts = sorted(with_ppk, key=lambda r: (r["ppk"], -r["pts"]))[:10]

    by_pos: Dict[str, List[Dict[str, Any]]] = {}
    for r in with_ppk:
        by_pos.setdefault((r.get("pos") or "UNK").upper(), []).append(r)
    for pos, rows in list(by_pos.items()):
        by_pos[pos] = sorted(rows, key=lambda r: r["ppk"], reverse=True)[:10]

    # Team efficiency
    team_stats: Dict[str, Dict[str, float]] = {}
    for r in starters:
        fid = r["franchise_id"]
        team_stats.setdefault(fid, {"pts": 0.0, "sal": 0.0})
        team_stats[fid]["pts"] += _safe_float(r["pts"], 0.0)
        if r.get("salary") is not None:
            team_stats[fid]["sal"] += float(r["salary"])
    team_eff = []
    for fid, agg in team_stats.items():
        total_pts = round(agg["pts"], 2)
        total_sal = int(agg["sal"]) if agg["sal"] else 0
        team_eff.append({"franchise_id": fid, "total_pts": total_pts, "total_sal": total_sal,
                         "ppk": _ppk(total_pts, agg["sal"]) if agg["sal"] else None})
    team_eff.sort(key=lambda r: (r["ppk"] or 0.0, r["total_pts"]), reverse=True)

    return {
        "top_values": top_values,
        "top_busts": top_busts,
        "by_pos": by_pos,
        "team_efficiency": team_eff,
        "top_performers": top_performers,
        "samples": {"starters": len(starters), "with_ppk": len(with_ppk)},
    }
