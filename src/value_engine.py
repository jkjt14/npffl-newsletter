from __future__ import annotations
from typing import Any, Dict, List, Tuple
import pandas as pd

from typing import List, Dict, Any

def compute_values(players: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    players: list of dicts with at least keys: Name, Pos, Team, Pts, Salary
    returns: dict with 'value_leaders' and 'value_busts'
    """
    enriched = []
    for p in players:
        salary = float(p.get("Salary", 0) or 0)
        pts = float(p.get("Pts", 0) or 0)
        # avoid div-by-zero; if salary missing, treat as 0 -> value 0
        pts_per_k = (pts / (salary / 1000.0)) if salary > 0 else 0.0
        enriched.append({
            **p,
            "Pts_per_K": pts_per_k,  # <-- NO dollar sign in the key
        })

    # sort by value descending for leaders; ascending for busts
    leaders = sorted(enriched, key=lambda r: r["Pts_per_K"], reverse=True)[:10]
    busts   = sorted(enriched, key=lambda r: r["Pts_per_K"])[:10]

    return {
        "value_leaders": leaders,
        "value_busts": busts,
        "all_players_enriched": enriched,
    }

