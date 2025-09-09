from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Optional

import pandas as pd


def _find_latest_by_week(pattern: str) -> Optional[str]:
    """
    Given a glob like 'data/salaries/2025_*_Salary.xlsx',
    pick the file with the highest week number (the middle token).
    Expects filenames like: YYYY_WW_Salary.xlsx
    """
    candidates = glob.glob(pattern)
    best = None
    best_week = -1
    for p in candidates:
        name = Path(p).name
        m = re.match(r"(\d{4})_(\d{2})_Salary\.xlsx$", name)
        if not m:
            continue
        w = int(m.group(2))
        if w > best_week:
            best_week = w
            best = p
    if best:
        return best
    # fallback: if only one file, use it
    if len(candidates) == 1:
        return candidates[0]
    return None


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize the expected columns:
      Name, Team, Pos, Salary
    The sheet may have extra columns; we keep the key ones.
    """
    # Normalize column names (preserve original case for known labels)
    cols = {c.strip(): c for c in df.columns}
    name_col = None
    team_col = None
    pos_col = None
    sal_col = None

    for c in df.columns:
        cl = c.strip().lower()
        if cl == "name":
            name_col = c
        elif cl == "team":
            team_col = c
        elif cl in ("pos", "position"):
            pos_col = c
        elif cl == "salary":
            sal_col = c

    # If any of these are missing, just return the original df and let the caller fail-soft
    if not name_col or not sal_col:
        return df

    out = df[[name_col] + ([team_col] if team_col else []) + ([pos_col] if pos_col else []) + [sal_col]].copy()
    out.rename(
        columns={
            name_col: "Name",
            team_col or "Team": "Team",
            pos_col or "Pos": "Pos",
            sal_col: "Salary",
        },
        inplace=True,
    )

    # Coerce salary numeric
    out["Salary"] = pd.to_numeric(out["Salary"], errors="coerce")

    # Clean obvious stray punctuation in names like 'Barkley, Saquon!'
    out["Name"] = (
        out["Name"]
        .astype(str)
        .str.replace(r"[!·•]+", "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    # Drop rows with no name or no salary
    out = out[~out["Name"].isna() & ~out["Salary"].isna()]

    return out.reset_index(drop=True)


def load_salary(pattern: str) -> pd.DataFrame:
    """
    Load the salary Excel (sheet 'MFL Salary') matching the glob pattern.
    If multiple match, pick the latest week by filename (YYYY_WW_Salary.xlsx).
    """
    path = _find_latest_by_week(pattern) or pattern  # allow direct path too
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Salary file not found for pattern/path: {pattern}")

    # Most of your sheets use 'MFL Salary'
    df = pd.read_excel(p, sheet_name="MFL Salary")

    # Clean/standardize columns
    df = _clean_columns(df)
    if "Name" not in df.columns or "Salary" not in df.columns:
        raise ValueError("Salary file missing required columns 'Name' and 'Salary'.")

    return df
