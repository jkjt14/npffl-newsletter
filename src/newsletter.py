# src/newsletter.py
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from jinja2 import Environment, FileSystemLoader, select_autoescape
import markdown

__all__ = ["render_newsletter"]


# ---------------------------
# Jinja environment
# ---------------------------
def _mk_env() -> Environment:
    tpl_dir = Path("templates")
    tpl_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(tpl_dir)),
        autoescape=select_autoescape(enabled_extensions=("html",))
    )
    return env


# ---------------------------
# Helpers to summarize pools
# ---------------------------
def _fmt_top3_conf(pool_nfl: Dict[str, Any], franchise_names: Dict[str, str]) -> List[Dict[str, str]]:
    """Return [{'manager': 'Team Name', 'line': 'PHI(16), CIN(15), DEN(14)'}]"""
    out: List[Dict[str, str]] = []
    picks = (pool_nfl or {}).get("pool") or {}
    fr = picks.get("franchise") or []
    if isinstance(fr, dict):
        fr = [fr]
    for row in fr:
        fid = str(row.get("id") or "")
        name = franchise_names.get(fid, fid)
        px = row.get("pick") or []
        if isinstance(px, dict):
            px = [px]
        top3: List[Tuple[str, int]] = []
        for p in px:
            try:
                t = p.get("nflteam") or p.get("team") or ""
                c = int(p.get("points") or p.get("value") or 0)
                if t:
                    top3.append((t, c))
            except Exception:
                pass
        top3.sort(key=lambda x: x[1], reverse=True)
        top3 = top3[:3]
        if top3:
            line = ", ".join([f"{t}({c})" for t, c in top3])
            out.append({"manager": name, "line": line})
    return out


def _mk_pool_summary(pool_nfl: Dict[str, Any], franchise_names: Dict[str, str]) -> Dict[str, Any]:
    """Lightweight summary for template. Safe defaults; enhance later with odds/outcomes."""
    from collections import Counter
    top3 = _fmt_top3_conf(pool_nfl, franchise_names)

    all_firsts: List[str] = []
    no_picks: List[str] = []
    picks = (pool_nfl or {}).get("pool") or {}
    fr = picks.get("franchise") or []
    if isinstance(fr, dict):
        fr = [fr]
    for row in fr:
        fid = str(row.get("id") or "")
        name = franchise_names.get(fid, fid)
        px = row.get("pick") or []
        if isinstance(px, dict):
            px = [px]
        if not px:
            no_picks.append(name)
        else:
            # take highest-confidence as "first"
            try:
                first = max(px, key=lambda p: int(p.get("points") or p.get("value") or 0))
                t = first.get("nflteam") or first.get("team") or ""
                if t:
                    all_firsts.append(t)
            except Exception:
                pass

    most_common = {"team": "—", "count": 0}
    if all_firsts:
        t, cnt = Counter(all_firsts).most_common(1)[0]
        most_common = {"team": t, "count": cnt}

    # placeholders until odds/outcomes are wired
    boldest = {"manager": (top3[0]["manager"] if top3 else "—"), "team": "—", "conf": "—"}
    faceplant = {"manager": "—", "team": "—", "conf": "—"}

    return {
        "top3": top3,
        "no_picks": no_picks,
        "most_common": most_common,
        "boldest": boldest,
        "faceplant": faceplant,
    }


