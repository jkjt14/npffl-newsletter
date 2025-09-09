from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Dict, List, Optional, Tuple


# =========================
# Helpers
# =========================

def _name_for(fid: str, fmap: Dict[str, str]) -> str:
    return fmap.get(str(fid), str(fid))


def _as_list(x):
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        return [x]
    return []


def _pick(rows: List[Dict[str, Any]], key: str, reverse=True, default=None):
    rows = [r for r in rows if r is not None and r.get(key) is not None]
    if not rows:
        return default
    return sorted(rows, key=lambda r: r[key], reverse=reverse)[0]


def _pct_rank(idx: int, n: int) -> float:
    if n <= 1:
        return 1.0
    return 1.0 - (idx / (n - 1))


def _fmt_pts(x) -> str:
    try:
        return f"{float(x):.2f}"
    except Exception:
        return str(x)


def _fmt_sal(x) -> str:
    try:
        return f"${int(float(x)):,}"
    except Exception:
        return "-"


def _fmt_ppk(x) -> str:
    try:
        return f"{float(x):.2f}"
    except Exception:
        return "-"


def _player_str(r: Dict[str, Any]) -> str:
    nm = str(r.get("player") or "Unknown")
    pos = (r.get("pos") or "").upper()
    tm = r.get("team") or ""
    parts = [nm]
    if pos:
        parts.append(pos)
    if tm:
        parts.append(tm)
    return " ".join(parts)


def _seed_rng(week: int) -> random.Random:
    # Stable, week-based RNG so phrasing varies by week but is reproducible
    h = hashlib.sha1(f"npffl_roast_week_{week}".encode()).hexdigest()
    seed = int(h[:12], 16)
    return random.Random(seed)


def _choose(rng: random.Random, options: List[str]) -> str:
    if not options:
        return ""
    return options[rng.randrange(0, len(options))]


def _cap(text: str) -> str:
    return text[0:1].upper() + text[1:] if text else text


# =========================
# Core: Narrative Builders
# =========================

def _opener_narrative(week: int, standings: List[dict], efficiency: List[dict], fmap: Dict[str, str]) -> str:
    rng = _seed_rng(week)

    # Leader and cellar from standings (by PF, then VP if available)
    st = list(standings or [])
    try:
        st = sorted(st, key=lambda r: (float(r.get("pf") or 0.0), float(r.get("vp") or 0.0)), reverse=True)
    except Exception:
        st = standings or []

    lead = st[0] if st else None
    tail = st[-1] if st else None

    lead_name = _name_for(lead.get("id","?"), fmap) if lead else "Somebody"
    lead_pts  = _fmt_pts(lead.get("pf", 0)) if lead else "0.00"
    tail_name = _name_for(tail.get("id","?"), fmap) if tail else "Somebody"
    tail_pts  = _fmt_pts(tail.get("pf", 0)) if tail else "0.00"

    # Efficiency king (P/$1K)
    king = _pick([e for e in efficiency if e.get("ppk") is not None], "ppk", True)
    king_name = _name_for(king.get("franchise_id","?"), fmap) if king else lead_name
    king_ppk  = _fmt_ppk(king.get("ppk")) if king else "-"

    lines = [
        f"{lead_name} opened Week {week} by lighting the league on fire with **{lead_pts}**. "
        f"If you heard sirens, that was just {tail_name} crawling to **{tail_pts}** and tripping over their own roster.",
        f"On the money side, {king_name} ran a masterclass in cap efficiency at **{king_ppk} pts/$1K**. "
        f"If you didn’t bring coupons this week, the receipt is going to hurt.",
    ]

    spice = [
        "Half the league played bumper cars in the mid-table while the leaders sped off in the HOV lane.",
        "The waiver wire is already side-eyeing a few of you. And it’s only Week {week}.",
        "If you slept through kickoff, congrats—you drafted like you were still dreaming.",
        "Somebody set their lineup from the nosebleeds; the altitude clearly affected decision-making.",
    ]
    lines.append(_choose(rng, spice).replace("{week}", str(week)))
    return " ".join(lines)


