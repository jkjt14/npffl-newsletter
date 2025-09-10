from __future__ import annotations

import hashlib
import math
import random
from typing import Any, Dict, List, Tuple, Optional


def _as_list(x):
    if isinstance(x, list): return x
    if isinstance(x, dict): return [x]
    return []


def _fmt2(x) -> str:
    try: return f"{float(x):.2f}"
    except Exception: return str(x)


def _name_for(fid: str, fmap: Dict[str, str]) -> str:
    return fmap.get(str(fid), str(fid)) if fid else "unknown"


def _seed_rng(week: int) -> random.Random:
    h = hashlib.sha1(f"npffl_spicy_week_{week}".encode()).hexdigest()
    return random.Random(int(h[:12], 16))


def _choose(rng: random.Random, *groups: List[str]) -> str:
    bag = [s for g in groups for s in g]
    return bag[rng.randrange(0, len(bag))] if bag else ""


# VP rule 5/7/5 scaled
def _vp_splits(n: int) -> Tuple[int, int, int]:
    if n <= 3:
        return (1, 1, max(0, n - 2))
    top = max(1, round(n * 5 / 17))
    mid = max(1, round(n * 7 / 17))
    if top + mid > n: mid = n - top
    bot = n - top - mid
    return top, mid, bot


def _vp_buckets(scores: List[Tuple[str, float]]) -> Dict[str, str]:
    n = max(1, len(scores))
    top_n, mid_n, _ = _vp_splits(n)
    sorted_scores = sorted(scores, key=lambda t: t[1], reverse=True)
    out = {}
    for i, (fid, _) in enumerate(sorted_scores):
        if i < top_n: out[fid] = "top"
        elif i < top_n + mid_n: out[fid] = "mid"
        else: out[fid] = "bot"
    return out


def _vp_villain_and_misses(scores: List[Tuple[str, float]]) -> Tuple[Optional[str], List[Tuple[str, float]]]:
    if not scores: return None, []
    n = len(scores)
    top_n, mid_n, _ = _vp_splits(n)
    ss = sorted(scores, key=lambda t: t[1], reverse=True)
    gate_idx = min(n - 1, top_n + mid_n - 1)
    villain = ss[gate_idx][0] if n > gate_idx else None
    cut = ss[gate_idx][1] if n > gate_idx else float("inf")
    NEAR = 1.5
    misses: List[Tuple[str, float]] = []
    for fid, sc in ss[top_n + mid_n:]:
        delta = cut - sc
        if 0 <= delta <= NEAR:
            misses.append((fid, delta))
    return villain, misses


def _confidence_top3(fr: dict) -> str:
    games = _as_list(fr.get("game"))
    try: games = sorted(games, key=lambda g: int(g.get("rank") or 0), reverse=True)
    except Exception: pass
    return ", ".join([f"{g.get('pick','?')}({g.get('rank','-')})" for g in games[:3]]) if games else "—"


def _survivor_summary(week: int, survivor_pool: Dict[str, Any], fmap: Dict[str, str]) -> Dict[str, Any]:
    out = {"no_picks": [], "pick_counts": {}, "picks_by_team": {}}
    sp = survivor_pool.get("survivorPool") if isinstance(survivor_pool, dict) else None
    if not isinstance(sp, dict): return out
    for fr in _as_list(sp.get("franchise")):
        fid = fr.get("id")
        wk = None
        for w in _as_list(fr.get("week")):
            if str(w.get("week") or "") == str(week): wk = w; break
        if not wk or not wk.get("pick"):
            out["no_picks"].append(_name_for(fid, fmap)); continue
        tm = str(wk.get("pick"))
        out["pick_counts"][tm] = out["pick_counts"].get(tm, 0) + 1
        out["picks_by_team"].setdefault(tm, []).append(fid)
    return out


