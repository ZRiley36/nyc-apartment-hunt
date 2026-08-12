from apthunt.llm import VerificationResult
from apthunt.pipeline.verify import verify_listing
from apthunt.pipeline.normalize import Listing
from apthunt.config.schema import Profile

def _profile():
    return Profile.model_validate({"name": "z", "email": "z@e.com", "enabled": True,
        "budget": {"min": 1, "max": 9999}, "locations": ["Bushwick"], "bedrooms": {},
        "bathrooms": {}, "move_in": {}, "amenities": {"laundry_in_building": "required"}, "run": {}})

def _listing():
    return Listing(id="x", source="aggregator", url="u", address="1 A St", neighborhood="Bushwick",
                   price=3000, bedrooms=1, bathrooms=1, sqft=None, available_date=None,
                   description="1BR with laundry in building", photos=["https://cdn/a.jpg"])

class _FakeParsed:
    def __init__(self, obj): self.parsed_output = obj

class _FakeMessages:
    def __init__(self, obj): self._obj = obj
    def parse(self, **kw):
        assert kw["model"] == "claude-haiku-4-5"
        assert kw["max_tokens"] >= 1024
        return _FakeParsed(self._obj)

class _FakeClient:
    def __init__(self, obj): self.messages = _FakeMessages(obj)

def test_verify_returns_parsed():
    vr = VerificationResult(is_active=True, scam_risk="low", scam_reasons=[],
                            amenity_findings={"laundry_in_building": "confirmed"}, summary="Nice 1BR.")
    out = verify_listing(_listing(), _profile(), client=_FakeClient(vr))
    assert out.amenity_findings["laundry_in_building"] == "confirmed"
