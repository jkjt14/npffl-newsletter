from transform.phrase_cycler import PhraseCycler

BANK = {"cat": [f"L{i}" for i in range(50)]}

def test_no_duplicates_until_exhaustion(tmp_path):
    pc = PhraseCycler(BANK, season=2025, state_dir=tmp_path.as_posix())
    seen = set()
    for _ in range(50):
        s = pc.next("cat", "TEAM")
        assert s not in seen
        seen.add(s)
    # exhausted: fallback behavior returns a valid phrase deterministically
    assert pc.next("cat", "TEAM") in BANK["cat"]

def test_deterministic_across_runs(tmp_path):
    pc1 = PhraseCycler(BANK, season=2025, state_dir=tmp_path.as_posix())
    a1 = [pc1.next("cat", "TEAM") for _ in range(5)]
    pc2 = PhraseCycler(BANK, season=2025, state_dir=tmp_path.as_posix())
    a2 = [pc2.next("cat", "TEAM") for _ in range(5)]
    assert a1 == a2
