from __future__ import annotations

from typing import Any, Dict, List, Optional


def _pick_best(rows: List[Dict[str, Any]], key: str, reverse=True):
    if not rows:
        return None
    try:
        return sorted([r for r in rows if r.get(key) is not None], key=lambda r: r[key], reverse=reverse)[0]
    except Exception:
        return None


def _pick_worst(rows: List[Dict[str, Any]], key: str):
    return _pick_best(rows, key, reverse=False)


def _fmt_player(r: Dict[str, Any]) -> str:
    nm = r.get("player") or "Unknown"
    pos = r.get("pos")
    if pos:
        return f"{nm} ({pos})"
    return str(nm)


def build_roasts(cfg: Dict[str, Any], week: int, value_results: Dict[str, Any], week_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simple trophy set based on available metrics:
      - coupon_clipper: best P/$1K starter
      - dumpster_fire: worst P/$1K starter (with salary)
      - galaxy_brain: highest raw points starter under a modest salary threshold
      - banana_peel: confidence pool — franchise with the highest sum of top-3 ranks
      - walk_of_shame: lowest team score of the week
    All logic is safe/fail-soft if inputs are missing.
    """
    roasts: Dict[str, Any] = {}

    # Value-based trophies
    tv = (value_results or {}).get("top_values") or []
    tb = (value_results or {}).get("top_busts") or []
    with_ppk = tv + tb

    # coupon_clipper: top value per $1k
    best_val = _pick_best(with_ppk, "ppk", reverse=True)
    if best_val:
        roasts["coupon_clipper"] = f"{_fmt_player(best_val)} delivered {best_val.get('pts')} pts at ${best_val.get('salary')} — elite couponing ({best_val.get('ppk')} pts/$1K)."

    # dumpster_fire: worst value per $1k
    worst_val = _pick_worst(with_ppk, "ppk")
    if worst_val:
        roasts["dumpster_fire"] = f"{_fmt_player(worst_val)} sputtered to {worst_val.get('pts')} pts at ${worst_val.get('salary')} — dumpster-level ROI ({worst_val.get('ppk')} pts/$1K)."

    # galaxy_brain: big raw score with modest salary (<= $6,000 threshold)
    modest = [r for r in with_ppk if r.get("salary") and r["salary"] <= 6000]
    gbest = _pick_best(modest, "pts", reverse=True)
    if gbest:
        roasts["galaxy_brain"] = f"{_fmt_player(gbest)} was a smart play: {gbest.get('pts')} pts for ${gbest.get('salary')}."

    # Team scores for walk_of_shame
    wr = (week_data or {}).get("weekly_results") or {}
    wr_root = wr.get("weeklyResults") if isinstance(wr, dict) else None
    worst_team = None
    if isinstance(wr_root, dict):
        frs = wr_root.get("franchise")
        if isinstance(frs, list) and frs:
            try:
                worst_team = sorted(frs, key=lambda f: float(f.get("score") or 0))[0]
            except Exception:
                pass
    if worst_team:
        roasts["walk_of_shame"] = f"Team {worst_team.get('id')} takes the stroll with just {worst_team.get('score')} pts."

    # Confidence Pool banana_peel (sum of top-3 ranks per franchise; highest total = ‘boldest card’)
    pool = (week_data or {}).get("pool_nfl")
    if isinstance(pool, dict):
        picks_root = pool.get("poolPicks")
        if isinstance(picks_root, dict):
            best_sum = None
            best_id = None
            for fr in picks_root.get("franchise", []):
                fid = fr.get("id")
                # find this week
                week_nodes = fr.get("week", [])
                games = []
                for wn in week_nodes:
                    if str(wn.get("week")) == str(week):
                        g = wn.get("game", [])
                        if isinstance(g, dict):
                            g = [g]
                        games = g
                        break
                # compute sum of top-3 ranks
                try:
                    ranks = sorted([int(g.get("rank") or 0) for g in games], reverse=True)[:3]
                    s = sum(ranks)
                    if best_sum is None or s > best_sum:
                        best_sum, best_id = s, fid
                except Exception:
                    pass
            if best_id is not None:
                roasts["banana_peel"] = f"Confidence daredevil: {best_id} stacked {best_sum} points in top-3 picks."
    return roasts
