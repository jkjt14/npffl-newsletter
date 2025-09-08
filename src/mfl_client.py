import os
import time
import requests
from urllib.parse import urlencode
from tenacity import retry, wait_exponential, stop_after_attempt

BASE = "https://api.myfantasyleague.com"

class MFLClient:
    def __init__(self, year: int, league_id: str, api_key: str):
        self.year = year
        self.league_id = league_id
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "npffl-newsletter/1.0"})

    @retry(wait=wait_exponential(min=1, max=16), stop=stop_after_attempt(5))
    def _get(self, type_name: str, **params):
        """
        Generic MFL export fetcher using APIKEY + JSON=1
        Example endpoint:
        https://api.myfantasyleague.com/2025/export?TYPE=leagueStandings&L=35410&APIKEY=...&JSON=1
        """
        q = {"TYPE": type_name, "L": self.league_id, "APIKEY": self.api_key, "JSON": 1}
        q.update({k: v for k, v in params.items() if v is not None})
        url = f"{BASE}/{self.year}/export?{urlencode(q)}"
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        return r.json()

    def league_standings(self):
        return self._get("leagueStandings")

    def weekly_results(self, week: int):
        # RESULTS + starters/lineups for customization of value/busts per franchise
        return self._get("weeklyResults", W=week, DETAILS=1)

    def survivor_pool(self):
        return self._get("survivorPool")

    def pool_nfl(self, week: int | None = None):
        # NFL Pick'em; week optional
        return self._get("pool", POOLTYPE="NFL", W=week)

    def salaries(self):
        # Some leagues expose salaries via export=players or a league salary report.
        # If your league has a dedicated salaries export enabled:
        return self._get("salaries")

