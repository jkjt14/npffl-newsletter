from __future__ import annotations
from typing import Any, Dict, List, Tuple
import statistics
from collections import Counter, defaultdict

from .prose import Tone, ProseBuilder

def _fmt2(x: float | int | None, default="0.00") -> str:
    if x is None: return default
    try: return f"{float(x):.2f}"
    except Exception: return default

def _collapse(items: List[str], n: int) -> List[str]:
    c = Counter([s.strip() for s in items if s and str(s).strip()])
    return [k for k,_ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))][:n]

# ===================
# Weekly Results
# ===================

def weekly_results_blurb(scores: Dict[str, Any], tone: Tone) -> str:
    rows = scores.get("rows") or []
    if not rows: return ""
    top_team, top_pts = rows[0]
    bot_team, bot_pts = rows[-1]
    pts_only = [p for _, p in rows]
    median = statistics.median(pts_only) if pts_only else 0.0
    band_low = f"{max(min(pts_only), median-5):.2f}" if pts_only else f"{median:.2f}"
    band_high = f"{min(max(pts_only), median+5):.2f}" if pts_only else f"{median:.2f}"
    chasers = ", ".join([t for t,_ in rows[1:6]]) if len(rows) > 6 else ", ".join([t for t,_ in rows[1:]])

    pb = ProseBuilder(tone)
    lead  = pb.sentence(f"**{top_team}** set the pace at **{_fmt2(top_pts)}** while **{bot_team}** limped home at **{_fmt2(bot_pts)}**")
    mid   = pb.sentence(f"{chasers} stayed within shouting distance as the middle jammed up")
    chaos = pb.sentence(f"The heart of the slate lived between **{band_low}–{band_high}** — every slot mattered")
    return pb.paragraph(lead, mid, chaos)

def weekly_results_roast(tone: Tone) -> str:
    e = tone.emojis["boom"]
    if tone.name == "mild":
        return "Margin for error was tiny; a single slot swung the room."
    if tone.name == "inferno":
        return f"{e} The middle was a blender—stack or get shredded."
    return f"{e} One wrong click and you were chasing all night."

# ===================
# VP Drama
# ===================

def vp_drama_blurb(vp: Dict[str, Any], tone: Tone) -> str:
    if not vp: return ""
    villain, bubble, gap = vp.get("villain"), vp.get("bubble"), vp.get("gap_pf")
    top5 = vp.get("top5") or []
    sixth = vp.get("sixth") or {}
    top_names = ", ".join(r["name"] for r in top5) if top5 else "—"
    sixth_name = sixth.get("name","—")

    pb = ProseBuilder(tone)
    a = pb.sentence(f"**League Villain:** {villain} grabbed the last 2.5 VP seat; {bubble} missed by **{_fmt2(gap)}** PF")
    b = pb.sentence(f"Up top: {top_names}. First out beyond the rope: **{sixth_name}**")
    c = pb.sentence("Decimal scoring turns whispers into grudges")
    return pb.paragraph(a, b, c)

def vp_drama_roast(tone: Tone) -> str:
    if tone.name == "mild":
        return "Close calls build rivalries; this one just got interesting."
    return f"{tone.emojis['fire']} Bottle service is closed—someone’s filing emotional chargebacks."

# ===================
# Headliners
# ===================

_HEAD_TEMPLATES = [
    "— **{team}** built their night on {plays}",
    "— **{team}** rode {plays} and didn’t look back",
    "— **{team}** got lift from {plays}",
    "— **{team}** stacked {plays} and made it count",
    "— **{team}** let {plays} carry the load",
]

def headliners_blurb(rows: List[Dict[str, Any]], tone: Tone) -> str:
    if not rows: return ""
    team_plays: Dict[str, List[str]] = {}
    for h in rows[:10]:
        who = (h.get("player") or "").strip() or "Somebody"
        pts = _fmt2(h.get("pts"))
        token = f"{who} {pts}"
        for team in h.get("managers", []):
            team_plays.setdefault(team, []).append(token)

    if not team_plays:
        return ""

    lines: List[str] = []
    ordered = sorted(team_plays.items(), key=lambda kv: -len(kv[1]))[:4]
    pb = ProseBuilder(tone)
    for team, plays in ordered:
        uniq = []
        seen = set()
        for p in plays:
            name = p.split(" ", 1)[0]
            if name not in seen:
                uniq.append(p); seen.add(name)
            if len(uniq) == 2: break
        top2 = ", ".join(uniq) if uniq else ", ".join(plays[:2])
        tmpl = pb.choose(_HEAD_TEMPLATES)
        lines.append(tmpl.format(team=team, plays=top2))

    closer = "If you faded those names, you spent the night chasing."
    return " ".join(lines) + " " + pb.sentence(tone.amp(closer, "The best names did the heavy lifting."))

