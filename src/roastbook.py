from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Dict, List, Tuple, Optional


# -------------------------
# Basic helpers
# -------------------------

def _as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x]
    return []


def _fmt2(x) -> str:
    try:
        return f"{float(x):.2f}"
    except Exception:
        return str(x)


def _name_for(fid: str, fmap: Dict[str, str]) -> str:
    return fmap.get(str(fid), str(fid)) if fid else "unknown"


def _seed_rng(week: int) -> random.Random:
    h = hashlib.sha1(f"npffl_blog_week_{week}".encode()).hexdigest()
    return random.Random(int(h[:12], 16))


def _choose(rng: random.Random, opts: List[str]) -> str:
    return opts[rng.randrange(0, len(opts))] if opts else ""


# -------------------------
# VP math / cut-lines (top/middle/bottom thirds)
# -------------------------

def _vp_cutlines(scores: List[Tuple[str, float]]) -> Tuple[float, float]:
    """
    Return (top_cut, middle_cut) thresholds by splitting scores into thirds, high to low.
    If 17 teams, top=6, mid=6, bottom=5, etc.
    Returns the MINIMUM score to be in top, and MINIMUM score to be in middle-or-better.
    """
    n = len(scores)
    if n == 0:
        return (math.inf, math.inf)
    # sort high->low
    sorted_scores = sorted([s for _, s in scores], reverse=True)
    top_n = max(1, n // 3 + (1 if n % 3 > 0 else 0))
    mid_n = max(1, n // 3)
    top_cut = sorted_scores[top_n - 1] if len(sorted_scores) >= top_n else sorted_scores[-1]
    mid_cut = sorted_scores[top_n + mid_n - 1] if len(sorted_scores) >= (top_n + mid_n) else sorted_scores[-1]
    return (top_cut, mid_cut)


def _vp_villain_and_nearmisses(scores: List[Tuple[str, float]]) -> Tuple[Optional[str], List[Tuple[str, float]]]:
    """
    Given (fid, score) list, return:
      - 'villain' fid: the LAST team inside the middle tier (they 'kept out' the next team).
      - near-misses: teams that missed middle tier by <= 2.0 pts (configurable threshold).
    """
    if not scores:
        return None, []
    # Determine tiers
    top_cut, mid_cut = _vp_cutlines(scores)
    # sort high->low
    ssorted = sorted(scores, key=lambda t: t[1], reverse=True)

    # Figure out who is the last team >= mid_cut (the 'gatekeeper')
    villain = None
    for fid, sc in reversed(ssorted):  # low->high scan
        if sc >= mid_cut:
            villain = fid
            break

    # near-misses: those just below mid_cut
    NEAR = 2.0
    misses = []
    for fid, sc in ssorted:
        if sc < mid_cut and (mid_cut - sc) <= NEAR:
            misses.append((fid, mid_cut - sc))
    return villain, misses


# -------------------------
# Survivor / Confidence utilities
# -------------------------

def _confidence_top3_line(fr: dict) -> str:
    games = _as_list(fr.get("game"))
    try:
        games = sorted(games, key=lambda g: int(g.get("rank") or 0), reverse=True)
    except Exception:
        pass
    return ", ".join([f"{g.get('pick','?')}({g.get('rank','-')})" for g in games[:3]]) if games else "—"


def _survivor_summary(week: int, survivor_pool: Dict[str, Any], fmap: Dict[str, str]) -> Dict[str, Any]:
    """
    Return:
      - no_picks: [team names]
      - pick_counts: {team: count}
      - picks_by_team: {team: [fid,...]}
    """
    out = {"no_picks": [], "pick_counts": {}, "picks_by_team": {}}
    sp = survivor_pool.get("survivorPool") if isinstance(survivor_pool, dict) else None
    if not isinstance(sp, dict):
        return out
    for fr in _as_list(sp.get("franchise")):
        fid = fr.get("id")
        wk = None
        for w in _as_list(fr.get("week")):
            if str(w.get("week") or "") == str(week):
                wk = w; break
        if not wk or not wk.get("pick"):
            out["no_picks"].append(_name_for(fid, fmap)); continue
        team = str(wk.get("pick"))
        out["pick_counts"][team] = out["pick_counts"].get(team, 0) + 1
        out["picks_by_team"].setdefault(team, []).append(fid)
    return out


def _boldest_and_boring_survivor_picks(week: int,
                                       survivor_pool: Dict[str, Any],
                                       fmap: Dict[str, str],
                                       week_odds: Optional[Dict[str, Dict[str, float]]] = None,
                                       winners: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Identify:
      - boldest_winner: (team, win_prob, managers) -> lowest win_prob among winning picks (if odds provided)
        fallback: least popular winning pick
      - boring_pick: most-picked team overall (regardless of outcome)
    'week_odds' is optional: { 'ARI': {'win_prob': 0.41}, ... }
    'winners' optional: list of NFL team codes that actually won (if you want to highlight correctly)
      If not provided, we just pick "boldest" by lowest win_prob or rarity ignoring outcome.
    """
    out = {"boldest": None, "boring": None}
    summ = _survivor_summary(week, survivor_pool, fmap)
    counts = summ["pick_counts"] or {}
    picks_by_team = summ["picks_by_team"]

    if not counts:
        return out

    # boring = most popular pick
    boring_team = max(counts.items(), key=lambda kv: kv[1])[0]
    out["boring"] = {"team": boring_team, "count": counts[boring_team], "managers": [ _name_for(fid, fmap) for fid in picks_by_team.get(boring_team, []) ]}

    # Boldest by odds if available… else rarity
    candidate_teams = list(counts.keys())
    if week_odds:
        with_probs = []
        for t in candidate_teams:
            prob = week_odds.get(t, {}).get("win_prob")
            if isinstance(prob, (int, float)):
                with_probs.append((t, prob))
        if with_probs:
            with_probs.sort(key=lambda kv: kv[1])  # ascending -> boldest first
            bold_team = with_probs[0][0]
            out["boldest"] = {
                "team": bold_team,
                "win_prob": with_probs[0][1],
                "managers": [ _name_for(fid, fmap) for fid in picks_by_team.get(bold_team, []) ]
            }
            return out

    # Fallback: rarity
    rare_team = min(counts.items(), key=lambda kv: kv[1])[0]
    out["boldest"] = {
        "team": rare_team,
        "win_prob": None,
        "managers": [ _name_for(fid, fmap) for fid in picks_by_team.get(rare_team, []) ]
    }
    return out


# -------------------------
# Narratives (DFS-first, no drafts/trades/waivers/H2H language)
# -------------------------

def opener(week: int, standings: List[dict], efficiency: List[dict], fmap: Dict[str, str]) -> str:
    rng = _seed_rng(week)
    st = list(standings or [])
    try:
        st = sorted(st, key=lambda r: (float(r.get("pf") or 0), float(r.get("vp") or 0)), reverse=True)
    except Exception:
        pass
    top = st[0] if st else None
    low = st[-1] if st else None
    top_name = _name_for(top.get("id","?"), fmap) if top else "Somebody"
    low_name = _name_for(low.get("id","?"), fmap) if low else "Somebody"
    top_pts = _fmt2(top.get("pf", 0))
    low_pts = _fmt2(low.get("pf", 0))

    eff = [e for e in (efficiency or []) if e.get("ppk") is not None]
    eff_leader = _name_for(eff[0].get("franchise_id","?"), fmap) if eff else top_name

    spice = _choose(rng, [
        "The cap sheet told a story this week—some listened, others doodled in the margins.",
        "If lineup setting was a pop quiz, a few of you circled ‘All of the above’ and hoped for partial credit.",
        "This wasn’t a points race; it was a points jailbreak."
    ])
    return f"{top_name} set the pace at **{top_pts}**, while {low_name} brought a pillow to a sprint with **{low_pts}**. {eff_leader} squeezed premium juice out of every slot. {spice}"


def standings_note(standings: List[dict], fmap: Dict[str, str]) -> str:
    if not standings:
        return "Standings? Vapor. Commit to some points next time."
    try:
        st = sorted(standings, key=lambda r: (float(r.get("vp") or 0), float(r.get("pf") or 0)), reverse=True)
    except Exception:
        st = standings
    top3 = ", ".join(_name_for(r.get("id","?"), fmap) for r in st[:3])
    bottom3 = ", ".join(_name_for(r.get("id","?"), fmap) for r in st[-3:])
    return f"**Heat check:** {top3} are cruising; {bottom3} are composing apology notes to their bankrolls. Everyone else is stuck in the slow lane."


def scores_note(weekly_results: Dict[str, Any]) -> str:
    wr = weekly_results.get("weeklyResults") if isinstance(weekly_results, dict) else None
    fr = _as_list(wr.get("franchise") if isinstance(wr, dict) else None)
    if not fr:
        return "The scoreboard ghosted us."
    scores = []
    for f in fr:
        try:
            scores.append(float(f.get("score") or 0.0))
        except Exception:
            pass
    if not scores:
        return "Points hid under the couch cushions."
    hi, lo = max(scores), min(scores)
    mid = sum(scores) / len(scores)
    return f"Range **{_fmt2(lo)} → {_fmt2(hi)}** (avg {_fmt2(mid)}). Tight clumps in the middle made every slot matter."


def performers_note(top_performers: List[dict], fmap: Dict[str, str]) -> str:
    if not top_performers:
        return "Headliners took the night off; benches sighed in relief."
    # Show 4–5 names with managers
    head = top_performers[:5]
    parts = []
    for r in head:
        mgrs = ", ".join(_name_for(fid, fmap) for fid in (r.get("franchise_ids") or []))
        parts.append(f"{r.get('player')} {r.get('pos') or ''} {r.get('team') or ''} **{_fmt2(r.get('pts'))}** ({mgrs})")
    return "Headliners: " + "; ".join(parts) + ". If you weren’t riding these, you were towing a trailer uphill."


def values_note(top_values: List[dict], top_busts: List[dict]) -> str:
    # Avoid the nerd metric; keep vibes DFS-y
    if not top_values and not top_busts:
        return "Value vs. Busts: the receipts are sealed. For now."
    lines = []
    if top_values:
        a = top_values[0]
        lines.append(f"{a.get('player')} punched above their price tag—felt like you found a loophole.")
    if top_busts:
        b = top_busts[0]
        lines.append(f"{b.get('player')} was boutique pricing for gas-station output.")
    return " ".join(lines)


def efficiency_note(efficiency: List[dict], fmap: Dict[str, str]) -> str:
    eff = [e for e in efficiency if e.get("ppk") is not None]
    if not eff:
        return "The efficiency board is blank. Plausible deniability, noted."
    best = eff[0]; worst = eff[-1]
    return f"Efficiency tiers: {_name_for(best.get('franchise_id','?'), fmap)} ran a clinic; {_name_for(worst.get('franchise_id','?'), fmap)} turned cap into compost."


def vp_drama_note(weekly_results: Dict[str, Any], fmap: Dict[str, str]) -> Dict[str, Any]:
    """
    Build the VP drama story:
      - villain: team that was last inside the middle tier (the gatekeeper)
      - near_misses: teams that missed middle tier by <=2 pts with delta
      - summary line for prose
    """
    wr = weekly_results.get("weeklyResults") if isinstance(weekly_results, dict) else None
    fr = _as_list(wr.get("franchise") if isinstance(wr, dict) else None)
    if not fr:
        return {"line": "VP tiers: nothing to see here.", "villain": None, "misses": []}
    scores = []
    for f in fr:
        fid = f.get("id")
        try:
            scores.append((fid, float(f.get("score") or 0.0)))
        except Exception:
            scores.append((fid, 0.0))
    villain, misses = _vp_villain_and_nearmisses(scores)
    villain_name = _name_for(villain, fmap) if villain else None
    miss_lines = []
    for fid, delta in misses:
        miss_lines.append(f"{_name_for(fid, fmap)} missed middle tier by **{_fmt2(delta)}**")
    line = ""
    if villain_name and miss_lines:
        line = f"**League Villain:** {villain_name} slammed the gate on the middle-tier line. " \
               f"{'; '.join(miss_lines)}."
    elif villain_name:
        line = f"**League Villain:** {villain_name} held the last middle-tier chair; everyone else stood."
    else:
        line = "VP tiers were merciful this week. No heartbreakers—somehow."
    return {"line": line, "villain": villain_name, "misses": misses}


def confidence_note(week: int, pool_nfl: Dict[str, Any], fmap: Dict[str, str]) -> str:
    pr = pool_nfl.get("poolPicks") if isinstance(pool_nfl, dict) else None
    if not isinstance(pr, dict):
        return "Confidence: questionable swagger, interesting receipts."
    parts = []
    no_picks = []
    best_sum, best_id = None, None
    for fr in _as_list(pr.get("franchise")):
        fid = fr.get("id")
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
    if best_id is not None:
        parts.append(f"{_name_for(best_id, fmap)} stacked the heaviest numbers on their ‘locks’ and didn’t blink.")
    if no_picks:
        parts.append(f"No-submit parade: {', '.join(no_picks)}.")
    return " ".join(parts) if parts else "Confidence: bravado met reality; results pending appeal."


def survivor_note(week: int,
                  survivor_pool: Dict[str, Any],
                  fmap: Dict[str, str],
                  week_odds: Optional[Dict[str, Dict[str, float]]] = None,
                  winners: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Return:
      - line: narrative
      - boldest: dict or None
      - boring: dict or None
      - no_picks: list of names
    """
    summ = _survivor_summary(week, survivor_pool, fmap)
    bold_and_boring = _boldest_and_boring_survivor_picks(week, survivor_pool, fmap, week_odds, winners)
    no_picks = summ["no_picks"]

    parts = []
    if bold_and_boring.get("boldest"):
        b = bold_and_boring["boldest"]
        if b.get("win_prob") is not None:
            parts.append(f"Boldest lifeline: **{b['team']}** (low public confidence) — played by {', '.join(b['managers'])}.")
        else:
            parts.append(f"Boldest lifeline: **{b['team']}** (rare pick) — played by {', '.join(b['managers'])}.")
    if bold_and_boring.get("boring"):
        bb = bold_and_boring["boring"]
        parts.append(f"Boring consensus: **{bb['team']}** ({bb['count']} entries). Safety blanket energy.")
    if no_picks:
        parts.append(f"No-pick stroll of shame: {', '.join(no_picks)}.")
    line = " ".join(parts) if parts else "Survivor: everyone toe-tapped through without face-planting."
    return {"line": line, "boldest": bold_and_boring.get("boldest"), "boring": bold_and_boring.get("boring"), "no_picks": no_picks}


# -------------------------
# Public API
# -------------------------

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

    # Optional odds for Survivor (if main passes it)
    week_odds: Optional[Dict[str, Dict[str, float]]] = (week_data or {}).get("odds")
    winners: Optional[List[str]] = (week_data or {}).get("winners")  # optional future hook

    notes = {
        "opener": opener(week, standings, efficiency, fmap),
        "standings": standings_note(standings, fmap),
        "scores": scores_note(weekly_results),
        "performers": performers_note(top_performers, fmap),
        "values": values_note(top_values, top_busts),
        "efficiency": efficiency_note(efficiency, fmap),
    }

    # VP drama / villain
    vp = vp_drama_note(weekly_results, fmap)
    notes["vp"] = vp.get("line", "")

    # Confidence + Survivor
    notes["confidence"] = confidence_note(week, pool_nfl, fmap)
    sv = survivor_note(week, survivor_pool, fmap, week_odds, winners)
    notes["survivor"] = sv.get("line", "")

    # Trophies (short/punchy)
    trophies: Dict[str, str] = {}
    if top_values:
        a = top_values[0]
        trophies["coupon_clipper"] = f"{a.get('player')} was premium output at a friendly tag."
    if top_busts:
        b = top_busts[0]
        trophies["dumpster_fire"] = f"{b.get('player')} charged steakhouse prices and served soggy fries."
    # modest-price hero (<= $6K) by raw points
    modest = [r for r in (top_values + top_busts) if r.get('salary') and float(r['salary']) <= 6000]
    if modest:
        best = sorted(modest, key=lambda r: r.get("pts") or 0, reverse=True)[0]
        trophies["galaxy_brain"] = f"{best.get('player')} turned small change into loud points."
    # Walk of Shame — lowest score
    wr = weekly_results.get("weeklyResults") if isinstance(weekly_results, dict) else None
    frs = _as_list(wr.get("franchise") if isinstance(wr, dict) else None)
    if frs:
        worst = sorted(frs, key=lambda f: float(f.get("score") or 0))[0]
        trophies["walk_of_shame"] = f"{_name_for(worst.get('id','?'), fmap)} tripped over { _fmt2(worst.get('score')) }."
    # Banana Peel — biggest stacked ranks
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
            trophies["banana_peel"] = f"{_name_for(best_id, fmap)} piled the biggest numbers on their ‘locks’ and dared the football gods."

    return {"notes": notes, **trophies}
