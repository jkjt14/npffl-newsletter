from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional
from .phrase_cycler import PhraseCycler
from .insult_bank import BANK, team_slug

@dataclass
class Narrative:
    quick_hits: List[str]
    dumpster_fire: Optional[Dict]
    fraud_watch: Optional[Dict]
    vp_crime_scene: Optional[Dict]
    talk_spotlight: Optional[Dict]
    value_hits: List[Dict]
    chalk_busts: List[Dict]

def _tier(points: float) -> str:
    if points < 70: return "df_sub70"
    if points < 80: return "df_70s"
    if points < 90: return "df_80s"
    return "generic"

def _group_by(items: List[Dict], key: str) -> Dict[str, List[Dict]]:
    out: Dict[str, List[Dict]] = {}
    for it in items or []:
        out.setdefault(str(it.get(key)), []).append(it)
    return out

def build_narratives(week: Dict, *, season: int, state_dir: str = "state") -> Narrative:
    teams = {t["team_id"]: t["name"] for t in week["teams"]}
    scores = week["scores"]
    cycler = PhraseCycler(BANK, season=season, state_dir=state_dir)

    # Quick hits
    top = max(scores, key=lambda s: s["points"])
    worst = min(scores, key=lambda s: s["points"])
    avg = sum(s["points"] for s in scores)/len(scores)
    quick_hits = [
        f'{teams[top["team_id"]]} led at {top["points"]:.2f} (avg {avg:.2f}).',
        f'{teams[worst["team_id"]]} brought up the rear at {worst["points"]:.2f}.'
    ]

    # Dumpster Fire with team-name pun + tier line
    slug_worst = team_slug(teams[worst["team_id"]])
    pun_df = cycler.next(f"name:{slug_worst}", worst["team_id"], fallback=("generic",))
    tier_line = cycler.next(_tier(worst["points"]), worst["team_id"], fallback=("generic",))
    dumpster_fire = {
        "name": teams[worst["team_id"]],
        "points": worst["points"],
        "line": f"{pun_df} {tier_line}"
    }

    # Fraud Watch: top-half team with bottom-5 proj_next_week
    fraud = None
    half = len(scores)//2
    top_half = sorted(scores, key=lambda s: s["points"], reverse=True)[:half]
    if any(s.get("proj_next_week") is not None for s in scores):
        cand = sorted(scores, key=lambda s: (s.get("proj_next_week") is None, s.get("proj_next_week") or 9e9))[:5]
        pool = [s for s in top_half if s in cand]
        if pool:
            s = pool[0]
            slug_fw = team_slug(teams[s["team_id"]])
            fraud = {
                "name": teams[s["team_id"]],
                "proj_next_week": s["proj_next_week"],
                "line": f'{cycler.next(f"name:{slug_fw}", s["team_id"], fallback=("generic",))} '
                        f'{cycler.next("fraud", s["team_id"], fallback=("generic",))}'
            }

    # VP Crime Scene: closest miss of 2.5 VP
    victim = None
    misses = [v for v in week.get("vp_table", []) if not v.get("got_2p5")]
    if misses:
        m = min(misses, key=lambda v: abs(v["vp_cutoff_diff"]))
        slug_v = team_slug(teams[m["team_id"]])
        victim = {
            "name": teams[m["team_id"]],
            "diff": abs(m["vp_cutoff_diff"]),
            "line": f'{cycler.next(f"name:{slug_v}", m["team_id"], fallback=("generic",))} '
                    f'{cycler.next("vp_crime", m["team_id"], fallback=("generic",))}'
        }

    # Spotlight: team with ≥1 chalk bust and worst salary/points ratio
    chalk_by_team = _group_by(week.get("chalk_busts", []), key="team_id")
    value_ratio = sorted(scores, key=lambda s: (s.get("salary_spent") or 1)/max(s["points"], 0.01), reverse=True)
    spotlight = None
    for s in value_ratio:
        busts = chalk_by_team.get(s["team_id"])
        if busts:
            slug_sp = team_slug(teams[s["team_id"]])
            q = cycler.next("quotes", s["team_id"], fallback=("generic",))
            spotlight = {
                "name": teams[s["team_id"]],
                "busts": [{"player": b["player"], "pts": b["points"]} for b in busts[:3]],
                "quote": q,
                "tag": f'{cycler.next(f"name:{slug_sp}", s["team_id"], fallback=("generic",))} '
                       f'{cycler.next("chalk_bust", s["team_id"], fallback=("generic",))}'
            }
            break

    return Narrative(
        quick_hits=quick_hits,
        dumpster_fire=dumpster_fire,
        fraud_watch=fraud,
        vp_crime_scene=victim,
        talk_spotlight=spotlight,
        value_hits=sorted(week.get("value_hits", []), key=lambda x: x["points"], reverse=True)[:3],
        chalk_busts=sorted(week.get("chalk_busts", []), key=lambda x: x["points"])[:3],
    )
