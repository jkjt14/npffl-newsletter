from __future__ import annotations
from typing import Any, Dict, List, Tuple
import statistics, random, re
from collections import Counter

# ----------------------------
# Tiny prose helpers
# ----------------------------

class ProseBuilder:
    def __init__(self):
        self.used_words: set[str] = set()

    def choose(self, items: List[str]) -> str:
        if not items: return ""
        pool = [w for w in items if w not in self.used_words]
        pick = random.choice(pool or items)
        self.used_words.add(pick)
        return pick

    def sentence(self, *parts: str) -> str:
        text = " ".join(p.strip() for p in parts if p and p.strip())
        text = re.sub(r"\s+", " ", text).strip()
        if text and text[-1] not in ".!?…": text += "."
        return text

    def paragraph(self, *sentences: str) -> str:
        return " ".join(s for s in sentences if s and s.strip())

def _fmt2(x: float | int | None, default="0.00") -> str:
    if x is None: return default
    try: return f"{float(x):.2f}"
    except Exception: return default

def _collapse(items: List[str], n: int) -> List[str]:
    """Most frequent first, capped at n."""
    c = Counter([s.strip() for s in items if s and str(s).strip()])
    return [k for k,_ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))][:n]

# ----------------------------
# Weekly Results (team-first)
# ----------------------------

def weekly_results_blurb(scores: Dict[str, Any]) -> str:
    rows = scores.get("rows") or []
    if not rows: return ""
    top_team, top_pts = rows[0]
    bot_team, bot_pts = rows[-1]
    pts_only = [p for _, p in rows]
    median = statistics.median(pts_only) if pts_only else 0.0
    band_low = f"{max(min(pts_only), median-5):.2f}" if pts_only else f"{median:.2f}"
    band_high = f"{min(max(pts_only), median+5):.2f}" if pts_only else f"{median:.2f}"
    chasers = ", ".join([t for t,_ in rows[1:6]]) if len(rows) > 6 else ", ".join([t for t,_ in rows[1:]])

    pb = ProseBuilder()
    lead  = pb.sentence(f"**{top_team}** set the pace at **{_fmt2(top_pts)}** while **{bot_team}** limped home at **{_fmt2(bot_pts)}**")
    mid   = pb.sentence(f"{chasers} stayed in shouting distance as the middle jammed up")
    chaos = pb.sentence(f"The heart of the slate lived between **{band_low}–{band_high}** — every slot mattered")
    return pb.paragraph(lead, mid, chaos)

# ----------------------------
# VP Drama (top-5 vs 6th + bubble)
# ----------------------------

def vp_drama_blurb(vp: Dict[str, Any]) -> str:
    if not vp: return ""
    villain, bubble, gap = vp.get("villain"), vp.get("bubble"), vp.get("gap_pf")
    top5 = vp.get("top5") or []
    sixth = vp.get("sixth") or {}
    top_names = ", ".join(r["name"] for r in top5) if top5 else "—"
    sixth_name = sixth.get("name","—")

    pb = ProseBuilder()
    a = pb.sentence(f"**League Villain:** {villain} grabbed the last 2.5 VP seat; {bubble} missed by **{_fmt2(gap)}** PF")
    b = pb.sentence(f"Up top: {top_names}. First out beyond the rope: **{sixth_name}**")
    c = pb.sentence("Decimal scoring turns whispers into grudges")
    return pb.paragraph(a, b, c)

# ----------------------------
# Headliners (team-centric, varied templates)
# ----------------------------

_HEAD_TEMPLATES = [
    "— **{team}** built their night on {plays}",
    "— **{team}** rode {plays} and didn’t look back",
    "— **{team}** got lift from {plays}",
    "— **{team}** stacked {plays} and made it count",
    "— **{team}** let {plays} carry the load",
]

def headliners_blurb(rows: List[Dict[str, Any]]) -> str:
    """Turn top player outputs into team stories with phrasing variety."""
    if not rows: return ""
    # Build {team: [ "Player 33.8", ... ]}
    team_plays: Dict[str, List[str]] = {}
    for h in rows[:10]:
        who = (h.get("player") or "").strip() or "Somebody"
        pts = _fmt2(h.get("pts"))
        play = f"{who} {pts}"
        for team in h.get("managers", []):
            team_plays.setdefault(team, []).append(play)

    if not team_plays:
        return ""

    # Pick up to 4 teams with the most headline plays
    lines: List[str] = []
    ordered = sorted(team_plays.items(), key=lambda kv: -len(kv[1]))[:4]
    pb = ProseBuilder()
    for team, plays in ordered:
        top2 = ", ".join(plays[:2])
        tmpl = pb.choose(_HEAD_TEMPLATES)
        lines.append(tmpl.format(team=team, plays=top2))

    closer = "If you faded those names, you spent the night chasing."
    return " ".join(lines) + " " + closer

# ----------------------------
# Values / Busts (story, not lists)
# ----------------------------

_VAL_OPENERS = [
    "The bargain bin paid out where it mattered:",
    "Smart money found the quiet corners:",
    "The best tags wore no neon:",
]
_BUST_OPENERS = [
    "On the other side of the ledger:",
    "Meanwhile, the pricey names left bruises:",
    "The tax bracket didn’t buy points here:",
]

def _name_and_user_blurbs(rows: List[Dict[str, Any]], cap: int = 3) -> List[str]:
    """Return short blurbs like 'Josh Allen (used by FlatFootWorks, Dominators)'."""
    out: List[str] = []
    for r in rows[:cap]:
        nm = (r.get("player") or "Someone").strip()
        mans = r.get("managers") or []
        if mans:
            mans = sorted(mans)[:3]
            out.append(f"{nm} (used by {', '.join(mans)})")
        else:
            out.append(nm)
    return out

