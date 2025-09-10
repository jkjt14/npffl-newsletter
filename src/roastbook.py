from __future__ import annotations
import random

ROASTS = {
    "aggressive": [
        "spent like a drunken GM for {{name}}'s {{pos}} slot.",
        "set a lineup that would make a bye week blush.",
        "drafted vibes, benched points.",
        "needs an intervention from the waiver wire fairy.",
    ],
    "light": [
        "made a curious call at flex.",
        "trusted the process… the process trusted the bench.",
    ],
}

def roast(level: str, context: dict) -> str:
    bank = ROASTS.get(level or "aggressive") or ROASTS["aggressive"]
    tmpl = random.choice(bank)
    return tmpl.replace("{{name}}", context.get("player","")).replace("{{pos}}", context.get("pos",""))
