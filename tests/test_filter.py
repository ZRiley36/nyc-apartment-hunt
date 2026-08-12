from datetime import date
from apthunt.config.schema import Profile
from apthunt.pipeline.normalize import Listing
from apthunt.pipeline.filter import apply_filters

def _profile():
    return Profile.model_validate({
        "name": "z", "email": "z@e.com", "enabled": True,
        "budget": {"min": 2000, "max": 3800}, "locations": ["Bushwick"],
        "bedrooms": {"min": 1, "max": 2}, "bathrooms": {"min": 1},
        "move_in": {"latest": "2026-10-15"},
        "amenities": {"laundry_in_building": "required"}, "run": {},
    })

def _l(**kw):
    base = dict(id="x", source="aggregator", url="u", address="a", neighborhood="Bushwick",
               price=3000, bedrooms=1, bathrooms=1, sqft=None, available_date=None)
    base.update(kw)
    return Listing(**base)

def test_price_out_of_band_dropped():
    assert apply_filters([_l(price=5000)], _profile()) == []

def test_unknown_price_kept():
    assert len(apply_filters([_l(price=None)], _profile())) == 1

def test_wrong_neighborhood_dropped():
    assert apply_filters([_l(neighborhood="Harlem")], _profile()) == []

def test_late_move_in_dropped():
    assert apply_filters([_l(available_date=date(2026, 12, 1))], _profile()) == []

def test_required_amenity_absent_still_kept():
    # provider flag says no in-building laundry, but we must NOT drop here
    lst = _l()
    lst.amenities_raw = {"laundry_in_building": False}
    assert len(apply_filters([lst], _profile())) == 1
