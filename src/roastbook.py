from __future__ import annotations
from typing import Any, Dict, List, Tuple
import statistics, random, re

def _fmt2(x: float | int | None, default="0.00") -> str:
    if x is None: return default
    try: return f"{float(x):.2f}"
    except Exception: return default

def _choose(seq: List[str], used: set[str] | None = None) -> str:
    if not seq: return ""
    if not used: return random.choice(seq)
    pool = [w for w in seq if w not in used]
    return random.choice(pool or seq)

def _collapse_names(rows: List[Dict[str, Any]], key="player", n=5) -> List[str]:
    from collections import Counter
    names = [str(r.get(key,"Unknown")).strip() for r in rows if str(r.get(key,"")).strip()]
    c = Counter(names)
    return [k for k,_ in sorted(c.items(), key=lambda x:(-x[1], x[0]))][:n]

# ---------- Weekly Results (long-form, team-first narrative) ----------

def weekly_results_blurb(scores: Dict[str, Any]) -> str:
    rows = scores.get("rows") or []
    if not rows: return ""
    top = rows[0]; bot = rows[-1]
    sc = [s for _, s in rows]
    names = [n for n,_ in rows]

    med = statistics.median(sc) if sc else 0.0
    low = f"{max(min(sc), med-5):.2f}" if sc else f"{med:.2f}"
    high = f"{min(max(sc), med+5):.2f}" if sc else f"{med:.2f}"

    tier_names = names[1:6] if len(names) > 6 else names[1:]
    tier = ", ".join(tier_names)

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
    line1 = f"**League Villain:** {villain} grabbed the last seat at 2.5 VP; {bubble} missed by **{_fmt2(gap)}** PF."
    line2 = f"Up top: {top_names}. First out of bottle service: **{sixth_name}**."
    line3 = "Decimal scoring: where friendships go to get audited."
    return " ".join([line1, line2, line3])

# ---------- Headliners (team-centric phrasing, varied verbs/objects) ----------

_VERBS = ["cooked", "punished", "detonated", "torched", "baptized", "smoked", "steamrolled", "shredded"]
_OBJECTS = ["the slate", "the board", "the scoreboard", "the lobby", "the room"]

def _clean_verb(v: str) -> str:
    return re.sub(r"(ed)+$", "ed", v)

def headliners_blurb(rows: List[Dict[str, Any]]) -> str:
    """Focus on teams who *used* the headline players, not just the players."""
    if not rows: return ""
    # Build a per-team shout list: {team: [ (player, pts), ... ]}
    team_to_plays: Dict[str, List[str]] = {}
    for h in rows[:8]:
        who = h.get("player") or "Somebody"
        pts = _fmt2(h.get("pts"))
        for team in h.get("managers", []):
            team_to_plays.setdefault(team, []).append(f"{who} **{pts}**")

    # Turn into 3–5 compact lines
    lines = []
    for i, (team, plays) in enumerate(sorted(team_to_plays.items(), key=lambda kv: -len(kv[1]))):
        if i >= 5: break
        v = _clean_verb(_choose(_VERBS))
        obj = _choose(_OBJECTS)
        tail = ", ".join(plays[:3])
        lines.append(f"**{team}** {v} {obj} with {tail}")
    if not lines:
        # fallback to player-first if managers missing
        used_verbs, used_objs = set(), set()
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
        half = (len(bits) + 1) // 2
        return "; ".join(bits[:half]) + ". " + "; ".join(bits[half:]) + "."
    return ". ".join(lines) + "."

# ---------- Values / Busts (prose only, zero dup spam) ----------

