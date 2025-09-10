from __future__ import annotations
from pathlib import Path
from typing import Optional, List, Tuple
import re
import pandas as pd

NAME_HEADERS = ["name", "player", "player name"]
TEAM_HEADERS = ["team", "nfl", "nfl team", "nfl_team"]
POS_HEADERS  = ["pos", "position"]
SAL_HEADERS  = ["salary", "sal", "cost", "price"]

SUFFIX_RX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?", re.I)
PARENS_RX = re.compile(r"\([^)]*\)")
EXTRA_RX  = re.compile(r"[^A-Za-z0-9 ,.'-]+")

def _detect(df: pd.DataFrame, cand: List[str]) -> Optional[str]:
    cols = {c.lower(): c for c in df.columns}
    for c in cand:
        if c in cols:
            return cols[c]
    return None

def _clean_name(n: str) -> str:
    if not n: return ""
    n = n.strip()
    n = PARENS_RX.sub("", n)
    n = SUFFIX_RX.sub("", n)
    n = EXTRA_RX.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()

def _first_last(n: str) -> str:
    if not n: return ""
    if "," in n:
        last, first = [t.strip() for t in n.split(",", 1)]
        return f"{first} {last}".strip()
    return n.strip()

def _last_first(fl: str) -> str:
    toks = [t for t in (fl or "").split(" ") if t]
    if len(toks) >= 2:
        return f"{toks[-1]}, {' '.join(toks[:-1])}"
    return fl

def _canon_pair(n: str) -> Tuple[str, str]:
    fl = _first_last(n)
    lf = _last_first(fl)
    flk = _clean_name(fl).lower()
    lfk = _clean_name(lf).lower()
    return flk, lfk

def load_salary(glob_pattern: str) -> pd.DataFrame:
    paths = sorted(Path(".").glob(glob_pattern))
    if not paths:
        raise FileNotFoundError(f"No salary files found for pattern: {glob_pattern}")
    path = paths[-1]

    df = pd.read_excel(path, sheet_name="MFL Salary")

    name_col = _detect(df, [c.lower() for c in NAME_HEADERS]) or ""
    pos_col  = _detect(df, [c.lower() for c in POS_HEADERS]) or ""
    team_col = _detect(df, [c.lower() for c in TEAM_HEADERS]) or ""
    sal_col  = _detect(df, [c.lower() for c in SAL_HEADERS]) or ""

    if not name_col or not sal_col:
        raise ValueError("Salary file must have at least a Name and Salary column.")

    # Normalize
    df["_name_raw"] = df.get(name_col).fillna("").astype(str)
    df["_fl_key"], df["_lf_key"] = zip(*df["_name_raw"].map(_canon_pair))
    df["_pos"]  = (df.get(pos_col).fillna("").astype(str).str.upper()) if pos_col else ""
    df["_team"] = (df.get(team_col).fillna("").astype(str).str.upper()) if team_col else ""
    df["_salary"] = pd.to_numeric(df.get(sal_col), errors="coerce")

    # Keep only rows that have name+salary
    keep = (df["_salary"].notna()) & (df["_fl_key"] != "")
    df = df.loc[keep].copy()

    print(f"[load_salary] Loaded {len(df)} salary rows from '{path.name}'")
    print(f"[load_salary] Detected -> name='{name_col}', pos='{pos_col}', team='{team_col}', salary='{sal_col}'")

    return df
