from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

try:
    import pandas as pd
except Exception:
    pd = None

# rapidfuzz is in requirements; guard import
try:
    from rapidfuzz import process, fuzz
except Exception:
    process = None
    fuzz = None


# -----------------------
# small utils
# -----------------------
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


# -----------------------
# salary indexing
# -----------------------
_ID_CANDIDATES = ["id", "playerid", "mfl_id", "player id", "mfl id"]

def _detect_col(df: "pd.DataFrame", *cands: str) -> str | None:
    cols = {c.lower(): c for c in df.columns}
    for c in cands:
        if c in cols: return cols[c]
    return None

def _salary_index_from_df(df: "pd.DataFrame"):
    """
    Build multiple indices:
      - id_to_row: {player_id_str: row dict}
      - name_to_salary / name_to_pos / name_to_team for name-based fallback
    Accepts flexible column headers.
    """
    if df is None or getattr(df, "empty", True):
        return {}, {}, {}, {}, {}

    # flexible headers
    id_col   = _detect_col(df, *_ID_CANDIDATES)
    name_col = _detect_col(df, "name", "player")
    pos_col  = _detect_col(df, "pos", "position")
    team_col = _detect_col(df, "team", "nfl", "nfl team")
    sal_col  = _detect_col(df, "salary", "sal", "cost")

    df2 = df.copy()

    if sal_col and sal_col in df2.columns:
        df2[sal_col] = pd.to_numeric(df2[sal_col], errors="coerce")

    id_to_row: Dict[str, Dict[str, Any]] = {}
    name_to_salary: Dict[str, float] = {}
    name_to_pos: Dict[str, str] = {}
    name_to_team: Dict[str, str] = {}

    for _, r in df2.iterrows():
        nm_raw = str(r.get(name_col) or "").strip() if name_col else ""
        nm_fl  = _first_last(nm_raw) if nm_raw else ""
        key_exact = _clean_key(nm_raw)
        key_fl    = _clean_key(nm_fl) if nm_fl else key_exact

        pos  = str(r.get(pos_col) or "").strip() if pos_col else ""
        team = str(r.get(team_col) or "").strip() if team_col else ""
        sal  = r.get(sal_col) if sal_col else None
        salf = float(sal) if sal is not None and (not pd or pd.isna(sal) is False) else None

        # name-based maps
        if salf is not None:
            if key_exact: name_to_salary[key_exact] = salf
            if key_fl:    name_to_salary.setdefault(key_fl, salf)
        if pos:
            if key_exact: name_to_pos[key_exact] = pos
            if key_fl:    name_to_pos.setdefault(key_fl, pos)
        if team:
            if key_exact: name_to_team[key_exact] = team
            if key_fl:    name_to_team.setdefault(key_fl, team)

        # id-based direct index (most reliable)
        if id_col:
            pid_raw = r.get(id_col)
            if pid_raw is not None and (not pd or pd.isna(pid_raw) is False):
                pid = str(pid_raw).strip()
                if pid:
                    id_to_row[pid] = {
                        "name_raw": nm_raw,
                        "name_fl": nm_fl or nm_raw,
                        "pos": pos,
                        "team": team,
                        "salary": salf,
                    }

    return id_to_row, name_to_salary, name_to_pos, name_to_team, {
        "cols": {"id": id_col, "name": name_col, "pos": pos_col, "team": team_col, "sal": sal_col}
    }


# -----------------------
# fuzzy helpers
# -----------------------
def _rf_extract(name_key: str, keys, scorer, cutoff: int):
    if not process or not scorer: return None
    try:
        return process.extractOne(name_key, keys, scorer=scorer, score_cutoff=cutoff)
    except Exception:
        return None

def _subset_then_fuzzy(name_key: str, pos: str, team: str,
                       name_to_salary: Dict[str, float],
                       name_to_pos: Dict[str, str],
                       name_to_team: Dict[str, str]) -> float | None:
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

    res = _rf_extract(name_key, subset_keys, fuzz.token_sort_ratio, 82)
    if res: return name_to_salary[res[0]]
    res2 = _rf_extract(name_key, subset_keys, fuzz.token_set_ratio, 78)
    if res2: return name_to_salary[res2[0]]
    return None

def _fuzzy_lookup(name_key: str, table: Dict[str, float], primary_cutoff=91, secondary_cutoff=86) -> float | None:
    if not name_key or not table or not process or not fuzz:
        return None
    res = _rf_extract(name_key, table.keys(), fuzz.token_sort_ratio, primary_cutoff)
    if res:  return table[res[0]]
    res2 = _rf_extract(name_key, table.keys(), fuzz.token_set_ratio, secondary_cutoff)
    if res2: return table[res2[0]]
    return None


# -----------------------
# main
# -----------------------
def compute_values(salary_df, week_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Priority:
      1) If salary sheet has an ID column, map starters by player_id -> (name,pos,team,salary)
      2) Else try exact name (First Last & Last, First), then fuzzy, then pos/team-constrained fuzzy
    """
    if pd is None:
        return {}

    id_to_row, name_to_salary, name_to_pos, name_to_team, _meta = _salary_index_from_df(salary_df)
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

            # --- ID-FIRST: if we have the row, we trust it completely
            row = id_to_row.get(pid)
            if row:
                display = _first_last(row.get("name_fl") or row.get("name_raw") or "")
                pos = row.get("pos")
                team = row.get("team")
                salary = row.get("salary")
            else:
                # Fallback to players_map + name-based salary matching
                pm = players_map.get(pid) or {}
                pm_name = pm.get("name") or (p.get("name") or "")
                display = _first_last(pm_name) if pm_name else pid
                pos = pm.get("pos") or p.get("position")
                team = pm.get("team") or p.get("team")

                key_fl = _clean_key(display)
                key_raw = _clean_key(pm_name)

                # Prefer subset-by-pos/team first (tighter)
                salary = _subset_then_fuzzy(key_fl, pos, team, name_to_salary, name_to_pos, name_to_team)
                if salary is None and key_raw != key_fl:
                    salary = _subset_then_fuzzy(key_raw, pos, team, name_to_salary, name_to_pos, name_to_team)
                # Exact names
                if salary is None:
                    for k in (key_fl, key_raw):
                        if k in name_to_salary:
                            salary = name_to_salary[k]; break
                # Loose fuzzy
                if salary is None:
                    salary = _fuzzy_lookup(key_fl, name_to_salary)
                if salary is None and key_raw != key_fl:
                    salary = _fuzzy_lookup(key_raw, name_to_salary)

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

    # Busts = worst ppk (lowest first). Keep 10.
    top_busts = sorted(with_ppk, key=lambda r: (r["ppk"], -r["pts"]))[:10]

    # By-position leaders (top 10 by ppk)
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
        team_eff.append({
            "franchise_id": fid,
            "total_pts": total_pts,
            "total_sal": total_sal,
            "ppk": _ppk(total_pts, agg["sal"]) if agg["sal"] else None
        })
    team_eff.sort(key=lambda r: ((r["ppk"] or 0.0), r["total_pts"]), reverse=True)

    return {
        "top_values": top_values,
        "top_busts": top_busts,
        "by_pos": by_pos,
        "team_efficiency": team_eff,
        "top_performers": top_performers,
        "samples": {"starters": len(starters), "with_ppk": len(with_ppk)},
    }
