import glob
import pandas as pd

def load_latest_salary(salary_glob: str) -> pd.DataFrame:
    files = sorted(glob.glob(salary_glob))
    if not files:
        raise FileNotFoundError(f"No salary files match: {salary_glob}")
    path = files[-1]
    df = pd.read_excel(path) if path.lower().endswith((".xlsx", ".xls")) else pd.read_csv(path)
    # Normalize columns expected: Name (Last, First), Team, Pos, Salary
    # Handle odd columns if present
    cols = {c.strip().lower(): c for c in df.columns}
    # Try to map common variants
    rename = {}
    for k,v in cols.items():
        if k in ("name",): rename[v] = "Name"
        if k in ("team","tm"): rename[v] = "Team"
        if k in ("pos","position"): rename[v] = "Pos"
        if k in ("salary","sal"): rename[v] = "Salary"
        if k in ("proj","projection","projected"): rename[v] = "Proj"
    df = df.rename(columns=rename)
    if "Salary" not in df: raise ValueError("Salary column not found in salary file.")
    # Clean name to "Last, First"
    df["Name"] = df["Name"].astype(str).str.replace(r"\s+\(.*\)$", "", regex=True).str.strip()
    # Keep the essentials
    keep = [c for c in ["Name","Team","Pos","Salary","Proj"] if c in df.columns]
    return df[keep].copy()

