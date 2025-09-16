"""Build weekly league narratives on top of the raw data bundle."""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Any, Dict, Iterable, List, Optional

from .phrase_cycler import PhraseCycler

def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_points(value: Any) -> str:
    val = _safe_float(value)
    if val is None:
        return "0.00"
    return f"{val:.2f}"


def _truncate(text: str, limit: int = 140) -> str:
    cleaned = " ".join(text.split()).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(0, limit - 1)].rstrip() + "…"


def _format_diff(points: Optional[float], average: Optional[float]) -> str:
    if points is None or average is None:
        return ""
    diff = points - average
    if abs(diff) < 0.05:
        return ""
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.1f} vs avg"


@dataclass
class ScoreLine:
    team_id: str
    team: str
    points: float


@dataclass
class WeekBundle:
    season: int
    week: int
    week_label: str
    title: str
    timezone: Optional[str]
    league_id: Optional[str]
    franchise_names: Dict[str, str]
    name_to_id: Dict[str, str]
    lower_name_to_id: Dict[str, str]
    standings: List[Dict[str, Any]]
    scores: List[ScoreLine]
    average_score: Optional[float]
    top_values: List[Dict[str, Any]]
    top_busts: List[Dict[str, Any]]
    team_efficiency: List[Dict[str, Any]]
    vp_drama: Dict[str, Any]
    headliners: List[Dict[str, Any]]
    confidence_rows: List[Dict[str, Any]]
    confidence_summary: Dict[str, Any]
    confidence_meta: Dict[str, Any]
    team_prob: Dict[str, float]
    survivor_rows: List[Dict[str, Any]]
    survivor_summary: Dict[str, Any]
    survivor_meta: Dict[str, Any]
    raw_payload: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------ factories ------------------------------
    @classmethod
    def from_payload(
        cls,
        payload: Dict[str, Any],
        *,
        season: Optional[int] = None,
        week: Optional[int] = None,
    ) -> "WeekBundle":
        title = str(payload.get("title") or "NPFFL Weekly Newsletter").strip()
        timezone = payload.get("timezone")
        league_id = payload.get("league_id")
        season_val = season or int(payload.get("year") or 0)
        week_label = str(payload.get("week_label") or "00").zfill(2)
        if week is None:
            try:
                week_val = int(week_label.lstrip("0") or payload.get("week") or 0)
            except (TypeError, ValueError):
                week_val = int(payload.get("week") or 0)
        else:
            week_val = int(week)

        raw_franchise = payload.get("franchise_names") or {}
        franchise_names: Dict[str, str] = {}
        for fid, name in raw_franchise.items():
            if name is None:
                continue
            fid_str = str(fid).strip()
            if fid_str.isdigit() and len(fid_str) <= 4:
                fid_key = fid_str.zfill(4)
            else:
                fid_key = fid_str or ""
            if not fid_key:
                continue
            franchise_names[fid_key] = str(name).strip()

        standings_raw = payload.get("standings_rows") or []
        standings: List[Dict[str, Any]] = []
        for row in standings_raw:
            if isinstance(row, dict):
                copy = dict(row)
                fid = copy.get("id") or copy.get("team_id")
                fid_str = str(fid or "").strip()
                if fid_str.isdigit() and len(fid_str) <= 4:
                    copy["id"] = fid_str.zfill(4)
                elif fid_str:
                    copy["id"] = fid_str
                name = copy.get("name") or copy.get("team")
                if name and copy.get("id"):
                    franchise_names.setdefault(copy["id"], str(name).strip())
                standings.append(copy)

        name_to_id = {name: fid for fid, name in franchise_names.items() if name}
        lower_name_to_id = {name.lower(): fid for name, fid in name_to_id.items()}

        scores_info = payload.get("scores_info") or {}
        score_rows: List[ScoreLine] = []
        raw_rows = scores_info.get("rows") or []
        for row in raw_rows:
            if isinstance(row, dict):
                team_name = str(row.get("team") or row.get("name") or "").strip()
                pts = _safe_float(row.get("pts") or row.get("points") or row.get("score"))
            elif isinstance(row, (list, tuple)) and len(row) >= 2:
                team_name = str(row[0]).strip()
                pts = _safe_float(row[1])
            else:
                continue
            if not team_name:
                continue
            team_id = cls._lookup_team_id(team_name, name_to_id, lower_name_to_id)
            score_rows.append(ScoreLine(team_id=team_id, team=team_name, points=pts or 0.0))

        average = _safe_float(scores_info.get("avg"))

        top_values = list(payload.get("top_values") or [])
        top_busts = list(payload.get("top_busts") or [])
        team_eff = list(payload.get("team_efficiency") or [])
        vp_drama = dict(payload.get("vp_drama") or {})
        headliners = list(payload.get("headliners") or [])
        conf_rows = list(payload.get("confidence_top3") or [])
        conf_summary = dict(payload.get("confidence_summary") or {})
        conf_meta = dict(payload.get("confidence_meta") or {})
        team_prob = {str(k): float(v) for k, v in (payload.get("team_prob") or {}).items() if _safe_float(v) is not None}
        survivor_rows = list(payload.get("survivor_list") or [])
        survivor_summary = dict(payload.get("survivor_summary") or {})
        survivor_meta = dict(payload.get("survivor_meta") or {})

        return cls(
            season=season_val,
            week=week_val,
            week_label=week_label,
            title=title,
            timezone=timezone,
            league_id=str(league_id) if league_id is not None else None,
            franchise_names=franchise_names,
            name_to_id=name_to_id,
            lower_name_to_id=lower_name_to_id,
            standings=standings,
            scores=score_rows,
            average_score=average,
            top_values=top_values,
            top_busts=top_busts,
            team_efficiency=team_eff,
            vp_drama=vp_drama,
            headliners=headliners,
            confidence_rows=conf_rows,
            confidence_summary=conf_summary,
            confidence_meta=conf_meta,
            team_prob=team_prob,
            survivor_rows=survivor_rows,
            survivor_summary=survivor_summary,
            survivor_meta=survivor_meta,
            raw_payload=dict(payload),
        )

    @staticmethod
    def _lookup_team_id(name: str, name_to_id: Dict[str, str], lower_lookup: Dict[str, str]) -> str:
        if name in name_to_id:
            return name_to_id[name]
        key = name.lower()
        if key in lower_lookup:
            return lower_lookup[key]
        return name

    # ------------------------------ helpers ------------------------------
    def resolve_team_id(self, name: Optional[str]) -> str:
        if not name:
            return "GLOBAL"
        key = name.strip()
        if not key:
            return "GLOBAL"
        if key in self.name_to_id:
            return self.name_to_id[key]
        lower = key.lower()
        if lower in self.lower_name_to_id:
            return self.lower_name_to_id[lower]
        return key

    def sorted_scores(self, reverse: bool = False) -> List[ScoreLine]:
        return sorted(self.scores, key=lambda s: s.points, reverse=reverse)