def _standings_narrative(week: int, standings: List[dict], fmap: Dict[str, str]) -> str:
    if not standings:
        return "Standings are a mystery this week—apparently so was anyone’s plan."
    # Rank by VP then PF to echo table vibe
    try:
        st = sorted(standings, key=lambda r: (float(r.get("vp") or 0.0), float(r.get("pf") or 0.0)), reverse=True)
    except Exception:
        st = standings

    top = st[:3]
    tail = st[-3:]
    top_names = ", ".join([_name_for(r.get("id","?"), fmap) for r in top])
    tail_names = ", ".join([_name_for(r.get("id","?"), fmap) for r in tail])

    return (
        f"**Standings heat check:** The podium rotation is {top_names}. "
        f"In the basement, {tail_names} are trying to set new records for creative underachievement. "
        f"Middle of the pack? A traffic jam of 90-ish points and second-guessing."
    )


def _scores_narrative(week: int, weekly_results: Dict[str, Any], fmap: Dict[str, str]) -> str:
    wr = weekly_results.get("weeklyResults") if isinstance(weekly_results, dict) else None
    fr = _as_list(wr.get("franchise") if isinstance(wr, dict) else None)
    if not fr:
        return "The scoreboard is blank—like some of those lineups."

    # Spread and mid-pack congestion
    scores = []
    for f in fr:
        try:
            scores.append(float(f.get("score") or 0.0))
        except Exception:
            pass
    if not scores:
        return "The scoreboard was allergic to points this week."

    hi, lo = max(scores), min(scores)
    spread = hi - lo

    return (
        f"**Weekly scores pulse:** Range **{_fmt_pts(lo)} → {_fmt_pts(hi)}** (spread {_fmt_pts(spread)}). "
        f"Enough chaos to make a projection model cry and a group chat explode."
    )


def _top_performers_narrative(week: int, top_performers: List[dict], fmap: Dict[str, str]) -> str:
    if not top_performers:
        return "Top Performers took the week off. Your benches sympathize."
    headliners = top_performers[:5]
    names = []
    for r in headliners:
        names.append(f"{_player_str(r)} **{_fmt_pts(r.get('pts'))}**")
    joined = "; ".join(names)
    return f"**Headliners:** {joined}. If you didn’t hitch your wagon to one of these, you were pushing it uphill."


def _values_narrative(week: int, top_values: List[dict], top_busts: List[dict]) -> str:
    if not top_values and not top_busts:
        return "Value vs. Busts: No receipts this week—just vibes and regret."
    parts = []
    if top_values:
        a = top_values[0]
        parts.append(
            f"**Coupon crime of the week:** {_player_str(a)} gave **{_fmt_pts(a.get('pts'))}** for "
            f"{_fmt_sal(a.get('salary'))} (~{_fmt_ppk(a.get('ppk'))} pts/$1K). That’s daylight robbery."
        )
    if top_busts:
        b = top_busts[0]
        parts.append(
            f"**Premium disappointment:** {_player_str(b)} returned **{_fmt_pts(b.get('pts'))}** on "
            f"{_fmt_sal(b.get('salary'))} (~{_fmt_ppk(b.get('ppk'))} pts/$1K). That’s artisanal sadness."
        )
    return " ".join(parts)


def _efficiency_narrative(week: int, efficiency: List[dict], fmap: Dict[str, str]) -> str:
    eff = [e for e in efficiency if e.get("ppk") is not None]
    if not eff:
        return "Efficiency board is empty—like someone’s FAAB by Week 3."
    best = eff[0]
    worst = eff[-1]
    best_name = _name_for(best.get("franchise_id","?"), fmap)
    worst_name = _name_for(worst.get("franchise_id","?"), fmap)
    return (
        f"**Efficiency tiers:** {best_name} ran the numbers at **{_fmt_ppk(best.get('ppk'))} pts/$1K**. "
        f"{worst_name} turned salary into compost at **{_fmt_ppk(worst.get('ppk'))} pts/$1K**."
    )


