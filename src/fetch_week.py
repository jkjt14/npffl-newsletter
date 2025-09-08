# src/fetch_week.py
from __future__ import annotations
import os, sys
from typing import Optional, Tuple
import pandas as pd
import numpy as np
from .mfl_client import MFLClient

def get_weekly_data(
    year: int,
    league_id: str,
    api_key: str,
    week: int,
    *,
    weekly_path: Optional[str] = None,          # kept for back-compat
    standings_path: Optional[str] = None,
    survivor_path: Optional[str] = None,
    pool_nfl_path: Optional[str] = None,
    sheet: Optional[str] = None,
) -> Tuple[int, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (wk, standings, weekly, survivor, pool_nfl) via MFL API."""
    wk = int(week) if week else int(os.getenv("WEEK", "0") or 0)
    if wk <= 0:
        # crude auto: use previous week (for Tuesday runs, week-1 should be complete)
        wk = max(1, int(os.getenv("GITHUB_RUN_ATTEMPT", "2")) - 1)  # harmless fallback
    client = MFLClient(year=int(year), league_id=str(league_id), api_key=api_key)

    standings = client.league_standings(wk)
    weekly    = client.weekly_results(wk)
    survivor  = client.survivor_pool(wk)
    pool_nfl  = client.pool(wk, pooltype="NFL")

    def _shape(df: pd.DataFrame) -> str:
        return f"{df.shape[0]}x{df.shape[1]}" if isinstance(df, pd.DataFrame) else "NA"
    print(f"[fetch_week] (API) week={wk} -> standings={_shape(standings)}, weekly={_shape(weekly)}, "
          f"survivor={_shape(survivor)}, pool_nfl={_shape(pool_nfl)}", file=sys.stderr, flush=True)
    return wk, standings, weekly, survivor, pool_nfl

def flatten_weekly_starters(df: pd.DataFrame) -> pd.DataFrame:
    """Use boolean Starter column if present; else pass-through."""
    if df is None or df.empty: return df.copy()
    if "Starter" in df.columns:
        s = df["Starter"]
        if str(s.dtype) in ("bool", "boolean"):
            return df[s == True].copy()
        return df[df["Starter"].astype(str).str.lower().isin(["true","1","starter","yes"])].copy()
    return df.copy()
