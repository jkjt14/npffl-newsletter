from __future__ import annotations
from typing import Any, Dict, List, Tuple
import statistics
import random

# ---------- helpers ----------

def _fmt2(x: float | int | None, default="0.00") -> str:
    if x is None:
        return default
    try:
        f = float(x)
        return f"{f:.2f}"
    except Exception:
        return default

def _pick(seq: List[str]) -> str:
    return random.choice(seq) if seq else ""

# ---------- core roasts (DFS tone, no pp$ shown) ----------

def opener(scores: Dict[str, Any]) -> str:
    rows = scores.get("rows") or []
    if not rows:
        return ""
    top = rows[0]; bot = rows[-1]
    line = [
        f"**{top[0]}** lit the slate with **{top[1]:.2f}**.",
        f"**{bot[0]}**? Paid the cover charge and watched from the parking lot (**{bot[1]:.2f}**).",
    ]
    # crowding
    if len(rows) > 6:
        sc = [s for _, s in rows]
        med = statistics.median(sc); span = max(sc) - min(sc)
        if span <= 20:
            line.append("The middle was a mosh pit—one bench swap changes everything.")
        else:
            line.append(f"Chaos swirled around **{med:.2f}**—stack or be stacked.")
    return " ".join(line)

def weekly_wrap(scores: Dict[str, Any]) -> str:
    rows = scores.get("rows") or []
    if not rows:
        return ""
    names = [r[0] for r in rows]
    mid = len(rows)//2
    midpack = ", ".join(names[max(0, mid-2):mid+1])
    leaders = ", ".join(names[:3])
    laggers = ", ".join(names[-3:])
    return (f"Leaders: **{leaders}**. Middle pack clinging together: {midpack}. "
            f"Down bad: {laggers}. Tight slate, tighter nerves.")

def vp_drama_blurb(vp: Dict[str, Any]) -> str:
    if not vp:
        return ""
    return (f"**League Villain:** {vp['villain']} slammed the door on the 2.5 VP lounge; "
            f"{vp['bubble']} missed by **{_fmt2(vp['gap_pf'])}** PF. Bring tissues.")

def headliners_blurb(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    verbs = ["torch", "cook", "punish", "detonate", "style on", "baptize", "smoke"]
    bits = []
    for h in rows[:6]:
        v = _pick(verbs)
        mgrs = ", ".join(h.get("managers", []))
        who = h.get("player") or "Somebody"
        pts = _fmt2(h.get("pts"))
        pos = h.get("pos") or ""
        team = h.get("team") or ""
        # spice up with position/team in parens when present
        tail = f" ({pos} {team})" if (pos or team) else ""
        bits.append(f"{who}{tail} {v}ed the slate for **{pts}** ({mgrs})")
    return " • ".join(bits) + "."

def values_blurb(values: List[Dict[str, Any]]) -> str:
    if not values:
        return "No heists this week—chalk lineups everywhere."
    top = values[:5]
    names = ", ".join(v.get("player","Unknown") for v in top)
    return (f"**Biggest Steals:** {names}. Budget ballers turned into headline numbers. "
            f"If you missed those tags, that’s an expensive nap.")

def busts_blurb(busts: List[Dict[str, Any]]) -> str:
    if not busts:
        return "No overpriced misfires… for once. Don’t get comfy."
    top = busts[:5]
    names = ", ".join(v.get("player","Unknown") for v in top)
    return (f"**Overpriced Misfires:** {names}. Premium spend, bargain-bin returns. "
            f"That sound you hear is salary lighting itself on fire.")

def power_ranks_blurb(eff: List[Dict[str, Any]]) -> str:
    if not eff:
        return "Efficiency board refused to cooperate; everyone vibe-checked equally mid."
    # rank by internal ppk (not shown)
    rows = []
    for r in eff:
        pts = float(r.get("total_pts") or 0.0)
        sal = float(r.get("total_sal") or 0.0)
        ppk = (pts / (sal/1000)) if sal > 0 else 0.0
        rows.append((ppk, r.get("name","")))
    rows.sort(reverse=True)
    leaders = ", ".join(x[1] for x in rows[:5])
    laggers = ", ".join(x[1] for x in rows[-3:])
    return (f"**Power Vibes:** {leaders} ran cleaner builds than the room. "
            f"Meanwhile {laggers} were busy donating rake.")

def confidence_blurb(summary: Dict[str, Any], no_picks: List[str]) -> str:
    parts = []
    if summary.get("boldest_pick"):
        parts.append(f"**Boldest Pick:** {summary['boldest_pick']} (Vegas hated it; they didn’t).")
    if summary.get("boring_pick"):
        parts.append(f"**Boring Pick:** {summary['boring_pick']} (everyone’s comfort blanket).")
    if no_picks:
        parts.append(f"**No-Pick Parade:** {', '.join(no_picks)} — did your internet go out?")
    return " — ".join(parts) + ("." if parts else "")

def survivor_blurb(summary: Dict[str, Any], no_picks: List[str]) -> str:
    parts = []
    if summary.get("boldest_lifeline"):
        parts.append(f"**Boldest Lifeline:** {summary['boldest_lifeline']} (walking the tightrope).")
    if summary.get("boring_consensus"):
        parts.append(f"**Boring Consensus:** {summary['boring_consensus']} (training wheels).")
    if no_picks:
        parts.append(f"**No-Pick Parade:** {', '.join(no_picks)} — auto-fade of the week.")
    return " — ".join(parts) + ("." if parts else "")

def dumpster_division_blurb(standings: List[Dict[str, Any]]) -> str:
    if not standings:
        return ""
    n = len(standings); k = max(1, n//3)
    names = ", ".join(r["name"] for r in standings[-k:])
    return f"**Dumpster Division:** {names}. Someone please call housekeeping."

def fraud_watch_blurb(eff: List[Dict[str, Any]]) -> str:
    if not eff:
        return ""
    # decent pts with low internal ppk
    rows = []
    for r in eff:
        pts = float(r.get("total_pts") or 0.0)
        sal = float(r.get("total_sal") or 0.0)
        ppk = (pts / (sal/1000)) if sal > 0 else 0.0
        rows.append({"name": r.get("name",""), "pts": pts, "ppk": ppk})
    if not rows:
        return ""
    rows.sort(key=lambda x: (x["ppk"], -x["pts"]))
    fraud = rows[0]
    return (f"🔥 **Fraud Watch:** {fraud['name']} put up **{_fmt2(fraud['pts'])}** with a money bonfire. "
            "DFS accountant says: charged off as a loss.")

def fantasy_jail_blurb(starters: Dict[str, List[Dict[str, Any]]] | None, f_map: Dict[str,str] | None) -> str:
    if not starters or not f_map:
        return ""
    offenders = []
    for fid, rows in starters.items():
        zeroes = [r for r in rows if float(r.get("pts") or 0.0) == 0.0 and (r.get("player_id") or "") != ""]
        if zeroes:
            offenders.append((f_map.get(fid, fid), len(zeroes)))
    if not offenders:
        return ""
    offenders.sort(key=lambda t: -t[1])
    name, cnt = offenders[0]
    return f"🚔 **Fantasy Jail:** {name} started {cnt} goose-egg slot{'s' if cnt!=1 else ''}. Community service: lineup locks 101."
