from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path

def render_newsletter(context: dict, out_dir: str, week: int):
    env = Environment(
        loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
        autoescape=select_autoescape(enabled_extensions=("html",))
    )
    tpl = env.get_template("newsletter.md.j2")
    md = tpl.render(**context)
    outp = Path(out_dir)
    outp.mkdir(parents=True, exist_ok=True)
    md_path = outp / f"NPFFL_Week_{week:02d}.md"
    md_path.write_text(md, encoding="utf-8")
    return str(md_path)
