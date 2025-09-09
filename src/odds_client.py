from __future__ import annotations

import os
from typing import Dict, Any, Optional
import requests
import math


ODDS_API_BASE = "https://api.the-odds-api.com/v4"


def _implied_prob_from_moneyline(money: Optional[float]) -> Optional[float]:
    if money is None:
        return None
    try:
        ml = float(money)
    except Exception:
        return None
    if ml < 0:
        # favorite
        return (-ml) / ((-ml) + 100.0)
    else:
        # dog
        return 100.0 / (ml + 100.0)


def fetch_week_win_probs_nfl(week: int, season_year: int) -> Dict[str, Dict[str, float]]:
    """
    Return map like {"PHI": {"win_prob": 0.68}, "ARI": {"win_prob": 0.41}, ...}
    Using the-odds-api.com. Requires THE_ODDS_API_KEY in env.

    We average across available bookmakers (or pick one if you prefer).
    """
    api_key = os.environ.get("THE_ODDS_API_KEY", "").strip()
    if not api_key:
        return {}

    # the-odds-api NFL gridiron is "americanfootball_nfl"
    # markets: "h2h" gives moneylines
    # We don't have official "week" labeling across providers, so we pull all upcoming
    # and then just compute implied win probs per team from moneyline where available.
    url = f"{ODDS_API_BASE}/sports/americanfootball_nfl/odds"
    params = {
        "apiKey": api_key,
        "regions": "us,us2",   # us books
        "markets": "h2h",
        "oddsFormat": "american",
    }

    try:
        r = requests.get(url, params=params, timeout=25)
        r.raise_for_status()
        games = r.json()
    except Exception:
        return {}

    # Aggregate moneylines per team
    agg: Dict[str, Dict[str, float]] = {}   # team -> {"sum": x, "n": k}
    for g in games or []:
        # current state: g["bookmakers"] -> [ {"markets":[{"outcomes":[{"name":"Philadelphia Eagles","price":-200},...] }]} ]
        bookmakers = g.get("bookmakers") or []
        for bk in bookmakers:
            for m in (bk.get("markets") or []):
                if (m.get("key") or "") != "h2h":
                    continue
                for oc in (m.get("outcomes") or []):
                    name = (oc.get("name") or "").strip()
                    price = oc.get("price")
                    prob = _implied_prob_from_moneyline(price)
                    if prob is None:
                        continue
                    # Map full team name to short code guess; we keep both for safety.
                    # The newsletter uses short NFL codes. We include uppercased word code if present.
                    # Minimal normalization: take last token or standard 3-letter codes if present.
                    # We'll keep the full name as key as fallback.
                    key = name.upper()
                    # Also derive a naive code: first 3 letters of last word
                    parts = [p for p in name.split(" ") if p]
                    if parts:
                        code_guess = parts[-1][:3].upper()
                        for k in {key, code_guess}:
                            agg.setdefault(k, {"sum": 0.0, "n": 0})
                            agg[k]["sum"] += prob
                            agg[k]["n"] += 1

    out: Dict[str, Dict[str, float]] = {}
    for k, v in agg.items():
        if v["n"] > 0:
            out[k] = {"win_prob": v["sum"] / v["n"]}
    return out

