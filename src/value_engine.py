# src/value_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

import pandas as pd
from rapidfuzz import process, fuzz


@dataclass
class StarterRow:
    franchise_id: str
    player_id: str
    name: str
    pos: str
    team: str
    pts: float
    salary: int
    ppk: float  # points per $1K


def _to_name_first_last(name: str) -> str:
    if not isinstance(name, str):
        return ""
    nm = name.strip()
    if "," in nm:
        a, b = [p.strip() for p in nm.split(",", 1)]
        if a and b:
            nm = f"{b} {a}"
    return " ".join(nm.split())


def _norm_key(name: str, pos: str, team: str) -> Tuple[str, str, str]:
    return (name.strip().lower(), pos.strip().upper(), team.strip().upper())


def _build_salary_index(salary_df: pd.DataFrame) -> Dict[Tuple[str, str, str], int]:
    idx: Dict[Tuple[str, str, str], int] = {}
    for _, r in salary_df.iterrows():
        nm = _to_name_first_last(str(r.get("name", "")))
        pos = str(r.get("pos", "")).upper()
        team = str(r.get("team", "")).upper()
        sal = int(r.get("salary", 0) or 0)
        if nm:
            idx[_norm_key(nm, pos, team)] = sal
    return idx


def _fuzzy_lookup(
    name_key: Tuple[str, str, str],
    table: Dict[Tuple[str, str, str], int],
    cache: Dict[Tuple[str, str, str], int],
    score_cutoff: int = 88,
) -> Optional[int]:
    """
    Try exact first; otherwise fuzzy match on the name part with same POS.
    """
    if name_key in cache:
        return cache[name_key]
    if name_key in table:
        cache[name_key] = table[name_key]
        return table[name_key]

    name_lc, pos, team = name_key
    # limit candidates to same POS; if that fails, allow any POS
    same_pos = [k for k in table.keys() if k[1] == pos]
    search_space = same_pos if same_pos else list(table.keys())

    cand = process.extractOne(
        name_lc,
        [k[0] for k in search_space],
        scorer=fuzz.token_sort_ratio,
        score_cutoff=score_cutoff,
    )
    if not cand:
        return None
    matched_name, score, idx = cand  # type: ignore
    key = search_space[idx]
    cache[name_key] = table[key]
    return table[key]


def compute_values(
    salary_df: pd.DataFrame,
    players_map: Dict[str, Dict[str, Any]],
    starters_by_franchise: Dict[str, List[Dict[str, Any]]],
    franchise_names: Dict[str, str],
    week: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Returns:
      {
        "starters_with_salary": [StarterRow-like dicts],
        "team_efficiency": [{franchise_id, total_pts, total_sal, ppk}],
        "top_values": [dict],
        "top_busts": [dict]
      }
    """
    # Build a fast salary index
    sal_idx = _build_salary_index(salary_df)
    fuzzy_cache: Dict[Tuple[str, str, str], int] = {}

    starters_out: List[StarterRow] = []

    # Flatten starters and attach names/pos/team via players_map when needed
    for fid, items in (starters_by_franchise or {}).items():
        fid = str(fid).zfill(4)
        for it in items:
            pid = str(it.get("player_id") or it.get("id") or "")
            nm = it.get("player") or it.get("name") or ""
            if not nm and pid and pid in players_map:
                nm = players_map[pid].get("name") or ""
            pos = it.get("pos") or it.get("position") or ""
            if not pos and pid and pid in players_map:
                pos = players_map[pid].get("position") or ""
            team = it.get("team") or it.get("nflteam") or ""
            if not team and pid and pid in players_map:
                team = players_map[pid].get("team") or players_map[pid].get("nflteam") or ""

            nm = _to_name_first_last(nm)
            pos = str(pos).upper().strip()
            team = str(team).upper().strip()
            pts = float(it.get("pts") or it.get("points") or 0.0)

            # find salary
            key = _norm_key(nm, pos, team)
            sal = sal_idx.get(key)
            if sal is None:
                sal = _fuzzy_lookup(key, sal_idx, fuzzy_cache) or 0

            ppk = (pts / (sal / 1000.0)) if sal else 0.0

            starters_out.append(
                StarterRow(
                    franchise_id=fid,
                    player_id=pid,
                    name=nm,
                    pos=pos,
                    team=team,
                    pts=pts,
                    salary=int(sal or 0),
                    ppk=ppk,
                )
            )

    # Team efficiency
    by_team: Dict[str, Dict[str, Any]] = {}
    for row in starters_out:
        rec = by_team.setdefault(
            row.franchise_id, {"franchise_id": row.franchise_id, "total_pts": 0.0, "total_sal": 0}
        )
        rec["total_pts"] += row.pts
        rec["total_sal"] += row.salary
    team_eff: List[Dict[str, Any]] = []
    for fid, rec in by_team.items():
        sal = rec["total_sal"]
        ppk = (rec["total_pts"] / (sal / 1000.0)) if sal else 0.0
        team_eff.append(
            {
                "franchise_id": fid,
                "name": franchise_names.get(fid, fid),
                "total_pts": rec["total_pts"],
                "total_sal": int(sal),
                "ppk": ppk,
            }
        )
    team_eff.sort(key=lambda x: x["ppk"], reverse=True)

    # Value/bust boards
    # Filter to real-salary starters to avoid divide-by-zero artifacts
    paid = [s for s in starters_out if s.salary > 0]

    # Top values: high return; bias to mid/low salaries so we don’t only list elite studs
    top_values = sorted(
        paid, key=lambda s: (s.ppk, s.pts), reverse=True
    )[:15]

    # Top busts: price tags with disappointing pts/return
    bust_pool = [s for s in paid if s.salary >= 6000]  # only call it a bust if you actually paid up
    top_busts = sorted(
        bust_pool, key=lambda s: (s.ppk, s.pts)
    )[:15]  # low ppk rises to top (worst first)

    def _serialize(rows: List[StarterRow]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "player_id": r.player_id,
                    "player": r.name,
                    "pos": r.pos,
                    "team": r.team,
                    "pts": r.pts,
                    "salary": r.salary,
                    "ppk": r.ppk,
                    "franchise_id": r.franchise_id,
                    "franchise_name": franchise_names.get(r.franchise_id, r.franchise_id),
                }
            )
        return out

    return {
        "starters_with_salary": _serialize(starters_out),
        "team_efficiency": team_eff,
        "top_values": _serialize(top_values),
        # For busts, reverse so the *worst* are first in the table (lowest ppk)
        "top_busts": _serialize(list(sorted(top_busts, key=lambda x: x.ppk))),
    }
