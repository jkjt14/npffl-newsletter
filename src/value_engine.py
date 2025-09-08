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
    Returns players_df with a `Salary` column merged in (numeric).
    """
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
      - (keeps/creates projection column)

    Tolerant behavior:
      - If no projection column is present, a placeholder 'ProjectedPoints' is created
        filled with NaN and used to compute NaN Pts_per_K (pipeline keeps running).
    """
    out = df.copy()

    if salary_col not in out.columns:
        raise KeyError(f"Missing salary column '{salary_col}' in dataframe.")

    # Find or create a projection column
    try:
        pcol = _pick_proj_col(out, explicit=proj_col)
    except KeyError as e:
        # Create a placeholder to keep pipeline alive
        pcol = "ProjectedPoints"
        if pcol not in out.columns:
            out[pcol] = np.nan
        print(
            f"[value_engine] WARNING: {e}. Created placeholder '{pcol}' with NaN values.",
            flush=True,
        )

    out[salary_col] = _coerce_numeric(out[salary_col])
    out[pcol] = _coerce_numeric(out[pcol])

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
    Outputs human-friendly labels; internally keeps Python-safe names.
    """
    if not isinstance(groupby, (list, tuple)):
        groupby = list(groupby)

    if any(col not in df.columns for col in groupby):
        missing = [c for c in groupby if c not in df.columns]
        raise KeyError(f"Groupby columns missing from dataframe: {missing}")

    if "Salary" not in df.columns:
        raise KeyError("Expected 'Salary' in dataframe. Did you run attach_salary()?")

    # Ensure value column exists (and projection col resolves, creating placeholder if needed)
    df = compute_value(df, proj_col=proj_col, salary_col="Salary", points_per_k_col=points_per_k_col)

    # After compute_value, determine the resolved projection column
    try:
        pcol = _pick_proj_col(df, explicit=proj_col)
    except KeyError:
        pcol = "ProjectedPoints"  # created by compute_value if missing

    g = df.groupby(list(groupby), dropna=False)
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
