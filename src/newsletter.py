from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
from jinja2 import Environment, FileSystemLoader, select_autoescape
import markdown


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
    out: List[Dict[str, str]] = []
    picks = (pool_nfl or {}).get("pool") or {}
    fr = picks.get("franchise") or []
    if isinstance(fr, dict):
        fr = [fr]
    for row in fr:
        fid = str(row.get("id") or "")
        name = franchise_names.get(fid, fid)
        px = row.get("pick") or []
        # normalize to list of dicts
        if isinstance(px, dict):
            px = [px]
        top3 = []
        for p in px:
            try:
                t = p.get("nflteam") or p.get("team") or ""
                c = int(p.get("points") or p.get("value") or 0)
                top3.append((t, c))
            except Exception:
                pass
        top3 = sorted(top3, key=lambda x: x[1], reverse=True)[:3]
        if top3:
            line = ", ".join([f"{t}({c})" for t, c in top3])
            out.append({"manager": name, "line": line})
    return out


def _mk_pool_summary(pool_nfl: Dict[str, Any], franchise_names: Dict[str, str]) -> Dict[str, Any]:
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

    # placeholders for boldest/faceplant until odds are wired (safe defaults)
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
    from collections import Counter
    rows: List[Dict[str, str]] = []
    no_picks: List[str] = []
    eliminated: List[str] = []  # can be derived if API returns outcome flags

    surv = (survivor_pool or {}).get("survivorPool") or {}
    fr = surv.get("franchise") or []
    if isinstance(fr, dict):
        fr = [fr]

    for row in fr:
        fid = str(row.get("id") or "")
        name = franchise_names.get(fid, fid)
        pick = row.get("pick") or ""
        if not pick:
            no_picks.append(name)
        rows.append({"manager": name, "pick": pick or "—"})

    picks = [r["pick"] for r in rows if r["pick"] and r["pick"] != "—"]
    mc = {"team": "—", "count": 0}
    if picks:
        t, cnt = Counter(picks).most_common(1)[0]
        mc = {"team": t, "count": cnt}

    # placeholder boldest = first non-empty
    boldest = {"manager": "—", "team": "—"}
   
