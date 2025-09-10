from __future__ import annotations
from typing import Any, Dict, List, Optional
import re
import pandas as pd
from rapidfuzz import process, fuzz

def _as_list(x):
    if isinstance(x, list): return x
    if isinstance(x, dict): return [x]
    return []

def _ppk(points: float, salary: Optional[float]):
    if salary and salary > 0:
        return round(points / (salary / 1000.0), 4)
    return None

def _clean_name(n: str) -> str:
    if not n: return ""
    n = n.strip()
    n = re.sub(r"\([^)]*\)", "", n)
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b\.?", "", n, flags=re.I)
    n = re.sub(r"[^A-Za-z0-9 ,.'-]+", " ", n)
    return re.sub(r"\s+", " ", n).strip().lower()

def _first_last(n: str) -> str:
    if not n: return ""
    if "," in n:
        last, first = [t.strip() for t in n.split(",", 1)]
        return f"{first} {last}".strip()
    return n.strip()

def _last_first(fl: str) -> str:
    toks = [t for t in (fl or "").split(" ") if t]
    if len(toks) >= 2:
        return f"{toks[-1]}, {' '.join(toks[:-1])}"
    return fl

def _build_salary_indices(df: pd.DataFrame):
    name_salary: Dict[str, float] = {}
    name_pos: Dict[str, str] = {}
    name_team: Dict[str, str] = {}
    for _, r in df.iterrows():
        sal = r.get("_salary")
        if pd.isna(sal):
            continue
        for k in (r.get("_fl_key"), r.get("_lf_key")):
            if not k: 
                continue
            name_salary[k] = float(sal)
            p = (r.get("_pos") or "").upper()
            t = (r.get("_team") or "").upper()
            if p: name_pos[k] = p
            if t: name_team[k] = t
    print(f"[value_engine] salary name keys: {len(name_salary)}")
    return name_salary, name_pos, name_team

def _best_salary_for_name(candidates: List[str], pos: str, team: str,
                          name_salary: Dict[str, float],
                          name_pos: Dict[str, str],
                          name_team: Dict[str, str]) -> Optional[float]:
    # exact key match first
    for k in candidates:
        if k in name_salary:
            return name_salary[k]

    # pos/team constrained fuzzy
    subset = []
    upos, uteam = (pos or "").upper(), (team or "").upper()
    for k in name_salary.keys():
        kp = (name_pos.get(k) or "").upper()
        kt = (name_team.get(k) or "").upper()
        if (upos and kp == upos) or (uteam and kt == uteam):
            subset.append(k)
    for src in (subset, list(name_salary.keys())):
        if not src:
            continue
        hit = process.extractOne(candidates[0], src, scorer=fuzz.WRatio, score_cutoff=68)
        if hit:
            return name_salary[hit[0]]
    return None

def compute_values(salary_df: pd.DataFrame, week_data: Dict[str, Any]) -> Dict[str, Any]:
    name_salary, name_pos, name_team = _build_salary_indices(salary_df)
    players_dir: Dict[str, Dict[str, str]] = week_data.get("players_map") or {}

    wr = week_data.get("weekly_results") or {}
    wr_root = wr.get("weeklyResults") if isinstance(wr, dict) else None
    franchises = _as_list(wr_root.get("franchise") if isinstance(wr_root, dict) else None)

    starters: List[Dict[str, Any]] = []
    unmatched_samples: List[str] = []

    for fr in franchises:
        fid = str(fr.get("id") or "").strip() or "unknown"
        for p in _as_list(fr.get("player")):
            # started only; treat empty as started (some shards omit 'status')
            st = (p.get("status") or "").lower()
            if st and st not in ("starter", "s"):
                continue

            pid = str(p.get("id") or "").strip()
            pts = float(p.get("score") or 0.0)

            meta = players_dir.get(pid) or {}
            raw = meta.get("raw") or (p.get("name") or "")
            fl  = meta.get("first_last") or _first_last(raw)
            lf  = meta.get("last_first") or _last_first(fl)
            pos = (meta.get("pos") or p.get("position") or "").upper()
            team= (meta.get("team") or p.get("team") or "").upper()

            # candidate keys — exact then fuzzy
            cands = [_clean_name(x) for x in (fl, lf, raw) if x]

            salary = _best_salary_for_name(cands, pos, team, name_salary, name_pos, name_team)
            if salary is None and len(unmatched_samples) < 8:
                unmatched_samples.append(f"{fl} [{pos}/{team}]")

            starters.append({
                "player_id": pid,
                "player": fl or raw or pid,
                "pos": pos,
                "team": team,
                "salary": salary,
                "pts": pts,
                "franchise_id": fid,
                "ppk": _ppk(pts, salary),
            })

    with_sal = [r for r in starters if r.get("salary")]
    print(f"[value_engine] starters={len(starters)} with_salary={len(with_sal)}")
    if with_sal and len(with_sal) < len(starters) // 2 and unmatched_samples:
        print("[value_engine] sample unmatched:", "; ".join(unmatched_samples))

    # Top performers (unique by player+pos)
    agg: Dict[str, Dict[str, Any]] = {}
    for r in starters:
        k = (r["player"].lower(), r.get("pos") or "")
        node = agg.setdefault(k, {"player": r["player"], "pos": r.get("pos"), "team": r.get("team"),
                                  "pts": 0.0, "franchise_ids": set()})
        node["pts"] = max(node["pts"], r["pts"])
        node["franchise_ids"].add(r["franchise_id"])

    top_performers = sorted(
        [{"player": v["player"], "pos": v["pos"], "team": v["team"], "pts": v["pts"],
          "franchise_ids": sorted(list(v["franchise_ids"]))}
         for v in agg.values()],
        key=lambda x: x["pts"], reverse=True
    )[:10]

    # Values / Busts (pts per $1K)
    with_ppk = [r for r in with_sal if r.get("ppk") is not None]
    top_values = sorted(with_ppk, key=lambda r: (r["ppk"], r["pts"]), reverse=True)[:10]
    top_busts  = sorted(with_ppk, key=lambda r: (r["ppk"], -r["pts"]))[:10]

    # Team efficiency
    team_totals: Dict[str, Dict[str, float]] = {}
    for r in starters:
        d = team_totals.setdefault(r["franchise_id"], {"pts": 0.0, "sal": 0.0})
        d["pts"] += float(r["pts"] or 0.0)
        if r.get("salary"):
            d["sal"] += float(r["salary"])

    team_eff = []
    for fid, d in team_totals.items():
        total_pts = round(d["pts"], 2)
        total_sal = int(d["sal"]) if d["sal"] else 0
        team_eff.append({"franchise_id": fid, "total_pts": total_pts,
                         "total_sal": total_sal, "ppk": _ppk(total_pts, d["sal"])})

    team_eff.sort(key=lambda r: ((r["ppk"] or 0.0), r["total_pts"]), reverse=True)

    return {
        "top_values": top_values,
        "top_busts": top_busts,
        "team_efficiency": team_eff,
        "top_performers": top_performers,
        "samples": {"starters": len(starters), "with_salary": len(with_sal)},
    }
