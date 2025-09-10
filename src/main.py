from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from .mfl_client import MFLClient
from .fetch_week import fetch_week_data  # must return weekly data dict
from .load_salary import load_salary_file  # must return pandas DataFrame
from .value_engine import compute_values   # returns dict with value/busts & team efficiency
from .newsletter import render_newsletter


def _read_config(path: str | Path = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _week_label(week: int | None) -> str:
    return f"{int(week):02d}" if week is not None else "01"


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _merge_franchise_names(*maps: Dict[str, str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for mp in maps:
        for k, v in (mp or {}).items():
            if k is None:
                continue
            out[str(k).zfill(4)] = str(v)
    return out


def _build_standings_rows(week_data: Dict[str, Any], f_map: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    Expected output rows: {id, name, pf, vp}
    Tries multiple shapes from fetch_week payloads.
    """
    rows: List[Dict[st]()]()
