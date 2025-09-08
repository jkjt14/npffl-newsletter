# src/fetch_week.py
from __future__ import annotations

import os
import re
import sys
from typing import Iterable, Optional, List, Tuple, Dict

import pandas as pd
import numpy as np


# ===========
# Utilities
# ===========

def _normalize(s: str) -> str:
    t = re.sub(r"[^0-9A-Za-z]+", "_", str(s).strip().lower())
    return re.sub(r"_+", "_", t).strip("_")


def _find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    norm_map = {_normalize(c): c for c in df.columns}
    for cand in candidates:
        key = _normalize(cand)
        if key in norm_map:
            return norm_map[key]
    for cand in candidates:
        key = _normalize(cand)
        for k, orig in norm_map.items():
            if key and key in k:
                return orig
    return None


def _read_any(path: str, sheet: Optional[str] = None) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt"):
        return pd.read_csv(path)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(path, sheet_name=sheet or 0)
    if ext == ".json":
        return pd.read_json(path)
    raise ValueError(f"Unsupported file extension: {ext}")


def _try_load(kind: str, week: int, explicit_path: Optional[str] = None, sheet: Optional[str] = None) -> pd.DataFrame:
    """
    Load a dataset of a given 'kind' for the week, trying:
      1) explicit_path
      2) env var NPFFL_{KIND}_PATH
      3) common repo paths
    If not found, returns empty DataFrame and logs a warning.
    """
    # 1) explicit
    if explicit_path:
        if os.path.exists(explicit_path):
            try:
                return _read_any(explicit_path, sheet=sheet)
            except Exception as e:
                print(f"[fetch_week] ERROR reading {kind} from explicit path '{explicit_path}': {e}",
                      file=sys.stderr, flush=True)
        else:
            print(f"[fetch_week] WARNING: explicit {kind} path not found: {explicit_path}",
                  file=sys.stderr, flush=True)

    # 2) env var
    env_key = f"NPFFL_{kind.upper()}_PATH"
    env_path = os.getenv(env_key)
    if env_path:
        if os.path.exists(env_path):
            try:
                return _read_any(env_path, sheet=sheet)
            except Exception as e:
                print(f"[fetch_week] ERROR reading {kind} from {env_key}='{env_path}': {e}",
                      file=sys.stderr, flush=True)
        else:
            print(f"[fetch_week] WARNING: {env_key} not found at '{env_path}'",
                  file=sys.stderr, flush=True)

    # 3) common candidates
    w = int(week)
    base_candidates = [
        f"data/{kind}_week{w}.csv",
        f"data/{kind}/week{w}.csv",
        f"data/{kind}/week_{w}.csv",
        f"{kind}_week{w}.csv",

        f"data/{kind}_week{w}.xlsx",
        f"data/{kind}/week{w}.xlsx",
        f"data/{kind}/week_{w}.xlsx",
        f"{kind}_week{w}.xlsx",

        f"data/{kind}_week{w}.json",
        f"data/{kind}/week{w}.json",
        f"data/{kind}/week_{w}.json",
        f"{kind}_week{w}.json",
    ]
    for cand in base_candidates:
        if os.path.exists(cand):
            try:
                return _read_any(cand, sheet=sheet)
            except Exception as e:
                print(f"[fetch_week] ERROR reading {kind} from '{cand}': {e}",
                      file=sys.stderr, flush=True)

    # Not found
    print(f"[fetch_week] WARNING: No {kind} file found for week={w}; returning empty DataFrame.",
          file=sys.stderr, flush=True)
    return pd.DataFrame()


# =========================
# Public API used by main.py
# =========================

def get_weekly_data(
    year: int,
    league_id: str,
    api_key: str,
    week: int,
    *,
    weekly_path: Optional[str] = None,
    standings_path: Optional[str] = None,
    survivor_path: Optional[str] = None,
    pool_nfl_path: Optional[str] = None,
    sheet: Optional[str] = None,
) -> Tuple[int, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Return (wk, standings, weekly, survivor, pool_nfl) for the requested week.

    This implementation is file-driven (no network calls). It tries:
      explicit paths -> env vars -> common repo paths. Missing files
      come back as empty DataFrames so CI can continue.

    Env var overrides (optional):
      NPFFL_STANDINGS_PATH
      NPFFL_WEEKLY_PATH
      NPFFL_SURVIVOR_PATH
      NPFFL_POOL_NFL_PATH
    """
    wk = int(week)

    standings = _try_load("standings", wk, explicit_path=standings_path, sheet=sheet)
    weekly    = _try_load("weekly",    wk, explicit_path=weekly_path,    sheet=sheet)
    survivor  = _try_load("survivor",  wk, explicit_path=survivor_path,  sheet=sheet)
    pool_nfl  = _try_load("pool_nfl",  wk, explicit_path=pool_nfl_path,  sheet=sheet)

    # Lightweight visibility
    def _shape(df: pd.DataFrame) -> str:
        return f"{df.shape[0]}x{df.shape[1]}" if isinstance(df, pd.DataFrame) else "NA"

    print(f"[fetch_week] Loaded week={wk} -> standings={_shape(standings)}, weekly={_shape(weekly)}, "
          f"survivor={_shape(survivor)}, pool_nfl={_shape(pool_nfl)}", file=sys.stderr, flush=True)

    return wk, standings, weekly, survivor, pool_nfl


def flatten_weekly_starters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return only starters from a weekly dataframe.

    Strategy:
      1) Find explicit starter flag column (case/space tolerant).
      2) Fallback: infer from slot/roster column (exclude BN/Bench/IR/RES/etc.).
      3) If neither exists, warn and return df unchanged (assume all starters).
    """
    if df is None or len(df) == 0:
        return df.copy()

    # Explicit starter flags
    starter_candidates = [
        "Starter", "Starters", "Is Starter", "IsStarter", "Starting", "In Lineup",
        "InLineup", "Active", "Starter?", "Starter Flag", "Starter_YN", "is_starter",
    ]
    starter_col = _find_col(df, starter_candidates)
    if starter_col:
        mask = _coerce_bool_series(df[starter_col])
        if mask.isna().mean() > 0.5:
            try:
                num = pd.to_numeric(df[starter_col], errors="coerce")
                mask = (num.fillna(0) > 0).astype("boolean")
            except Exception:
                pass
        return df[mask.fillna(False)].copy()

    # Infer from slot/roster
    inferred = _infer_from_slot(df)
    if inferred is not None:
        return df[inferred.fillna(False)].copy()

    print(
        "[fetch_week] WARNING: Could not locate a 'Starter' or 'Slot' column. "
        "Proceeding with ALL rows treated as starters.",
        file=sys.stderr,
        flush=True,
    )
    return df.copy()


# =========================
# Inference internals
# =========================

def _coerce_bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool or str(s.dtype) == "boolean":
        return s.astype("boolean")
    st = s.astype(str).str.strip().str.lower()
    truthy = {"true", "t", "1", "y", "yes", "starter", "start", "starting", "active", "in", "play"}
    falsey = {"false", "f", "0", "n", "no", "bench", "bn", "out", "inactive", "na", "dnp", "res", "reserve", "ir", "bye"}
    out = np.where(st.isin(truthy), True, np.where(st.isin(falsey), False, pd.NA))
    return pd.Series(out, index=s.index, dtype="boolean")


def _infer_from_slot(df: pd.DataFrame) -> Optional[pd.Series]:
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
