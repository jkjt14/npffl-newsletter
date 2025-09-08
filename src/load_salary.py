import glob
import pandas as pd

def load_latest_salary(salary_glob: str) -> pd.DataFrame:
    files = sorted(glob.glob(salary_glob))
    if not files:
        raise FileNotFoundError(f"No salary files match: {salary_glob}")
    path = files[-1]
    df = pd.read_excel(path) if path.lower().endswith((".xlsx", ".xls")) else pd.read_csv(path)

    # Normalize expected columns
    cols = {c.strip().lower(): c for c in df.columns}
    rename = {}
    for k,v in cols.items():
        if k == "name": rename[v] = "Name"
        if k in ("team","tm"): rename[v] = "Team"
        if k in ("pos","position"): rename[v] = "Pos"
        if k in ("salary","sal"): rename[v] = "Salary"
        if k in ("proj","projection","projected"): rename[v] = "Proj"
    df = df.rename(columns=rename)

    if "Name" not in df or "Salary" not in df:
        raise ValueError("Salary file must have columns: Name, Salary (and ideally Team, Pos).")

    df["Name"] = df["Name"].astype(str).str.replace(r"\s+\(.*\)$", "", regex=True).str.strip()
    keep = [c for c in ["Name","Team","Pos","Salary","Proj"] if c in df.columns]
    return df[keep].copy()
