import pandas as pd

def normalize_name(last_first: str) -> str:
    # Normalize "Last, First ..."  (strip team/pos adornments if any slipped through)
    return (last_first or "").replace("\xa0", " ").split("  ")[0].strip()

def attach_salary(starters: pd.DataFrame, salary_df: pd.DataFrame) -> pd.DataFrame:
    starters = starters.copy()
    starters["NameNorm"] = starters["Name"].apply(normalize_name)
    salary_df = salary_df.copy()
    salary_df["NameNorm"] = salary_df["Name"].apply(normalize_name)

    merged = starters.merge(
        salary_df[["NameNorm","Salary","Pos"]].rename(columns={"Pos":"PosSalary"}),
        on="NameNorm", how="left"
    )
    return merged

def compute_value(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["Salary"] = pd.to_numeric(out["Salary"], errors="coerce")
    out["Pts"] = pd.to_numeric(out["Pts"], errors="coerce").fillna(0.0)
    out["Pts_per_$K"] = out["Pts"] / (out["Salary"] / 1000.0)
    return out

def leaderboard_values(df: pd.DataFrame, top_n=10):
    # Top individual values (steals)
    best = df.sort_values("Pts_per_$K", ascending=False).head(top_n)

    # Worst individual values (busts) among expensive players
    costly = df[df["Salary"] >= 6000].copy()
    worst = costly.sort_values("Pts_per_$K", ascending=True).head(top_n)

    # Team rollups
    team_agg = df.groupby(["FranchiseId","FranchiseName"], dropna=False).agg(
        Total_Salary=("Salary","sum"),
        Total_Points=("Pts","sum"),
        Avg_Pts_per_$K=("Pts_per_$K","mean")
    ).reset_index()
    team_best = team_agg.sort_values(["Avg_Pts_per_$K","Total_Points"], ascending=[False, False]).head(5)
    team_worst = team_agg.sort_values(["Avg_Pts_per_$K","Total_Points"], ascending=[True, True]).head(5)

    return best, worst, team_best, team_worst

