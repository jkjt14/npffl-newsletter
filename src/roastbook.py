from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, List

# ---------- helpers ----------

def _name_for(fid: str, fmap: Dict[str, str]) -> str:
    return fmap.get(str(fid), str(fid))


def _as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x]
    return []


def _fmt(x, n=2):
    try:
        return f"{float(x):.{n}f}"
    except Exception:
        return str(x)


def _seed_rng(week: int) -> random.Random:
    h = hashlib.sha1(f"npffl_roastblog_week_{week}".encode()).hexdigest()
    return random.Random(int(h[:12], 16))


def _choose(rng: random.Random, opts: List[str]) -> str:
    return opts[rng.randrange(0, len(opts))] if opts else ""


# ---------- per-section narratives (no explicit “points per dollar” language) ----------

def opener(week: int, standings: List[dict], efficiency: List[dict], fmap: Dict[str, str]) -> str:
    st = list(standings or [])
    try:
        st = sorted(st, key=lambda r: (float(r.get("pf") or 0), float(r.get("vp") or 0)), reverse=True)
    except Exception:
        pass
    top = st[0] if st else None
    low = st[-1] if st else None
    top_name = _name_for(top.get("id","?"), fmap) if top else "Somebody"
    low_name = _name_for(low.get("id","?"), fmap) if low else "Somebody"
    top_pts = _fmt(top.get("pf", 0))
    low_pts = _fmt(low.get("pf", 0))

    # Efficiency leader (ordered elsewhere by ppk internally)
    eff = [e for e in (efficiency or []) if e.get("ppk") is not None]
    leader = eff[0] if eff else None
    eff_name = _name_for(leader.get("franchise_id","?"), fmap) if leader else top_name

    rng = _seed_rng(week)
    spice = _choose(rng, [
        "Half the league was stuck in neutral while the frontrunners floored it.",
        "If panic trades had a sound, this week was a marching band.",
        "Even the waiver wire looked concerned.",
    ])
    return f"{top_name} set the bar at **{top_pts}**, while {low_name} brought the floor down to **{low_pts}**. {eff_name} squeezed every last drop out of the lineup. {spice}"


def standings_note(standings: List[dict], fmap: Dict[str, str]) -> str:
    if not standings:
        return "Standings? Foggy. So were a few Sunday decisions."
    try:
        st = sorted(standings, key=lambda r: (float(r.get("vp") or 0), float(r.get("pf") or 0)), reverse=True)
    except Exception:
        st = standings
    top3 = ", ".join(_name_for(r.get("id","?"), fmap) for r in st[:3])
    bottom3 = ", ".join(_name_for(r.get("id","?"), fmap) for r in st[-3:])
    return f"Up top: {top3}. In the cellar: {bottom3}. Everyone else is loitering around the middle like it’s happy hour."


def scores_note(weekly_results: Dict[str, Any]) -> str:
    wr = weekly_results.get("weeklyResults") if isinstance(weekly_results, dict) else None
    fr = _as_list(wr.get("franchise") if isinstance(wr, dict) else None)
    if not fr:
        return "The scoreboard took a personal day."
    scores = []
    for f in fr:
        try:
            scores.append(float(f.get("score") or 0.0))
        except Exception:
            pass
    if not scores:
        return "Points were allergic to your lineups."
    hi, lo = max(scores), min(scores)
    return f"Spread check: **{_fmt(lo)} → {_fmt(hi)}**. Enough chaos to make projections cry."


def performers_note(top_performers: List[dict], fmap: Dict[str, str]) -> str:
    if not top_performers:
        return "Headliners: The stage was empty. Fitting for some benches."
    head = top_performers[:5]
    bits = []
    for r in head:
        mgrs = ", ".join(_name_for(fid, fmap) for fid in (r.get("franchise_ids") or []))
        bits.append(f"{r.get('player')} {r.get('pos') or ''} {r.get('team') or ''} **{_fmt(r.get('pts'))}** ({mgrs})")
    return "Headliners: " + "; ".join(bits) + ". If you weren’t riding with one of these, you were dragging a piano uphill."


def values_note(top_values: List[dict], top_busts: List[dict]) -> str:
    # Deliberately avoid exposing the metric; use vibe-y language
    parts = []
    if top_values:
        a = top_values[0]
        parts.append(f"{a.get('player')} was premium production on a clearance tag.")
    if top_busts:
        b = top_busts[0]
        parts.append(f"{b.get('player')} came priced like gold and played like tin.")
    return " ".join(parts) if parts else "Value vs. Busts: the receipts are… mixed."


def efficiency_note(efficiency: List[dict], fmap: Dict[str, str]) -> str:
    eff = [e for e in efficiency if e.get("ppk") is not None]
    if not eff:
        return "The efficiency board refused to incriminate anyone."
    best = eff[0]; worst = eff[-1]
    return f"Efficiency tiers: {_name_for(best.get('franchise_id','?'), fmap)} ran a clinic; {_name_for(worst.get('franchise_id','?'), fmap)} set money on fire."


