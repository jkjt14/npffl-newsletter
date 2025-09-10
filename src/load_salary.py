# src/load_salary.py
from __future__ import annotations

import glob
from pathlib import Path
from typing import Optional, Tuple, List

import pandas as pd


def _normalize_name(raw: str) -> str:
    """
    Convert 'Last, First' -> 'First Last', strip tags like ' (RB-PHI)' if any,
    and collapse whitespace.
    """
    if not isinstance(raw, str):
        return ""
    name = raw.strip()

    # some sheets include tags after the name; strip at first '  ' sequence or ' ('
    cutmarks = ["  ", " (", " - "]
    for cm in cutmarks:
        if cm in name:
            name = name.split(cm, 1)[0].strip()

    # Handle "Last, First" -> "First Last"
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        if len(parts) == 2 and parts[0] and parts[1]:
            name = f"{parts[1]} {parts[0]}"

    # Collapse spaces
    name = " ".join(name.split())
    return name


def _detect_columns(df: pd.DataFrame) -> Tuple[str, str, str, str]:
    """
    Heuristically detect the Name/Pos/Team/Salary columns (case-insensitive).
    Returns canonical column names actually present in df.
    Raises ValueError if required columns not found.
    """
    cols = {c.lower().strip(): c for c in df.columns}

    # possible headers seen across variants
    name_keys = ["name", "player", "player name"]
    pos_keys = ["pos", "position"]
    team_keys = ["team", "nfl", "nfl team", "nflteam"]
    sal_keys = ["salary", "cost", "price", "sal"]

    def pick(keys: List[str], label: str) -> str:
        for k in keys:
            if k in cols:
                return cols[k]
        # also try fuzzy contains
        for lc, orig in cols.items():
            for k in keys:
                if k in lc:
                    return orig
        raise ValueError(f"Could not detect '{label}' column. Found columns: {list(df.columns)}")

    name_col = pick(name_keys, "Name")
    pos_col = pick(pos_keys, "Pos")
    team_col = pick(team_keys, "Team")
    sal_col = pick(sal_keys, "Salary")
    return name_col, pos_col, team_col, sal_col


def _read_excel_with_fallback(xlsx_path: Path) -> pd.DataFrame:
    """
    Try to read the intended sheet name; fall back to the first sheet if not found.
    """
    # Try obvious sheet names first
    try_sheets = ["MFL Salary", "Salary", "Salaries", 0]

    for sheet in try_sheets:
        try:
            df = pd.read_excel(xlsx_path, sheet_name=sheet, engine="openpyxl")
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except Exception:
            continue

    # Final fallback: read without specifying sheet (defaults to first)
    return pd.read_excel(xlsx_path, engine="openpyxl")


def _pick_latest_file(pattern: str) -> Optional[Path]:
    matches = sorted(glob.glob(pattern))
    if not matches:
        return None
    # choose the lexicographically latest (e.g., 2025_09_Salary.xlsx > 2025_01_Salary.xlsx)
    latest = sorted(matches)[-1]
    return Path(latest)


def load_salary_file(salary_glob: str = "data/salaries/2025_*_Salary.xlsx") -> pd.DataFrame:
    """
    Read and normalize the salary sheet.

    Returns a DataFrame with canonical columns:
      - name (str, 'First Last')
      - pos  (str)
      - team (str)
      - salary (int)

    Prints a short log about what it detected.
    """
    xlsx_path = _pick_latest_file(salary_glob)
    if not xlsx_path:
        raise FileNotFoundError(
            f"[load_salary] No files matched pattern '{salary_glob}'. "
            "Drop a file like 'data/salaries/2025_01_Salary.xlsx'."
        )

    raw = _read_excel_with_fallback(xlsx_path)
    if raw is None or raw.empty:
        raise ValueError(f"[load_salary] '{xlsx_path.name}' appears empty or unreadable.")

    # detect columns
    name_col, pos_col, team_col, sal_col = _detect_columns(raw)

    # subset & rename
    df = raw[[name_col, pos_col, team_col, sal_col]].rename(
        columns={name_col: "name", pos_col: "pos", team_col: "team", sal_col: "salary"}
    )

    # normalize
    df["name"] = df["name"].astype(str).map(_normalize_name)
    df["pos"] = df["pos"].astype(str).str.strip().str.upper()
    df["team"] = df["team"].astype(str).str.strip().str.upper()

    # salary coercion
    def _to_int(x) -> int:
        try:
            # sometimes salary comes like 8100.0 or '$8,100'
            if isinstance(x, str):
                x = x.replace("$", "").replace(",", "").strip()
            val = int(float(x))
            return max(val, 0)
        except Exception:
            return 0

    df["salary"] = df["salary"].map(_to_int)

    # drop empty names
    df = df[df["name"] != ""].copy()

    print(f"[load_salary] Loaded {len(df)} salary rows from '{xlsx_path.name}'")
    print(f"[load_salary] Detected -> name='name', pos='pos', team='team', salary='salary'")

    return df
