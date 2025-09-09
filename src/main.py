from __future__ import annotations

import os
import sys
import argparse
import textwrap
import glob
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml  # requires PyYAML

# keep this import/alias — avoids ImportError if function is named post_to_slack
from .post_outputs import post_to_slack as post_slack, mailchimp_send
from .newsletter import render_newsletter


# -----------------------------
# Config / Week Resolution
# -----------------------------

def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_week(args_week: Optional[str], cfg: Dict[str, Any]) -> int:
    """
    Priority:
      1) --week CLI input if provided and numeric
      2) inputs.week (if present)
      3) inputs.week_strategy (int or "auto")
      4) infer from salary files matching inputs.salary_glob (pick max week)
      5) default to 1
    """
    # CLI wins
    if args_week and args_week.strip().isdigit():
        return int(args_week.strip())

    inputs = (cfg.get("inputs") or {})

    # explicit week
    wk = inputs.get("week")
    if isinstance(wk, int):
        return wk
    if isinstance(wk, str) and wk.strip().isdigit():
        return int(wk.strip())

    # strategy
    strat = inputs.get("week_strategy", "auto")
    if isinstance(strat, int):
        return strat
    if isinstance(strat, str) and strat.strip().isdigit():
        return int(strat.strip())

    # infer from salary filenames like YYYY_WW_Salary.xlsx
    salary_glob = inputs.get("salary_glob", "data/salaries/*Salary.xlsx")
    weeks: list[int] = []
    for p in glob.glob(salary_glob):
        m = re.search(r"(\d{4})_(\d{2})_Salary\.xlsx$", Path(p).name)
        if m:
            weeks.append(int(m.group(2)))
    if weeks:
        return max(weeks)

    return 1


# -----------------------------
# Auth / Clients
# -----------------------------

def build_auth_from_env() -> Dict[str, Optional[str]]:
    return {
        "username": os.getenv("MFL_USERNAME"),
        "password": os.getenv("MFL_PASSWORD"),
    }


def make_mfl_client(cfg: Dict[str, Any], auth: Dict[str, Optional[str]]):
    """
    Creates an authenticated MFL client (cookie-based). Returns None if unavailable.
    """
    try:
        from .mfl_client import MFLClient  # type: ignore
    except Exception as e:
        print(f"ERROR: mfl_client import failed: {e}", file=sys.stderr)
        return None

    league_id = cfg.get("league_id")
    if not league_id:
        print("ERROR: config.yaml missing 'league_id'", file=sys.stderr)
        return None

    host = os.getenv("MFL_HOST") or None
    year_env = os.getenv("MFL_YEAR")
    year = int(year_env) if year_env and year_env.isdigit() else None

    try:
        return MFLClient(
            league_id=league_id,
            username=auth.get("username"),
            password=auth.get("password"),
            host=host,
            year=year,
            user_agent=os.getenv("MFL_USER_AGENT", "NPFFLNewsletter/1.0 (automation)"),
        )
    except Exception as e:
        print(f"ERROR: failed to construct MFLClient: {e}", file=sys.stderr)
        return None


# -----------------------------
# Data Loading Helpers
# -----------------------------

def load_salary_frame(cfg: Dict[str, Any]):
    """
    Returns a pandas.DataFrame or None, and also returns the DF in context for rendering.
    """
    try:
        from .load_salary import load_salary  # type: ignore
    except Exception:
        print("NOTE: load_salary module not available; continuing without salaries.")
        return None

    pattern = (cfg.get("inputs") or {}).get("salary_glob", "data/salaries/*Salary.xlsx")
    try:
        return load_salary(pattern)
    except Exception as e:
        print(f"WARNING: load_salary failed: {e}", file=sys.stderr)
        return None


def fetch_week_data(cfg: Dict[str, Any], week: int, client) -> Dict[str, Any]:
    """
    Calls into src/fetch_week.py if present; returns {} if not available.
    """
    try:
        import importlib
        fw = importlib.import_module(__package__ + ".fetch_week")  # type: ignore
    except Exception:
        print("NOTE: fetch_week module not available; continuing with empty week data.")
        return {}

    # Try preferred signature
    fn = getattr(fw, "fetch_week_data", None)
    if callable(fn):
        try:
            return fn(cfg.get("league_id"), week, client)
        except Exception as e:
            print(f"WARNING: fetch_week_data failed: {e}", file=sys.stderr)
            return {}

    # Fallbacks if your function name differs
    for alt in ("fetch_week", "get_week"):
        f = getattr(fw, alt, None)
        if callable(f):
            try:
                return f(cfg.get("league_id"), week, client)  # type: ignore[misc]
            except Exception as e:
                print(f"WARNING: {alt} failed: {e}", file=sys.stderr)
                break

    return {}


def compute_values(salary_df, week_data) -> Dict[str, Any]:
    """
    Returns a dict (top_values/top_busts/etc.) or {}.
    """
    try:
        import importlib
        ve = importlib.import_module(__package__ + ".value_engine")  # type: ignore
    except Exception:
        print("NOTE: value_engine module not available; skipping value computation.")
        return {}

    for fn_name in ("compute_values", "compute_value", "run"):
        fn = getattr(ve, fn_name, None)
        if callable(fn):
            try:
                return fn(salary_df, week_data)  # type: ignore[misc]
            except Exception as e:
                print(f"WARNING: value_engine.{fn_name} failed: {e}", file=sys.stderr)
                break

    print("NOTE: No usable function found in value_engine; continuing without values.")
    return {}


