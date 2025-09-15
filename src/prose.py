from __future__ import annotations
from typing import List, Dict
import random
import re

class Tone:
    def __init__(self, name: str = "spicy"):
        self.name = (name or "spicy").strip().lower()
        if self.name not in ("mild", "spicy", "inferno"):
            self.name = "spicy"

    @property
    def emojis(self) -> Dict[str, str]:
        if self.name == "mild":
            return {"fire": "", "ice": "", "dart": "", "warn": "", "boom": "", "jail": ""}
        if self.name == "inferno":
            return {"fire": "🔥", "ice": "🧊", "dart": "🎯", "warn": "🟡", "boom": "💥", "jail": "🚔"}
        return {"fire": "🔥", "ice": "🧊", "dart": "🎯", "warn": "🟡", "boom": "💥", "jail": "🚔"}

    def amp(self, text_spicy: str, text_mild: str = "") -> str:
        if self.name == "mild":
            return text_mild or re.sub(r"[!?]+", ".", text_spicy)
        return text_spicy


class ProseBuilder:
    def __init__(self, tone: Tone):
        self.tone = tone
        self.used: set[str] = set()

    def choose(self, items: List[str], unique: bool = False) -> str:
        if not items:
            return ""
        pool = [i for i in items if not unique or i not in self.used]
        pick = random.choice(pool or items)
        if unique:
            self.used.add(pick)
        return pick

    def sentence(self, *parts: str) -> str:
        text = " ".join(p.strip() for p in parts if p and p.strip())
        text = re.sub(r"\s+", " ", text).strip()
        if text and text[-1] not in ".!?…":
            text += "."
        return text

    def paragraph(self, *sentences: str) -> str:
        return " ".join(s for s in sentences if s and s.strip())
