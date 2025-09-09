from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

try:
    import pandas as pd
except Exception:
    pd = None

# rapidfuzz is in requirements; still guard against import errors
try:
    from rapidfuzz import process, fuzz
except Exception:
    process = None
    fuzz = None


def _as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x]
    return []


def _clean_key(n: str) -> str:
    n = (n or "").strip()
    n = re.sub(r"[^A-Za-z0-9 ,.'-]+", " ", n)
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
        if not nm:
            continue
        # store both "Last, First" and "First Last" keys for easier matching
        key_exact = _clean_key(nm)
        if "," in nm:
            last, first = [t.strip() for t in nm.split(",", 1)]
            key_fl = _clean_key(f"{first} {last}")
        else:
            key_fl = key_exact

        sal = r.get("Salary")
        if sal is not None and (not pd or pd.isna(sal) is False):
            sal_val = float(sal)
            name_to_salary[key_exact] = sal_val
            name_to_salary.setdefault(key_fl, sal_val)

        pos = str(r.get("Pos") or "").strip()
        team = str(r.get("Team") or "").strip()
        if pos:
            name_to_pos[key_exact] = pos
            name_to_pos.setdefault(key_fl, pos)
        if team:
            name_to_team[key_exact] = team
            name_to_team.setdefault(key_fl, team)

    return name_to_salary, name_to_pos, name_to_team


def _fuzzy_lookup(name_key: str, table: Dict[str, float], cache: Dict[str, float],
                  primary_cutoff: int = 91, secondary_cutoff: int = 86) -> float | None:
    """
    Defensive fuzzy finder:
      1) exact key in table
      2) rapidfuzz token_sort_ratio with cutoff
      3) token_set_ratio a bit looser
    Returns None if no decent match.
    """
    if not name_key:
        return None
    if name_key in table:
        return table[name_key]

    if not process or not fuzz or not table:
        return None

    # Primary attempt
    try:
        res = process.extractOne(
            name_key, table.keys(),
            scorer=fuzz.token_sort_ratio,
            score_cutoff=primary_cutoff
        )
    except Exception:
        res = None

    if res:
        # res is (candidate, score, idx) in rapidfuzz >= 2.0
        cand = res[0]
        cache[name_key] = table[cand]
        return table[cand]

    # Secondary attempt (looser & different scorer)
    try:
        res2 = process.extractOne(
            name_key, table.keys(),
            scorer=fuzz.token_set_ratio,
            score_cutoff=secondary_cutoff
        )
    except Exception:
        res2 = None

    if res2:
        cand2 = res2[0]
        cache[name_key] = table[cand2]
        return table[cand2]

    return None


def compute_values(salary_df, week_data: Dict[str, Any]) -> Dict[str, Any]:
    if pd is None:
        return {}

    name_to_salary, name_to_pos, name_to_team = _salary_index_from_df(salary_df)
    players_map = week_data.get("players_map") or {}

    wr = week_data.get("weekly_results") or {}
    wr_root = wr.get("weeklyResults") if isinstance(wr, dict) else None
    franchises = _as_list(wr_root.get("franchise") if isinstance(wr_root, dict) else None)

    # For fuzzy caching
    fuzzy_cache: Dict[str, float] = {}

    starters: List[Dict[str, Any]] = []
    for fr in franchises:
        fid = fr.get("id") or "unknown"
        for p in _as_list(fr.get("player")):
            st = str(p.get("status") or "").lower()
            if st and st not in ("starter", "s"):
                continue
            pid = str(p.get("id") or "").strip()
            pts = _safe_float(p.get("score"), 0.0)

            # Resolve to First Last for display
            pm = players_map.get(pid) or {}
            pm_name = pm.get("name") or (p.get("name") or "")
            display_name = _first_last(pm_name)

            # Build lookup keys
            key_fl = _clean_key(display_name)              # "first last"
            key_raw = _clean_key(pm_name)                  # might be "last, first"

            # salary match: exact → fuzzy (twice) on both keys
            salary = None
            for key in (key_fl, key_raw):
                salary = name_to_salary.get(key)
                if salary is not None:
                    break
            if salary is None:
                salary = _fuzzy_lookup(key_fl, name_to_salary, fuzzy_cache)
            if salary is None and key_raw != key_fl:
                salary = _fuzzy_lookup(key_raw, name_to_salary, fuzzy_cache)

            # position / team
            pos = pm.get("pos") or name_to_pos.get(key_fl) or name_to_pos.get(key_raw) or p.get("position")
            team = pm.get("team") or name_to_team.get(key_fl) or name_to_team.get(key_raw) or p.get("team")

            starters.append({
                "player_id": pid,
                "player": display_name or pid,
                "pos": pos,
                "team": team,
                "salary": salary,
                "pts": pts,
                "franchise_id": fid,
                "ppk": _ppk(pts, salary) if salary else None,
            })

    # Aggregate top performers (dedupe by player+pos)
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
    team_eff.sort(key=lambda r: ((r["ppk"] or 0.0), r["total_pts"]), reverse=True)

    return {
        "top_values": top_values,
        "top_busts": top_busts,
        "by_pos": by_pos,
        "team_efficiency": team_eff,
        "top_performers": top_performers,
        "samples": {"starters": len(starters), "with_ppk": len(with_ppk)},
    }