def headliners_roast(tone: Tone) -> str:
    if tone.name == "mild":
        return "Star power made the difference."
    return f"{tone.emojis['fire']} The highlight reel was ruthless."

# ===================
# Values / Busts (team-first)
# ===================

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

def _team_support_blurb(rows: List[Dict[str, Any]], cap_players: int = 2) -> List[Tuple[str, str]]:
    team_to_players: Dict[str, List[str]] = defaultdict(list)
    team_counts: Counter = Counter()
    for r in rows:
        who = (r.get("player") or "Someone").strip()
        mans = r.get("managers") or []
        for t in mans:
            if who not in team_to_players[t]:
                team_to_players[t].append(who)
            team_counts[t] += 1
    if not team_counts:
        return []
    ordered = sorted(team_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    out: List[Tuple[str,str]] = []
    for team, _ in ordered[:3]:
        names = team_to_players.get(team, [])[:cap_players]
        out.append((team, ", ".join(names)))
    return out

def values_blurb(values: List[Dict[str, Any]], tone: Tone) -> str:
    if not values: return "No value play broke the room this time."
    pb = ProseBuilder(tone)
    opener = pb.choose(_VAL_OPENERS)
    teams = _team_support_blurb(values, cap_players=2)
    if not teams:
        names = ", ".join(_collapse([v.get("player") for v in values], 3))
        return pb.paragraph(pb.sentence(opener, names), "Edges come from quiet clicks, not loud salaries.")
    leader = teams[0]
    runner = teams[1] if len(teams) > 1 else None
    lead_line = pb.sentence(f"**Biggest Heist:** {leader[0]} turned budget tags into real points with {leader[1]}")
    if runner:
        run_line = pb.sentence(f"**Runner-up:** {runner[0]} found similar juice with {runner[1]}")
        close = pb.sentence("That’s how you buy ceiling without paying sticker")
        return pb.paragraph(opener, lead_line, run_line, close)
    close = pb.sentence("That’s how you buy ceiling without paying sticker")
    return pb.paragraph(opener, lead_line, close)

def values_roast(tone: Tone) -> str:
    if tone.name == "mild":
        return "Sharp choices, clean returns."
    return f"{tone.emojis['dart']} Quiet tags, loud results."

def busts_blurb(busts: List[Dict[str, Any]], tone: Tone) -> str:
    if not busts: return "Premium chalk held serve—no headline busts worth circling."
    pb = ProseBuilder(tone)
    opener = pb.choose(_BUST_OPENERS)
    teams = _team_support_blurb(busts, cap_players=2)
    if not teams:
        names = ", ".join(_collapse([b.get("player") for b in busts], 3))
        return pb.paragraph(pb.sentence(opener, names), "The cap hit was real; the points were not.")
    leader = teams[0]
    runner = teams[1] if len(teams) > 1 else None
    lead_line = pb.sentence(f"**Overpriced Misfire:** {leader[0]} paid up and got little back—{leader[1]} led the regret")
    if runner:
        run_line = pb.sentence(f"**Honorable Mention:** {runner[0]} weren’t far behind on sunk cost")
        close = pb.sentence("That’s a receipt nobody frames")
        return pb.paragraph(opener, lead_line, run_line, close)
    close = pb.sentence("That’s a receipt nobody frames")
    return pb.paragraph(opener, lead_line, close)

def busts_roast(tone: Tone) -> str:
    if tone.name == "mild":
        return "Expensive names, quiet nights."
    return f"{tone.emojis['ice']} Paying premium for silence is a special skill."

# ===================
# Power Vibes (season prose)
# ===================

def power_vibes_blurb(season_rows: List[Dict[str, Any]], tone: Tone) -> str:
    if not season_rows: return "Season board loading…"
    pb = ProseBuilder(tone)
    top = [r["team"] for r in season_rows[:3]]
    bot = [r["team"] for r in season_rows[-3:]] if len(season_rows) >= 3 else []
    lines = []
    if top:
        lines.append(pb.sentence(f"{', '.join(top)} turned salary into points without the drama"))
    if bot:
        lines.append(pb.sentence(f"{', '.join(bot)} burned cash and never found the throttle"))
    lines.append(pb.sentence("Everyone else is bartering with variance week to week"))
    return pb.paragraph(*lines)

def power_vibes_roast(tone: Tone) -> str:
    if tone.name == "mild":
        return "Early patterns usually hold—until they don’t."
    return f"{tone.emojis['fire']} Rank is rented; payments are weekly."

# ===================
# Confidence (odds narrative)
# ===================

def _bold_score(rank: int, prob: float) -> float:
    try:
        r = float(rank); p = float(prob)
    except Exception:
        return 0.0
    return max(0.0, r) * max(0.0, 1.0 - min(max(p, 0.0), 1.0))

def confidence_story(conf3: List[Dict[str, Any]], team_prob: Dict[str, float], no_picks: List[str], tone: Tone) -> str:
    if not conf3 and not no_picks:
        return "No Confidence cards this week."
    teams = []
    upset_pick = None  # (team, code, prob, rank)
    safe_scores: Dict[str, float] = {}

    for row in conf3:
        t = row.get("team","Team")
        bold, safe = 0.0, 0.0
        for g in row.get("top3", []):
            r = int(g.get("rank", 0))
            code = str(g.get("pick","")).upper()
            p = float(team_prob.get(code, 0.5))
            w = _bold_score(r, p)
            if upset_pick is None or (w > 0 and p < (upset_pick[2] if upset_pick else 1.0)):
                upset_pick = (t, code, p, r)
            bold += w
            safe += r * p
        teams.append((t, bold, safe))
        safe_scores[t] = safe

    parts: List[str] = []
    if teams:
        teams.sort(key=lambda x: (-x[1], x[2], x[0]))
        bold_names = [t for t,_,_ in teams if teams[0][1] > 0][:3]
        if bold_names:
            parts.append(f"{tone.emojis['fire']} **Bold Board:** {', '.join(bold_names)} pushed live dogs into top slots.")
        chalk_team = max(safe_scores.items(), key=lambda kv: kv[1])[0] if safe_scores else None
        if chalk_team:
            parts.append(f"{tone.emojis['ice']} **Chalk Fortress:** {chalk_team} stacked heavy favorites and slept fine.")
    if upset_pick:
        t, code, p, r = upset_pick
        parts.append(f"{tone.emojis['dart']} **Upset Ticket:** {t} hit {code} at rank {r}, beating a {int(round((1-p)*100))}% ‘nope’ from Vegas.")
    if no_picks:
        parts.append(f"{tone.emojis['warn']} **Ghost Entries:** {', '.join(no_picks)} left cards blank; excuses pending.")
    return " ".join(parts) if parts else "Everything landed in the middle—no heroes, no villains."

def confidence_roast(tone: Tone) -> str:
    if tone.name == "mild":
        return "Upsets make the room louder; chalk makes it calmer."
    return f"{tone.emojis['dart']} Pick bravely or live quietly."

# ===================
# Survivor (odds narrative)
# ===================

def survivor_story(surv: List[Dict[str, Any]], team_prob: Dict[str, float], no_picks: List[str], tone: Tone) -> str:
    if not surv and not no_picks:
        return "No Survivor tickets posted."
    pieces: List[str] = []
    if surv:
        picks = [(r.get("team","Team"), str(r.get("pick","")).upper(), float(team_prob.get(str(r.get("pick","")).upper(), 0.5))) for r in surv if r.get("pick")]
        if picks:
            picks.sort(key=lambda x: x[2])  # lowest prob = boldest
            bold = [f"{t} → {code}" for t,code,_ in picks[:2]]
            if len(picks) > 2:
                bold.append(f"{picks[2][0]} → {picks[2][1]}")
            pieces.append(f"{tone.emojis['fire']} **Boldest Lifelines:** {', '.join(bold)} — tightrope work, clean landing.")
            from collections import Counter
            codes = [c for _,c,_ in picks]
            common_code, _ = sorted(Counter(codes).items(), key=lambda x: (-x[1], x[0]))[0]
            p = float(team_prob.get(common_code, 0.75))
            pieces.append(f"{tone.emojis['ice']} **Boring Consensus:** {common_code} ({int(round(p*100))}% implied) — training wheels engaged.")
    if no_picks:
        pieces.append(f"{tone.emojis['warn']} **No-Show:** {', '.join(no_picks)} skipped the booth.")
    return " ".join(pieces)

def survivor_roast(tone: Tone) -> str:
    if tone.name == "mild":
        return "Staying alive is half the game."
    return f"{tone.emojis['fire']} Survivor pays the brave and exposes the cautious."

# ===================
# Chalk vs Leverage (ownership)
# ===================

def chalk_leverage_blurb(starters_by_franchise: Dict[str, List[Dict[str, Any]]] | None, tone: Tone) -> str:
    """
    Uses starters to infer 'ownership'. Chalk = widely started; Leverage = rarely started.
    Then crosses with output to produce two short team-first paragraphs.
    """
    if not starters_by_franchise:
        return "Ownership patterns were thin this week."

    # Aggregate ownership and outputs
    total_entries = max(1, len(starters_by_franchise))
    player_to_count: Counter = Counter()
    player_to_pts: Dict[str, float] = {}
    player_to_teams: Dict[str, List[str]] = defaultdict(list)

    for team_id, rows in starters_by_franchise.items():
        for r in rows:
            name = (r.get("player") or "").strip()
            if not name:
                continue
            pts = float(r.get("pts") or 0.0)
            player_to_count[name] += 1
            player_to_pts[name] = max(player_to_pts.get(name, pts), pts)  # take max (avoid multi rows)
            # note: we don't have team names here; newsletter passes franchise map for display elsewhere

    if not player_to_count:
        return "Ownership patterns were thin this week."

    # thresholds
    counts = sorted(player_to_count.values())
    median_cnt = counts[len(counts)//2]
    chalk_cut = max(2, median_cnt)            # widely used
    leverage_cut = max(1, int(0.15 * total_entries))  # rarely used

    chalk_face = []
    leverage_paid = []
    for name, cnt in player_to_count.items():
        pts = player_to_pts.get(name, 0.0)
        if cnt >= chalk_cut and pts <= 10.0:
            chalk_face.append((name, cnt, pts))
        if cnt <= leverage_cut and pts >= 20.0:
            leverage_paid.append((name, cnt, pts))

    chalk_face.sort(key=lambda x: (-x[1], x[2], x[0]))          # most-owned flops first
    leverage_paid.sort(key=lambda x: (x[1], -x[2], x[0]))       # least-owned smashes first

    pb = ProseBuilder(tone)
    pieces = []
    if chalk_face:
        nm, cnt, pts = chalk_face[0]
        pieces.append(pb.sentence(f"**Chalk that face-planted:** {nm} showed up everywhere and gave back just **{_fmt2(pts)}**"))
    if leverage_paid:
        nm, cnt, pts = leverage_paid[0]
        pieces.append(pb.sentence(f"**Leverage that paid:** {nm} was a quiet click that cashed for **{_fmt2(pts)}**"))
    if not pieces:
        return "Chalk behaved and the leverage was tame."
    return " ".join(pieces)

def chalk_leverage_roast(tone: Tone) -> str:
    if tone.name == "mild":
        return "Ownership told a familiar story."
    return f"{tone.emojis['dart']} Fading the brochure is still a strategy."

# ===================
# One-liners per team (Around the League)
# ===================

def around_the_league_lines(franchise_names: Dict[str,str], scores_info: Dict[str,Any], week: int, tone: Tone, n: int = 7) -> List[str]:
    """
    Rotate teams weekly: deterministic slice based on week index.
    Produce one sentence per selected team.
    """
    rows = scores_info.get("rows") or []
    if not rows: return []
    # Build list [(team_name, pts)]
    ordered = rows[:]  # list of (name, pts)
    # rotate by week so different teams get a line
    if week and len(ordered) > 0:
        k = (week - 1) % len(ordered)
        ordered = ordered[k:] + ordered[:k]
    picks = ordered[:max(1, min(n, len(ordered)))]
    pb = ProseBuilder(tone)
    out = []
    for name, pts in picks:
        if pts >= 100:
            line = pb.sentence(f"{name} didn’t just clear the bar—they raised it to **{_fmt2(pts)}**")
        elif pts >= 90:
            line = pb.sentence(f"{name} kept the speakers loud at **{_fmt2(pts)}**")
        elif pts >= 80:
            line = pb.sentence(f"{name} stayed on the floor at **{_fmt2(pts)}**")
        else:
            line = pb.sentence(f"{name} paid cover and stared at **{_fmt2(pts)}**")
        out.append(line)
    return out
