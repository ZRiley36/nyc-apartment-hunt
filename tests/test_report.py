from apthunt.pipeline.report import build_report
from apthunt.pipeline.grade import Graded, Grade
from apthunt.pipeline.normalize import Listing
from apthunt.llm import VerificationResult
from apthunt.config.schema import Profile

def _p(): return Profile.model_validate({"name": "z", "email": "z@e.com", "enabled": True,
    "budget": {"min": 1, "max": 9999}, "locations": ["X"], "bedrooms": {}, "bathrooms": {},
    "move_in": {}, "amenities": {}, "run": {}})

def _graded(id, grade, score, price=3000):
    l = Listing(id=id, source="s", url="u", address=id, neighborhood="X", price=price,
                bedrooms=1, bathrooms=1, sqft=None, available_date=None, photos=["p"])
    v = VerificationResult(is_active=True, scam_risk="low", amenity_findings={}, summary="sum")
    return Graded(l, v, grade, "why", score)

def test_nope_excluded_but_counted():
    ctx = build_report([_graded("a", Grade.APPLY, 5), _graded("b", Grade.NOPE, -1)],
                       seen={}, profile=_p(), generated_at="2026-08-11T08:00")
    assert [c.address for c in ctx.apply] == ["a"]
    assert ctx.nope_count == 1

def test_new_flag_and_ranking():
    ctx = build_report([_graded("a", Grade.APPLY, 2, price=3000),
                        _graded("b", Grade.APPLY, 9, price=3500)],
                       seen={"a": "2026-08-01"}, profile=_p(), generated_at="t")
    assert [c.address for c in ctx.apply] == ["b", "a"]  # higher score first
    assert ctx.apply[1].is_new is False and ctx.apply[0].is_new is True
