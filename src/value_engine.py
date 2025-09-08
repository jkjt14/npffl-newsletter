# src/value_engine.py
from __future__ import annotations

import math
from typing import Iterable, Optional, Sequence, Tuple

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


def _pick_proj_col(df: pd.DataFrame, explicit: Optional[str] = None) -> str:
    """
    Pick a projection column from the dataframe.
    Priority:
      1) explicit (if provided and present)
      2) first existing name from PROJ_COL_CANDIDATES
    Raises if none are found.
    """
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
    """Coerce to numeric safely (handles strings with commas/blank)."""
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


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
    """
    Attach salary to players_df by trying multiple join keys in priority order.

    Parameters
    ----------
    players_df : DataFrame
        Player stats / projections.
    salary_df : DataFrame
        Salary table for the given slate/week.
    on_priority : list of key-lists
        Ordered list of join key combinations to try until one succeeds.
    salary_col : str
        Column name in salary_df that contains the salary amount.

    Returns
    -------
    DataFrame
        players_df with a `Salary` column merged in (numeric).
    """
    if salary_col not in salary_df.columns:
        # Also try common variants
        for alt in ("salary", "SALARY", "Cost", "cost", "Price", "price"):
            if alt in salary_df.columns:
                salary_col = alt
                break
        else:
            raise KeyError(
                f"Salary column not found. Looked for '{salary_col}' "
                "and common variants (salary, SALARY, Cost, cost, Price, price)."
            )

    # Normalize salary numeric
    s = salary_df.copy()
    s["Salary"] = _coerce_numeric(s[salary_col])

    for keys in on_priority:
        if all(k in players_df.columns for k in keys) and all(k in s.columns for k in keys):
            merged = players_df.merge(s[keys + ("Salary",) if isinstance(keys, tuple) else list(keys) + ["Salary"]],
                                      on=list(keys), how="left", validate="m:1")
            # If we got a decent number of non-null salaries, accept this merge
            non_null = merged["Salary"].notna().sum()
            if non_null > 0:
                return merged

    # Fallback: attach nothing but keep shape (warn via NaN)
    out = players_df.copy()
    out["Salary"] = np.nan
    return out


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
      - (keeps projection column intact)

    Parameters
    ----------
    df : DataFrame
        Input with at least a projection column and Salary.
    proj_col : str, optional
        Name of projection column. If None, auto-detect.
    salary_col : str
        Salary column name (numeric or coercible).
    points_per_k_col : str
        Output column name for points per $1K (kept Python-safe).

    Returns
    -------
    DataFrame
        Copy of df with added value columns.
    """
    out = df.copy()

    if salary_col not in out.columns:
        raise KeyError(f"Missing salary column '{salary_col}' in dataframe.")

    pcol = _pick_proj_col(out, explicit=proj_col)

    out[salary_col] = _coerce_numeric(out[salary_col])
    out[pcol] = _coerce_numeric(out[pcol])

    # Avoid division by zero
    denom = out[salary_col] / 1000.0
    denom = denom.replace(0, np.nan)

    out[points_per_k_col] = out[pcol] / denom

    return out


def leaderboard_values(
    df: pd.DataFrame,
    *,
    groupby: Iterable[str] = ("Pos",),
    proj_col: Optional[str] = None,
    points_per_k_col: str = "Pts_per_K",
) -> pd.DataFrame:
    """
    Produce a compact leaderboard of value metrics by group (e.g., by position).

    Outputs columns (example):
      - Count
      - Avg_Salary
      - Median_Salary
      - Avg_Proj
      - Median_Proj
      - Max_Proj
      - Avg_Pts_per_$K  <-- human-friendly label, backed by points_per_k_col

    Parameters
    ----------
    df : DataFrame
        Input containing projection column, Salary, and points_per_k_col (if not, call compute_value first).
    groupby : Iterable[str]
        Columns to group by (e.g., ("Pos",) or ("Team",), etc.).
    proj_col : str, optional
        Projection column to aggregate. Auto-detected if None.
    points_per_k_col : str
        Python-safe per-$K column (computed by compute_value).

    Returns
    -------
    DataFrame
        Aggregated leaderboard with friendly column names (no Python syntax hazards).
    """
    if not isinstance(groupby, (list, tuple)):
        groupby = list(groupby)

    if any(col not in df.columns for col in groupby):
        missing = [c for c in groupby if c not in df.columns]
        raise KeyError(f"Groupby columns missing from dataframe: {missing}")

    if "Salary" not in df.columns:
        raise KeyError("Expected 'Salary' in dataframe. Did you run attach_salary()?")

    pcol = _pick_proj_col(df, explicit=proj_col)
    if points_per_k_col not in df.columns:
        # Compute if not present
        df = compute_value(df, proj_col=pcol, salary_col="Salary", points_per_k_col=points_per_k_col)

    g = df.groupby(list(groupby), dropna=False)

    # Use dict-based agg to avoid keyword-name parsing issues with '$'
    agg_map = {
        "Salary": ["count", "mean", "median"],
        pcol: ["mean", "median", "max"],
        points_per_k_col: ["mean"],
    }

    agg = g.agg(agg_map)

    # Flatten MultiIndex columns
    agg.columns = ["_".join([c for c in map(str, col) if c and c != "<lambda>"]).strip("_") for col in agg.columns]
    agg = agg.reset_index()

    # Rename to human-friendly labels (including $), but only in final output
    rename_map = {
        "Salary_count": "Count",
        "Salary_mean": "Avg_Salary",
        "Salary_median": "Median_Salary",
        f"{pcol}_mean": "Avg_Proj",
        f"{pcol}_median": "Median_Proj",
        f"{pcol}_max": "Max_Proj",
        f"{points_per_k_col}_mean": "Avg_Pts_per_$K",  # friendly label with $
    }
    agg = agg.rename(columns=rename_map)

    # Order columns nicely if all present
    desired_order = list(groupby) + [
        "Count",
        "Avg_Salary",
        "Median_Salary",
        "Avg_Proj",
        "Median_Proj",
        "Max_Proj",
        "Avg_Pts_per_$K",
    ]
    existing = [c for c in desired_order if c in agg.columns]
    remainder = [c for c in agg.columns if c not in existing]
    agg = agg[existing + remainder]

    return agg


# Optional: tiny helper for ranking best values within each position/team/etc.
def rank_value_within_group(
    df: pd.DataFrame,
    *,
    groupby: Iterable[str] = ("Pos",),
    value_col: str = "Pts_per_K",
    rank_col: str = "Value_Rank",
    ascending: bool = False,
) -> pd.DataFrame:
    """
    Rank players by value within group (default: by Pos). Lower rank is better when ascending=False.

    Parameters
    ----------
    df : DataFrame
        Must include value_col.
    groupby : Iterable[str]
        Grouping columns.
    value_col : str
        Column to rank (default: per-$K).
    rank_col : str
        Output rank column name.
    ascending : bool
        True = worst to best; False = best to worst.

    Returns
    -------
    DataFrame
        Copy with rank column added.
    """
    if value_col not in df.columns:
        raise KeyError(f"Missing '{value_col}'. Did you call compute_value()?")

    out = df.copy()
    out[rank_col] = (
        out.groupby(list(groupby), dropna=False)[value_col]
        .rank(method="dense", ascending=ascending)
        .astype("Int64")
    )
    return out
