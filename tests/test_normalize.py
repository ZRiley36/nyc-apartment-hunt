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
    assert lst.url == "https://apartments.com/x/1"
    assert lst.neighborhood == "Bushwick"
    assert lst.available_date == date(2026, 9, 15)
    assert lst.id == canonical_id("aggregator", "123 Main St, Brooklyn, NY 11249", 3200)
    # amenities parsed from the unit/community string lists
    assert lst.amenities_raw["laundry_in_building"] is True
    assert lst.amenities_raw["laundry_in_unit"] is True
    assert lst.amenities_raw["gym"] is True
    assert lst.amenities_raw["ac"] is True
    assert lst.amenities_raw["dishwasher"] is False

def test_normalize_aggregator_coerces_range_fields():
    # real actor returns price.value / bedrooms / bathrooms as {min,max} on some providers
    raw = RawListing("aggregator", {
        "source": {"url": "u"}, "address": {"formattedAddress": "1 A St"},
        "price": {"value": {"min": 2500, "max": 3000}},
        "bedrooms": {"min": 2, "max": 4}, "bathrooms": {"min": 1, "max": 2},
        "pictures": [], "amenities": {}})
    lst = normalize(raw)
    assert lst.price == 2500 and lst.bedrooms == 2 and lst.bathrooms == 1

def test_normalize_streeteasy():
    lst = normalize(_raw("streeteasy_raw.json"))
    assert lst.price == 3500 and lst.bathrooms == 1
    assert lst.neighborhood == "Williamsburg"

def test_unusable_returns_none():
    assert normalize(RawListing(source="aggregator", data={"description": "no price no url"})) is None