# ------------------------------ section builders ------------------------------

def _build_dumpster_fire(bundle: WeekBundle, cycler: PhraseCycler) -> Dict[str, Any]:
    ordered = bundle.sorted_scores(reverse=False)
    if not ordered:
        return {}
    tiers_config = [
        ("Five-Alarm Flames", "dumpster_fire_tier1", ordered[:1]),
        ("Active Blaze", "dumpster_fire_tier2", ordered[1:3]),
        ("Lingering Smoke", "dumpster_fire_tier3", ordered[3:6]),
    ]
    tiers: List[Dict[str, Any]] = []
    for label, category, rows in tiers_config:
        entries = []
        for row in rows:
            phrase = cycler.pick(category, row.team_id)
            diff = _format_diff(row.points, bundle.average_score)
            stats = f"{_fmt_points(row.points)} pts"
            if diff:
                stats = f"{stats} ({diff})"
            blurb = _truncate(f"{row.team} {phrase} {stats}")
            entries.append({
                "team": row.team,
                "points": row.points,
                "phrase": phrase,
                "blurb": blurb,
                "diff": diff,
            })
        if entries:
            tiers.append({"label": label, "entries": entries})
    return {"tiers": tiers, "average": bundle.average_score}


def _build_fraud_watch(bundle: WeekBundle, cycler: PhraseCycler) -> Dict[str, Any]:
    rows = bundle.standings
    if not rows:
        return {}
    pf_values = [_safe_float(r.get("pf")) for r in rows if _safe_float(r.get("pf")) is not None]
    pf_median = median(pf_values) if pf_values else None
    candidates: List[Dict[str, Any]] = []
    for row in rows:
        name = str(row.get("name") or row.get("team") or "").strip()
        pf = _safe_float(row.get("pf"))
        vp = _safe_float(row.get("vp"))
        if not name or pf is None or vp is None:
            continue
        if pf_median is not None and vp >= 2 and pf < pf_median:
            candidates.append({
                "team": name,
                "team_id": bundle.resolve_team_id(name),
                "pf": pf,
                "vp": vp,
            })
    if not candidates:
        # Fall back to lowest PF despite healthy VP totals
        rows_sorted = sorted(
            [
                {
                    "team": str(r.get("name") or r.get("team") or "").strip(),
                    "team_id": bundle.resolve_team_id(r.get("name") or r.get("team")),
                    "pf": _safe_float(r.get("pf")) or 0.0,
                    "vp": _safe_float(r.get("vp")) or 0.0,
                }
                for r in rows
                if (r.get("name") or r.get("team"))
            ],
            key=lambda item: (item["pf"], -item["vp"]),
        )
        candidates = rows_sorted[:2]
    else:
        candidates.sort(key=lambda item: (-item["vp"], item["pf"], item["team"]))

    entries = []
    for cand in candidates[:3]:
        phrase = cycler.pick("fraud_watch", cand["team_id"])
        stats = f"{cand['vp']:.1f} VP, {_fmt_points(cand['pf'])} PF"
        blurb = _truncate(f"{cand['team']} {phrase} ({stats})")
        entries.append({"team": cand["team"], "phrase": phrase, "blurb": blurb, "vp": cand["vp"], "pf": cand["pf"]})
    return {"entries": entries}


