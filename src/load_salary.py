from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Optional, Tuple, List

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


def _select_sheet_by_columns(xl_path: Path, preferred: str = "MFL Salary") -> Tuple[str, pd.DataFrame]:
    """
    Try the preferred sheet name first; otherwise scan sheets to find one
    that contains at least Name + Salary columns. Returns (sheet_name, df).
    """
    xls = pd.ExcelFile(xl_path, engine="openpyxl")
    # 1) try preferred
    if preferred in xls.sheet_names:
        df = pd.read_excel(xl_path, sheet_name=preferred, engine="openpyxl")
        return preferred, df
    # 2) scan sheets
    for s in xls.sheet_names:
        df = pd.read_excel(xl_path, sheet_name=s, engine="openpyxl")
        low = [c.strip().lower() for c in df.columns]
        if "name" in low and "salary" in low:
            return s, df
    # 3) last resort: first sheet
    s0 = xls.sheet_names[0]
    df = pd.read_excel(xl_path, sheet_name=s0, engine="openpyxl")
    return s0, df


def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize to: Name, Team, Pos, Salary
    """
    cols_l = {c: c.strip().lower() for c in df.columns}
    name_col = next((c for c, l in cols_l.items() if l == "name"), None)
    team_col = next((c for c, l in cols_l.items() if l == "team"), None)
    pos_col  = next((c for c, l in cols_l.items() if l in ("pos", "position")), None)
    sal_col  = next((c for c, l in cols_l.items() if l == "salary"), None)

    # If missing critical columns, just return df unchanged; caller will fail-soft
    if not name_col or not sal_col:
        return df

    keep: List[str] = [name_col, sal_col]
    if team_col: keep.insert(1, team_col)
    if pos_col:  keep.insert(2 if team_col else 1, pos_col)

    out = df[keep].copy()
    rename_map = {name_col: "Name", sal_col: "Salary"}
    if team_col: rename_map[team_col] = "Team"
    if pos_col:  rename_map[pos_col] = "Pos"
    out.rename(columns=rename_map, inplace=True)

    # Coerce salary numeric
    out["Salary"] = pd.to_numeric(out["Salary"], errors="coerce")

    # Clean names (remove stray punctuation like '!')
    out["Name"] = (
        out["Name"]
        .astype(str)
        .str.replace(r"[!·•]+", "", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    # Drop empty rows
    out = out[~out["Name"].isna() & ~out["Salary"].isna()].reset_index(drop=True)
    return out


def load_salary(pattern: str) -> pd.DataFrame:
    """
    Load the salary Excel matching the glob pattern.
    Detect the right sheet automatically if 'MFL Salary' isn't present.
    """
    path = _find_latest_by_week(pattern) or pattern
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Salary file not found for pattern/path: {pattern}")

    sheet, raw = _select_sheet_by_columns(p, preferred="MFL Salary")
    df = _clean_columns(raw)

    if "Name" not in df.columns or "Salary" not in df.columns:
        raise ValueError(f"Salary file '{p.name}' (sheet '{sheet}') missing required columns 'Name' and 'Salary'.")

    print(f"[load_salary] Loaded {len(df)} rows from '{p.name}' (sheet: '{sheet}')")
    return df
