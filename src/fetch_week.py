import os
import pandas as pd
from .mfl_client import MFLClient

def autodetect_week(client: MFLClient) -> int:
    # Strategy: find latest week with any points in weeklyResults
    for wk in range(18, 0, -1):
        try:
            data = client.weekly_results(wk)
            # If there are any matchup results with starters, call it valid
            if data.get("weeklyResults", {}).get("matchup"):
                return wk
        except Exception:
            continue
    return 1

def get_weekly_data(year: int, league_id: str, api_key: str, week: int | None):
    client = MFLClient(year, league_id, api_key)
    wk = week or autodetect_week(client)
    standings = client.league_standings()
    weekly = client.weekly_results(wk)
    # Survivor/pool may not have picks every week; safe to try
    try:
        survivor = client.survivor_pool()
    except Exception:
        survivor = None
    try:
        pool_nfl = client.pool_nfl(wk)
    except Exception:
        pool_nfl = None
    return wk, standings, weekly, survivor, pool_nfl

def flatten_weekly_starters(weekly_json: dict) -> pd.DataFrame:
    """
    Produce a DataFrame with (FranchiseId, FranchiseName, PlayerName, PlayerId, Pos, Pts, StarterFlag).
    We rely on weeklyResults DETAILS=1 to include starters and points.
    """
    rows = []
    matchups = weekly_json.get("weeklyResults", {}).get("matchup", [])
    if isinstance(matchups, dict): matchups = [matchups]
    for m in matchups:
        for side in ("franchise",):
            fr = m.get(side, [])
            if isinstance(fr, dict): fr = [fr]
            for team in fr:
                fid = team.get("id")
                fname = team.get("name")
                roster = team.get("players", {}).get("player", [])
                if isinstance(roster, dict): roster = [roster]
                for p in roster:
                    rows.append({
                        "FranchiseId": fid,
                        "FranchiseName": fname,
                        "PlayerId": p.get("id"),
                        "Name": p.get("name"),
                        "Pos": p.get("position"),
                        "Pts": float(p.get("score","0") or 0.0),
                        "Starter": (p.get("status") == "starter")
                    })
    df = pd.DataFrame(rows)
    # Only starters for DFS value/bust against cap
    return df[df["Starter"] == True].copy()

