from __future__ import annotations
from typing import Any, Dict, List, Tuple
import statistics, random

def _fmt2(x: float | int | None, default="0.00") -> str:
    if x is None: return default
    try: return f"{float(x):.2f}"
    except Exception: return default

def _pick(seq: List[str]) -> str:
    return random.choice(seq) if seq else ""

# ---------- Weekly Results (long-form, your requested style) ----------

def weekly_results_blurb(scores: Dict[str, Any]) -> str:
    rows = scores.get("rows") or []
    if not rows: return ""
    top = rows[0]; bot = rows[-1]
    names = [n for n,_ in rows]
    sc = [s for _,s in rows]
    med = statistics.median(sc) if sc else 0.0

    line1 = f"**{top[0]}** lit the slate with **{top[1]:.2f}**. **{bot[0]}**? Paid the cover charge and sat in the parking lot (**{bot[1]:.2f}**)."

    # Mention 2–3 teams in the next tier
    mid_callouts = ", ".join(names[1:5]) if len(names) >= 5 else ", ".join(names[1:])
    line2 = f"{mid_callouts} kept it loud just behind, while a couple of hopefuls pressed their noses on the VIP glass."

    # chaos band around the median
    # find a narrow band around median (±5)
    low = max(min(sc), med-5) if sc else med
    high = min(max(sc), med+5) if sc else med
    band = f"{low:.2f}–{high:.2f}" if sc else f"{med:.2f}"

    line3 = f"Chaos swirled around **{band}** — stack or be stacked."

    return " ".join([line1, line2, line3])

# ---------- VP drama (top5 vs 6th + villain/bubble) ----------

def vp_drama_blurb(vp: Dict[str, Any]) -> str:
    if not vp: return ""
    villain, bubble, gap = vp.get("villain"), vp.get("bubble"), vp.get("gap_pf")
    top5 = vp.get("top5") or []
    sixth = vp.get("sixth")
    top_names = ", ".join(r["name"] for r in top5) if top5 else "—"
    sixth_name = sixth["name"] if sixth else "—"
    msg = (f"**League Villain:** {villain} slammed the door on the 2.5 VP lounge; "
           f"{bubble} missed by **{_fmt2(gap)}** PF. Up top: {top_names}. "
           f"First out of the bottle service: **{sixth_name}**. Decimal scoring never felt so personal.")
    return msg

# ---------- Headliners (human variety) ----------

def headliners_blurb(rows: List[Dict[str, Any]]) -> str:
    if not rows: return ""
    verbs = ["cooked", "punished", "detonated", "styled on", "smoked", "baptized", "steamrolled"]
    bits = []
    # group a few stories
    for h in rows[:6]:
        v = _pick(verbs)
        mgrs = ", ".join(h.get("managers", []))
        who = h.get("player") or "Somebody"
        pts = _fmt2(h.get("pts"))
        pos = h.get("pos") or ""
        team = h.get("team") or ""
        tail = f" ({pos} {team})" if (pos or team) else ""
        bits.append(f"{who}{tail} {v} the slate for **{pts}** ({mgrs})")
    # combine with variety punctuation
    return "; ".join(bits) + "."

# ---------- Values / Busts (prose only, collapse dups) ----------

def _collapse_names(rows: List[Dict[str, Any]], key="player", n=5) -> List[str]:
    from collections import Counter
    names = [r.get(key,"Unknown") for r in rows]
    c = Counter(names)
    # sort by freq desc, then name
    return [k for k,_ in sorted(c.items(), key=lambda x:(-x[1], x[0]))][:n]

def values_blurb(values: List[Dict[str, Any]]) -> str:
    if not values: return "No heists this week — chalk builds everywhere."
    top = _collapse_names(values, "player", 5)
    names = ", ".join(top)
    return (f"**Biggest Steals:** {names}. Budget heroes, headline numbers. "
            f"If you faded them, you were playing from behind at lock.")

