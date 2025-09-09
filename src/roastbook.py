from __future__ import annotations

from typing import Any, Dict, List, Optional


def _name_for(fid: str, fmap: Dict[str, str]) -> str:
    return fmap.get(str(fid), str(fid))


def _fmt_player(r: Dict[str, Any]) -> str:
    nm = r.get("player") or "Unknown"
    pos = r.get("pos")
    team = r.get("team")
    bits = [nm]
    if pos:
        bits.append(pos)
    if team:
        bits.append(team)
    return " ".join(bits)


def _pick_best(rows: List[Dict[str, Any]], key: str, reverse=True):
    rows = [r for r in rows if r.get(key) is not None]
    if not rows:
        return None
    return sorted(rows, key=lambda r: r[key], reverse=reverse)[0]


def build_roasts(cfg: Dict[str, Any], week: int, value_results: Dict[str, Any], week_data: Dict[str, Any]) -> Dict[str, Any]:
    fmap = (cfg or {}).get("franchise_names") or {}
    roasts: Dict[str, Any] = {"lines": []}

    # Coupon Clipper / Dumpster Fire from player P/$1K
    tv = (value_results or {}).get("top_values") or []
    tb = (value_results or {}).get("top_busts") or []

    best_val = _pick_best(tv, "ppk", reverse=True) or _pick_best(tv+tb, "ppk", reverse=True)
    worst_val = _pick_best(tb, "ppk", reverse=False) or _pick_best(tv+tb, "ppk", reverse=False)

    if best_val:
        roasts["coupon_clipper"] = f"{_fmt_player(best_val)} delivered {best_val.get('pts'):.2f} pts at ${int(best_val.get('salary') or 0):,} — highway robbery ({best_val.get('ppk'):.3f} pts/$1K)."
    if worst_val:
        roasts["dumpster_fire"] = f"{_fmt_player(worst_val)} face-planted for {worst_val.get('pts'):.2f} pts at ${int(worst_val.get('salary') or 0):,} — dumpster-tier ROI ({worst_val.get('ppk'):.3f} pts/$1K)."

    # Galaxy Brain: biggest raw points under a modest salary
    modest = [r for r in (tv+tb) if r.get("salary") and r["salary"] <= 6000]
    gb = _pick_best(modest, "pts", True)
    if gb:
        roasts["galaxy_brain"] = f"{_fmt_player(gb)} was a chef’s kiss: {gb.get('pts'):.2f} pts for ${int(gb.get('salary')):,}."

    # Team Walk of Shame: lowest weekly score
    wr = (week_data or {}).get("weekly_results") or {}
    wr_root = wr.get("weeklyResults") if isinstance(wr, dict) else None
    worst_team = None
    if isinstance(wr_root, dict):
        frs = wr_root.get("franchise")
        if isinstance(frs, list):
            try:
                worst_team = sorted(frs, key=lambda f: float(f.get("score") or 0))[0]
            except Exception:
                pass
    if worst_team:
        roasts["walk_of_shame"] = f"{_name_for(worst_team.get('id','?'), fmap)} limped to {worst_team.get('score')} pts. Ouch."

    # Banana Peel: boldest confidence picks (sum top-3 ranks)
    pool = (week_data or {}).get("pool_nfl")
    if isinstance(pool, dict):
        pr = pool.get("poolPicks")
        if isinstance(pr, dict):
            best_sum = None
            best_id = None
            for fr in pr.get("franchise", []):
                fid = fr.get("id")
                for w in fr.get("week", []):
                    if str(w.get("week")) == str(week):
                        ranks = []
                        games = w.get("game", [])
                        if isinstance(games, dict):
                            games = [games]
                        try:
                            ranks = sorted([int(g.get("rank") or 0) for g in games], reverse=True)[:3]
                            s = sum(ranks)
                            if best_sum is None or s > best_sum:
                                best_sum, best_id = s, fid
                        except Exception:
                            pass
                        break
            if best_id:
                roasts["banana_peel"] = f"{_name_for(best_id, fmap)} stacked {best_sum} confidence points in their top-3 picks."

    # League Flavor — quick spicy one-liners
    te = (value_results or {}).get("team_efficiency") or []
    if te:
        best_team = _pick_best([r for r in te if r.get("ppk") is not None], "ppk", True)
        worst_team = _pick_best([r for r in te if r.get("ppk") is not None], "ppk", False)
        if best_team:
            roasts["lines"].append(f"{_name_for(best_team['franchise_id'], fmap)} ran a **clinic** in cap efficiency ({best_team['ppk']:.2f} pts/$1K).")
        if worst_team:
            roasts["lines"].append(f"{_name_for(worst_team['franchise_id'], fmap)} set money on fire ({worst_team['ppk']:.2f} pts/$1K).")

    return roasts
