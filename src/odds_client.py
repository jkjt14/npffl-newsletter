from __future__ import annotations
import json
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError

# Minimal, dependency-free client for The Odds API (NFL moneyline)

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"
REGION = "us"
MARKETS = "moneyline"
FORMAT = "american"

# Common MFL / pool code variants -> sportsbook codes
TEAM_MAP = {
    "ARI": "ARI", "ATL": "ATL", "BAL": "BAL", "BUF": "BUF",
    "CAR": "CAR", "CHI": "CHI", "CIN": "CIN", "CLE": "CLE",
    "DAL": "DAL", "DEN": "DEN", "DET": "DET", "GB": "GB", "GBP": "GB",
    "HOU": "HOU", "IND": "IND", "JAC": "JAX", "JAX": "JAX",
    "KC": "KC", "KAN": "KC", "LAC": "LAC",
    "LAR": "LAR", "LV": "LV", "LVR": "LV",
    "MIA": "MIA", "MIN": "MIN", "NE": "NE", "NEP": "NE",
    "NO": "NO", "NOS": "NO", "NYG": "NYG", "NYJ": "NYJ",
    "PHI": "PHI", "PIT": "PIT", "SEA": "SEA",
    "SF": "SF", "SFO": "SF", "TB": "TB", "TBB": "TB",
    "TEN": "TEN", "WAS": "WSH", "WSH": "WSH",
}

def _http_get_json(url: str, headers: Optional[Dict[str, str]] = None) -> Any:
    req = Request(url, headers=headers or {})
    with urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def _american_to_prob(odds: float) -> float:
    # american moneyline to implied probability (0-1)
    try:
        o = float(odds)
    except Exception:
        return 0.5
    if o == 0.0:
        return 0.5
    if o > 0:
        return 100.0 / (o + 100.0)
    # negative favorite
    return (-o) / ((-o) + 100.0)

def _norm(team: str) -> str:
    return TEAM_MAP.get(team.upper().strip(), team.upper().strip())

def fetch_week_moneylines(api_key: Optional[str]) -> List[Dict[str, Any]]:
    """
    Pulls current NFL moneylines. If api_key is None or request fails, return [].
    Response normalized to:
    [
      {"home": "PHI", "away": "DAL", "home_prob": 0.61, "away_prob": 0.39},
      ...
    ]
    Note: The Odds API is not week-indexed; we fetch the board and use team codes.
    """
    if not api_key:
        return []
    url = (f"{ODDS_API_BASE}/sports/{SPORT}/odds?"
           f"regions={REGION}&markets={MARKETS}&oddsFormat={FORMAT}&apiKey={api_key}")
    try:
        data = _http_get_json(url)
    except URLError:
        return []
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for ev in data or []:
        home = _norm(ev.get("home_team") or "")
        away = _norm(ev.get("away_team") or "")
        ml = None
        for b in ev.get("bookmakers", []):
            for m in b.get("markets", []):
                if m.get("key") == "moneyline":
                    ml = m
                    break
            if ml:
                break
        if not ml:
            continue
        h_line = None
        a_line = None
        for o in ml.get("outcomes", []):
            t = _norm(o.get("name") or "")
            price = o.get("price")
            if t == home:
                h_line = price
            elif t == away:
                a_line = price
        if h_line is None or a_line is None:
            continue
        out.append({
            "home": home,
            "away": away,
            "home_prob": _american_to_prob(h_line),
            "away_prob": _american_to_prob(a_line),
        })
    return out

def build_team_prob_index(games: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Returns a dict of team -> implied win probability. Uses whichever side matches.
    """
    idx: Dict[str, float] = {}
    for g in games:
        idx[g["home"]] = max(idx.get(g["home"], 0.0), g["home_prob"])
        idx[g["away"]] = max(idx.get(g["away"], 0.0), g["away_prob"])
    return idx