def confidence_note(week: int, pool_nfl: Dict[str, Any], fmap: Dict[str, str]) -> str:
    pr = pool_nfl.get("poolPicks") if isinstance(pool_nfl, dict) else None
    if not isinstance(pr, dict):
        return "Confidence picks: a lot of confidence, questionable picks."
    best_sum, best_id = None, None
    no_picks: List[str] = []
    for fr in _as_list(pr.get("franchise")):
        fid = fr.get("id")
        # find week node
        wk = None
        for w in _as_list(fr.get("week")):
            if str(w.get("week") or "") == str(week):
                wk = w; break
        if not wk:
            no_picks.append(_name_for(fid, fmap)); continue
        games = _as_list(wk.get("game"))
        if not games:
            no_picks.append(_name_for(fid, fmap)); continue
        try:
            s = sum(sorted([int(g.get("rank") or 0) for g in games], reverse=True)[:3])
            if best_sum is None or s > best_sum:
                best_sum, best_id = s, fid
        except Exception:
            pass
    parts = []
    if best_id is not None:
        parts.append(f"{_name_for(best_id, fmap)} stacked the heaviest numbers up top and didn’t flinch.")
    if no_picks:
        parts.append(f"Also, {', '.join(no_picks)} forgot to submit. Bold strategy.")
    return " ".join(parts) if parts else "Confidence: chaos with a side of swagger."


def survivor_note(week: int, survivor_pool: Dict[str, Any], fmap: Dict[str, str]) -> str:
    sp = survivor_pool.get("survivorPool") if isinstance(survivor_pool, dict) else None
    if not isinstance(sp, dict):
        return "Survivor: everyone survived boredom."
    no_pick: List[str] = []
    picks: Dict[str, int] = {}
    for fr in _as_list(sp.get("franchise")):
        fid = fr.get("id")
        wk = None
        for w in _as_list(fr.get("week")):
            if str(w.get("week") or "") == str(week):
                wk = w; break
        if not wk or not wk.get("pick"):
            no_pick.append(_name_for(fid, fmap)); continue
        team = str(wk.get("pick"))
        picks[team] = picks.get(team, 0) + 1
    parts = []
    if picks:
        top_team = sorted(picks.items(), key=lambda kv: kv[1], reverse=True)[0][0]
        parts.append(f"Most popular lifeline: **{top_team}**. Safety in numbers… until there isn’t.")
    if no_pick:
        parts.append(f"No-pick stroll of shame: {', '.join(no_pick)}.")
    return " ".join(parts) if parts else "Survivor: everyone tiptoed, nobody tripped."
    

# ---------- public API ----------

def build_roasts(cfg: Dict[str, Any], week: int, value_results: Dict[str, Any], week_data: Dict[str, Any]) -> Dict[str, Any]:
    fmap = (cfg or {}).get("franchise_names") or {}
    standings: List[dict] = (week_data or {}).get("standings") or []
    weekly_results: Dict[str, Any] = (week_data or {}).get("weekly_results") or {}
    top_values: List[dict] = (value_results or {}).get("top_values") or []
    top_busts: List[dict]  = (value_results or {}).get("top_busts") or []
    top_performers: List[dict] = (value_results or {}).get("top_performers") or []
    efficiency: List[dict] = (value_results or {}).get("team_efficiency") or []
    pool_nfl: Dict[str, Any] = (week_data or {}).get("pool_nfl") or {}
    survivor_pool: Dict[str, Any] = (week_data or {}).get("survivor_pool") or {}

    # Trophies (short, punchy). We keep these as before via value math:
    trophies: Dict[str, str] = {}
    if top_values:
        a = top_values[0]
        trophies["coupon_clipper"] = f"{a.get('player')} was premium production on a markdown sticker."
    if top_busts:
        b = top_busts[0]
        trophies["dumpster_fire"] = f"{b.get('player')} charged steakhouse prices and served cold fries."
    # “Galaxy Brain” — best raw points at modest tag (<= $6K), if present
    modest = [r for r in (top_values + top_busts) if r.get('salary') and float(r['salary']) <= 6000]
    if modest:
        best = sorted(modest, key=lambda r: r.get("pts") or 0, reverse=True)[0]
        trophies["galaxy_brain"] = f"{best.get('player')} turned small change into loud points."
    # Walk of Shame — lowest team score
    wr = weekly_results.get("weeklyResults") if isinstance(weekly_results, dict) else None
    frs = _as_list(wr.get("franchise") if isinstance(wr, dict) else None)
    if frs:
        worst = sorted(frs, key=lambda f: float(f.get("score") or 0))[0]
        trophies["walk_of_shame"] = f"{_name_for(worst.get('id','?'), fmap)} tripped over { _fmt(worst.get('score')) }."
    # Banana Peel — heaviest stacked confidence ranks
    pr = pool_nfl.get("poolPicks") if isinstance(pool_nfl, dict) else None
    if isinstance(pr, dict):
        best_sum, best_id = None, None
        for fr in _as_list(pr.get("franchise")):
            fid = fr.get("id")
            for w in _as_list(fr.get("week")):
                games = _as_list(w.get("game"))
                try:
                    s = sum(sorted([int(g.get("rank") or 0) for g in games], reverse=True)[:3])
                    if best_sum is None or s > best_sum:
                        best_sum, best_id = s, fid
                except Exception:
                    pass
                break
        if best_id is not None:
            trophies["banana_peel"] = f"{_name_for(best_id, fmap)} piled the biggest numbers on their ‘sure things’ and dared the football gods."

    # Section narratives
    notes = {
        "opener": opener(week, standings, efficiency, fmap),
        "standings": standings_note(standings, fmap),
        "scores": scores_note(weekly_results),
        "performers": performers_note(top_performers, fmap),
        "values": values_note(top_values, top_busts),
        "efficiency": efficiency_note(efficiency, fmap),
        "confidence": confidence_note(week, pool_nfl, fmap),
        "survivor": survivor_note(week, survivor_pool, fmap),
    }

    return {"notes": notes, **trophies}
