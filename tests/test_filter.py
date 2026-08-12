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

def test_studio_or_unknown_bedrooms_dropped_when_min_set():
    # min is 1 in _profile(): a studio (0) and an unstated count must both drop
    assert apply_filters([_l(bedrooms=0)], _profile()) == []
    assert apply_filters([_l(bedrooms=None)], _profile()) == []

def _share_profile():
    return Profile.model_validate({
        "name": "n", "email": "n@e.com", "enabled": True,
        "budget": {"per_room_max": 2700}, "locations": ["Midtown"],
        "bedrooms": {"min": 2}, "bathrooms": {"min": 1}, "min_bath_per_bed": 0.5,
        "move_in": {}, "amenities": {}, "run": {}})

def test_per_room_share_budget():
    p = _share_profile()
    # 2BR @ 5400 -> 2700/room (keep); 2BR @ 6000 -> 3000/room (drop)
    assert len(apply_filters([_l(bedrooms=2, price=5400, neighborhood="Midtown")], p)) == 1
    assert apply_filters([_l(bedrooms=2, price=6000, neighborhood="Midtown")], p) == []
    # 3BR @ 8100 -> 2700/room (keep) — bigger apartment, more splitting
    assert len(apply_filters([_l(bedrooms=3, price=8100, bathrooms=2, neighborhood="Midtown")], p)) == 1

def test_bath_per_bed_ratio():
    p = _share_profile()  # 0.5 = 1 bath per 2 beds
    assert apply_filters([_l(bedrooms=3, bathrooms=1, price=6000, neighborhood="Midtown")], p) == []   # 3bed/1bath out
    assert len(apply_filters([_l(bedrooms=3, bathrooms=2, price=6000, neighborhood="Midtown")], p)) == 1  # 3bed/2bath ok
    assert len(apply_filters([_l(bedrooms=2, bathrooms=1, price=5000, neighborhood="Midtown")], p)) == 1  # 2bed/1bath ok

def test_room_share_dropped_despite_reported_bedrooms():
    # co-living: reports 3 bedrooms but the description says it's a private room
    lst = _l(bedrooms=3, description="Stylish Private ROOM in Greenpoint, 107 Greenpoint Ave")
    assert apply_filters([lst], _profile()) == []

def test_room_share_detected_in_title():
    # co-living puts "Private ROOM" in the TITLE; description is generic
    lst = _l(bedrooms=3, description="Bright unit near the park", title="Stylish Private ROOM in Greenpoint")
    assert apply_filters([lst], _profile()) == []

def test_whole_apartment_kept():
    lst = _l(bedrooms=2, description="Sunny 2BR apartment, renovated kitchen, near the L train")
    assert len(apply_filters([lst], _profile())) == 1

def test_unknown_bedrooms_kept_when_no_min():
    p = Profile.model_validate({
        "name": "z", "email": "z@e.com", "enabled": True,
        "budget": {"min": 2000, "max": 3800}, "locations": ["Bushwick"],
        "bedrooms": {}, "bathrooms": {}, "move_in": {}, "amenities": {}, "run": {}})
    assert len(apply_filters([_l(bedrooms=None)], p)) == 1
