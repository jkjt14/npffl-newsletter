from __future__ import annotations
from typing import Any, Dict, List, Tuple
import statistics, random, re

def _fmt2(x: float | int | None, default="0.00") -> str:
    if x is None: return default
    try: return f"{float(x):.2f}"
    except Exception: return default

def _choose(seq: List[str], used: set[str] | None = None) -> str:
    """Pick a word not in used if possible."""
    if not seq: return ""
    if not used: return random.choice(seq)
    pool = [w for w in seq if w not in used]
    return random.choice(pool or seq)

def _collapse_names(rows: List[Dict[str, Any]], key="player", n=5) -> List[str]:
    from collections import Counter
    names = [str(r.get(key,"Unknown")).strip() for r in rows if str(r.get(key,"")).strip()]
    c = Counter(names)
    return [k for k,_ in sorted(c.items(), key=lambda x:(-x[1], x[0]))][:n]

# ---------- Weekly Results (long-form, engaging) ----------

def weekly_results_blurb(scores: Dict[str, Any]) -> str:
    """Narrative: top, bottom, a few mid names, and a chaos band."""
    rows = scores.get("rows") or []
    if not rows: return ""
    top = rows[0]; bot = rows[-1]
    sc = [s for _, s in rows]
    names = [n for n,_ in rows]

    # Chaos band around the median ±5
    med = statistics.median(sc) if sc else 0.0
    low = f"{max(min(sc), med-5):.2f}" if sc else f"{med:.2f}"
    high = f"{min(max(sc), med+5):.2f}" if sc else f"{med:.2f}"

    tier = ", ".join(names[1:6]) if len(names) > 6 else ", ".join(names[1:])
    parts = [
        f"**{top[0]}** lit the slate with **{top[1]:.2f}**.",
        f"**{bot[0]}**? Paid the cover charge and sat in the parking lot (**{bot[1]:.2f}**).",
        f"{tier} kept it loud just behind, while a couple of hopefuls pressed their noses on the VIP glass.",
        f"Chaos swirled between **{low}–{high}** — stack or be stacked."
    ]
    return " ".join(parts)

# ---------- VP drama (top5 vs 6th + villain/bubble) ----------

def vp_drama_blurb(vp: Dict[str, Any]) -> str:
    if not vp: return ""
    villain, bubble, gap = vp.get("villain"), vp.get("bubble"), vp.get("gap_pf")
    top5 = vp.get("top5") or []
    sixth = vp.get("sixth")
    top_names = ", ".join(r["name"] for r in top5) if top5 else "—"
    sixth_name = (sixth or {}).get("name","—")
    # If we have both, make it human:
    line1 = f"**League Villain:** {villain} grabbed the last seat at 2.5 VP; {bubble} missed by **{_fmt2(gap)}** PF."
    line2 = f"Up top: {top_names}. First out of bottle service: **{sixth_name}**."
    line3 = "Decimal scoring: where friendships go to get audited."
    return " ".join([line1, line2, line3])

# ---------- Headliners (varied verbs/objects, typo-guard) ----------

_VERBS = ["cooked", "punished", "detonated", "torched", "baptized", "smoked", "steamrolled", "shredded"]
_OBJECTS = ["the slate", "the board", "the scoreboard", "the lobby", "the room"]

def _clean_verb(v: str) -> str:
    # fix double 'ed' edge cases from input
    return re.sub(r"(ed)+$", "ed", v)

def headliners_blurb(rows: List[Dict[str, Any]]) -> str:
    if not rows: return ""
    used_verbs: set[str] = set()
    used_objs: set[str] = set()
    bits = []
    for h in rows[:6]:
        v = _clean_verb(_choose(_VERBS, used_verbs)); used_verbs.add(v)
        obj = _choose(_OBJECTS, used_objs); used_objs.add(obj)
        who = h.get("player") or "Somebody"
        pos = (h.get("pos") or "").strip()
        team = (h.get("team") or "").strip()
        tail = f" ({pos} {team})" if (pos or team) else ""
        pts = _fmt2(h.get("pts"))
        mgrs = ", ".join(h.get("managers", []))
        bits.append(f"{who}{tail} {v} {obj} for **{pts}** ({mgrs})")
    # Two shorter sentences read more human than one mega-sentence
    half = (len(bits) + 1) // 2
    return "; ".join(bits[:half]) + ". " + "; ".join(bits[half:]) + "."

# ---------- Values / Busts (prose only, zero dup spam) ----------

_VAL_OUTROS = [
    "If you faded those tags, you were playing from behind at lock.",
    "They printed while the room chased chalk.",
    "The waiver wire of hope had nothing on these price tags.",
]
_BUST_OUTROS = [
    "That crackling sound is salary catching fire.",
    "Premium prices, clearance-rack returns.",
    "DFS accountant marked it down as 'donation.'",
]

def values_blurb(values: List[Dict[str, Any]]) -> str:
    if not values: return "No heists this week — chalk builds everywhere."
    top = _collapse_names(values, "player", 5)
    names = ", ".join(top)
    outro = random.choice(_VAL_OUTROS)
    return f"**Biggest Steals:** {names}. Budget heroes, headline numbers. {outro}"

def busts_blurb(busts: List[Dict[str, Any]]) -> str:
    if not busts: return "No overpriced misfires… this time. Don’t get comfortable."
    top = _collapse_names(busts, "player", 5)
    names = ", ".join(top)
    outro = random.choice(_BUST_OUTROS)
    return f"**Overpriced Misfires:** {names}. {outro}"

# ---------- Power vibes (commentary only; season table renders elsewhere) ----------

def power_vibes_blurb(season_rows: List[Dict[str, Any]]) -> str:
    if not season_rows: return "Season board loading…"
    top = [r["team"] for r in season_rows[:3]]
    bot = [r["team"] for r in season_rows[-3:]] if len(season_rows) >= 3 else []
    lines = []
    if top:
        lines.append(f"{', '.join(top)} made salary dance like portfolio managers.")
    if bot:
        lines.append(f"{', '.join(bot)} lit cash like fireworks in a rainstorm.")
    lines.append("Everyone else is negotiating with variance.")
    return " ".join(lines)

# ---------- Confidence / Survivor (prose lead; renderer does mini tables) ----------

def confidence_blurb(summary: Dict[str, Any], no_picks: List[str]) -> str:
    bold = summary.get("boldest_pick")
    safe = summary.get("boring_pick")
    parts = []
    if bold and safe and bold == safe:
        parts.append(f"**Consensus Chaos:** {safe} was both the bravest and the blanket — go figure.")
    else:
        if bold: parts.append(f"**Boldest Pick:** {bold} (Vegas shook its head).")
        if safe: parts.append(f"**Safety Blanket:** {safe} (everybody cuddled up).")
    if no_picks:
        parts.append(f"**No-Pick Parade:** {', '.join(no_picks)} — did your Wi-Fi take a bye week?")
    return " ".join(parts)

def survivor_blurb(summary: Dict[str, Any], no_picks: List[str]) -> str:
    parts = []
    if summary.get("boldest_lifeline"):
        parts.append(f"**Boldest Lifeline:** {summary['boldest_lifeline']} (tightrope, but lived).")
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
    return f"**Dumpster Division:** {names}. Housekeeping has questions."

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
    return (f"🔥 **Fraud Watch:** {f['name']} posted **{_fmt2(f['pts'])}** with efficiency"
            " that belongs in small claims court.")

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
