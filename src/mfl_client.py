from __future__ import annotations
from typing import Any, Dict, List, Tuple
import os, requests

BASE = "https://api.myfantasyleague.com/%d/export"

def _api_key() -> str:
    return os.environ.get("MFL_API_KEY","").strip()

class MFLClient:
    def __init__(self, year: int, league_id: str):
        self.year = year
        self.league_id = str(league_id)

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        # Minimal wrapper; caller should handle failures gracefully
        params = dict(params or {})
        params.setdefault("JSON","1")
        params.setdefault("L", self.league_id)
        url = f"https://www46.myfantasyleague.com/{self.year}{endpoint}"
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()

    def standings(self) -> Dict[str, Any]:
        return self._get("/export", {"TYPE":"leagueStandings"})

    def weekly_results(self, week: int) -> Dict[str, Any]:
        return self._get("/export", {"TYPE":"liveScoring","W":week})
