from __future__ import annotations
from typing import Any, Dict, List, Tuple
import statistics
import random
import re

# ----------------------------
# Small prose engine utilities
# ----------------------------

class ProseBuilder:
    """Tiny helper to keep tone consistent, avoid repetition, and build paragraphs."""
    def __init__(self):
        self.used_words: set[str] = set()
        self.used_phrases: set[str] = set()

    def choose(self, items: List[str], allow_repeat: bool = False) -> str:
        if not items:
            return ""
        if allow_repeat:
            return random.choice(items)
        pool = [w for w in items if w not in self.used_words]
        pick = random.choice(pool or items)
        self.used_words.add(pick)
        return pick

    def sentence(self, *parts: str) -> str:
        text = " ".join(p.strip() for p in parts if p and p.strip())
        # simple spacing polish
        text = re.sub(r"\s+", " ", text).strip()
        if not text.endswith((".", "!", "?", "…")):
            text += "."
        return text

    def paragraph(self, *sentences: str) -> str:
        sents = [s for s in sentences if s and s.strip()]
        return " ".join(sents)

def _fmt2(x: float | int | None, default="0.00") -> str:
    if x is None: return default
    try: return f"{float(x):.2f}"
    except Exception: return default

def _collapse_names(rows: List[Dict[str, Any]], key="player", n=5) -> List[str]:
    from collections import Counter
    names = [str(r.get(key,"Unknown")).strip() for r in rows if str(r.get(key,"")).strip()]
    c = Counter(names)
    return [k for k,_ in sorted(c.items(), key=lambda x:(-x[1], x[0]))][:n]

# ----------------------------
# Weekly Results (team-first)
# ----------------------------

def weekly_results_blurb(scores: Dict[str, Any]) -> str:
    pb = ProseBuilder()
    rows = scores.get("rows") or []
    if not rows:
        return ""
    top_team, top_pts = rows[0]
    bot_team, bot_pts = rows[-1]
    pts_only = [p for _, p in rows]
    median = statistics.median(pts_only) if pts_only else 0.0
    band_low = f"{max(min(pts_only), median-5):.2f}" if pts_only else f"{median:.2f}"
    band_high = f"{min(max(pts_only), median+5):.2f}" if pts_only else f"{median:.2f}"

    chasers = ", ".join([t for t,_ in rows[1:6]]) if len(rows) > 6 else ", ".join([t for t,_ in rows[1:]])
    lead = pb.sentence(
        f"**{top_team}** set the pace at **{_fmt2(top_pts)}**",
        f"while **{bot_team}** limped home at **{_fmt2(bot_pts)}**"
    )
    mid = pb.sentence(
        f"{chasers} were in the mix right behind the leader",
        "and a few more hovered just outside the rope"
    )
    chaos = pb.sentence(
        f"The middle of the room lived between **{band_low}–{band_high}**",
        "where every slot mattered"
    )
    return pb.paragraph(lead, mid, chaos)

# ----------------------------
# VP Drama (top-5 vs 6th + bubble)
# ----------------------------

def vp_drama_blurb(vp: Dict[str, Any]) -> str:
    if not vp: return ""
    pb = ProseBuilder()
    villain, bubble, gap = vp.get("villain"), vp.get("bubble"), vp.get("gap_pf")
    top5 = vp.get("top5") or []
    sixth = vp.get("sixth") or {}
    top_names = ", ".join(r["name"] for r in top5) if top5 else "—"
    sixth_name = sixth.get("name","—")

    line1 = pb.sentence(
        f"**League Villain:** {villain} claimed the final 2.5 VP seat",
        f"and {bubble} missed by **{_fmt2(gap)}** PF"
    )
    line2 = pb.sentence(
        f"The velvet rope held for {top_names}",
        f"with **{sixth_name}** staring in from the curb"
    )
    line3 = pb.sentence("Decimal scoring makes for petty grudges")
    return pb.paragraph(line1, line2, line3)

# ----------------------------
# Headliners (team-centric)
# ----------------------------

