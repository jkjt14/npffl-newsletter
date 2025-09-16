"""CLI entry point for the Barstool-style NPFFL newsletter."""
from __future__ import annotations

import argparse
import datetime as _dt
import tempfile
from pathlib import Path
from typing import Any, Dict, Tuple

from jinja2 import Environment, FileSystemLoader, select_autoescape

from transform.insult_bank import PHRASE_BANK
from transform.league_narratives import WeekBundle, build_league_narrative
from transform.phrase_cycler import PhraseCycler


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the NPFFL roast newsletter")
    parser.add_argument("--config", default="config.yaml", help="Path to configuration file")
    parser.add_argument("--week", type=int, default=None, help="Week to process (default: from config)")
    parser.add_argument("--out-dir", default="build", help="Directory for rendered output")
    parser.add_argument(
        "--season",
        type=int,
        default=_dt.date.today().year,
        help="Season year for phrase tracking",
    )
    parser.add_argument(
        "--state-dir",
        default="state",
        help="Directory for persistent phrase selection state",
    )
    return parser.parse_args()


def _load_config(path: str | Path) -> Dict[str, Any]:
    from src.main import _read_config

    return _read_config(path)


def _derive_week(cfg: Dict[str, Any], explicit: int | None) -> int:
    if explicit is not None:
        return int(explicit)
    week = cfg.get("week")
    return int(week or 1)


def _capture_payload(cfg: Dict[str, Any], week: int) -> Dict[str, Any]:
    from src import main as legacy_main
    from src import newsletter as legacy_newsletter

    captured: Dict[str, Any] = {}

    original_render = legacy_newsletter.render_newsletter

    def _capture(payload: Dict[str, Any], output_dir: str, wk: int) -> Dict[str, str]:
        nonlocal captured
        captured = dict(payload)
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        placeholder_md = out_path / "legacy_placeholder.md"
        placeholder_html = out_path / "legacy_placeholder.html"
        placeholder_md.write_text("", encoding="utf-8")
        placeholder_html.write_text("", encoding="utf-8")
        return {"md_path": str(placeholder_md), "html_path": str(placeholder_html)}

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            legacy_newsletter.render_newsletter = _capture
            legacy_main.generate_newsletter(cfg, week, Path(tmpdir))
        finally:
            legacy_newsletter.render_newsletter = original_render

    if not captured:
        raise RuntimeError("Failed to capture league payload from ingestion")
    return captured


def _render_templates(bundle: WeekBundle, narrative: Dict[str, Any], out_dir: Path) -> Tuple[Path, Path]:
    template_dir = Path(__file__).resolve().parents[1] / "render" / "templates"
    env = Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    context = {"bundle": bundle, "narrative": narrative}
    html = env.get_template("newsletter.html.j2").render(context)
    text = env.get_template("newsletter.txt.j2").render(context)

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"npffl_week_{bundle.week_label}_newsletter.html"
    text_path = out_dir / f"npffl_week_{bundle.week_label}_newsletter.txt"
    html_path.write_text(html, encoding="utf-8")
    text_path.write_text(text, encoding="utf-8")
    return html_path, text_path


def main() -> Tuple[Path, Path]:
    args = _parse_args()
    cfg = _load_config(args.config)
    week = _derive_week(cfg, args.week)

    payload = _capture_payload(cfg, week)

    bundle = WeekBundle.from_payload(payload, season=args.season, week=week)
    cycler = PhraseCycler(PHRASE_BANK, season=args.season, state_dir=args.state_dir)
    narrative = build_league_narrative(bundle, cycler)

    html_path, text_path = _render_templates(bundle, narrative, Path(args.out_dir))
    print(f"[newsletter] HTML written to {html_path}")
    print(f"[newsletter] Text written to {text_path}")
    print(f"[newsletter] Phrase state persisted at {cycler.state_path}")
    return html_path, text_path


if __name__ == "__main__":
    main()
