# src/mfl_client.py
from __future__ import annotations
import os, sys
from typing import Dict, Optional, Any, List
import requests
import pandas as pd

def _base(year: int) -> str:
    return f"https://www.myfantasyleague.com/{year}/export"

def _get(url: str, params: Dict[str, str], timeout: int = 25) -> Optional[dict]:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[mfl_client] WARN GET {url} failed: {e}", file=sys.stderr, flush=True)
        return None

class MFLClient:
    def __init__(self, year: int, league_id: str, api_key: str):
        self.year = int(year)
        self.league_id = str(league_id)
        self.api_key = api_key

    def league_standings(self, week: int) -> pd.DataFrame:
        params = {"TYPE":"leagueStandings", "L": self.league_id, "W": str(week), "APIKEY": self.api_key, "JSON":"1"}
        data = _get(_base(self.year), params)
        if not data or "leagueStandings" not in data: return pd.DataFrame()
        fr = data["leagueStandings"].get("franchise", [])
        if isinstance(fr, dict): fr = [fr]
        rows = []
        for f in fr:
            rows.append({
                "FranchiseID": f.get("id"),
                "H2H_W": int(f.get("h2hw", 0) or 0),
                "H2H_L": int(f.get("h2hl", 0) or 0),
                "H2H_T": int(f.get("h2ht", 0) or 0),
                "PF": float(f.get("pf", 0) or 0),
                "PA": float(f.get("pa", 0) or 0),
                "Streak": f.get("streak"),
                "Avg_PF": float(f.get("avg_pf", 0) or 0),
                "Avg_PA": float(f.get("avg_pa", 0) or 0),
            })
        return pd.DataFrame(rows)

    def weekly_results(self, week: int) -> pd.DataFrame:
        """Return starters/bench with points per franchise."""
        params = {"TYPE":"weeklyResults", "L": self.league_id, "W": str(week), "APIKEY": self.api_key, "JSON":"1"}
        data = _get(_base(self.year), params)
        rows: List[Dict[str, Any]] = []

        def add(fr_id: str, p: dict, starter: bool):
            rows.append({
                "Franchise": fr_id,
                "PlayerID": p.get("id") or p.get("player_id"),
                "Name": p.get("name"),
                "Team": p.get("team"),
                "Pos": p.get("position") or p.get("pos"),
                "Points": float(p.get("score", 0) or 0),
                "Starter": bool(starter),
            })

        if data and "weeklyResults" in data and "matchup" in data["weeklyResults"]:
            matchups = data["weeklyResults"]["matchup"]
            if isinstance(matchups, dict): matchups = [matchups]
            for m in matchups:
                franchises = m.get("franchise", [])
                if isinstance(franchises, dict): franchises = [franchises]
                for fr in franchises:
                    fr_id = fr.get("id")
                    starters = fr.get("starters", {}).get("player", [])
                    bench = fr.get("bench", {}).get("player", [])
                    if isinstance(starters, dict): starters = [starters]
                    if isinstance(bench, dict): bench = [bench]
                    for p in starters: add(fr_id, p, True)
                    for p in bench: add(fr_id, p, False)
            return pd.DataFrame(rows)

        # fallback: liveScoring with DETAILS=1
        params = {"TYPE":"liveScoring", "L": self.league_id, "W": str(week), "DETAILS":"1", "APIKEY": self.api_key, "JSON":"1"}
        data = _get(_base(self.year), params)
        if data and "liveScoring" in data and "matchup" in data["liveScoring"]:
            matchups = data["liveScoring"]["matchup"]
            if isinstance(matchups, dict): matchups = [matchups]
            for m in matchups:
                franchises = m.get("franchise", [])
                if isinstance(franchises, dict): franchises = [franchises]
                for fr in franchises:
                    fr_id = fr.get("id")
                    players = fr.get("players", {}).get("player", [])
                    if isinstance(players, dict): players = [players]
                    for p in players:
                        status = (p.get("status") or "").lower()
                        is_starter = (status == "starter") or (str(p.get("isStarter","")).strip() == "1")
                        add(fr_id, p, is_starter)
            return pd.DataFrame(rows)

        return pd.DataFrame()

    def pool(self, week: int, pooltype: str = "NFL") -> pd.DataFrame:
        params = {"TYPE":"pool", "L": self.league_id, "W": str(week), "POOLTYPE": pooltype, "APIKEY": self.api_key, "JSON":"1"}
        data = _get(_base(self.year), params)
        if not data or "pool" not in data: return pd.DataFrame()
        return pd.json_normalize(data["pool"]).fillna("")

    def survivor_pool(self, week: int) -> pd.DataFrame:
        params = {"TYPE":"survivorPool", "L": self.league_id, "W": str(week), "APIKEY": self.api_key, "JSON":"1"}
        data = _get(_base(self.year), params)
        if not data or "survivorPool" not in data: return pd.DataFrame()
        return pd.json_normalize(data["survivorPool"]).fillna("")

    def salaries(self, week: int) -> pd.DataFrame:
        """If your league exposes salaries via export. Otherwise return empty."""
        params = {"TYPE":"salaries", "L": self.league_id, "W": str(week), "APIKEY": self.api_key, "JSON":"1"}
        data = _get(_base(self.year), params)
        # If endpoint exists, normalize it; else return empty and your loader can take local file.
        if not data or "salaries" not in data:
            return pd.DataFrame()
        sal = data["salaries"].get("playerSalary", [])
        if isinstance(sal, dict): sal = [sal]
        rows = []
        for s in sal:
            rows.append({
                "PlayerID": s.get("id"),
                "Name": s.get("name"),
                "Team": s.get("team"),
                "Pos": s.get("position") or s.get("pos"),
                "Salary": s.get("salary"),
            })
        df = pd.DataFrame(rows)
        if "Salary" in df.columns:
            df["Salary"] = pd.to_numeric(df["Salary"], errors="coerce")
        return df
