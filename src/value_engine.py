from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

try:
    import pandas as pd
except Exception:
    pd = None

try:
    from rapidfuzz import process, fuzz
except Exception:
    process = None
    fuzz = None


def _as_list(x):
    if isinstance(x, list): return x
    if isinstance(x, dict): return [x]
    return []


def _clean_key(n: str) -> str:
    n = (n or "").strip()
    n = re.sub(r"[^A-Za-z0-9 ,.'-]+", " ", n)
    n = re.sub(r"\s+", " ", n)
    return n.lower()


def _first_last(name: str) -> str:
    if not name: return name
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
    try: return float(x)
    except Exception: return float(default)


def _salary_index_from_df(df: "pd.DataFrame"):
    if df is None or getattr(df, "empty", True):
        return {}, {}, {}

    # Accept common column names (Name/Player, Pos, Position)
    cols = {c.lower(): c for c in df.columns}
    name_col = cols.get("name") or cols.get("player") or "Name"
    pos_col = cols.get("pos") or cols.get("position") or "Pos"
    team_col = cols.get("team") or "Team"
    sal_col = cols.get("salary") or "Salary"

    df2 = df.copy()
    if sal_col in df2.columns:
        df2[sal_col] = pd.to_numeric(df2[sal_col], errors="coerce")

    name_to_salary, name_to_pos, name_to_team = {}, {}, {}

    for _, r in df2.iterrows():
        nm = str(r.get(name_col) or "").strip()
        if not nm: continue
        key_exact = _clean_key(nm)
        if "," in nm:
            last, first = [t.strip() for t in nm.split(",", 1)]
            key_fl = _clean_key(f"{first} {last}")
        else:
            key_fl = key_exact

        sal = r.get(sal_col)
        if sal is not None and (not pd or pd.isna(sal) is False):
            sal_val = float(sal)
            name_to_salary[key_exact] = sal_val
            name_to_salary.setdefault(key_fl, sal_val)

        pos = str(r.get(pos_col) or "").strip()
        if pos:
            name_to_pos[key_exact] = pos
            name_to_pos.setdefault(key_fl, pos)

        team = str(r.get(team_col) or "").strip()
        if team:
            name_to_team[key_exact] = team
            name_to_team.setdefault(key_fl, team)

    return name_to_salary, name_to_pos, name_to_team


def _rf_extract(name_key: str, keys, scorer, cutoff: int):
    if not process or not scorer: return None
    try:
        return process.extractOne(name_key, keys, scorer=scorer, score_cutoff=cutoff)
    except Exception:
        return None


def _fuzzy_lookup(name_key: str, table: Dict[str, float], cache: Dict[str, float],
                  primary_cutoff: int = 91, secondary_cutoff: int = 86) -> float | None:
    if not name_key or not table:
        return None
    if name_key in table:
        return table[name_key]

    res = _rf_extract(name_key, table.keys(), fuzz.token_sort_ratio if fuzz else None, primary_cutoff)
    if res:
        cand = res[0]
        cache[name_key] = table[cand]
        return table[cand]

    res2 = _rf_extract(name_key, table.keys(), fuzz.token_set_ratio if fuzz else None, secondary_cutoff)
    if res2:
        cand2 = res2[0]
        cache[name_key] = table[cand2]
        return table[cand2]
    return None


def _subset_then_fuzzy(name_key: str, pos: str, team: str,
                       name_to_salary: Dict[str, float],
                       name_to_pos: Dict[str, str],
                       name_to_team: Dict[str, str]) -> float | None:
    """
    If global fuzzy failed, try to constrain to rows with same pos/team
    and fuzzy match within that subset.
    """
    if not process or not fuzz or not name_to_salary:
        return None
    pos = (pos or "").upper()
    team = (team or "").upper()

    subset_keys = []
    for k in name_to_salary.keys():
        kp = (name_to_pos.get(k) or "").upper()
        kt = (name_to_team.get(k) or "").upper()
        if (pos and kp == pos) or (team and kt == team):
            subset_keys.append(k)
    if not subset_keys:
        return None

    res = _rf_extract(name_key, subset_keys, fuzz.token_sort_ratio, 80)
    if res: return name_to_salary[res[0]]
    res2 = _rf_extract(name_key, subset_keys, fuzz.token_set_ratio, 75)
    if res2: return name_to_salary[res2[0]]
    return None


def compute_values(salary_df, week_data: Dict[str, Any]) -> Dict[str, Any]:
    if pd is None:
        return {}

    name_to_salary, name_to_pos, name_to_team = _salary_index_from_df(salary_df)
    players_map = week_data.get("players_map") or {}

    wr = week_data.get("weekly_results") or {}
    wr_root = wr.get("weeklyResults") if isinstance(wr, dict) else None
    franchises = _as_list(wr_root.get("franchise") if isinstance(wr_root, dict) else None)

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

            pm = players_map.get(pid) or {}
            pm_name = pm.get("name") or (p.get("name") or "")
            display = _first_last(pm_name) if pm_name else pid

            # For salary matching we try both keys
            key_fl = _clean_key(display)           # first last
            key_raw = _clean_key(pm_name)          # possibly last, first

            # Pos/Team from players_map is most reliable
            pos = pm.get("pos") or p.get("position")
            team = pm.get("team") or p.get("team")

            salary = None
            # exact
            for k in (key_fl, key_raw):
                if k in name_to_salary:
                    salary = name_to_salary[k]; break
            # fuzzy across all
            if salary is None:
                salary = _fuzzy_lookup(key_fl, name_to_salary, fuzzy_cache)
            if salary is None and key_raw != key_fl:
                salary = _fuzzy_lookup(key_raw, name_to_salary, fuzzy_cache)
            # subset by pos/team if still None
            if salary is None:
                salary = _subset_then_fuzzy(key_fl, pos, team, name_to_salary, name_to_pos, name_to_team)
            if salary is None and key_raw != key_fl:
                salary = _subset_then_fuzzy(key_raw, pos, team, name_to_salary, name_to_pos, name_to_team)

            starters.append({
                "player_id": pid,
                "player": display,
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
