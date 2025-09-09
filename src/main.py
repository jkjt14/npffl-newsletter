from __future__ import annotations

import argparse
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
    if x is None: return None
    s = str(x).strip()
    return int(s) if s.isdigit() else None


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
    assets_cfg = cfg.get("assets", {})
    salary_glob = inputs.get("salary_glob", "data/salaries/2025_*_Salary.xlsx")
    out_dir = outputs.get("dir", "build")

    week = _try_int(args.week) or 1

    client = MFLClient(league_id=league_id, year=year)

    week_data = fetch_week_data(client, week=week)

    salary_df = load_salary(salary_glob)

    values = compute_values(salary_df, {
        "weekly_results": week_data.get("weekly_results"),
        "players_map": week_data.get("players_map"),
    })

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

    context = {
        "timezone": tz,
        "newsletter": cfg.get("newsletter", {}),
        "outputs": cfg.get("outputs", {}),
        "franchise_map": week_data.get("franchise_names", {}),
        "assets": assets_cfg,
        "data": {
            "standings": week_data.get("standings_rows"),
            "weekly_results": week_data.get("weekly_results"),
            "values": values,
            "pool_nfl": week_data.get("pool_nfl"),
            "survivor_pool": week_data.get("survivor_pool"),
            "roasts": {"notes": roasts, **roasts},
        },
    }

    path = render_newsletter(context, output_dir=out_dir, week=week)
    print(f"[out] Wrote: {path}")


if __name__ == "__main__":
    main()