def busts_blurb(busts: List[Dict[str, Any]]) -> str:
    if not busts: return "No overpriced misfires… this time. Don’t get comfortable."
    top = _collapse_names(busts, "player", 5)
    names = ", ".join(top)
    return (f"**Overpriced Misfires:** {names}. Premium spend, thrift-store returns. "
            f"That crackling sound is salary catching fire.")

# ---------- Power vibes (commentary only; season table rendered elsewhere) ----------

def power_vibes_blurb(season_rows: List[Dict[str, Any]]) -> str:
    if not season_rows: return "Season board loading…"
    top = [r["team"] for r in season_rows[:3]]
    bot = [r["team"] for r in season_rows[-3:]] if len(season_rows) >= 3 else []
    top_txt = ", ".join(top)
    bot_txt = ", ".join(bot)
    return (f"{top_txt} are making their salary dance like hedge-fund managers. "
            f"{bot_txt} are lighting cash like fireworks in a rainstorm. "
            f"The rest are arguing with variance.")

# ---------- Confidence / Survivor (prose lead lines; tables live in renderer) ----------

def confidence_blurb(summary: Dict[str, Any], no_picks: List[str]) -> str:
    parts = []
    if summary.get("boldest_pick"):
        parts.append(f"**Boldest Pick:** {summary['boldest_pick']} (Vegas win-prob said ‘nope’).")
    if summary.get("boring_pick"):
        parts.append(f"**Safety Blanket:** {summary['boring_pick']} (consensus comfort pick).")
    if no_picks:
        parts.append(f"**No-Pick Parade:** {', '.join(no_picks)} — was the Wi-Fi on airplane mode?")
    return " ".join(parts)

def survivor_blurb(summary: Dict[str, Any], no_picks: List[str]) -> str:
    parts = []
    if summary.get("boldest_lifeline"):
        parts.append(f"**Boldest Lifeline:** {summary['boldest_lifeline']} (tightrope but survived).")
    if summary.get("boring_consensus"):
        parts.append(f"**Boring Consensus:** {summary['boring_consensus']} (training wheels).")
    if no_picks:
        parts.append(f"**No-Pick Parade:** {', '.join(no_picks)} — auto-fade of the week.")
    return " ".join(parts)

# ---------- Dumpster / Fraud / Jail ----------

def dumpster_division_blurb(standings: List[Dict[str, Any]]) -> str:
    if not standings: return ""
    n = len(standings); k = max(1, n//3)
    names = ", ".join(r["name"] for r in standings[-k:])
    return f"**Dumpster Division:** {names}. Someone call housekeeping."

def fraud_watch_blurb(eff: List[Dict[str, Any]]) -> str:
    if not eff: return ""
    rows = []
    for r in eff:
        pts = float(r.get("total_pts") or 0.0)
        sal = float(r.get("total_sal") or 0.0)
        ppk = (pts / (sal/1000)) if sal > 0 else 0.0
        rows.append({"name": r.get("name",""), "pts": pts, "ppk": ppk})
    if not rows: return ""
    rows.sort(key=lambda x: (x["ppk"], -x["pts"]))  # worst ppk, highest pts
    f = rows[0]
    return (f"🔥 **Fraud Watch:** {f['name']} posted **{_fmt2(f['pts'])}** with efficiency that belongs in small claims court.")

def fantasy_jail_blurb(starters: Dict[str, List[Dict[str, Any]]] | None, f_map: Dict[str,str] | None) -> str:
    if not starters or not f_map: return ""
    offenders = []
    for fid, rows in starters.items():
        zeroes = [r for r in rows if float(r.get("pts") or 0.0) == 0.0 and (r.get("player_id") or "") != ""]
        if zeroes:
            offenders.append((f_map.get(fid, fid), len(zeroes)))
    if not offenders: return ""
    offenders.sort(key=lambda t: -t[1])
    name, cnt = offenders[0]
    return f"🚔 **Fantasy Jail:** {name} started {cnt} goose-egg slot{'s' if cnt!=1 else ''}. Lineup locks 101."
