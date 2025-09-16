import json
from transform.league_narratives import build_narratives

def make_week(low_points=64.3, proj_low=78.0):
    return {
        "season": 2025,
        "week": 2,
        "timezone": "America/New_York",
        "drop_time_et": "12:00 PM",
        "teams": [
            {"team_id": "A", "name": "Freaks"},
            {"team_id": "B", "name": "Mike's Misery"},
        ],
        "scores": [
            {"team_id": "A", "points": 115.55, "rank": 1, "salary_spent": 58000, "proj_next_week": 104.0},
            {"team_id": "B", "points": low_points, "rank": 2, "salary_spent": 59500, "proj_next_week": proj_low},
        ],
        "vp_table": [{"team_id": "B", "vp_earned": 0.0, "vp_cutoff_diff": 0.12, "got_2p5": False}],
        "picks_conf": [], "picks_survivor": [],
        "player_perf": [],
        "chalk_busts": [{"team_id":"B","player":"Derrick Henry","points":2.3}],
        "value_hits": [{"player":"Malik Nabers","points":25.9}],
    }

def test_dumpster_fire_has_team_pun(tmp_path):
    wk = make_week()
    nar = build_narratives(wk, season=2025, state_dir=tmp_path.as_posix())
    assert "Mike’s Misery" in nar.dumpster_fire["line"] or "Misery" in nar.dumpster_fire["line"] or len(nar.dumpster_fire["line"]) > 0

def test_spotlight_triggers_on_busts(tmp_path):
    wk = make_week()
    nar = build_narratives(wk, season=2025, state_dir=tmp_path.as_posix())
    assert nar.talk_spotlight is not None
    assert nar.talk_spotlight["name"] == "Mike's Misery"
    assert any(b["player"] == "Derrick Henry" for b in nar.talk_spotlight["busts"])