def _confidence_narrative(week: int, pool_nfl: Dict[str, Any], fmap: Dict[str, str]) -> str:
    pr = pool_nfl.get("poolPicks") if isinstance(pool_nfl, dict) else None
    if not isinstance(pr, dict):
        return "Confidence picks: half-confidence, half-chaos."
    best_sum = None
    best_id = None
    for fr in _as_list(pr.get("franchise")):
        fid = fr.get("id")
        for w in _as_list(fr.get("week")):
            if str(w.get("week") or "") == str(week):
                games = _as_list(w.get("game"))
                try:
                    s = sum(sorted([int(g.get("rank") or 0) for g in games], reverse=True)[:3])
                    if best_sum is None or s > best_sum:
                        best_sum, best_id = s, fid
                except Exception:
                    pass
                break
    if best_id:
        return f"Confidence spotlight: {_name_for(best_id, fmap)} stacked **{best_sum}** boldness points up top. Respect the audacity."
    return "Confidence spotlight: The dartboard won this week."


def _survivor_narrative(week: int, survivor_pool: Dict[str, Any], fmap: Dict[str, str]) -> str:
    sp = survivor_pool.get("survivorPool") if isinstance(survivor_pool, dict) else None
    if not isinstance(sp, dict):
        return "Survivor: No survivors; just vibes."
    # Count missing picks and duplicates for spice
    miss = 0
    total = 0
    for fr in _as_list(sp.get("franchise")):
        total += 1
        wk = None
        for w in _as_list(fr.get("week")):
            if str(w.get("week") or "") == str(week):
                wk = w; break
        if not wk or not wk.get("pick"):
            miss += 1
    if total == 0:
        return "Survivor: zero contestants, infinite confidence."
    if miss > 0:
        return f"Survivor: {miss} team(s) forgot to lock a pick. That’s a bold strategy, Cotton."
    return "Survivor: Everyone tip-toed through Week {week} without face-planting. Suspiciously responsible.".replace("{week}", str(week))


# =========================
# Trophies
# =========================

def _build_trophies(value_results: Dict[str, Any], week_data: Dict[str, Any], fmap: Dict[str, str]) -> Dict[str, str]:
    trophies: Dict[str, str] = {}
    tv = (value_results or {}).get("top_values") or []
    tb = (value_results or {}).get("top_busts") or []

    best_val = _pick(tv, "ppk", True) or _pick(tv + tb, "ppk", True)
    worst_val = _pick(tb, "ppk", False) or _pick(tv + tb, "ppk", False)

    if best_val:
        trophies["coupon_clipper"] = (
            f"{_player_str(best_val)} delivered **{_fmt_pts(best_val.get('pts'))}** at "
            f"{_fmt_sal(best_val.get('salary'))} — straight heist (**{_fmt_ppk(best_val.get('ppk'))} pts/$1K**)."
        )
    if worst_val:
        trophies["dumpster_fire"] = (
            f"{_player_str(worst_val)} gave back **{_fmt_pts(worst_val.get('pts'))}** on "
            f"{_fmt_sal(worst_val.get('salary'))} — artisan-grade flop (**{_fmt_ppk(worst_val.get('ppk'))} pts/$1K**)."
        )

    # Galaxy Brain — best raw points with modest salary (<= 6000)
    modest = [r for r in (tv + tb) if r.get("salary") and float(r["salary"]) <= 6000]
    galaxy = _pick(modest, "pts", True)
    if galaxy:
        trophies["galaxy_brain"] = (
            f"{_player_str(galaxy)} for {_fmt_sal(galaxy.get('salary'))} delivered **{_fmt_pts(galaxy.get('pts'))}**. "
            f"Chef’s-kiss lineup wizardry."
        )

    # Walk of Shame — worst team score this week
    wr = (week_data or {}).get("weekly_results") or {}
    wr_root = wr.get("weeklyResults") if isinstance(wr, dict) else None
    worst_team = None
    if isinstance(wr_root, dict):
        frs = _as_list(wr_root.get("franchise"))
        try:
            worst_team = sorted(frs, key=lambda f: float(f.get("score") or 0))[0] if frs else None
        except Exception:
            pass
    if worst_team:
        trophies["walk_of_shame"] = (
            f"{_name_for(worst_team.get('id','?'), fmap)} limped to **{_fmt_pts(worst_team.get('score'))}**. "
            f"Someone check on their cap sheet."
        )

    # Banana Peel — boldest confidence stack (sum top-3 ranks)
    pool = (week_data or {}).get("pool_nfl")
    best_sum = None
    best_id = None
    if isinstance(pool, dict):
        pr = pool.get("poolPicks")
        if isinstance(pr, dict):
            for fr in _as_list(pr.get("franchise")):
                fid = fr.get("id")
                for w in _as_list(fr.get("week")):
                    if str(w.get("week") or "") == str((week_data or {}).get("week") or "") or True:
                        games = _as_list(w.get("game"))
                        try:
                            s = sum(sorted([int(g.get("rank") or 0) for g in games], reverse=True)[:3])
                            if best_sum is None or s > best_sum:
                                best_sum, best_id = s, fid
                        except Exception:
                            pass
                        break
    if best_id is not None and best_sum is not None:
        trophies["banana_peel"] = (
            f"{_name_for(best_id, fmap)} stacked **{best_sum}** confidence on their heaviest picks. "
            f"Reckless? Maybe. Effective? Absolutely."
        )

    return trophies


