"""Deterministic phrase selection with persistent state."""
from __future__ import annotations

import json
import random
from collections.abc import MutableMapping
from pathlib import Path
from typing import Dict, List, Optional

PhraseBank = MutableMapping[str, List[str]]


def _normalize_team_id(team_id: str | int | None) -> str:
    raw = "" if team_id is None else str(team_id).strip()
    if raw.isdigit() and len(raw) <= 4:
        return raw.zfill(4)
    return raw or "GLOBAL"


def _build_seed(season: str, team_id: str, category: str) -> str:
    return f"{season}:{team_id}:{category}"


class PhraseCycler:
    """Cycle through phrases without repeating them within a season."""

    def __init__(
        self,
        bank: PhraseBank,
        *,
        season: int | str,
        state_dir: str | Path = "state",
        fallback_category: str = "generic",
        state_filename: str = "phrase_state.json",
    ) -> None:
        if not isinstance(bank, MutableMapping):
            raise TypeError("bank must be a mapping")
        self._bank = {key: list(values) for key, values in bank.items()}
        self._season = str(season)
        self._fallback = fallback_category
        if self._fallback not in self._bank:
            raise ValueError(f"Fallback category '{fallback_category}' missing from phrase bank")
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = self._state_dir / state_filename
        self._state = self._load_state()

    # ------------------------------ persistence ------------------------------
    def _load_state(self) -> Dict[str, Dict[str, Dict[str, Dict[str, List[int]]]]]:
        if not self._state_path.exists():
            return {"seasons": {}}
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"seasons": {}}
        if not isinstance(data, dict):
            return {"seasons": {}}
        data.setdefault("seasons", {})
        return data

    def _save_state(self) -> None:
        tmp_path = self._state_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self._state, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(self._state_path)

    # ------------------------------ helpers ------------------------------
    def _season_bucket(self) -> Dict[str, Dict[str, Dict[str, List[int]]]]:
        seasons = self._state.setdefault("seasons", {})
        bucket = seasons.setdefault(self._season, {})
        return bucket

    def _category_bucket(self, category: str) -> Dict[str, Dict[str, List[int]]]:
        season_bucket = self._season_bucket()
        return season_bucket.setdefault(category, {})

    def _ensure_entry(self, category: str, team_id: str) -> Optional[Dict[str, List[int] | int]]:
        phrases = self._bank.get(category, [])
        if not phrases:
            return None
        cat_bucket = self._category_bucket(category)
        entry = cat_bucket.get(team_id)
        total = len(phrases)
        seed = _build_seed(self._season, team_id, category)
        if entry is None:
            order = list(range(total))
            rng = random.Random(seed)
            rng.shuffle(order)
            entry = {"order": order, "index": 0}
            cat_bucket[team_id] = entry
            return entry
        order = [i for i in (entry.get("order") or []) if isinstance(i, int) and 0 <= i < total]
        if len(order) != total:
            rng = random.Random(seed)
            shuffled = list(range(total))
            rng.shuffle(shuffled)
            extended = order + [i for i in shuffled if i not in order]
            order = extended
        entry["order"] = order
        index = entry.get("index")
        if not isinstance(index, int) or index < 0:
            entry["index"] = 0
        elif index > len(order):
            entry["index"] = len(order)
        return entry

    def _pull(self, category: str, team_id: str) -> Optional[str]:
        entry = self._ensure_entry(category, team_id)
        if not entry:
            return None
        order = entry.get("order") or []
        index = entry.get("index", 0)
        if not isinstance(index, int):
            index = 0
        if index >= len(order):
            return None
        phrase_index = order[index]
        phrases = self._bank.get(category, [])
        if phrase_index >= len(phrases):
            return None
        phrase = phrases[phrase_index]
        entry["index"] = index + 1
        return phrase

    # ------------------------------ public API ------------------------------
    def pick(self, category: str, team_id: str | int | None) -> str:
        team_key = _normalize_team_id(team_id)
        phrase = self._pull(category, team_key)
        if phrase is not None:
            self._save_state()
            return phrase
        if category != self._fallback:
            fallback = self._pull(self._fallback, team_key)
            if fallback is not None:
                self._save_state()
                return fallback
        raise ValueError(f"No phrases remaining for category '{category}' (team {team_key})")

    def reset_category(self, category: str, team_id: str | int | None) -> None:
        """Reset phrase progress for testing or manual overrides."""
        team_key = _normalize_team_id(team_id)
        cat_bucket = self._category_bucket(category)
        if team_key in cat_bucket:
            del cat_bucket[team_key]
            self._save_state()

    @property
    def season(self) -> str:
        return self._season

    @property
    def state_path(self) -> Path:
        return self._state_path

__all__ = ["PhraseCycler"]
