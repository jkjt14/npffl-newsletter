# src/load_salary.py
from __future__ import annotations
import glob, os, sys
import pandas as pd
from .mfl_client import MFLClient

def load_latest_salary(pattern: str, *, year: int, league_id: str, api_key: str, week: int) -> pd.DataFrame:
    # Try MFL salaries endpoint first
    try:
        df = MFLClient(year, league_id, api_key).salaries(week)
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
    except Exception as e:
        print(f"[load_salary] WARN salaries API failed: {e}", file=sys.stderr)

    # Fallback to file pattern
    paths = sorted(glob.glob(pattern))
    if not paths:
        print(f"[load_salary] WARN no salary files matching {pattern}", file=sys.stderr)
        return pd.DataFrame()
    path = paths[-1]
    if path.lower().endswith((".xlsx",".xls")):
        return pd.read_excel(path)
    return pd.read_csv(path)
