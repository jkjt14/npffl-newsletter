from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import yaml

from .fetch_week import fetch_week_data
from .load_salary import load_salary_file
from .value_engine import compute_values
from .newsletter import render_newsletter
from .odds_client import fetch_odds_snapshot
from .post_outputs import maybe_post_to_slack

def read_config(path: str | Path = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def main() -> None:
    ap = argparse.ArgumentParser(description="Build NPFFL Weekly Newsletter")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--week", type=int, default=None, help="Override week number")
    args = ap.parse_args()

    cfg = read_config(args.config)
    year = int(cfg.get("year", 2025))
    league_id = str(cfg.get("league_id", "0"))
    week = int(args.week or 1)
    out_dir = str(cfg.get("outputs", {}).get("dir", "build"))
    make_html = bool(cfg.get("outputs", {}).get("make_html", True))
    title = str(cfg.get("newsletter", {}).get("title", "League Newsletter"))

    # Data fetching
    week_data = fetch_week_data(year, league_id, week)
    values = compute_values(week_data.get("players", []))
    odds = fetch_odds_snapshot()

    context = {
        "title": title,
        "year": year,
        "league_id": league_id,
        "week": week,
        "standings": week_data.get("standings", []),
        **values,
        "odds": odds,
    }

    outputs = render_newsletter(context, templates_dir=str(Path(__file__).parent / "templates"), out_dir=out_dir, make_html=make_html)
    if cfg.get("outputs", {}).get("push_to_slack"):
        maybe_post_to_slack(outputs.get("md"))

    print(json.dumps(outputs, indent=2))

if __name__ == "__main__":
    main()