def _bold_boring_from_odds(week: int, survivor_pool: Dict[str, Any], fmap: Dict[str, str],
                           odds_map: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    summ = _survivor_summary(week, survivor_pool, fmap)
    counts = summ["pick_counts"] or {}
    picks_by_team = summ["picks_by_team"]
    no_picks = summ["no_picks"]
    out = {"boldest": None, "boring": None, "no_picks": no_picks}

    if counts:
        # boring = most common
        boring_team = max(counts.items(), key=lambda kv: kv[1])[0]
        out["boring"] = {"team": boring_team, "count": counts[boring_team],
                         "managers": [_name_for(fid, fmap) for fid in picks_by_team.get(boring_team, [])]}

        # boldest by lowest win_prob (if available), else least common
        if odds_map:
            def _prob(code: str) -> Optional[float]:
                code = (code or "").upper()
                if code in odds_map and isinstance(odds_map[code], dict):
                    return odds_map[code].get("win_prob")
                return odds_map.get(code[:3], {}).get("win_prob")
            with_probs = [(t, _prob(t)) for t in counts.keys()]
            with_probs = [(t, p) for (t, p) in with_probs if isinstance(p, (int, float))]
            if with_probs:
                with_probs.sort(key=lambda kv: kv[1])  # lowest prob = boldest
                t, p = with_probs[0]
                out["boldest"] = {"team": t, "win_prob": p,
                                  "managers": [_name_for(fid, fmap) for fid in picks_by_team.get(t, [])]}
        if out["boldest"] is None:
            rare = min(counts.items(), key=lambda kv: kv[1])[0]
            out["boldest"] = {"team": rare, "win_prob": None,
                              "managers": [_name_for(fid, fmap) for fid in picks_by_team.get(rare, [])]}
    return out


# ---------- narratives ----------

def opener(week: int, standings: List[dict], efficiency: List[dict], fmap: Dict[str, str]) -> str:
    rng = _seed_rng(week)
    st = list(standings or [])
    try: st = sorted(st, key=lambda r: (float(r.get("pf") or 0), float(r.get("vp") or 0)), reverse=True)
    except Exception: pass
    top = st[0] if st else None
    low = st[-1] if st else None
    top_name = _name_for(top.get("id","?"), fmap) if top else "Somebody"
    low_name = _name_for(low.get("id","?"), fmap) if low else "Somebody"
    top_pts = _fmt2(top.get("pf", 0))
    low_pts = _fmt2(low.get("pf", 0))
    riffs = [
        "Some of you built rocket ships; others brought a butter knife to a gunfight.",
        "The cap wasn’t the only thing tight — so were a few throats on Monday night.",
        "You either printed points or printed excuses. Many chose the second printer."
    ]
    return f"{top_name} blasted off with **{top_pts}**, while {low_name} curled up with **{low_pts}**. {rng.choice(riffs)}"


def standings_note(standings: List[dict], fmap: Dict[str, str]) -> str:
    if not standings: return "Standings are shy. Be louder next week."
    try: st = sorted(standings, key=lambda r: (float(r.get("vp") or 0), float(r.get("pf") or 0)), reverse=True)
    except Exception: st = standings
    top3 = ", ".join(_name_for(r.get("id","?"), fmap) for r in st[:3])
    mid = ", ".join(_name_for(r.get("id","?"), fmap) for r in st[3:7])
    cel = ", ".join(_name_for(r.get("id","?"), fmap) for r in st[-3:])
    return (f"Top shelf: {top3}. The buffet line: {mid}. Cellar dwellers: {cel}. "
            f"This isn’t head-to-head — it’s a DFS sprint. Keep up.")


def scores_note(weekly_results: Dict[str, Any]) -> str:
    wr = weekly_results.get("weeklyResults") if isinstance(weekly_results, dict) else None
    fr = _as_list(wr.get("franchise") if isinstance(wr, dict) else None)
    if not fr: return "Scoreboard said ‘out of office.’"
    scores = []
    for f in fr:
        try: scores.append(float(f.get("score") or 0.0))
        except Exception: pass
    if not scores: return "Points hid under the couch."
    return (f"Range **{_fmt2(min(scores))} → {_fmt2(max(scores))}** "
            f"(avg {_fmt2(sum(scores)/len(scores))}). Middle pack was a mosh pit; every slot mattered.")


def headliners_note(top_performers: List[dict], fmap: Dict[str, str]) -> str:
    if not top_performers:
        return "Headliners: the stage was empty and so were a few lineups."
    lines = []
    for r in top_performers[:5]:
        mgrs = ", ".join(_name_for(fid, fmap) for fid in (r.get("franchise_ids") or []))
        nm = r.get("player")
        pos = r.get("pos") or ""
        tm = r.get("team") or ""
        pts = _fmt2(r.get("pts"))
        lines.append(f"**{nm}** {pos} {tm} detonated for {pts} ({mgrs})")
    return " • ".join(lines) + ". If you didn’t hitch your wagon to one of these, you were pushing it uphill."


def values_note(top_values: List[dict], top_busts: List[dict]) -> str:
    blips = []
    if top_values:
        v = top_values[0]
        blips.append(f"{v.get('player')} was champagne on a lemonade budget. No spreadsheets required to see the heist.")
    if top_busts:
        b = top_busts[0]
        blips.append(f"{b.get('player')} charged steakhouse prices and served microwave leftovers.")
    return " ".join(blips) if blips else "Values vs. Busts: receipts pending; excuses loading."


def efficiency_note(eff: List[dict], fmap: Dict[str, str]) -> str:
    eff = [e for e in eff if e.get("ppk") is not None]
    if not eff: return "Efficiency board refuses to snitch this week."
    best = eff[0]; worst = eff[-1]
    return (f"{_name_for(best.get('franchise_id','?'), fmap)} ran a clinic; "
            f"{_name_for(worst.get('franchise_id','?'), fmap)} set cash on fire and roasted marshmallows over it.")


def vp_drama(weekly_results: Dict[str, Any], fmap: Dict[str, str]) -> str:
    wr = weekly_results.get("weeklyResults") if isinstance(weekly_results, dict) else None
    fr = _as_list(wr.get("franchise") if isinstance(wr, dict) else None)
    if not fr: return "VP cut-lines took a vacation."
    scores: List[Tuple[str, float]] = []
    for f in fr:
        fid = f.get("id")
        try: sc = float(f.get("score") or 0.0)
        except Exception: sc = 0.0
        scores.append((fid, sc))
    villain, misses = _vp_villain_and_misses(scores)
    parts = []
    if villain:
        parts.append(f"**League Villain:** {_name_for(villain, fmap)} blocked the last seat in the 2.5 VP lounge.")
    for fid, delta in misses:
        parts.append(f"{_name_for(fid, fmap)} missed the middle by **{_fmt2(delta)}**. That’s a bad beat and a worse lineup.")
    return " ".join(parts) if parts else "VP drama stayed quiet — this time."


def fraud_watch(values: Dict[str, Any], fmap: Dict[str, str]) -> str:
    eff = values.get("team_efficiency") or []
    if not eff: return "Fraud Watch: inconclusive."
    top_half = sorted(eff, key=lambda r: r.get("total_pts", 0.0), reverse=True)[: max(1, len(eff)//2)]
    worst = sorted(top_half, key=lambda r: (r.get("ppk") or 0.0))[0]
    return (f"**Fraud Watch 🔥** {_name_for(worst.get('franchise_id','?'), fmap)} looked rich on the scoreboard, "
            f"but their lineup hemorrhaged cap like a busted faucet.")


def dfs_jail(values: Dict[str, Any], fmap: Dict[str, str]) -> str:
    # Count starters with <= 1.0 point
    ghost_count: Dict[str, int] = {}
    for pos_rows in (values.get("by_pos") or {}).values():
        for r in pos_rows:
            if (r.get("pts") or 0.0) <= 1.0:
                fid = r.get("franchise_id")
                ghost_count[fid] = ghost_count.get(fid, 0) + 1
    if not ghost_count:
        return "DFS Jail 🚔: surprisingly empty. Parole for everyone."
    perp = max(ghost_count.items(), key=lambda kv: kv[1])[0]
    return f"DFS Jail 🚔: {_name_for(perp, fmap)} started more ghosts than players. Community service: read injury reports first."


def confidence_spice(week: int, pool_nfl: Dict[str, Any], fmap: Dict[str, str]) -> str:
    pr = pool_nfl.get("poolPicks") if isinstance(pool_nfl, dict) else None
    if not isinstance(pr, dict): return "Confidence: bravado with a side of denial."
    best_sum, best_id = None, None
    no_picks = []
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
    parts = []
    if best_id is not None:
        parts.append(f"{_name_for(best_id, fmap)} stacked the fattest numbers up top and didn’t blink.")
    if no_picks:
        parts.append(f"No-submit roll call: {', '.join(no_picks)}.")
    return " ".join(parts) if parts else "Confidence: big talk, mixed receipts."


def survivor_spice(week: int, survivor_pool: Dict[str, Any], fmap: Dict[str, str], odds: Optional[Dict[str, Dict[str, float]]]) -> str:
    bb = _bold_boring_from_odds(week, survivor_pool, fmap, odds)
    parts = []
    if bb.get("boldest"):
        b = bb["boldest"]
        if b.get("win_prob") is not None:
            parts.append(f"**Boldest Lifeline:** {b['team']} (low book confidence) — {', '.join(b['managers'])}.")
        else:
            parts.append(f"**Boldest Lifeline:** {b['team']} (rare pick) — {', '.join(b['managers'])}.")
    if bb.get("boring"):
        t = bb["boring"]
        parts.append(f"**Boring Consensus:** {t['team']} ({t['count']} entries). Safety blanket energy.")
    if bb.get("no_picks"):
        parts.append(f"**No-Pick Parade:** {', '.join(bb['no_picks'])}.")
    return " ".join(parts) if parts else "Survivor: everyone tiptoed past the landmines."


def build_roasts(cfg: Dict[str, Any], week: int, values: Dict[str, Any], week_data: Dict[str, Any]) -> Dict[str, Any]:
    fmap = (cfg or {}).get("franchise_names") or {}
    standings = (week_data or {}).get("standings") or []
    wr = (week_data or {}).get("weekly_results") or {}
    pool_nfl = (week_data or {}).get("pool_nfl") or {}
    survivor_pool = (week_data or {}).get("survivor_pool") or {}
    odds = (week_data or {}).get("odds") or {}

    notes = {
        "opener": opener(week, standings, values.get("team_efficiency") or [], fmap),
        "standings": standings_note(standings, fmap),
        "scores": scores_note(wr),
        "performers": headliners_note(values.get("top_performers") or [], fmap),
        "values": values_note(values.get("top_values") or [], values.get("top_busts") or []),
        "efficiency": efficiency_note(values.get("team_efficiency") or [], fmap),
        "vp": vp_drama(wr, fmap),
        "confidence": confidence_spice(week, pool_nfl, fmap),
        "survivor": survivor_spice(week, survivor_pool, fmap, odds),
        "fraud_watch": fraud_watch(values, fmap),
        "dfs_jail": dfs_jail(values, fmap),
    }

    # Trophies
    trophies: Dict[str, str] = {}
    tv = values.get("top_values") or []
    tb = values.get("top_busts") or []
    if tv:
        trophies["coupon_clipper"] = f"{tv[0].get('player')} was premium output at a thrift-store tag."
    if tb:
        trophies["dumpster_fire"] = f"{tb[0].get('player')} turned cap space into a grease fire."
    # Walk of Shame (lowest score)
    wr_root = wr.get("weeklyResults") if isinstance(wr, dict) else None
    frs = _as_list(wr_root.get("franchise") if isinstance(wr_root, dict) else None)
    if frs:
        worst = sorted(frs, key=lambda f: float(f.get("score") or 0))[0]
        trophies["walk_of_shame"] = f"{_name_for(worst.get('id','?'), fmap)} tripped over {_fmt2(worst.get('score'))}."

    # Banana Peel — fattest top-3 confidence stack
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
            trophies["banana_peel"] = f"{_name_for(best_id, fmap)} stacked the biggest numbers and dared the football gods."

    return {"notes": notes, **trophies}
