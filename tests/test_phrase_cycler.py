import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from transform.phrase_cycler import PhraseCycler


@pytest.fixture()
def sample_bank():
    return {
        "cat": ["alpha", "bravo", "charlie"],
        "generic": ["fallback-one", "fallback-two", "fallback-three"],
    }


def test_no_duplicates_until_exhaustion(tmp_path, sample_bank):
    state_dir = tmp_path / "state"
    cycler = PhraseCycler(sample_bank, season=2025, state_dir=state_dir)

    seen = set()
    for _ in range(len(sample_bank["cat"])):
        phrase = cycler.pick("cat", "0001")
        assert phrase not in seen
        seen.add(phrase)

    fallback_seen = set()
    for _ in range(len(sample_bank["generic"])):
        phrase = cycler.pick("cat", "0001")
        assert phrase not in seen
        assert phrase not in fallback_seen
        fallback_seen.add(phrase)

    with pytest.raises(ValueError):
        cycler.pick("cat", "0001")


def test_deterministic_selection(tmp_path, sample_bank):
    state_dir = tmp_path / "state"
    first = PhraseCycler(sample_bank, season=2025, state_dir=state_dir)
    picks_first = [first.pick("cat", "0002") for _ in range(3)]

    # new state directory to ensure clean slate
    state_dir_fresh = tmp_path / "fresh"
    second = PhraseCycler(sample_bank, season=2025, state_dir=state_dir_fresh)
    picks_second = [second.pick("cat", "0002") for _ in range(3)]

    assert picks_first == picks_second


def test_state_persists_across_runs(tmp_path, sample_bank):
    state_dir = tmp_path / "state"
    first = PhraseCycler(sample_bank, season=2025, state_dir=state_dir)
    first_pick = first.pick("cat", "0003")

    # Recreate cycler with same state directory
    second = PhraseCycler(sample_bank, season=2025, state_dir=state_dir)
    second_pick = second.pick("cat", "0003")

    assert second_pick != first_pick

    # Ensure the saved state file exists and contains the season bucket
    state_path = second.state_path
    assert state_path.exists()
    data = json.loads(state_path.read_text())
    assert "2025" in data.get("seasons", {})
