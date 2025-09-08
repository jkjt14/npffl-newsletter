# src/fetch_week.py
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, Optional, List, Dict

import pandas as pd
import numpy as np


# =========================
# Generic file I/O helpers
# =========================

def _normalize(s: str) -> str:
    """Lowercase and collapse non-alnum to underscores for fuzzy column matching."""
    t = re.sub(r"[^0-9A-Za-z]+", "_", s.strip().lower())
    return re.sub(r"_+", "_", t).strip("_")


def _find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    """Find a column by normalized name among candidate names. Tries exact then partial."""
    norm_map = {_normalize(c): c for c in df.columns}
    # exact
    for cand in candidates:
        key = _normalize(cand)
        if key in norm_map:
            return norm_map[key]
    # partial (contains)
    for cand in candidates:
        key = _normalize(cand)
        for k, orig in norm_map.items():
            if key and key in k:
                return orig
    return None


def _read_any(path: str, sheet: Optional[str] = None) -> pd.DataFrame:
    """Read CSV/XLSX/JSON based on file extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt"):
        return pd.read_csv(path)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=sheet or 0)
    if ext in (".json",):
        return pd.read_json(path)
    raise ValueError(f"Unsupported file extension: {ext}")


def _candidate_paths(week: int) -> List[str]:
    """Common path patterns to try when path is not provided."""
    w = int(week)
    candidates = [
        f"data/weekly_week{w}.csv",
        f"data/weekly/week{w}.csv",
        f"data/weekly/weekly_week{w}.csv",
        f"data/week{w}.csv",
        f"weekly_week{w}.csv",

        f"data/weekly_week{w}.xlsx",
        f"data/weekly/week{w}.xlsx",
        f"data/weekly/weekly_week{w}.xlsx",
        f"data/week{w}.xlsx",
        f"weekly_week{w}.xlsx",

        f"data/weekly_week{w}.json",
        f"data/weekly/week{w}.json",
        f"data/weekly/weekly_week{w}.json",
        f"data/week{w}.json",
        f"weekly_week{w}.json",
    ]
    return candidates


# ==================================
# Public API expected by main.py
# ==================================

def get_weekly_data(week: int, path: Optional[str] = None, sheet: Optional[str] = None) -> pd.DataFrame:
    """
    Load the raw weekly lineup/results table for a given week.

    Loading priority:
      1) explicit path argument (if provided)
      2) NPFFL_WEEKLY_PATH env var (if set)
      3) Common repo paths for week N:
         - data/weekly_week{N}.csv
         - data/weekly/week{N}.csv
         - data/weekly_week{N}.xlsx (sheet optional)
         - ... (also tries .json)

    Returns
    -------
    DataFrame
        Raw weekly dataframe. If no file is found, returns an empty DataFrame
        and prints a clear warning to stderr (so the pipeline won’t hard-fail).
    """
    # 1) explicit path param
    if path:
        if os.path.exists(path):
            try:
                return _read_any(path, sheet=sheet)
            except Exception as e:
                print(f"[fetch_week] ERROR: Failed to read path={path}: {e}", file=sys.stderr, flush=True)
        else:
            print(f"[fetch_week] WARNING: Path does not exist: {path}", file=sys.stderr, flush=True)

    # 2) env var
    envp = os.getenv("NPFFL_WEEKLY_PATH")
    if envp:
        if os.path.exists(envp):
            try:
                return _read_any(envp, sheet=sheet)
            except Exception as e:
                print(f"[fetch_week] ERROR: Failed to read NPFFL_WEEKLY_PATH={envp}: {e}", file=sys.stderr, flush=True)
        else:
            print(f"[fetch_week] WARNING: NPFFL_WEEKLY_PATH does not exist: {envp}", file=sys.stderr, flush=True)

    # 3) common candidates
    for cand in _candidate_paths(week):
        if os.path.exists(cand):
            try:
                return _read_any(cand, sheet=sheet)
            except Exception as e:
                print(f"[fetch_week] ERROR: Failed to read {cand}: {e}", file=sys.stderr, flush=True)

    # Nothing found — return empty to keep pipeline alive (downstream can handle)
    print(
        f"[fetch_week] WARNING: No weekly file found for week={week}. "
        "Returning empty DataFrame.",
        file=sys.stderr,
        flush=True,
    )
    return pd.DataFrame()


def flatten_weekly_starters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return only starters from a weekly dataframe.

    Strategy:
      1) Try to find an explicit starter flag column (case/space tolerant):
         ["Starter","Is Starter","IsStarter","Starting","In Lineup","Active","Starter?"].
      2) Fallback: infer from a 'slot' style column (BN/Bench/IR/RES/etc. -> not starter).
      3) If neither exists, warn and return df unchanged (assume all starters).

    This function is defensive so CI won’t explode on minor schema drift.
    """
    if df is None or len(df) == 0:
        return df.copy()

    # ----- explicit starter flag
    starter_candidates = [
        "Starter", "Starters", "Is Starter", "IsStarter", "Starting", "In Lineup",
        "InLineup", "Active", "Starter?", "Starter Flag", "Starter_YN", "is_starter",
    ]
    starter_col = _find_col(df, starter_candidates)
    if starter_col:
        mask = _coerce_bool_series(df[starter_col])
        # If many NA after coercion, try numeric > 0 as truthy
        if mask.isna().mean() > 0.5:
            try:
                num = pd.to_numeric(df[starter_col], errors="coerce")
                mask = (num.fillna(0) > 0).astype("boolean")
            except Exception:
                pass
        return df[mask.fillna(False)].copy()

    # ----- infer via slot/roster column
    inferred = _infer_from_slot(df)
    if inferred is not None:
        return df[inferred.fillna(False)].copy()

    # ----- last resort: let pipeline proceed
    print(
        "[fetch_week] WARNING: Could not locate a 'Starter' or 'Slot' column. "
        "Proceeding with ALL rows treated as starters.",
        file=sys.stderr,
        flush=True,
    )
    return df.copy()


# =========================
# Internals for inference
# =========================

def _coerce_bool_series(s: pd.Series) -> pd.Series:
    """Coerce varied truthy/falsey markers into booleans (dtype=boolean)."""
    if s.dtype == bool or str(s.dtype) == "boolean":
        return s.astype("boolean")
    st = s.astype(str).str.strip().str.lower()
    truthy = {"true", "t", "1", "y", "yes", "starter", "start", "starting", "active", "in", "play"}
    falsey = {"false", "f", "0", "n", "no", "bench", "bn", "out", "inactive", "na", "dnp", "res", "reserve", "ir", "bye"}
    out = np.where(st.isin(truthy), True, np.where(st.isin(falsey), False, pd.NA))
    return pd.Series(out, index=s.index, dtype="boolean")


def _infer_from_slot(df: pd.DataFrame) -> Optional[pd.Series]:
    """
    Infer starters from a slot/lineup column where bench-like slots are excluded.
    Returns a boolean series or None if no slot column.
    """
    slot_candidates = [
        "Slot", "Lineup Slot", "LineupSlot", "Roster Slot", "Position Slot", "RosterPosition",
        "Roster_Pos", "RosterPos", "PosSlot", "MFL_Slot", "Position", "Pos",
    ]
    slot_col = _find_col(df, slot_candidates)
    if not slot_col:
        return None

    bench_markers = {"bn", "bench", "res", "reserve", "ir", "dnp", "inactive", "na", "out", "bye"}
    st = df[slot_col].astype(str).str.strip().str.lower()
    starters = ~st.isin(bench_markers)
    return starters.astype("boolean")