def headliners_blurb(rows: List[Dict[str, Any]]) -> str:
    if not rows: return ""
    pb = ProseBuilder()

    # Build which teams rode which headline plays
    team_plays: Dict[str, List[str]] = {}
    for h in rows[:8]:
        who = h.get("player") or "Somebody"
        pts = _fmt2(h.get("pts"))
        for team in h.get("managers", []):
            team_plays.setdefault(team, []).append(f"{who} {_fmt2(h.get('pts'))}")

    if team_plays:
        lines: List[str] = []
        for team, plays in sorted(team_plays.items(), key=lambda kv: -len(kv[1]))[:4]:
            chunk = ", ".join(plays[:3])
            lines.append(pb.sentence(f"**{team}** leaned on {chunk}"))
        closer = pb.sentence("If you faded those names, you were chasing from the jump")
        return pb.paragraph(*lines, closer)

    # Fallback: player-first if manager data is missing
    verbs = ["punched above weight", "took over", "drove the scoreboard", "tilted the room", "stole the show"]
    obj = ["the board", "the late window", "the primetime crowd", "every parlay in the building"]
    bits = []
    for h in rows[:6]:
        who = h.get("player") or "Somebody"
        tail = []
        pos = (h.get("pos") or "").strip()
        team = (h.get("team") or "").strip()
        if pos or team:
            tail.append(f"({pos} {team})".strip())
        verb = pb.choose(verbs)
        thing = pb.choose(obj)
        bits.append(pb.sentence(f"{who} {' '.join(tail)} {verb} with **{_fmt2(h.get('pts'))}** against {thing}"))
    return pb.paragraph(*bits)

# ----------------------------
# Values / Busts (prose only)
# ----------------------------

VAL_OUTROS = [
    "That’s how edges are built while everyone else plays the brochure.",
    "Smart tags; smarter timing.",
    "That’s money well spent.",
]
BUST_OUTROS = [
    "The cap hit left a dent and not much else.",
    "That’s a donation the accountant won’t forget.",
    "They’ll show up on the highlight reel—just not this week.",
]

def values_blurb(values: List[Dict[str, Any]]) -> str:
    if not values: return "No bargains broke the slate this time."
    pb = ProseBuilder()
    names = ", ".join(_collapse_names(values, "player", 5))
    outro = pb.choose(VAL_OUTROS)
    return pb.paragraph(pb.sentence(f"**Biggest Steals:** {names}", outro))

def busts_blurb(busts: List[Dict[str, Any]]) -> str:
    if not busts: return "No premium misfires worth framing this week."
    pb = ProseBuilder()
    names = ", ".join(_collapse_names(busts, "player", 5))
    outro = pb.choose(BUST_OUTROS)
    return pb.paragraph(pb.sentence(f"**Overpriced Misfires:** {names}", outro))

# ----------------------------
# Power Vibes (season prose)
# ----------------------------

def power_vibes_blurb(season_rows: List[Dict[str, Any]]) -> str:
    if not season_rows: return "Season board loading…"
    pb = ProseBuilder()
    top = [r["team"] for r in season_rows[:3]]
    bot = [r["team"] for r in season_rows[-3:]] if len(season_rows) >= 3 else []

    lines = []
    if top:
        lines.append(pb.sentence(f"{', '.join(top)} turned salary into points with zero drama"))
    if bot:
        lines.append(pb.sentence(f"{', '.join(bot)} burned cash and didn’t move the needle"))
    lines.append(pb.sentence("Everyone else kept the spreadsheet honest and the sweat alive"))
    return pb.paragraph(*lines)

# ----------------------------
# Confidence (odds-driven, no tables)
# ----------------------------

def _bold_score(rank: int, prob: float) -> float:
    # Rank matters, underdog matters
    try:
        r = float(rank)
        p = float(prob)
    except Exception:
        return 0.0
    return max(0.0, r) * max(0.0, 1.0 - min(max(p, 0.0), 1.0))