def _build_vp_crime_scene(bundle: WeekBundle, cycler: PhraseCycler) -> Dict[str, Any]:
    drama = bundle.vp_drama
    if not drama:
        return {}
    villain_name = str(drama.get("villain") or "").strip()
    bubble_name = str(drama.get("bubble") or "").strip()
    gap = _safe_float(drama.get("gap_pf"))
    villain_entry = None
    if villain_name:
        team_id = bundle.resolve_team_id(villain_name)
        phrase = cycler.pick("vp_crime_scene_villain", team_id)
        detail = f"stole {gap:.2f} PF" if gap is not None else "jacked the VP stack"
        villain_entry = {
            "team": villain_name,
            "phrase": phrase,
            "blurb": _truncate(f"{villain_name} {phrase} ({detail})"),
        }
    victim_entry = None
    if bubble_name:
        team_id = bundle.resolve_team_id(bubble_name)
        phrase = cycler.pick("vp_crime_scene_victim", team_id)
        detail = f"missed by {gap:.2f} PF" if gap is not None else "caught the heist"
        victim_entry = {
            "team": bubble_name,
            "phrase": phrase,
            "blurb": _truncate(f"{bubble_name} {phrase} ({detail})"),
        }
    top5 = drama.get("top5") or []
    return {"villain": villain_entry, "victim": victim_entry, "top5": top5}


def _find_headliner(bundle: WeekBundle, target_team: str) -> Optional[Dict[str, Any]]:
    for headliner in bundle.headliners:
        managers = headliner.get("managers") or []
        if isinstance(managers, list) and any(str(m).strip() == target_team for m in managers):
            return headliner
    return None


def _build_spotlight(bundle: WeekBundle, cycler: PhraseCycler) -> Dict[str, Any]:
    scores_desc = bundle.sorted_scores(reverse=True)
    if not scores_desc:
        return {}
    top_entry = scores_desc[0]
    bottom_entry = scores_desc[-1]
    top_phrase = cycler.pick("shit_talk_spotlight_alpha", top_entry.team_id)
    top_blurb = _truncate(f"{top_entry.team} {top_phrase} ({_fmt_points(top_entry.points)} pts)")
    bottom_phrase = cycler.pick("shit_talk_spotlight_beta", bottom_entry.team_id)
    bottom_blurb = _truncate(f"{bottom_entry.team} {bottom_phrase} ({_fmt_points(bottom_entry.points)} pts)")
    headliner_info = None
    headliner = _find_headliner(bundle, top_entry.team)
    if headliner:
        player = str(headliner.get("player") or "").strip()
        pts = _safe_float(headliner.get("pts"))
        if player:
            detail = f"{player} dropped {_fmt_points(pts)}" if pts is not None else f"{player} showed up"
            headliner_info = _truncate(detail)
    return {
        "top": {"team": top_entry.team, "phrase": top_phrase, "blurb": top_blurb, "points": top_entry.points},
        "bottom": {"team": bottom_entry.team, "phrase": bottom_phrase, "blurb": bottom_blurb, "points": bottom_entry.points},
        "headliner": headliner_info,
    }


def _extract_value_lines(rows: Iterable[Dict[str, Any]], bundle: WeekBundle, cycler: PhraseCycler, category: str) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    for row in rows:
        player = str(row.get("player") or row.get("name") or "").strip()
        managers = row.get("managers") or []
        team_name = ""
        if isinstance(managers, list) and managers:
            team_name = str(managers[0]).strip()
        elif isinstance(managers, str):
            team_name = managers.strip()
        team_id = bundle.resolve_team_id(team_name) if team_name else "GLOBAL"
        phrase = cycler.pick(category, team_id)
        pts = _safe_float(row.get("pts") or row.get("score"))
        stats = f"{_fmt_points(pts)} pts" if pts is not None else ""
        prefix = f"{team_name}: " if team_name else ""
        blurb = _truncate(f"{prefix}{player} {phrase} {stats}".strip())
        lines.append({
            "team": team_name,
            "player": player,
            "phrase": phrase,
            "blurb": blurb,
        })
        if len(lines) == 3:
            break
    return lines


