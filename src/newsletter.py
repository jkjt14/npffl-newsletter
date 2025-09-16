from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape

from transform.insult_bank import PHRASE_BANK
from transform.league_narratives import WeekBundle, build_league_narrative
from transform.phrase_cycler import PhraseCycler


def _resolve_season(payload: Dict[str, Any]) -> int:
    raw = payload.get("year") or payload.get("season")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return _dt.date.today().year


def _resolve_state_dir(payload: Dict[str, Any]) -> Path:
    cfg = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    state_hints = [
        payload.get("state_dir"),
        cfg.get("state_dir") if isinstance(cfg, dict) else None,
    ]
    state_cfg = cfg.get("state") if isinstance(cfg, dict) else None
    if isinstance(state_cfg, dict):
        state_hints.extend([state_cfg.get("dir"), state_cfg.get("path")])
    for hint in state_hints:
        if not hint:
            continue
        path = Path(str(hint)).expanduser()
        if str(path):
            return path
    return Path("state")


def _build_environment() -> Environment:
    template_dir = Path(__file__).resolve().parents[1] / "render" / "templates"
    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_newsletter(payload: Dict[str, Any], output_dir: str, week: int) -> Dict[str, str]:
    """Render the NPFFL newsletter using the roast narrative engine."""

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    season = _resolve_season(payload)
    bundle = WeekBundle.from_payload(payload, season=season, week=week)

    state_dir = _resolve_state_dir(payload)
    cycler = PhraseCycler(PHRASE_BANK, season=season, state_dir=state_dir)
    narrative = build_league_narrative(bundle, cycler)

    env = _build_environment()
    context = {"bundle": bundle, "narrative": narrative}

    html = env.get_template("newsletter.html.j2").render(context)
    text = env.get_template("newsletter.txt.j2").render(context)

    html_path = out_dir / f"npffl_week_{bundle.week_label}_newsletter.html"
    md_path = out_dir / f"npffl_week_{bundle.week_label}_newsletter.md"

    html_path.write_text(html, encoding="utf-8")
    md_path.write_text(text, encoding="utf-8")

    print(f"[newsletter] Wrote markdown: {md_path}")
    print(f"[newsletter] Wrote HTML:     {html_path}")
    print(f"[newsletter] Phrase state:   {cycler.state_path}")

    return {"md_path": str(md_path), "html_path": str(html_path)}


__all__ = ["render_newsletter"]
