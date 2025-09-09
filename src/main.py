from __future__ import annotations

import os
import sys
import argparse
import textwrap
import glob
import re
from pathlib import Path
from typing import Any, Dict, Optional

# Local imports (keep these names stable)
from .post_outputs import post_to_slack as post_slack, mailchimp_send
from .newsletter import render_newsletter

# Optional modules — imported inside functions with try/except to avoid hard crashes
#   - .mfl_client
#   - .load_salary
#   - .fetch_week
#   - .value_engine
#   - .roastbook

try:
    import yaml  # PyYAML
except Exception as e:  # pragma: no cover
    print("ERROR: PyYAML is required. Add 'PyYAML' to requirements.txt.", file=sys.stderr)
    raise

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
    # 1) CLI wins
    if args_week and args_week.strip().isdigit():
        return int(args_week.strip())

    inputs = (cfg.get("inputs") or {})

    # 2) explicit week (int/str)
    wk = inputs.get("week")
    if isinstance(wk, int):
        return wk
    if isinstance(wk, str) and wk.strip().isdigit():
        return int(wk.strip())

    # 3) week_strategy
    strat = inputs.get("week_strategy", "auto")
    if isinstance(strat, int):
        return strat
    if isinstance(strat, str) and strat.strip().isdigit():
        return int(strat.strip())

    # 4) auto: infer from salary filenames like YYYY_WW_Salary.xlsx
    salary_glob = inputs.get("salary_glob", "data/salaries/*Salary.xlsx")
    weeks: list[int] = []
    for p in glob.glob(salary_glob):
        m = re.search(r"(\d{4})_(\d{2})_Salary\.xlsx$", Path(p).name)
        if m:
            weeks.append(int(m.group(2)))
    if weeks:
        return max(weeks)

    # 5) safe default
    return 1

# -----------------------------
# Data Loading Helpers (best-effort)
# -----------------------------

def build_auth_from_env() -> Dict[str, Optional[str]]:
    return {
        "api_key": os.getenv("MFL_API_KEY"),
        "username": os.getenv("MFL_USERNAME"),
        "password": os.getenv("MFL_PASSWORD"),
    }

def make_mfl_client(auth: Dict[str, Optional[str]]):
    """
    Best-effort: construct an MFL client if the module/class exists.
    Otherwise return None — downstream fetch functions should accept that.
    """
    try:
        from .mfl_client import MFLClient  # type: ignore
    except Exception:
        return None

    # Prefer API key if present
    if auth.get("api_key"):
        try:
            return MFLClient(api_key=auth["api_key"])
        except Exception:
            pass

    # Fallback to username/password if present
    if auth.get("username") and auth.get("password"):
        try:
            return MFLClient(username=auth["username"], password=auth["password"])
        except Exception:
            pass

    # No viable auth
    return None

def load_salary_frame(cfg: Dict[str, Any]):
    """
    Returns a pandas.DataFrame or None.
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
    Returns a dict with whatever the fetch module provides, or {}.
    Tries a few common function names to be tolerant of implementation.
    """
    try:
        import importlib
        fw = importlib.import_module(__package__ + ".fetch_week")  # type: ignore
    except Exception:
        print("NOTE: fetch_week module not available; continuing with empty week data.")
        return {}

    league_id = cfg.get("league_id") or (cfg.get("newsletter") or {}).get("league_id")
    if not league_id:
        league_id = (cfg.get("inputs") or {}).get("league_id")

    # Try common entry points with graceful fallback
    for fn_name in ("fetch_week_data", "fetch_week", "get_week"):
        fn = getattr(fw, fn_name, None)
        if callable(fn):
            try:
                # Try passing client and league_id if supported, else fewer args
                try:
                    return fn(league_id=league_id, week=week, client=client)  # type: ignore[arg-type]
                except TypeError:
                    try:
                        return fn(league_id=league_id, week=week)  # type: ignore[misc]
                    except TypeError:
                        return fn(week)  # type: ignore[misc]
            except Exception as e:
                print(f"WARNING: {fn_name} raised: {e}", file=sys.stderr)
                break

    print("NOTE: No usable fetch function found in fetch_week; continuing empty.")
    return {}

def compute_values(salary_df, week_data) -> Dict[str, Any]:
    """
    Returns a result dict (top values, busts, etc.) or {}.
    """
    try:
        import importlib
        ve = importlib.import_module(__package__ + ".value_engine")  # type: ignore
    except Exception:
        print("NOTE: value_engine module not available; skipping value computation.")
        return {}

    # Try common function names
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
    Returns roasts/trophies payload or {}.
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

    # Auth + client (best-effort)
    auth = build_auth_from_env()
    client = make_mfl_client(auth)

    # Data pipeline (best-effort, with graceful fallbacks)
    salary_df = load_salary_frame(cfg)
    week_data = fetch_week_data(cfg, week, client)
    value_results = compute_values(salary_df, week_data)
    roasts = build_roasts(cfg, week, value_results, week_data)

    # Build a context for the newsletter (keep keys simple + tolerant)
    context: Dict[str, Any] = {
        "year": cfg.get("year"),
        "league_id": cfg.get("league_id"),
        "timezone": cfg.get("timezone", "America/New_York"),
        "newsletter": cfg.get("newsletter", {}),
        "trophies": cfg.get("trophies", []),
        "week": week,
        "data": {
            "salary_rows": int(getattr(salary_df, "shape", [0, 0])[0]) if salary_df is not None else 0,
            "week": week_data or {},
            "values": value_results or {},
            "roasts": roasts or {},
            "standings": (week_data or {}).get("standings"),
        },
    }

    # Render newsletter (Markdown + optional HTML)
    md_path = render_newsletter(context=context, output_dir=out_dir, week=week)
    print(f"[main] Wrote newsletter to {md_path}")

    # Optional Slack (post_outputs.post_to_slack is fail-soft if no webhook)
    push_to_slack = bool(out_cfg.get("push_to_slack", False))
    if push_to_slack:
        title = (cfg.get("newsletter") or {}).get("title", "NPFFL Weekly Roast")
        summary = f"{title} — Week {week}\n{Path(md_path).name}"
        try:
            post_slack(summary)
            print("[main] Posted summary to Slack.")
        except Exception as e:
            # Keep pipeline green even if Slack chokes
            print(f"WARNING: Slack post failed: {e}", file=sys.stderr)

    # Optional: email / Mailchimp hook if configured (no-op by default)
    # Example (only if you’ve implemented mailchimp_send):
    # mc_cfg = (cfg.get("mailchimp") or {})
    # if mc_cfg.get("enabled"):
    #     try:
    #         mailchimp_send(md_path, cfg, week)
    #     except Exception as e:
    #         print(f"WARNING: mailchimp_send failed: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
