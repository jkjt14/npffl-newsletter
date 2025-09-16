import argparse, pathlib, json
from jinja2 import Environment, FileSystemLoader, select_autoescape
from transform.league_narratives import build_narratives

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", default="sample_week.json")
    ap.add_argument("--season", type=int)
    ap.add_argument("--state-dir", default="state")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()

    wk = json.loads(pathlib.Path(args.bundle).read_text(encoding="utf-8"))
    season = args.season or wk.get("season") or 2025

    nar = build_narratives(wk, season=season, state_dir=args.state_dir)

    env = Environment(
        loader=FileSystemLoader("render/templates"),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True, lstrip_blocks=True,
    )
    ctx = {
        "week": {"week": wk["week"], "timezone": wk["timezone"], "drop_time_et": wk["drop_time_et"]},
        "scores": wk["scores"],
        "teams_by_id": {t["team_id"]: t["name"] for t in wk["teams"]},
        "nar": nar,
    }

    out = pathlib.Path(args.out); out.mkdir(parents=True, exist_ok=True)
    (out/"newsletter.html").write_text(env.get_template("newsletter.html.j2").render(**ctx), encoding="utf-8")
    (out/"newsletter.txt").write_text(env.get_template("newsletter.txt.j2").render(**ctx), encoding="utf-8")

if __name__ == "__main__":
    main()
