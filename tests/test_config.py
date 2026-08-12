from pathlib import Path
from datetime import date
from apthunt.config.schema import Profile, Amenity
from apthunt.config.loader import load_profiles

def test_profile_parses_amenities_tristate(tmp_path: Path):
    (tmp_path / "z.yaml").write_text(
        "name: z\nemail: z@e.com\nenabled: true\n"
        "budget: {min: 2000, max: 3800}\nlocations: [Bushwick]\n"
        "bedrooms: {min: 1}\nbathrooms: {min: 1}\n"
        "move_in: {earliest: 2026-09-01, latest: 2026-10-15}\n"
        "amenities: {laundry_in_building: required, gym: preferred, dishwasher: ignore}\n"
        "run: {sources: [aggregator], max_verify_per_run: 10}\n"
    )
    profiles = load_profiles(tmp_path)
    assert len(profiles) == 1
    p = profiles[0]
    assert p.required_amenities() == ["laundry_in_building"]
    assert p.preferred_amenities() == ["gym"]
    assert p.move_in.earliest == date(2026, 9, 1)

def test_disabled_profiles_excluded(tmp_path: Path):
    (tmp_path / "z.yaml").write_text(
        "name: z\nemail: z@e.com\nenabled: false\n"
        "budget: {min: 1, max: 2}\nlocations: [X]\nbedrooms: {}\nbathrooms: {}\n"
        "move_in: {}\namenities: {}\nrun: {}\n"
    )
    assert load_profiles(tmp_path) == []

def test_only_filter(tmp_path: Path):
    for n in ("a", "b"):
        (tmp_path / f"{n}.yaml").write_text(
            f"name: {n}\nemail: {n}@e.com\nenabled: true\n"
            "budget: {min: 1, max: 2}\nlocations: [X]\nbedrooms: {}\nbathrooms: {}\n"
            "move_in: {}\namenities: {}\nrun: {}\n"
        )
    got = load_profiles(tmp_path, only="b")
    assert [p.name for p in got] == ["b"]
