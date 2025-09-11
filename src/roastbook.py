from __future__ import annotations
from typing import Any, Dict, List, Tuple
import statistics, random, re
from collections import Counter, defaultdict

# ----------------------------
# Tiny prose helpers (with tone)
# ----------------------------

class ProseBuilder:
    def __init__(self, tone: str = "spicy"):
        # tone: "mild" | "medium" | "spicy"
        self.tone = (tone or "spicy").lower()
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
    c = Counter([s.strip() for s in items if s and str(s).strip()])
    return [k for k,_ in sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))][:n]

# ----------------------------
# Weekly Results (team-first)
# ----------------------------

def weekly_results_blurb(scores: Dict[str, Any], tone: str = "spicy") -> str:
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
    mid   = pb.sentence(f"{chasers} stayed within reach as the middle jammed up")
    chaos = pb.sentence(f"The slate’s heartbeat sat between **{band_low}–{band_high}**—every slot mattered")
    return pb.paragraph(lead, mid, chaos)

# ----------------------------
# VP Drama (top-5 vs 6th + bubble)
# ----------------------------

def vp_drama_blurb(vp: Dict[str, Any], tone: str = "spicy") -> str:
    if not vp: return ""
    villain, bubble, gap = vp.get("villain"), vp.get("bubble"), vp.get("gap_pf")
    top5 = vp.get("top5") or []
    sixth = vp.get("sixth") or {}
    top_names = ", ".join(r["name"] for r in top5) if top5 else "—"
    sixth_name = sixth.get("name","—")

    pb = ProseBuilder(tone)
    a = pb.sentence(f"**League Villain:** {villain} grabbed the last 2.5 VP seat; {bubble} missed by **{_fmt2(gap)}** PF")
    b = pb.sentence(f"Up top: {top_names}. First outside the rope: **{sixth_name}**")
    c = pb.sentence("Decimal scoring turns whispers into grudges")
    return pb.paragraph(a, b, c)

# ----------------------------
# Headliners (team-centric, varied templates)
# ----------------------------

_HEAD_TEMPLATES_MILD = [
    "— **{team}** leaned on {plays}",
    "— **{team}** got lift from {plays}",
    "— **{team}** built the score with {plays}",
]
_HEAD_TEMPLATES_SPICY = [
    "— **{team}** rode {plays} and didn’t look back",
    "— **{team}** stacked {plays} and made it count",
    "— **{team}** let {plays} do the heavy lifting",
]

def headliners_blurb(rows: List[Dict[str, Any]], tone: str = "spicy") -> str:
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
    tmpls = _HEAD_TEMPLATES_SPICY if tone == "spicy" else _HEAD_TEMPLATES_MILD
    for team, plays in ordered:
        # unique players per team line to avoid duplicates
        uniq = []
        seen = set()
        for p in plays:
            name = p.split(" ", 1)[0]
            if name not in seen:
                uniq.append(p)
                seen.add(name)
            if len(uniq) == 2:
                break
        top2 = ", ".join(uniq) if uniq else ", ".join(plays[:2])
        tmpl = pb.choose(tmpls)
        lines.append(tmpl.format(team=team, plays=top2))

    closer = "Fade those names and you spend the night chasing."
    return " ".join(lines) + " " + closer

# ----------------------------
# Values / Busts (TEAM story, deduped, tone-aware)
# ----------------------------

