from __future__ import annotations
from typing import Any, Dict, List, Tuple
import math
import statistics


def _fmt2(x: float | int | None, default="0.00") -> str:
    if x is None:
        return default
    try:
        f = float(x)
        return f"{f:.2f}"
    except Exception:
        return default


# ---------- Core Roasts (DFS tone) ----------

def opener_blurb(scores_info: Dict[str, Any]) -> str:
    rows = scores_info.get("rows") or []
    if not rows:
        return ""
    top = rows[0]
    bottom = rows[-1]
    mid_msg = ""
    if len(rows) >= 4:
        # measure congestion around the median
        scores = [s for _, s in rows]
        med = statistics.median(scores)
        span = max(scores) - min(scores)
        tight = span <= 20
        if tight:
            mid_msg = " The middle was a mosh pit—every lineup point mattered."
        else:
            mid_msg = f" The middle was chaos around {med:.2f}."
    return (f"**{top[0]}** blasted off with **{top[1]:.2f}**, while **{bottom[0]}** "
            f"brought a sleep mask and hit **{bottom[1]:.2f}**.{mid_msg}")


def vp_drama_blurb(vp_drama: Dict[str, Any]) -> str:
    if not vp_drama:
        return ""
    villain = vp_drama.get("villain")
    bubble = vp_drama.get("bubble")
    gap = vp_drama.get("gap_pf")
    return (f"**League Villain:** {villain} grabbed the last chair in the 2.5 VP lounge "
            f"and locked the door. **{bubble}** missed by **{_fmt2(gap)}** PF. Brutal.")


def headliners_blurb(headliners: List[Dict[str, Any]]) -> str:
    if not headliners:
        return ""
    bits = []
    for h in headliners[:5]:
        nm = h.get("player") or "Unknown"
        pts = _fmt2(h.get("pts"))
        mgrs = ", ".join(h.get("managers", []))
        bits.append(f"{nm} dropped **{pts}** ({mgrs})")
    return " ; ".join(bits) + "."


def confidence_blurb(conf_rows: List[Dict[str, Any]], boring_pick: str | None = None, bold_pick: str | None = None) -> str:
    if not conf_rows:
        return ""
    pieces = []
    if bold_pick:
        pieces.append(f"**Boldest Pick:** {bold_pick}")
    if boring_pick:
        pieces.append(f"**Boring Pick:** {boring_pick} (safety blanket energy)")
    if not pieces:
        return "Confidence game is on—top stacks loaded up high."
    return " — ".join(pieces) + "."


def survivor_blurb(survivor_rows: List[Dict[str, Any]], lifeline: str | None = None, consensus: str | None = None, no_picks: List[str] | None = None) -> str:
    if not survivor_rows and not (lifeline or consensus or no_picks):
        return ""
    pieces = []
    if lifeline:
        pieces.append(f"**Boldest Lifeline:** {lifeline}")
    if consensus:
        pieces.append(f"**Boring Consensus:** {consensus}")
    if no_picks:
        pieces.append(f"**No-Pick Parade:** {', '.join(no_picks)}")
    return " — ".join(pieces) + "."


def dumpster_division_blurb(standings_rows: List[Dict[str, Any]]) -> str:
    if not standings_rows:
        return ""
    n = len(standings_rows)
    k = max(1, n // 3)  # bottom third
    cellar = standings_rows[-k:]
    names = ", ".join(r["name"] for r in cellar)
    return f"**Dumpster Division:** {names}. Someone call the custodial crew."


def fraud_watch_blurb(team_efficiency: List[Dict[str, Any]]) -> str:
    """Find a team with decent points but weak Pts/$1K (ppk)."""
    if not team_efficiency:
        return ""
    # compute ppk; pick top points among bottom quartile ppk
    rows = []
    for r in team_efficiency:
        pts = float(r.get("total_pts") or 0.0)
        sal = float(r.get("total_sal") or 0.0)
        ppk = (pts / (sal/1000)) if sal > 0 else 0.0
        rows.append({"name": r.get("name",""), "pts": pts, "ppk": ppk})
    if not rows:
        return ""
    ppk_vals = sorted(x["ppk"] for x in rows)
    if not ppk_vals:
        return ""
    q1 = ppk_vals[max(0, (len(ppk_vals)//4)-1)]
    candidates = [x for x in rows if x["ppk"] <= q1]
    if not candidates:
        return ""
    fraud = max(candidates, key=lambda x: x["pts"])
    return (f"🔥 **Fraud Watch:** {fraud['name']} posted **{fraud['pts']:.2f}** but lit salary on fire. "
            f"Efficiency: **{fraud['ppk']:.2f} pts/$1K**. Looks rich, spends dumb.")


def fantasy_jail_blurb(starters_index: Dict[str, List[Dict[str, Any]]] | None, f_map: Dict[str,str] | None) -> str:
    """
    If we have starters with 0.0 pts, put those managers in 'Fantasy Jail'.
    If starters aren't provided in payload, return "" (safe no-op).
    """
    if not starters_index or not f_map:
        return ""
    offenders = []
    for fid, rows in starters_index.items():
        zeroes = [r for r in rows if float(r.get("pts") or 0.0) == 0.0 and (r.get("player_id") or "") != ""]
        if zeroes:
            offenders.append((f_map.get(fid, fid), len(zeroes)))
    if not offenders:
        return ""
    offenders.sort(key=lambda t: -t[1])
    name, cnt = offenders[0]
    extra = ", ".join(f"{n}({c})" for n,c in offenders[1:3])
    msg = f"🚔 **Fantasy Jail:** {name} started {cnt} goose-egg slot{'s' if cnt!=1 else ''}."
    if extra:
        msg += f" Parole lineup check for {extra}."
    return msg


def trophies_blurb(scores_info: Dict[str, Any]) -> Dict[str, str]:
    rows = scores_info.get("rows") or []
    if not rows:
        return {}
    return {
        "banana": f"🏆 **Banana Peel:** {rows[0][0]} stacked the biggest numbers.",
        "trombone": f"😬 **Walk of Shame:** {rows[-1][0]} tripped over the lowest score."
    }
