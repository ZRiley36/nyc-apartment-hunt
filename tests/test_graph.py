import json
from pathlib import Path
from apthunt.pipeline.graph import run_profile
from apthunt.sources.fixtures import FixtureClient
from apthunt.pipeline.normalize import RawListing
from apthunt.llm import VerificationResult
from apthunt.config.schema import Profile

FX = Path(__file__).parent / "fixtures"

def _profile():
    return Profile.model_validate({"name": "zach", "email": "z@e.com", "enabled": True,
        "budget": {"min": 2000, "max": 3800}, "locations": ["Bushwick"], "bedrooms": {"min": 1},
        "bathrooms": {"min": 1}, "move_in": {}, "amenities": {"laundry_in_building": "required"},
        "run": {"sources": ["aggregator"], "max_verify_per_run": 25}})

class _FakeMessages:
    def parse(self, **kw):
        class R: parsed_output = VerificationResult(
            is_active=True, scam_risk="low",
            amenity_findings={"laundry_in_building": "confirmed"}, summary="Nice.")
        return R()

class _FakeLLM:
    messages = _FakeMessages()

def test_pipeline_end_to_end_dry():
    recs = [RawListing(r["source"], r["data"]) for r in json.loads((FX / "pipeline_records.json").read_text())]
    ctx = run_profile(_profile(), clients=[FixtureClient(recs)], llm_client=_FakeLLM(),
                      seen={}, generated_at="2026-08-11T08:00")
    # Only the in-area, in-budget listing survives filtering and grades Apply.
    assert len(ctx.apply) == 1
    assert ctx.apply[0].neighborhood.lower().startswith("bushwick")
    assert ctx.apply[0].is_new is True