def _build_value_vs_busts(bundle: WeekBundle, cycler: PhraseCycler) -> Dict[str, Any]:
    values = _extract_value_lines(bundle.top_values, bundle, cycler, "value_pop") if bundle.top_values else []
    busts = _extract_value_lines(bundle.top_busts, bundle, cycler, "value_bust") if bundle.top_busts else []
    if not values and not busts:
        return {}
    return {"values": values, "busts": busts}


def _build_pool_report(bundle: WeekBundle, cycler: PhraseCycler) -> Dict[str, Any]:
    confidence_lines: List[str] = []
    summary = bundle.confidence_summary
    boring = summary.get("boring_consensus") if isinstance(summary, dict) else None
    if boring:
        phrase = cycler.pick("confidence", f"NFL-{boring}")
        confidence_lines.append(_truncate(f"Consensus leaned {boring}. {phrase}"))
    bold = summary.get("boldest_lifeline") if isinstance(summary, dict) else None
    if bold:
        phrase = cycler.pick("confidence", f"NFL-{bold}-bold")
        confidence_lines.append(_truncate(f"Boldest dart: {bold}. {phrase}"))
    for row in bundle.confidence_rows:
        picks = row.get("top3") if isinstance(row, dict) else None
        if not picks:
            continue
        first = picks[0]
        pick_name = str(first.get("pick") or "").strip()
        rank = first.get("rank")
        team_name = str(row.get("team") or "").strip()
        if not team_name:
            continue
        phrase = cycler.pick("confidence", f"CONF-{bundle.resolve_team_id(team_name)}")
        if isinstance(rank, (int, float)):
            detail = f"rank {int(rank)}"
        else:
            detail = "top slot"
        confidence_lines.append(_truncate(f"{team_name} rode {pick_name} at {detail}. {phrase}"))
        break
    no_picks = bundle.confidence_meta.get("no_picks") if isinstance(bundle.confidence_meta, dict) else []
    if no_picks:
        for name in no_picks[:2]:
            phrase = cycler.pick("confidence", f"NO-{bundle.resolve_team_id(name)}")
            confidence_lines.append(_truncate(f"{name} ghosted the picks. {phrase}"))

    survivor_lines: List[str] = []
    surv_summary = bundle.survivor_summary
    boring_surv = surv_summary.get("boring_consensus") if isinstance(surv_summary, dict) else None
    if boring_surv:
        phrase = cycler.pick("survivor", f"NFL-{boring_surv}")
        survivor_lines.append(_truncate(f"Survivor chalk: {boring_surv}. {phrase}"))
    bold_surv = surv_summary.get("boldest_lifeline") if isinstance(surv_summary, dict) else None
    if bold_surv:
        phrase = cycler.pick("survivor", f"NFL-{bold_surv}-bold")
        survivor_lines.append(_truncate(f"Spiciest lifeline: {bold_surv}. {phrase}"))
    if bundle.survivor_rows:
        contrarian = min(
            bundle.survivor_rows,
            key=lambda row: bundle.team_prob.get(str(row.get("pick") or "").strip(), 1.0),
        )
        team_name = str(contrarian.get("team") or "").strip()
        pick = str(contrarian.get("pick") or "").strip()
        if team_name and pick:
            phrase = cycler.pick("survivor", f"SURV-{bundle.resolve_team_id(team_name)}")
            survivor_lines.append(_truncate(f"{team_name} rode {pick}. {phrase}"))
    surv_no = bundle.survivor_meta.get("no_picks") if isinstance(bundle.survivor_meta, dict) else []
    if surv_no:
        for name in surv_no[:2]:
            phrase = cycler.pick("survivor", f"NOPICK-{bundle.resolve_team_id(name)}")
            survivor_lines.append(_truncate(f"{name} skipped survivor. {phrase}"))

    return {"confidence": confidence_lines, "survivor": survivor_lines}


# ------------------------------ public interface ------------------------------

def build_league_narrative(bundle: WeekBundle, cycler: PhraseCycler) -> Dict[str, Any]:
    return {
        "dumpster_fire": _build_dumpster_fire(bundle, cycler),
        "fraud_watch": _build_fraud_watch(bundle, cycler),
        "vp_crime_scene": _build_vp_crime_scene(bundle, cycler),
        "spotlight": _build_spotlight(bundle, cycler),
        "value_vs_busts": _build_value_vs_busts(bundle, cycler),
        "pool_report": _build_pool_report(bundle, cycler),
    }


__all__ = ["WeekBundle", "build_league_narrative"]
