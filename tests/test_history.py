import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.history import build_season_rankings, update_history


def test_weekly_ppk_and_rates():
    history = {"teams": {}, "meta": {}}
    names = {"0001": "Alpha"}

    update_history(
        history,
        year=2024,
        week=1,
        franchise_names=names,
        weekly_scores=[("0001", 120.0)],
        team_efficiency=[{"id": "0001", "total_sal": 40000}],
    )

    update_history(
        history,
        year=2024,
        week=2,
        franchise_names=names,
        weekly_scores=[("0001", 60.0)],
        team_efficiency=[{"id": "0001", "total_sal": 60000}],
    )

    weeks = history["teams"]["0001"]["weeks"]
    week1 = next(w for w in weeks if w["week"] == 1)
    week2 = next(w for w in weeks if w["week"] == 2)

    assert week1["ppk"] == pytest.approx(3.0)
    assert week2["ppk"] == pytest.approx(1.0)

    season_rows = build_season_rankings(history)
    assert season_rows

    row = season_rows[0]
    assert row["boom_rate"] == pytest.approx(0.5)
    assert row["bust_rate"] == pytest.approx(0.5)
    assert row["rank"] == 1
