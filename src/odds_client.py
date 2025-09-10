from __future__ import annotations
from typing import Any, Dict, List

def fetch_odds_snapshot() -> List[Dict[str, Any]]:
    # Placeholder that keeps pipeline robust when no API key is present
    return [
        {"matchup":"DAL @ PHI","spread": -2.5, "total": 48.5},
        {"matchup":"GB @ CHI","spread": +1.5, "total": 43.0},
    ]