_VAL_OUTROS = [
    "If you faded those tags, you were playing from behind at lock.",
    "They printed while the room chased chalk.",
    "The DFS accountant smiled; everyone else sighed.",
]
_BUST_OUTROS = [
    "Premium prices, clearance-rack returns.",
    "The cap hit didn’t show up on the scoreboard.",
    "DFS accountant filed it under ‘donation.’",
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

# ---------- Power vibes (season narrative; table renders elsewhere) ----------

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

# ---------- Confidence / Survivor (odds-driven narrative, no tables) ----------

def _bold_score(rank: int, prob: float) -> float:
    """
    Higher = bolder: heavy weight on rank (16 > 1) and on being an underdog (low prob).
    score = rank * (1 - prob)
    """
    try:
        r = float(rank)
        p = float(prob)
    except Exception:
        return 0.0
    return max(0.0, r) * max(0.0, 1.0 - min(max(p, 0.0), 1.0))

def confidence_story(conf3: List[Dict[str, Any]], team_prob: Dict[str, float], no_picks: List[str]) -> str:
    """
    Build a prose recap:
    - Identify teams with the boldest weighted stance (ranked picks on low-prob teams).
    - Identify 'blanket huggers' who stacked high-prob favorites at the top.
    - Roast no-picks.
    """
    if not conf3:
        if no_picks:
            return f"No Confidence picks submitted. **No-Pick Parade:** {', '.join(no_picks)} — did your Wi-Fi take a bye week?"
        return "No Confidence picks submitted."

    team_scores = []  # (team, bold_score_sum, safest_score_sum)
    for row in conf3:
        tname = row.get("team","Team")
        picks = row.get("top3", [])
        if not picks:
            team_scores.append((tname, 0.0, 0.0))
            continue
        bold_sum, safe_sum = 0.0, 0.0
        for g in picks:
            rank = int(g.get("rank", 0))
            pcode = str(g.get("pick","")).upper()
            prob = float(team_prob.get(pcode, 0.5))
            bold_sum += _bold_score(rank, prob)
            safe_sum += (rank * prob)
        team_scores.append((tname, bold_sum, safe_sum))

    # Boldest (highest bold_sum)
    bold_sorted = sorted(team_scores, key=lambda t: (-t[1], t[2], t[0]))
    # Safety blankets (highest safe_sum)
    safe_sorted = sorted(team_scores, key=lambda t: (-t[2], t[1], t[0]))

    highlights = []
    if bold_sorted and bold_sorted[0][1] > 0:
        names = ", ".join(t for t,_,_ in bold_sorted[:3])
        highlights.append(f"**Bold Board:** {names} stacked conviction on live dogs. Vegas frowned; they pressed submit.")
    if safe_sorted and safe_sorted[0][2] > 0:
        names = ", ".join(t for t,_,_ in safe_sorted[:2])
        highlights.append(f"**Safety Blankets:** {names} wrapped their top slots in heavy favorites and called it game theory.")
    if no_picks:
        highlights.append(f"**No-Pick Parade:** {', '.join(no_picks)} — auto-fade of the week.")

    return " ".join(highlights) if highlights else "Picks landed in the mushy middle — nobody brave, nobody reckless."

def survivor_story(surv: List[Dict[str, Any]], team_prob: Dict[str, float], no_picks: List[str]) -> str:
    """
    Pure write-up:
    - Boldest lifelines = lowest-prob chosen teams.
    - Boring consensus = most common / high prob.
    - Roast no-picks. No tables.
    """
    if not surv and not no_picks:
        return "No Survivor picks submitted."
    parts: List[str] = []
    if surv:
        picks = [(r.get("team","Team"), str(r.get("pick","")).upper(), float(team_prob.get(str(r.get("pick","")).upper(), 0.5))) for r in surv if r.get("pick")]
        if picks:
            picks.sort(key=lambda x: x[2])  # lowest prob first
            bold = [f"{t} → {code}" for t,code,_ in picks[:3]]
            parts.append(f"**Boldest Lifelines:** {', '.join(bold)} — tightrope stuff.")
            # consensus-ish: highest prob among most-chosen code
            from collections import Counter
            codes = [c for _,c,_ in picks]
            common_code, _ = sorted(Counter(codes).items(), key=lambda x: (-x[1], x[0]))[0]
            parts.append(f"**Boring Consensus:** {common_code} — the league’s safety blanket.")
    if no_picks:
        parts.append(f"**Ghost Entries:** {', '.join(no_picks)} — seatbelt light was on?")
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
