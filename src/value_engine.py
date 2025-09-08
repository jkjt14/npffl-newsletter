# src/value_engine.py
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple, List
import numpy as np
import pandas as pd

# Candidate projection column names we’ll accept in input data
PROJ_COL_CANDIDATES: Tuple[str, ...] = (
    "PROJ. FPTS",
    "Proj",
    "ProjectedPoints",
    "Projected_Points",
    "FPTS",
    "Projected",
    "Points",
)

# ---------- small helpers ----------

def _pick_proj_col(df: pd.DataFrame, explicit: Optional[str] = None) -> str:
    if explicit and explicit in df.columns:
        return explicit
    for c in PROJ_COL_CANDIDATES:
        if c in df.columns:
            return c
    raise KeyError(
        "Could not find a projection column. "
        f"Tried: {', '.join(PROJ_COL_CANDIDATES)}. "
        f"Available columns: {list(df.columns)}"
    )

def _coerce_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")

def _ensure_cols(df: pd.DataFrame, cols_defaults: List[Tuple[str, object]]) -> pd.DataFrame:
    """
    Ensure columns exist; if missing, create with given default value.
    Returns a copy.
    """
    out = df.copy()
    for c, default in cols_defaults:
        if c not in out.columns:
            out[c] = default
    return out

def _pick_name_col(df: pd.DataFrame) -> str:
    for c in ("Name", "Player", "Player Name", "FullName", "PlayerName"):
        if c in df.columns:
            return c
    # If nothing reasonable, create a synthetic name column name for downstream selection
    return None

# ---------- salary attach ----------

def attach_salary(
    players_df: pd.DataFrame,
    salary_df: pd.DataFrame,
    *,
    on_priority: Sequence[Sequence[str]] = (
        ("player_id",),
        ("Name", "Team", "Pos"),
        ("Name", "Pos"),
        ("Name",),
    ),
    salary_col: str = "Salary",
) -> pd.DataFrame:
    if salary_col not in salary_df.columns:
        for alt in ("salary", "SALARY", "Cost", "cost", "Price", "price"):
            if alt in salary_df.columns:
                salary_col = alt
                break
        else:
            raise KeyError(
                f"Salary column not found. Looked for '{salary_col}' "
                "and common variants (salary, SALARY, Cost, cost, Price, price)."
            )

    s = salary_df.copy()
    s["Salary"] = _coerce_numeric(s[salary_col])

    for keys in on_priority:
        if all(k in players_df.columns for k in keys) and all(k in s.columns for k in keys):
            merged = players_df.merge(
                s[list(keys) + ["Salary"]],
                on=list(keys),
                how="left",
                validate="m:1",
            )
            if merged["Salary"].notna().any():
                return merged

    out = players_df.copy()
    out["Salary"] = np.nan
    return out

# ---------- value metrics ----------

def compute_value(
    df: pd.DataFrame,
    *,
    proj_col: Optional[str] = None,
    salary_col: str = "Salary",
    points_per_k_col: str = "Pts_per_K",
) -> pd.DataFrame:
    """
    Compute per-dollar value metrics.

    Adds:
      - Pts_per_K: projected points per $1,000 of salary
      - Keeps/creates projection column if missing (filled with NaN)
    """
    out = df.copy()

    if salary_col not in out.columns:
        raise KeyError(f"Missing salary column '{salary_col}' in dataframe.")

    # Find or create a projection column
    try:
        pcol = _pick_proj_col(out, explicit=proj_col)
    except KeyError as e:
        pcol = "ProjectedPoints"
        if pcol not in out.columns:
            out[pcol] = np.nan
        print(
            f"[value_engine] WARNING: {e}. Created placeholder '{pcol}' with NaN values.",
            flush=True,
        )

    out[salary_col] = _coerce_numeric(out[salary_col])
    out[pcol] = _coerce_numeric(out[pcol])

    denom = (out[salary_col] / 1000.0).replace(0, np.nan)
    out[points_per_k_col] = out[pcol] / denom
    return out

# ---------- leaderboards ----------

