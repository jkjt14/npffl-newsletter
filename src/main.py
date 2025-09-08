import os, argparse, textwrap
import pandas as pd
from pathlib import Path
import yaml
from .fetch_week import get_weekly_data, flatten_weekly_starters
from .load_salary import load_latest_salary
from .value_engine import attach_salary, compute_value, leaderboard_values
from .roastbook import roast_value, roast_bust
from .newsletter import render_newsletter
from .post_outputs import post_slack, mailchimp_send

def read_config():
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default="", help="Week number (1-18). Leave blank for auto.")
    args = ap.parse_args()
    cfg = read_config()

    year = int(cfg["year"])
    league_id = str(cfg["league_id"])
    api_key = os.getenv("MFL_API_KEY")
    week = int(args.week) if args.week.strip().isdigit() else (cfg["inputs"]["week"] or None)

    wk, standings, weekly, survivor, pool_nfl = get_weekly_data(year, league_id, api_key, week)
    starters = flatten_weekly_starters(weekly)
    salary_df = load_latest_salary(cfg["inputs"]["salary_glob"])
    merged = attach_salary(starters, salary_df)
    merged = compute_value(merged)

    best_ind, worst_ind, team_best, team_worst = leaderboard_values(merged)
    best_ind = best_ind.copy(); worst_ind = worst_ind.copy()
    best_ind["Roast"] = best_ind.apply(roast_value, axis=1)
    worst_ind["Roast"] = worst_ind.apply(roast_bust, axis=1)

    standings_text = "Standings will tighten once Week 1 finalizes."
    survivor_text = "Pending final week data or survivorPool export."
    pickem_text = "Pending final week data or pool (NFL) export."

    context = {
        "title": cfg["newsletter"]["title"],
        "week": wk,
        "best_individual": best_ind.to_dict(orient="records"),
        "worst_individual": worst_ind.to_dict(orient="records"),
        "team_best": team_best.to_dict(orient="records"),
        "team_worst": team_worst.to_dict(orient="records"),
        "standings_text": standings_text,
        "survivor_text": survivor_text,
        "pickem_text": pickem_text,
    }
    out_md = render_newsletter(context, cfg["outputs"]["dir"], wk)

    if cfg["outputs"].get("post_to_slack", False):
        summary = f"NPFFL Week {wk} — Newsletter ready\nTop value: {best_ind.iloc[0]['Name']} at {best_ind.iloc[0]['Pts_per_$K']:.2f} pts/$1K\nDumpster fire: {worst_ind.iloc[0]['Name']} at {worst_ind.iloc[0]['Pts_per_$K']:.2f} pts/$1K\nFile: {out_md}"
        post_slack(summary)

    if cfg["outputs"].get("post_to_mailchimp", False):
        md_text = Path(out_md).read_text(encoding="utf-8")
        html = "<pre style='font-family: ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre-wrap'>" + \
               md_text.replace("<","&lt;").replace(">","&gt;") + "</pre>"
        mailchimp_send(subject=f"NPFFL Week {wk} Newsletter", html=html)

if __name__ == "__main__":
    main()
