from __future__ import annotations
from typing import Any, Dict, List, Tuple
import pandas as pd

def compute_values(players: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    rows = []
    for p in players:
        salary = max(float(p.get("salary") or 0), 1.0)
        pts = float(p.get("pts") or 0.0)
        ppk = pts / (salary/1000.0)
        rows.append({"Name": p.get("name",""), "Pos": p.get("pos",""), "Team": p.get("team",""), "Pts": pts, "Salary": salary, "Pts_per_$K": ppk})
    df = pd.DataFrame(rows)
    if df.empty:
        return {"best_individual": [], "worst_individual": []}
    best = df.sort_values("Pts_per_$K", ascending=False).head(5).to_dict("records")
    worst = df.sort_values("Pts_per_$K", ascending=True).head(5).to_dict("records")
    return {"best_individual": best, "worst_individual": worst}
