import json
from datetime import date
from pathlib import Path
from apthunt.pipeline.normalize import normalize, RawListing, canonical_id

FX = Path(__file__).parent / "fixtures"

def _raw(name):
    d = json.loads((FX / name).read_text())
    return RawListing(source=d["source"], data=d["data"])

def test_normalize_aggregator():
    lst = normalize(_raw("aggregator_raw.json"))
    assert lst is not None
    assert lst.price == 3200 and lst.bedrooms == 1
    assert lst.neighborhood == "Bushwick"
    assert lst.available_date == date(2026, 9, 15)
    assert lst.id == canonical_id("aggregator", "123 Main St, Brooklyn, NY", 3200)

def test_normalize_streeteasy():
    lst = normalize(_raw("streeteasy_raw.json"))
    assert lst.price == 3500 and lst.bathrooms == 1
    assert lst.neighborhood == "Williamsburg"

def test_unusable_returns_none():
    assert normalize(RawListing(source="aggregator", data={"description": "no price no url"})) is None