_VAL_OPENERS_MILD = [
    "The bargain bin mattered this week:",
    "Smart tags paid off quietly:",
    "The value column did real work:",
]
_VAL_OPENERS_SPICY = [
    "The bargain bin paid out where it mattered:",
    "Sharp clicks beat loud salaries:",
    "Cheap tags, real damage:",
]
_BUST_OPENERS_MILD = [
    "Elsewhere, the premium tickets underwhelmed:",
    "On the high end, returns lagged:",
    "Some big names didn’t cash:",
]
_BUST_OPENERS_SPICY = [
    "On the other side of the ledger:",
    "The tax bracket didn’t buy points here:",
    "The pricey names left bruises:",
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

def values_blurb(values: List[Dict[str, Any]], tone: str = "spicy") -> str:
    if not values: return "No value play broke the room this time."
    pb = ProseBuilder(tone)
    opener = pb.choose(_VAL_OPENERS_SPICY if tone == "spicy" else _VAL_OPENERS_MILD)
    teams = _team_support_blurb(values, cap_players=2)
    if not teams:
        names = ", ".join(_collapse([v.get("player") for v in values], 3))
        closer = "Edges come from quiet clicks, not loud salaries." if tone == "spicy" else "Quiet picks > loud prices."
        return pb.paragraph(pb.sentence(opener, names), closer)
    leader = teams[0]
    runner = teams[1] if len(teams) > 1 else None
    lead_line = pb.sentence(f"**Biggest Heist:** {leader[0]} turned budget into scoreboard with {leader[1]}")
    if runner:
        run_line = pb.sentence(f"**Runner-up:** {runner[0]} found similar juice with {runner[1]}")
        close = pb.sentence("That’s how you buy ceiling without paying sticker")
        return pb.paragraph(opener, lead_line, run_line, close)
    close = pb.sentence("That’s how you buy ceiling without paying sticker")
    return pb.paragraph(opener, lead_line, close)

def busts_blurb(busts: List[Dict[str, Any]], tone: str = "spicy") -> str:
    if not busts: return "Premium chalk held serve—no headline busts worth circling."
    pb = ProseBuilder(tone)
    opener = pb.choose(_BUST_OPENERS_SPICY if tone == "spicy" else _BUST_OPENERS_MILD)
    teams = _team_support_blurb(busts, cap_players=2)
    if not teams:
        names = ", ".join(_collapse([b.get("player") for b in busts], 3))
        closer = "The cap hit was real; the points were not."
        return pb.paragraph(pb.sentence(opener, names), closer)
    leader = teams[0]
    runner = teams[1] if len(teams) > 1 else None
    lead_line = pb.sentence(f"**Overpriced Misfire:** {leader[0]} paid up and got little back—{leader[1]} led the regret")
    if runner:
        run_line = pb.sentence(f"**Honorable Mention:** {runner[0]} weren’t far behind on sunk cost")
        close = pb.sentence("That’s a receipt nobody frames")
        return pb.paragraph(opener, lead_line, run_line, close)
    close = pb.sentence("That’s a receipt nobody frames")
    return pb.paragraph(opener, lead_line, close)

# ----------------------------
# Power Vibes (season prose)
# ----------------------------

def power_vibes_blurb(season_rows: List[Dict[str, Any]], tone: str = "spicy") -> str:
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

# ----------------------------
# Confidence (odds-driven narrative)
# ----------------------------

def _bold_score(rank: int, prob: float) -> float:
    try:
        r = float(rank); p = float(prob)
    except Exception:
        return 0.0
    return max(0.0, r) * max(0.0, 1.0 - min(max(p, 0.0), 1.0))

def confidence_story(conf3: List[Dict[str, Any]], team_prob: Dict[str, float], no_picks: List[str], tone: str = "spicy") -> str:
    if not conf3 and not no_picks:
        return "No Confidence cards this week."
    teams = []
    upset_pick = None  # (team, code, prob, rank)
    chalk_team = None
    best_safe = -1.0
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
            parts.append(f"**🧨 Bold Board:** {', '.join(bold_names)} pushed underdogs into top slots and meant it.")
        chalk_team = max(safe_scores.items(), key=lambda kv: kv[1])[0] if safe_scores else None
        if chalk_team:
            parts.append(f"**🧱 Chalk Fortress:** {chalk_team} wrapped the top in favorites and slept fine.")
    if upset_pick:
        t, code, p, r = upset_pick
        parts.append(f"**🎫 Upset Ticket:** {t} slapped a rank-{r} on {code} ({int(round((1-p)*100))}% sweat) and got paid.")
    if no_picks:
        parts.append(f"**👻 Ghost Entries:** {', '.join(no_picks)} left their cards blank.")
    return " ".join(parts) if parts else "Everything landed in the middle—no heroes, no villains."

# ----------------------------
# Survivor (odds-driven narrative)
# ----------------------------

def survivor_story(surv: List[Dict[str, Any]], team_prob: Dict[str, float], no_picks: List[str], tone: str = "spicy") -> str:
    if not surv and not no_picks:
        return "No Survivor tickets posted."
    pieces: List[str] = []
    if surv:
        picks = [(r.get("team","Team"), str(r.get("pick","")).upper(), float(team_prob.get(str(r.get("pick","")).upper(), 0.5))) for r in surv if r.get("pick")]
        if picks:
            picks.sort(key=lambda x: x[2])
            bold = [f"{t} → {code}" for t,code,_ in picks[:2]]
            if len(picks) > 2:
                bold.append(f"{picks[2][0]} → {picks[2][1]}")
            pieces.append(f"**🪢 Boldest Lifelines:** {', '.join(bold)} — tightrope stuff, clean landing.")
            from collections import Counter
            codes = [c for _,c,_ in picks]
            common_code, _ = sorted(Counter(codes).items(), key=lambda x: (-x[1], x[0]))[0]
            pieces.append(f"**🧸 Boring Consensus:** {common_code} — training wheels engaged.")
    if no_picks:
        pieces.append(f"**🙈 No-Show Column:** {', '.join(no_picks)} skipped the booth.")
    return " ".join(pieces)

# ----------------------------
# Rotating one-liners
# ----------------------------

def fraud_watch_blurb(eff: List[Dict[str, Any]], tone: str = "spicy") -> str:
    if not eff: return ""
    rows = []
    for r in eff:
        pts = float(r.get("total_pts") or 0.0)
        sal = float(r.get("total_sal") or 0.0)
        ppk = (pts / (sal/1000)) if sal > 0 else 0.0
        rows.append({"name": r.get("name",""), "pts": pts, "ppk": ppk})
    if not rows: return ""
    rows.sort(key=lambda x: (x["ppk"], -x["pts"]))
    f = rows[0]
    emoji = "🔥" if tone != "mild" else "⚠️"
    return f"{emoji} **Fraud Watch:** {f['name']} posted **{_fmt2(f['pts'])}** with efficiency that won’t pass audit."

def fantasy_jail_blurb(starters: Dict[str, List[Dict[str, Any]]] | None, f_map: Dict[str,str] | None, tone: str = "spicy") -> str:
    if not starters or not f_map: return ""
    offenders = []
    for fid, rows in starters.items():
        zeroes = [r for r in rows if float(r.get("pts") or 0.0) == 0.0 and (r.get("player_id") or "") != ""]
        if zeroes:
            offenders.append((f_map.get(fid, fid), len(zeroes)))
    if not offenders: return ""
    offenders.sort(key=lambda t: -t[1])
    name, cnt = offenders[0]
    emoji = "🚔" if tone != "mild" else "🚧"
    return f"{emoji} **Fantasy Jail:** {name} started {cnt} goose-egg slot{'s' if cnt!=1 else ''}. Self-inflicted sweat."