def _aggregate_by(
    df: pd.DataFrame,
    group_cols: List[str],
    *,
    proj_col: Optional[str],
    points_per_k_col: str,
) -> pd.DataFrame:
    """
    Aggregate by group_cols into summary stats and return a tidy dataframe
    with friendly labels (Avg_Pts_per_$K, etc.). If group_cols are empty,
    produce a single 'All' group.
    """
    if not group_cols:
        df = df.copy()
        df["All"] = "All"
        group_cols = ["All"]

    # ensure value columns exist
    df = compute_value(df, proj_col=proj_col, salary_col="Salary", points_per_k_col=points_per_k_col)

    # figure out projection column name now present
    try:
        pcol = _pick_proj_col(df, explicit=proj_col)
    except KeyError:
        pcol = "ProjectedPoints"

    g = df.groupby(group_cols, dropna=False)
    agg_map = {
        "Salary": ["count", "mean", "median"],
        pcol: ["mean", "median", "max"],
        points_per_k_col: ["mean"],
    }
    agg = g.agg(agg_map)
    agg.columns = ["_".join([c for c in map(str, col) if c and c != "<lambda>"]).strip("_") for col in agg.columns]
    agg = agg.reset_index()

    rename_map = {
        "Salary_count": "Count",
        "Salary_mean": "Avg_Salary",
        "Salary_median": "Median_Salary",
        f"{pcol}_mean": "Avg_Proj",
        f"{pcol}_median": "Median_Proj",
        f"{pcol}_max": "Max_Proj",
        f"{points_per_k_col}_mean": "Avg_Pts_per_$K",
    }
    agg = agg.rename(columns=rename_map)

    # Order columns
    desired = group_cols + [
        "Count",
        "Avg_Salary",
        "Median_Salary",
        "Avg_Proj",
        "Median_Proj",
        "Max_Proj",
        "Avg_Pts_per_$K",
    ]
    existing = [c for c in desired if c in agg.columns]
    remainder = [c for c in agg.columns if c not in existing]
    agg = agg[existing + remainder]
    return agg

def leaderboard_values(
    df: pd.DataFrame,
    *,
    groupby: Iterable[str] = ("Pos",),
    proj_col: Optional[str] = None,
    points_per_k_col: str = "Pts_per_K",
    top_n: int = 10,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Return four leaderboards expected by main.py:
      (best_ind, worst_ind, team_best, team_worst)

    - Robust to missing columns:
        * If 'Pos' missing, uses a synthetic 'ALL' Pos.
        * If 'Team' missing, uses synthetic 'FA'.
    - Robust to empty frames: returns empty but correctly-shaped outputs.
    """
    # If df is empty or only Salary exists, still compute_value to add Pts_per_K/ProjectedPoints
    base = compute_value(df if df is not None else pd.DataFrame(), proj_col=proj_col)

    # Ensure standard columns exist for ranking/selection
    name_col = _pick_name_col(base)
    sel_cols = []
    if name_col:
        sel_cols.append(name_col)
    base = _ensure_cols(base, [
        ("Team", "FA"),
        ("Pos", "ALL"),
        ("Salary", np.nan),
        ("ProjectedPoints", np.nan),   # may already exist; harmless
        ("Pts_per_K", np.nan),
    ])

    # --- best/worst individuals by value ---
    sortable = base.copy()
    # safer replace inf with NaN to avoid weird ordering
    sortable["Pts_per_K"] = pd.to_numeric(sortable["Pts_per_K"], errors="coerce").replace([np.inf, -np.inf], np.nan)

    cols_for_ind = (sel_cols + ["Team", "Pos", "Salary", "ProjectedPoints", "Pts_per_K"])
    cols_for_ind = [c for c in cols_for_ind if c in sortable.columns]

    best_ind = (
        sortable.sort_values("Pts_per_K", ascending=False, na_position="last")
        .head(top_n)[cols_for_ind]
        .reset_index(drop=True)
    )
    worst_ind = (
        sortable.sort_values("Pts_per_K", ascending=True, na_position="last")
        .head(top_n)[cols_for_ind]
        .reset_index(drop=True)
    )

    # --- team aggregates (best/worst) ---
    team_agg = _aggregate_by(base, ["Team"], proj_col=proj_col, points_per_k_col=points_per_k_col)
    # when Team was synthetic 'FA' for all rows, this still returns one-row summary
    team_best = team_agg.sort_values("Avg_Pts_per_$K", ascending=False, na_position="last").head(top_n).reset_index(drop=True)
    team_worst = team_agg.sort_values("Avg_Pts_per_$K", ascending=True,  na_position="last").head(top_n).reset_index(drop=True)

    # Ensure all four outputs exist even if df was empty
    for out in (best_ind, worst_ind, team_best, team_worst):
        # nothing to do; already DataFrames
        pass

    return best_ind, worst_ind, team_best, team_worst

# ---------- optional: intra-group ranking ----------

def rank_value_within_group(
    df: pd.DataFrame,
    *,
    groupby: Iterable[str] = ("Pos",),
    value_col: str = "Pts_per_K",
    rank_col: str = "Value_Rank",
    ascending: bool = False,
) -> pd.DataFrame:
    if value_col not in df.columns:
        raise KeyError(f"Missing '{value_col}'. Did you call compute_value()?")

    if not isinstance(groupby, (list, tuple)):
        groupby = list(groupby)

    out = df.copy()
    out[rank_col] = (
        out.groupby(list(groupby), dropna=False)[value_col]
        .rank(method="dense", ascending=ascending)
        .astype("Int64")
    )
    return out
