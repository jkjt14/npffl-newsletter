# src/load_salary.py
from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Optional, Tuple, List

import logging
import pandas as pd

logger = logging.getLogger(__name__)


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


def _parse_week_number(path: Path) -> Optional[int]:
    """Best-effort parse of the week number from a salary filename."""

    stem = path.stem  # strip extension
    nums = [int(tok) for tok in re.findall(r"\d+", stem) if tok.isdigit()]
    for num in reversed(nums):
        if 1 <= num <= 22:  # cover regular season + playoffs
            return num
    return None


def _pick_latest_file(pattern: str) -> Optional[Path]:
    matches = sorted(glob.glob(pattern))
    if not matches:
        return None
    # choose the lexicographically latest (e.g., 2025_09_Salary.xlsx > 2025_01_Salary.xlsx)
    latest = sorted(matches)[-1]
    return Path(latest)


def _pick_week_file(pattern: str, week: int) -> Optional[Path]:
    """Return the salary sheet closest to the requested week."""

    matches = [Path(p) for p in sorted(glob.glob(pattern))]
    if not matches:
        return None

    target = int(week)

    # First pass: look for an exact match
    for path in matches:
        wk = _parse_week_number(path)
        if wk == target:
            return path

    # Second pass: prefer the latest prior week so values are at least historical
    prior: tuple[Optional[Path], Optional[int]] = (None, None)
    for path in matches:
        wk = _parse_week_number(path)
        if wk is None:
            continue
        diff = target - wk
        if diff < 0:
            continue
        if prior[0] is None or (prior[1] is not None and diff < prior[1]):
            prior = (path, diff)
    if prior[0] is not None:
        return prior[0]

    # Fallback: just hand back the latest sheet available
    return matches[-1]


def load_salary_file(
    salary_glob: str = "data/salaries/2025_*_Salary.xlsx",
    week: Optional[int] = None,
) -> pd.DataFrame:
    """
    Read and normalize the salary sheet.

    If ``week`` is provided, the loader will try to find a sheet for that
    specific slate. When an exact filename match is not available we fall back
    to the closest earlier week (or the latest sheet overall).

    Returns a DataFrame with canonical columns:
      - name (str, 'First Last')
      - pos  (str)
      - team (str)
      - salary (int)

    Prints a short log about what it detected.
    """
    if week is None:
        xlsx_path = _pick_latest_file(salary_glob)
    else:
        xlsx_path = _pick_week_file(salary_glob, week)
    if not xlsx_path:
        raise FileNotFoundError(
            f"[load_salary] No files matched pattern '{salary_glob}'. "
            "Drop a file like 'data/salaries/2025_01_Salary.xlsx'."
        )

    if week is not None:
        parsed = _parse_week_number(xlsx_path)
        if parsed != week:
            logger.warning(
                "[load_salary] Using '%s' for week %s (closest available match)",
                xlsx_path.name,
                week,
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

    logger.info("[load_salary] Loaded %d salary rows from '%s'", len(df), xlsx_path.name)
    logger.info("[load_salary] Detected -> name='name', pos='pos', team='team', salary='salary'")

    return df
