from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import math

try:
    import pandas as pd
except Exception:  # keep pipeline green even if pandas not present for some reason
    pd = None

try:
    from rapidfuzz import process, fuzz  # optional fuzzy matcher
except Exception:
    process = None
    fuzz = None


# -----------------------------
# Utilities
# -----------------------------

def _as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x]
    return []


def _norm_colnames(df):
    return {c.lower(): c for c in df.columns}


def _safe_num(x, default=0.0) -> float:
    try:
        if x is None or (isinstance(x, str) and x.strip() == ""):
            return float(default)
        return float(x)
    except Exception:
        return float(default)


def _ppk(points: float, salary: float) -> Optional[float]:
    if salary and salary > 0:
        return round(points / (salary / 1000.0), 4)
    return None


def _best_effort_player_lookup(
    player_id: str,
    player_id_to_name: Dict[str, str],
    salary_df_names: List[str],
    salary_lookup: Dict[str, float],
) -> Tuple[str, Optional[float]]:
    """
    Returns (name, salary) using:
      1) direct name via playerScores mapping (id->name)
      2) fuzzy match name -> salary_df
      3) fallback (id-str, None)
    """
    # Direct (if we have name by ID)
    name = player_id_to_name.get(player_id)
    if name:
        # exact name match to salary sheet
        sal = salary_lookup.get(name.lower())
        if sal is not None:
            return name, sal
        # fuzzy match if available
        if process and salary_df_names:
            match = process.extractOne(name, salary_df_names, scorer=fuzz.WRatio)
            if match and match[1] >= 88:  # reasonably strict
                matched_name = match[0]
                sal = salary_lookup.get(matched_name.lower())
                return matched_name, sal
        return name, None

    # no name → cannot fuzzy; fall back to ID
    return player_id, None


# -----------------------------
# Core
# -----------------------------

def compute_values(salary_df, week_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Produce:
      - top_values (list of dicts)
      - top_busts (list of dicts)
      - per_pos buckets if position is known
    Uses starter players from weeklyResults and their points.
    Salary source: salary_df
      - Preferred columns: 'Player' (or 'Name'), 'Pos'/'Position', 'Team', 'Salary'
      - Optional: 'MFL_ID' for direct ID joins
    Name resolution:
      - First try MFL_ID
      - Then try mapping from playerScores to get a 'name' for id
      - Then fuzzy match to salary names
    """

    # Defensive: if pandas missing or no salary_df, we still render from starters with None salaries
    if pd is None:
        return {}

    # Normalize salary df
    salary_lookup: Dict[str, float] = {}
    pos_lookup: Dict[str, str] = {}
    team_lookup: Dict[str, str] = {}
    id_to_salary: Dict[str, float] = {}

    if salary_df is not None and not getattr(salary_df, "empty", True):
        cols = _norm_colnames(salary_df)
        name_col = cols.get("player") or cols.get("name")
        pos_col = cols.get("pos") or cols.get("position")
        team_col = cols.get("team")
        salary_col = cols.get("salary")
        id_col = cols.get("mfl_id") or cols.get("id")

        df = salary_df.copy()
        if salary_col:
            df[salary_col] = pd.to_numeric(df[salary_col], errors="coerce")

        for _, r in df.iterrows():
            n = (str(r[name_col]).strip() if name_col in df.columns else None) if name_col else None
            s = float(r[salary_col]) if (salary_col and not pd.isna(r.get(salary_col))) else None
            p = (str(r[pos_col]).strip() if pos_col in df.columns else None) if pos_col else None
            t = (str(r[team_col]).strip() if team_col in df.columns else None) if team_col else None
            pid = (str(r[id_col]).strip() if id_col in df.columns else None) if id_col else None
            if n:
                salary_lookup[n.lower()] = s if s is not None else None
                if p:
                    pos_lookup[n.lower()] = p
                if t:
                    team_lookup[n.lower()] = t
            if pid and s is not None:
                id_to_salary[pid] = s

    # Map player_id -> name from playerScores if present
    player_id_to_name: Dict[str, str] = {}
    ps = week_data.get("player_scores")
    if isinstance(ps, dict):
        ps_root = ps.get("playerScores") or {}
        for pnode in _as_list(ps_root.get("player")):
            pid = str(pnode.get("id", "")).strip()
            nm = pnode.get("name")  # some leagues include 'name' — not guaranteed
            if nm:
                player_id_to_name[pid] = str(nm).strip()

    # Collect starters from weeklyResults
    starters: List[Dict[str, Any]] = []
    wr = week_data.get("weekly_results") or {}
    wr_root = wr.get("weeklyResults") if isinstance(wr, dict) else None
    for fr in _as_list(wr_root.get("franchise") if isinstance(wr_root, dict) else None):
        fid = str(fr.get("id") or "unknown")
        for p in _as_list(fr.get("player")):
            # Many exports only include starters; if a 'status' exists, prefer status=="starter"
            status = str(p.get("status") or "").lower()
            if status and status not in ("starter", "s"):
                continue
            pid = str(p.get("id") or "").strip()
            pts = _safe_num(p.get("score"), 0)
            starters.append({"franchise_id": fid, "player_id": pid, "pts": pts})

    # Enrich starters with names, positions, salaries
    salary_names_list = list(salary_lookup.keys())
    enriched: List[Dict[str, Any]] = []
    for row in starters:
        pid = row["player_id"]
        pts = row["pts"]

        # Prefer direct ID->salary (if salary sheet had MFL_ID)
        sal = id_to_salary.get(pid)

        # Resolve a name and/or salary via mapping/fuzzy
        name, sal2 = _best_effort_player_lookup(pid, player_id_to_name, salary_names_list, salary_lookup)
        if sal is None:
            sal = sal2

        # get pos/team if we resolved to a name
        nmkey = name.lower() if isinstance(name, str) else None
        pos = pos_lookup.get(nmkey) if nmkey else None
        team = team_lookup.get(nmkey) if nmkey else None

        enriched.append(
            {
                "player": name or pid,
                "pos": pos,
                "team": team,
                "salary": sal,
                "pts": pts,
                "franchise_id": row["franchise_id"],
                "ppk": _ppk(pts, sal) if sal else None,
            }
        )

    # Filter to those with some salary info when ranking value; still include unknowns in tails if needed
    with_ppk = [x for x in enriched if x.get("ppk") is not None]
    without_ppk = [x for x in enriched if x.get("ppk") is None]

    # Rank values/busts
    top_values = sorted(with_ppk, key=lambda r: (r["ppk"], r["pts"]), reverse=True)[:10]
    top_busts = sorted(with_ppk, key=lambda r: (r["ppk"], -r["pts"]))[:10]

    # Position buckets (best per position by P/$1K)
    pos_buckets: Dict[str, List[Dict[str, Any]]] = {}
    for r in with_ppk:
        pos = (r.get("pos") or "UNK").upper()
        pos_buckets.setdefault(pos, []).append(r)
    for pos, rows in list(pos_buckets.items()):
        pos_buckets[pos] = sorted(rows, key=lambda r: r["ppk"], reverse=True)[:10]

    return {
        "top_values": top_values,
        "top_busts": top_busts,
        "by_pos": pos_buckets,
        "samples": {
            "with_ppk": len(with_ppk),
            "without_ppk": len(without_ppk),
            "total_starters": len(enriched),
        },
    }