def confidence_story(conf3: List[Dict[str, Any]], team_prob: Dict[str, float], no_picks: List[str]) -> str:
    pb = ProseBuilder()
    if not conf3 and not no_picks:
        return "No Confidence cards on file—maybe everyone was too confident."

    # score boldness and safety
    scores = []
    for row in conf3:
        team = row.get("team","Team")
        bold_sum = 0.0
        safe_sum = 0.0
        for g in row.get("top3", []):
            rank = int(g.get("rank", 0))
            code = str(g.get("pick","")).upper()
            prob = float(team_prob.get(code, 0.5))
            bold_sum += _bold_score(rank, prob)
            safe_sum += rank * prob
        scores.append((team, bold_sum, safe_sum))

    text: List[str] = []
    if scores:
        bold_sorted = sorted(scores, key=lambda t: (-t[1], t[2], t[0]))
        safe_sorted = sorted(scores, key=lambda t: (-t[2], t[1], t[0]))

        bold_teams = ", ".join(t for t,_,_ in bold_sorted[:3] if bold_sorted[0][1] > 0)
        safe_teams = ", ".join(t for t,_,_ in safe_sorted[:2] if safe_sorted[0][2] > 0)

        if bold_teams:
            text.append(pb.sentence(f"**Bold Board:** {bold_teams} shoved their top chips behind live dogs and didn’t blink"))
        if safe_teams:
            text.append(pb.sentence(f"**Safety Blankets:** {safe_teams} hugged favorites and called it ‘optimal’"))

    if no_picks:
        text.append(pb.sentence(f"**Ghost Entries:** {', '.join(no_picks)} left their cards blank—seatbelt lights were on"))

    return " ".join(text) if text else "The picks landed in the middle—no heroes, no villains."

# ----------------------------
# Survivor (odds-driven, no tables)
# ----------------------------

def survivor_story(surv: List[Dict[str, Any]], team_prob: Dict[str, float], no_picks: List[str]) -> str:
    pb = ProseBuilder()
    if not surv and not no_picks:
        return "No Survivor tickets this week."

    pieces: List[str] = []
    if surv:
        picks = [(r.get("team","Team"), str(r.get("pick","")).upper(), float(team_prob.get(str(r.get("pick","")).upper(), 0.5))) for r in surv if r.get("pick")]
        if picks:
            picks.sort(key=lambda x: x[2])  # lowest prob = boldest
            bold_lines = ", ".join(f"{t} → {code}" for t,code,_ in picks[:3])
            pieces.append(pb.sentence(f"**Boldest Lifelines:** {bold_lines}", "tightrope work, clean landing"))

            from collections import Counter
            codes = [c for _,c,_ in picks]
            common_code, count = sorted(Counter(codes).items(), key=lambda x: (-x[1], x[0]))[0]
            pieces.append(pb.sentence(f"**Boring Consensus:** {common_code}", "training wheels never go out of style"))

    if no_picks:
        pieces.append(pb.sentence(f"**No-Show Column:** {', '.join(no_picks)} left Survivor on read"))

    return " ".join(pieces)

# ----------------------------
# Rotating one-liners
# ----------------------------

def dumpster_division_blurb(standings: List[Dict[str, Any]]) -> str:
    if not standings: return ""
    n = len(standings); k = max(1, n//3)
    names = ", ".join(r["name"] for r in standings[-k:])
    return f"**Dumpster Division:** {names}. Someone bring a broom."

def fraud_watch_blurb(eff: List[Dict[str, Any]]) -> str:
    if not eff: return ""
    rows = []
    for r in eff:
        pts = float(r.get("total_pts") or 0.0)
        sal = float(r.get("total_sal") or 0.0)
        ppk = (pts / (sal/1000)) if sal > 0 else 0.0
        rows.append({"name": r.get("name",""), "pts": pts, "ppk": ppk})
    if not rows: return ""
    rows.sort(key=lambda x: (x["ppk"], -x["pts"]))  # worst efficiency, then high raw points
    f = rows[0]
    return f"🔥 **Fraud Watch:** {f['name']} put up **{_fmt2(f['pts'])}** with efficiency that won’t pass audit."

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
    plural = "s" if cnt != 1 else ""
    return f"🚔 **Fantasy Jail:** {name} started {cnt} goose-egg slot{plural}. That’s a self-inflicted sweat."