def _mk_survivor_summary(survivor_pool: Dict[str, Any], franchise_names: Dict[str, str]) -> Dict[str, Any]:
    """Return rows + simple aggregates. Safe even with sparse data."""
    from collections import Counter
    rows: List[Dict[str, str]] = []
    no_picks: List[str] = []
    eliminated: List[str] = []  # derive later if API exposes results

    surv = (survivor_pool or {}).get("survivorPool") or {}
    fr = surv.get("franchise") or []
    if isinstance(fr, dict):
        fr = [fr]

    for row in fr:
        fid = str(row.get("id") or "")
        name = franchise_names.get(fid, fid)
        pick = (row.get("pick") or "").strip()
        if not pick:
            no_picks.append(name)
            rows.append({"manager": name, "pick": "—"})
        else:
            rows.append({"manager": name, "pick": pick})

    picks = [r["pick"] for r in rows if r["pick"] and r["pick"] != "—"]
    mc = {"team": "—", "count": 0}
    if picks:
        t, cnt = Counter(picks).most_common(1)[0]
        mc = {"team": t, "count": cnt}

    # placeholder boldest = first non-empty if any
    boldest = {"manager": "—", "team": "—"}
    for r in rows:
        if r["pick"] != "—":
            boldest = {"manager": r["manager"], "team": r["pick"]}
            break

    return {
        "rows": rows,
        "no_picks": no_picks,
        "eliminated": eliminated,
        "most_common": mc,
        "boldest": boldest,
    }


# ---------------------------
# Public API
# ---------------------------
def render_newsletter(
    payload: Dict[str, Any],
    output_dir: Optional[str | Path] = None,
    week: Optional[int] = None,
) -> Dict[str, str]:
    """
    Renders the narrative-first newsletter.

    Args:
        payload: context dict (see template for expected keys).
        output_dir: directory to write files (default 'build').
        week: week number used for filename label; if None, derive from payload 'week_label'.

    Returns:
        {
          "md": "<markdown string>",
          "html": "<html string>",
          "md_path": "build/NPFFL_Week_##.md",
          "html_path": "build/NPFFL_Week_##.html"
        }
    """
    title = payload.get("title", "NPFFL Weekly Roast")
    week_label = payload.get("week_label")
    if not week_label:
        if week is not None:
            week_label = f"{int(week):02d}"
        else:
            week_label = "01"

    timezone = payload.get("timezone", "America/New_York")
    standings_rows = payload.get("standings_rows", [])
    team_efficiency = payload.get("team_efficiency", [])
    top_performers = payload.get("top_performers", [])
    top_values = payload.get("top_values", [])
    top_busts = payload.get("top_busts", [])
    franchise_names = payload.get("franchise_names", {})
    roasts = payload.get("roasts", {})

    # Build summaries for pools if caller didn't provide them
    pool_nfl_summary = payload.get("pool_nfl_summary")
    if pool_nfl_summary is None:
        pool_nfl_summary = _mk_pool_summary(payload.get("pool_nfl", {}), franchise_names)

    survivor_summary = payload.get("survivor_summary")
    if survivor_summary is None:
        survivor_summary = _mk_survivor_summary(payload.get("survivor_pool", {}), franchise_names)

    # Jinja render
    env = _mk_env()
    try:
        tpl = env.get_template("newsletter.md.j2")
    except Exception as e:
        # Helpful error if template missing
        raise RuntimeError(
            "Missing template 'templates/newsletter.md.j2'. "
            "Create it per instructions or ensure it’s included in the repo."
        ) from e

    md = tpl.render(
        title=title,
        week_label=week_label,
        timezone=timezone,
        standings_rows=standings_rows,
        team_efficiency=team_efficiency,
        top_performers=top_performers,
        top_values=top_values,
        top_busts=top_busts,
        pool_nfl_summary=pool_nfl_summary,
        survivor_summary=survivor_summary,
        franchise_names=franchise_names,
        roasts=roasts,
        manager_traits=payload.get("manager_traits", {}),
    )

    html = markdown.markdown(md, extensions=["tables", "fenced_code"])

    # Write to disk if requested (or default to build/)
    out_dir = Path(output_dir) if output_dir else Path("build")
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"NPFFL_Week_{week_label}.md"
    html_path = out_dir / f"NPFFL_Week_{week_label}.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")

    return {
        "md": md,
        "html": html,
        "md_path": str(md_path),
        "html_path": str(html_path),
    }
