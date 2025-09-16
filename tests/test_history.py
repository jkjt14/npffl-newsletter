import sys
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.history import update_history, build_season_rankings


def test_cap_pct_stored_and_averaged():
    history = {"meta": {}, "teams": {}}
    franchise_names = {"0001": "Alpha"}

    update_history(
        history,
        year=2025,
        week=1,
        franchise_names=franchise_names,
        weekly_scores=[("0001", 120.0)],
        team_efficiency=[{"id": "0001", "franchise_id": "0001", "total_sal": 40000}],
        salary_cap=50000,
    )

    week_rows = history["teams"]["0001"]["weeks"]
    assert len(week_rows) == 1
    assert week_rows[0]["cap_pct"] == pytest.approx(0.8)

    update_history(
        history,
        year=2025,
        week=2,
        franchise_names=franchise_names,
        weekly_scores=[("0001", 110.0)],
        team_efficiency=[{"id": "0001", "franchise_id": "0001", "total_sal": 45000}],
        salary_cap=50000,
    )

    weeks = sorted(history["teams"]["0001"]["weeks"], key=lambda w: w["week"])
    assert weeks[1]["cap_pct"] == pytest.approx(0.9)

    rankings = build_season_rankings(history)
    assert rankings, "season rankings should include the team"
    assert rankings[0]["avg_cap_pct"] == pytest.approx(0.85)
    assert history["meta"]["salary_cap"] == pytest.approx(50000.0)
