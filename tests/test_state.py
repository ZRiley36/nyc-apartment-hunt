from pathlib import Path
from apthunt.state.store import load_state, save_state, record_seen

def test_roundtrip(tmp_path: Path):
    save_state("zach", {"abc": "2026-08-11"}, tmp_path)
    assert load_state("zach", tmp_path) == {"abc": "2026-08-11"}

def test_missing_is_empty(tmp_path: Path):
    assert load_state("nobody", tmp_path) == {}

def test_record_seen_only_adds_new():
    seen = {"a": "2026-08-01"}
    out = record_seen(seen, ["a", "b"], "2026-08-11")
    assert out == {"a": "2026-08-01", "b": "2026-08-11"}
    assert seen == {"a": "2026-08-01"}  # input untouched
