from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
import pandas as pd

from .mfl_client import MFLClient
from .load_salary import load_salary
from .fetch_week import fetch_week_data
from .value_engine import compute_values
from .roastbook import build_roasts
from .newsletter import render_newsletter


def _load_yaml(p: Path) -> Dict[str, Any]:
    return yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}


def _try_int(x: Optional[str]) -> Optional[int]:
    if x is None:
        return None
    s = str(x).strip()
    return int(s) if s.isdigit() else None


def _load_optional_odds(year: int, week: int) -> Dict[str, Dict[str, float]]:
    """
    Load simple odds CSV if present.
    Expected columns (case-insensitive): team, win_prob (0-1 or 0-100).
    Locations tried:
      data/odds/{year}_week_{week:02d}_odds.csv
      data/odds/week_{week:02d}_odds.csv
    """
    paths = [
        Path(f"data/odds/{year}_week_{week:02d}_odds.csv"),
        Path(f"data/odds/week_{week:02d}_odds.csv"),
    ]
    for p in paths:
        if p.exists():
            try:
                df = pd.read_csv(p)
                cols = {c.lower().strip(): c for c in df.columns}
                team_c = cols.get("team")
                prob_c = cols.get("win_prob")
                if not team_c or not prob_c:
                    continue
                out = {}
                for _, r in df.iterrows():
                    t = str(r.get(team_c) or "").strip().upper()
                    if not t:
                        continue
                    prob = r.get(prob_c)
                    try:
                        prob = float(prob)
                        if prob > 1.0:
                            prob = prob / 100.0
                    except Exception:
                        continue
                    out[t] = {"win_prob": prob}
                if out:
                    print(f"[odds] loaded {len(out)} teams from {p}")
                    return out
            except Exception as e:
                print(f"[odds] failed to read {p}: {e}")
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default="")
    args = ap.parse_args()

    cfg = _load_yaml(Path("config.yaml"))
    year = int(cfg.get("year", 2025))
    league_id = str(cfg.get("league_id", ""))
    tz = cfg.get("timezone", "America/New_York")
    inputs = cfg.get("inputs", {})
    outputs = cfg.get("outputs", {})
    salary_glob = inputs.get("salary_glob", "data/salaries/2025_*_Salary.xlsx")
    out_dir = outputs.get("dir", "build")

    # Determine week
    week = _try_int(args.week)
    if week is None:
        # If "auto": choose latest completed week from API results; fallback to 1
        week = 1

    # Auth from env/secrets (username/password or API key/cookie handled in client)
    client = MFLClient(league_id=league_id, year=year, timezone=tz)

    # Fetch raw week JSON (weekly results, standings, pools, players map)
    week_data = fetch_week_data(client, week=week)

    # Load salary file
    salary_df = load_salary(salary_glob)

    # Compute values, busts, efficiency, headliners
    values = compute_values(salary_df, {
        "weekly_results": week_data.get("weekly_results"),
        "players_map": week_data.get("players_map"),
    })

    # Optional odds
    odds_map = _load_optional_odds(year, week)
    if odds_map:
        week_data["odds"] = odds_map

    # Build roasts/notes/trophies (deep commentary)
    roasts = build_roasts(
        {"franchise_names": week_data.get("franchise_names")},
        week,
        values,
        {
            "standings": week_data.get("standings_rows"),
            "weekly_results": week_data.get("weekly_results"),
            "pool_nfl": week_data.get("pool_nfl"),
            "survivor_pool": week_data.get("survivor_pool"),
            "odds": week_data.get("odds", {}),
        },
    )

    # Assemble context for newsletter renderer
    context = {
        "timezone": tz,
        "newsletter": cfg.get("newsletter", {}),
        "outputs": cfg.get("outputs", {}),
        "franchise_map": week_data.get("franchise_names", {}),
        "data": {
            "standings": week_data.get("standings_rows"),
            "weekly_results": week_data.get("weekly_results"),
            "values": values,
            "pool_nfl": week_data.get("pool_nfl"),
            "survivor_pool": week_data.get("survivor_pool"),
            "roasts": {"notes": roasts, **roasts},  # notes + trophies live together
        },
    }

    # Render newsletter
    path = render_newsletter(context, output_dir=out_dir, week=week)
    print(f"[out] Wrote: {path}")


if __name__ == "__main__":
    main()
