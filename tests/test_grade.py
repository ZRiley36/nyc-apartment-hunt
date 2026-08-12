from apthunt.pipeline.grade import grade_listing, Grade
from apthunt.pipeline.normalize import Listing
from apthunt.llm import VerificationResult
from apthunt.config.schema import Profile

def _p(required=("laundry_in_building",), preferred=("gym",)):
    am = {a: "required" for a in required} | {a: "preferred" for a in preferred}
    return Profile.model_validate({"name": "z", "email": "z@e.com", "enabled": True,
        "budget": {"min": 2000, "max": 4000}, "locations": ["Bushwick"], "bedrooms": {},
        "bathrooms": {}, "move_in": {}, "amenities": am, "run": {}})

def _l(price=3000):
    return Listing(id="x", source="aggregator", url="u", address="a", neighborhood="Bushwick",
                   price=price, bedrooms=1, bathrooms=1, sqft=None, available_date=None)

def _v(active=True, risk="low", findings=None):
    return VerificationResult(is_active=active, scam_risk=risk, scam_reasons=[],
                              amenity_findings=findings or {}, summary="s")

def test_contradicted_required_is_nope():
    g = grade_listing(_l(), _v(findings={"laundry_in_building": "contradicted"}), _p())
    assert g.grade == Grade.NOPE

def test_high_scam_is_nope():
    g = grade_listing(_l(), _v(risk="high"), _p())
    assert g.grade == Grade.NOPE

def test_unconfirmed_required_is_consider():
    g = grade_listing(_l(), _v(findings={"laundry_in_building": "unconfirmed"}), _p())
    assert g.grade == Grade.CONSIDER
    assert "verify" in g.rationale.lower()

def test_all_confirmed_is_apply():
    g = grade_listing(_l(price=2500), _v(findings={"laundry_in_building": "confirmed"}), _p())
    assert g.grade == Grade.APPLY

def test_per_room_budget_profile_grades_without_crash():
    # per-room-share profile has budget.max = None; the top-band tie-break must not crash
    p = Profile.model_validate({"name": "n", "email": "n@e.com", "enabled": True,
        "budget": {"per_room_max": 2700}, "locations": ["Midtown"], "bedrooms": {"min": 2},
        "bathrooms": {}, "move_in": {}, "amenities": {}, "run": {}})
    g = grade_listing(_l(price=5400), _v(), p)
    assert g.grade == Grade.APPLY