# =========================
# Public API
# =========================

def build_roasts(cfg: Dict[str, Any], week: int, value_results: Dict[str, Any], week_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return a dict used by newsletter:
      - Named trophies: coupon_clipper, dumpster_fire, galaxy_brain, banana_peel, walk_of_shame
      - lines: list[str] narrative paragraphs (opener, sections)
    Everything is computed fresh per run/week — no carryovers.
    """
    fmap = (cfg or {}).get("franchise_names") or {}
    standings: List[dict] = (week_data or {}).get("standings") or []
    weekly_results: Dict[str, Any] = (week_data or {}).get("weekly_results") or {}
    top_values: List[dict] = (value_results or {}).get("top_values") or []
    top_busts: List[dict]  = (value_results or {}).get("top_busts") or []
    top_performers: List[dict] = (value_results or {}).get("top_performers") or []
    efficiency: List[dict] = (value_results or {}).get("team_efficiency") or []
    pool_nfl: Dict[str, Any] = (week_data or {}).get("pool_nfl") or {}
    survivor_pool: Dict[str, Any] = (week_data or {}).get("survivor_pool") or {}

    lines: List[str] = []

    # Opener
    try:
        lines.append(_opener_narrative(week, standings, efficiency, fmap))
    except Exception:
        pass

    # Sections
    try:
        lines.append(_standings_narrative(week, standings, fmap))
    except Exception:
        pass

    try:
        lines.append(_scores_narrative(week, weekly_results, fmap))
    except Exception:
        pass

    try:
        lines.append(_top_performers_narrative(week, top_performers, fmap))
    except Exception:
        pass

    try:
        lines.append(_values_narrative(week, top_values, top_busts))
    except Exception:
        pass

    try:
        lines.append(_efficiency_narrative(week, efficiency, fmap))
    except Exception:
        pass

    try:
        lines.append(_confidence_narrative(week, pool_nfl, fmap))
    except Exception:
        pass

    try:
        lines.append(_survivor_narrative(week, survivor_pool, fmap))
    except Exception:
        pass

    # Trophies
    trophies = {}
    try:
        trophies = _build_trophies(value_results, week_data, fmap)
    except Exception:
        trophies = {}

    # Assemble return
    roasts: Dict[str, Any] = {"lines": [s for s in lines if s and s.strip()]}

    # Put named trophies if they exist
    for k in ("coupon_clipper", "dumpster_fire", "galaxy_brain", "banana_peel", "walk_of_shame"):
        if trophies.get(k):
            roasts[k] = trophies[k]

    return roasts
