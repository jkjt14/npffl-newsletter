from __future__ import annotations
import json, hashlib, random
from pathlib import Path
from typing import Dict, List, Tuple

def _seed_for(season: int, team_id: str, category: str) -> int:
    s = f"{season}:{team_id}:{category}"
    return int(hashlib.sha256(s.encode()).hexdigest(), 16) % (2**31 - 1)

class PhraseCycler:
    """
    Deterministic, persistent phrase selector.
    For each (season, category, team_id), we precompute a permutation of phrase indices with a seeded RNG,
    store a 'cursor' in state, and advance it. No repeats until the bank is exhausted.
    """
    def __init__(self, bank: Dict[str, List[str]], season: int, state_dir: str = "state"):
        self.bank = bank
        self.season = int(season)
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / f"phrase_state_{self.season}.json"
        self.state: Dict[str, Dict[str, Dict[str, int]]] = self._load()

    def _load(self) -> Dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save(self) -> None:
        self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def _perm_for(self, category: str, team_id: str) -> List[int]:
        N = len(self.bank.get(category, []))
        if N == 0: return []
        rng = random.Random(_seed_for(self.season, team_id or "_", category))
        perm = list(range(N))
        rng.shuffle(perm)
        return perm

    def next(self, category: str, team_id: str = "_global", *, fallback: Tuple[str, ...] = ()) -> str:
        # try primary
        phrase = self._next_from_category(category, team_id)
        if phrase is not None:
            return phrase
        # fallbacks
        for fb in fallback:
            phrase = self._next_from_category(fb, team_id)
            if phrase is not None:
                return phrase
        # last resort: shortest from first available bank
        for cat in (category, *fallback):
            bank = self.bank.get(cat, [])
            if bank:
                s = bank[0].strip()
                return s if len(s) <= 140 else s[:137] + "…"
        return "…"

    def _next_from_category(self, category: str, team_id: str) -> str | None:
        phrases = self.bank.get(category, [])
        if not phrases:
            return None
        cat_state = self.state.setdefault(category, {})
        t_state = cat_state.setdefault(team_id or "_", {"cursor": 0})
        perm = self._perm_for(category, team_id)
        if not perm:
            return None
        cur = t_state["cursor"]
        if cur >= len(perm):
            return None  # exhausted
        idx = perm[cur]
        t_state["cursor"] = cur + 1
        self._save()
        s = phrases[idx].strip()
        return s if len(s) <= 140 else s[:137] + "…"