def build_roasts(cfg: Dict[str, Any], week: int, value_results: Dict[str, Any], week_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns roasts/trophies data or {}.
    """
    try:
        import importlib
        rb = importlib.import_module(__package__ + ".roastbook")  # type: ignore
    except Exception:
        print("NOTE: roastbook module not available; skipping roasts.")
        return {}

    for fn_name in ("build_roasts", "generate_roasts", "run"):
        fn = getattr(rb, fn_name, None)
        if callable(fn):
            try:
                return fn(cfg, week, value_results, week_data)  # type: ignore[misc]
            except Exception as e:
                print(f"WARNING: roastbook.{fn_name} failed: {e}", file=sys.stderr)
                break

    print("NOTE: No usable function found in roastbook; continuing without roasts.")
    return {}


# -----------------------------
# Entry
# -----------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """\
            NPFFL Weekly Newsletter Orchestrator

            Typical usage (auto week from config or salaries):
              python -m src.main

            Force a specific week:
              python -m src.main --week 1
            """
        ),
    )
    parser.add_argument("--config", default=os.getenv("CONFIG", "config.yaml"))
    parser.add_argument("--week", default=os.getenv("WEEK", ""))
    args = parser.parse_args()

    cfg = load_config(args.config)
    out_cfg = (cfg.get("outputs") or {})
    out_dir = out_cfg.get("dir", "build")
    week = resolve_week(args.week, cfg)

    print(f"[main] Year={cfg.get('year')} League={cfg.get('league_id')} Week={week}")

    # Auth + client
    auth = build_auth_from_env()
    client = make_mfl_client(cfg, auth)

    # Data pipeline
    salary_df = load_salary_frame(cfg)
    week_data = fetch_week_data(cfg, week, client)
    value_results = compute_values(salary_df, week_data)
    roasts = build_roasts(cfg, week, value_results, week_data)

    # --- Debug: quick counts & raw JSON dumps to artifacts
try:
    import json
    dbg_dir = Path(out_dir) / "debug"
    dbg_dir.mkdir(parents=True, exist_ok=True)

    wr = week_data.get("weekly_results") or {}
    st_list = week_data.get("standings") or []
    pools = {
        "pool_nfl": week_data.get("pool_nfl") or {},
        "survivor_pool": week_data.get("survivor_pool") or {},
    }

    print("[debug] weekly_results keys:", list(wr.keys()) if isinstance(wr, dict) else type(wr).__name__)
    print("[debug] standings_count:", len(st_list) if isinstance(st_list, list) else 0)

    (dbg_dir / f"weekly_results_w{week}.json").write_text(json.dumps(wr, indent=2), encoding="utf-8")
    (dbg_dir / "standings.json").write_text(json.dumps(st_list, indent=2), encoding="utf-8")
    (dbg_dir / "pool_nfl.json").write_text(json.dumps(pools["pool_nfl"], indent=2), encoding="utf-8")
    (dbg_dir / "survivor_pool.json").write_text(json.dumps(pools["survivor_pool"], indent=2), encoding="utf-8")
except Exception as e:
    print(f"[debug] failed to write debug artifacts: {e}", file=sys.stderr)

    # Build rendering context
    context: Dict[str, Any] = {
        "year": cfg.get("year"),
        "league_id": cfg.get("league_id"),
        "timezone": cfg.get("timezone", "America/New_York"),
        "newsletter": cfg.get("newsletter", {}),
        "outputs": cfg.get("outputs", {}),
        "trophies": cfg.get("trophies", []),
        "week": week,
        "data": {
            "salary_rows": int(getattr(salary_df, "shape", [0, 0])[0]) if salary_df is not None else 0,
            "salary_df": salary_df,            # allow salary fallbacks in the template
            "week": week_data or {},
            "values": value_results or {},
            "roasts": roasts or {},
            "standings": (week_data or {}).get("standings"),
        },
    }

    # Render newsletter (Markdown + optional HTML)
    md_path = render_newsletter(context=context, output_dir=out_dir, week=week)
    print(f"[main] Wrote newsletter to {md_path}")

    # Slack summary (fail-soft if webhook missing)
    push_to_slack = bool(out_cfg.get("push_to_slack", False))
    if push_to_slack:
        title = (cfg.get("newsletter") or {}).get("title", "NPFFL Weekly Roast")
        lines = [
            f"{title} — Week {week}",
            Path(md_path).name,
        ]
        if value_results:
            tv = len(value_results.get("top_values") or [])
            tb = len(value_results.get("top_busts") or [])
            lines.append(f"Top values: {tv} | Busts: {tb}")
        if salary_df is not None:
            try:
                lines.append(f"Salary rows: {getattr(salary_df, 'shape', [0])[0]}")
            except Exception:
                pass
        summary = "\n".join(lines)
        try:
            post_slack(summary)
            print("[main] Posted summary to Slack.")
        except Exception as e:
            print(f"WARNING: Slack post failed: {e}", file=sys.stderr)

    # Placeholder for optional email / Mailchimp
    # mc_cfg = (cfg.get("mailchimp") or {})
    # if mc_cfg.get("enabled"):
    #     try:
    #         mailchimp_send(md_path, cfg, week)
    #     except Exception as e:
    #         print(f"WARNING: mailchimp_send failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
