# src/fetch_week.py
from __future__ import annotations

import re
import sys
import pandas as pd
import numpy as np
from typing import Iterable, Optional, Tuple, List, Dict


# ---- helpers ---------------------------------------------------------------

def _normalize(s: str) -> str:
    """lowercase; collapse non-alnum to single underscore."""
    t = re.sub(r"[^0-9A-Za-z]+", "_", s.strip().lower())
    return re.sub(r"_+", "_", t).strip("_")


def _find_col(df: pd.DataFrame, candidates: Iterable[str]) -> Optional[str]:
    """Find a column by normalized name among candidate names."""
    norm_map = { _normalize(c): c for c in df.columns }
    for cand in candidates:
        key = _normalize(cand)
        if key in norm_map:
            return norm_map[key]
    # also try partial contains (e.g., "starter?" -> "starter")
    for cand in candidates:
        key = _normalize(cand)
        for k, orig in norm_map.items():
            if key and key in k:
                return orig
    return None


def _coerce_bool_series(s: pd.Series) -> pd.Series:
    """Coerce a series of varied truthy/falsey markers into booleans."""
    if s.dtype == bool:
        return s
    # Work with strings
    st = s.astype(str).str.strip().str.lower()
    truthy = {"true", "t", "1", "y", "yes", "starter", "start", "starting", "active", "in", "play"}
    falsey = {"false", "f", "0", "n", "no", "bench", "bn", "out", "inactive", "na", "dnp", "res", "reserve", "ir"}
    out = pd.Series(index=s.index, dtype="boolean")
    out = np.where(st.isin(truthy), True, np.where(st.isin(falsey), False, pd.NA))
    return pd.Series(out, index=s.index, dtype="boolean")


def _infer_from_slot(df: pd.DataFrame) -> Optional[pd.Series]:
    """
    Infer starters from a slot/lineup column where bench-like slots are excluded.
    Returns a boolean series or None if no slot column.
    """
    slot_candidates = [
        "Slot", "Lineup Slot", "LineupSlot", "Roster Slot", "Position Slot", "RosterPosition",
        "Roster_Pos", "RosterPos", "PosSlot", "MFL_Slot", "Position", "Pos"
    ]
    slot_col = _find_col(df, slot_candidates)
    if not slot_col:
        return None

    bench_markers = {"bn", "bench", "res", "reserve", "ir", "dnp", "inactive", "na", "out", "bye"}
    st = df[slot_col].astype(str).str.strip().str.lower()
    starters = ~st.isin(bench_markers)
    return starters.astype("boolean")


# ---- primary API -----------------------------------------------------------

def flatten_weekly_starters(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return only starters from a weekly dataframe.

    Strategy:
      1) Try to find an explicit starter flag column (case/space tolerant):
         ["Starter","Is Starter","IsStarter","Starting","In Lineup","Active","Starter?"].
      2) Fallback: infer from a 'slot' style column (BN/Bench/IR/RES/etc. -> not starter).
      3) If neither exists, warn and return df unchanged (assume all starters).
    """
    if df is None or len(df) == 0:
        return df.copy()

    starter_candidates = [
        "Starter", "Starters", "Is Starter", "IsStarter", "Starting", "In Lineup",
        "InLineup", "Active", "Starter?", "Starter Flag", "Starter_YN", "is_starter"
    ]

    # 1) explicit starter column
    starter_col = _find_col(df, starter_candidates)
    if starter_col:
        mask = _coerce_bool_series(df[starter_col])
        # if many NA after coercion, try numeric > 0 as truthy
        if mask.isna().mean() > 0.5:
            try:
                num = pd.to_numeric(df[starter_col], errors="coerce")
                mask = num.fillna(0) > 0
                mask = mask.astype("boolean")
            except Exception:
                pass
        result = df[mask.fillna(False)].copy()
        return result

    # 2) infer from slot
    inferred = _infer_from_slot(df)
    if inferred is not None:
        return df[inferred.fillna(False)].copy()

    # 3) last resort: let pipeline proceed to avoid hard failure
    print(
        "[fetch_week] WARNING: Could not locate a 'Starter' or 'Slot' column. "
        "Proceeding with ALL rows treated as starters.",
        file=sys.stderr,
        flush=True,
    )
    return df.copy()
