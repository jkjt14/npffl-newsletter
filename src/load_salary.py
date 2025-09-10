from __future__ import annotations
from typing import Any
import pandas as pd
from pathlib import Path
import glob

def load_salary_file(glob_pattern: str) -> pd.DataFrame:
    paths = sorted(glob.glob(glob_pattern))
    if not paths:
        # Return empty DataFrame with expected columns
        return pd.DataFrame(columns=["Name","Pos","Team","Salary"])
    # use the latest by name
    path = paths[-1]
    if path.endswith(".xlsx") or path.endswith(".xls"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)
    # normalize column names
    rename = {c:c.strip().title() for c in df.columns}
    df = df.rename(columns=rename)
    # standardize a few expected names
    df = df.rename(columns={"Position":"Pos","Pts":"Pts","Name":"Name","Team":"Team","Salary":"Salary"})
    return df[ [c for c in ["Name","Pos","Team","Salary"] if c in df.columns] ]