def values_blurb(values: List[Dict[str, Any]]) -> str:
    if not values: return "No value play broke the room this time."
    pb = ProseBuilder()
    opener = pb.choose(_VAL_OPENERS)
    blurbs = _name_and_user_blurbs(values, 3)
    middle = "; ".join(blurbs)
    closer = pb.sentence("Edges come from quiet clicks, not loud salaries")
    return pb.paragraph(pb.sentence(opener, middle), closer)

def busts_blurb(busts: List[Dict[str, Any]]) -> str:
    if not busts: return "Premium chalk held serve—no headline busts worth circling."
    pb = ProseBuilder()
    opener = pb.choose(_BUST_OPENERS)
    blurbs = _name_and_user_blurbs(busts, 3)
    middle = "; ".join(blurbs)
    closer = pb.sentence("The cap hit was real; the points were not")
    return pb.paragraph(pb.sentence(opener, middle), closer)

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
        lines.append(pb.sentence(f"{', '.join(top)} turned salary into points without the drama"))
    if bot:
        lines.append(pb.sentence(f"{', '.join(bot)} burned cash and never found the throttle"))
    lines.append(pb.sentence("Everyone else is bartering with variance week to week"))
    return pb.paragraph(*lines)

# ----------------------------
# Confidence (odds-driven narrative, no lists)
# ----------------------------

def _bold_score(rank: int, prob: float) -> float:
    try:
        r = float(rank); p = float(prob)
    except Exception:
        return 0.0
    return max(0.0, r) * max(0.0, 1.0 - min(max(p, 0.0), 1.0))

def confidence_story(conf3: List[Dict[str, Any]], team_prob: Dict[str, float], no_picks: List[str]) -> str:
    if not conf3 and not no_picks:
        return "No Confidence cards this week."

    teams = []
    for row in conf3:
        t = row.get("team","Team")
        bold, safe = 0.0, 0.0
        for g in row.get("top3", []):
            r = int(g.get("rank", 0))
            code = str(g.get("pick","")).upper()
            p = float(team_prob.get(code, 0.5))
            bold += _bold_score(r, p)
            safe += r * p
        teams.append((t, bold, safe))

    parts: List[str] = []
    if teams:
        bold_sorted = sorted(teams, key=lambda x: (-x[1], x[2], x[0]))
        safe_sorted = sorted(teams, key=lambda x: (-x[2], x[1], x[0]))
        # avoid echoing the same team in both spots
        bold_names = [t for t,_,_ in bold_sorted if bold_sorted[0][1] > 0]
        safe_names = [t for t,_,_ in safe_sorted if t not in bold_names]
        if bold_names:
            parts.append(f"**Bold Board:** {', '.join(bold_names[:3])} pushed underdogs into the top slots and made it interesting.")
        if safe_names:
            parts.append(f"**Safety Blankets:** {', '.join(safe_names[:2])} wrapped the top in heavy favorites and slept fine.")
    if no_picks:
        parts.append(f"**Ghost Entries:** {', '.join(no_picks)} left their cards blank; excuses pending.")

    return " ".join(parts) if parts else "Everything landed in the middle—no heroes, no villains."

# ----------------------------
# Survivor (odds-driven narrative, no table)
# ----------------------------

def survivor_story(surv: List[Dict[str, Any]], team_prob: Dict[str, float], no_picks: List[str]) -> str:
    if not surv and not no_picks:
        return "No Survivor tickets posted."
    pieces: List[str] = []
    if surv:
        picks = [(r.get("team","Team"), str(r.get("pick","")).upper(), float(team_prob.get(str(r.get("pick","")).upper(), 0.5))) for r in surv if r.get("pick")]
        if picks:
            picks.sort(key=lambda x: x[2])  # lowest prob = boldest
            # Top 2 boldest, plus one honorable mention if exists
            bold = [f"{t} → {code}" for t,code,_ in picks[:2]]
            if len(picks) > 2:
                bold.append(f"{picks[2][0]} → {picks[2][1]}")
            pieces.append(f"**Boldest Lifelines:** {', '.join(bold)} — tightrope stuff, clean landing.")
            # Consensus: most common code
            codes = [c for _,c,_ in picks]
            common_code, _ = sorted(Counter(codes).items(), key=lambda x: (-x[1], x[0]))[0]
            pieces.append(f"**Boring Consensus:** {common_code} — training wheels on, ride completed.")
    if no_picks:
        pieces.append(f"**No-Show Column:** {', '.join(no_picks)} skipped the booth.")
    return " ".join(pieces)

# ----------------------------
# Rotating one-liners
# ----------------------------

def fraud_watch_blurb(eff: List[Dict[str, Any]]) -> str:
    if not eff: return ""
    rows = []
    for r in eff:
        pts = float(r.get("total_pts") or 0.0)
        sal = float(r.get("total_sal") or 0.0)
        ppk = (pts / (sal/1000)) if sal > 0 else 0.0
        rows.append({"name": r.get("name",""), "pts": pts, "ppk": ppk})
    if not rows: return ""
    rows.sort(key=lambda x: (x["ppk"], -x["pts"]))  # worst efficiency first
    f = rows[0]
    return f"🔥 **Fraud Watch:** {f['name']} posted **{_fmt2(f['pts'])}** with efficiency that won’t pass audit."

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
    return f"🚔 **Fantasy Jail:** {name} started {cnt} goose-egg slot{'s' if cnt!=1 else ''}. Self-inflicted sweat."
