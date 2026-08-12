import json
from pathlib import Path
from apthunt.main import run
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

class _LLM:
    class messages:
        @staticmethod
        def parse(**kw):
            class R: parsed_output = VerificationResult(is_active=True, scam_risk="low",
                amenity_findings={"laundry_in_building": "confirmed"}, summary="Nice.")
            return R()

def test_run_writes_report_and_state(tmp_path):
    recs = [RawListing(r["source"], r["data"]) for r in json.loads((FX / "pipeline_records.json").read_text())]
    paths = run([_profile()], dry_run=True, clients_for=lambda p: [FixtureClient(recs)],
                llm_client=_LLM(), salt="salt1", today="2026-08-11",
                site_root=tmp_path / "site", state_dir=tmp_path / "state")
    assert paths and paths[0].exists()
    assert "Apply now" in paths[0].read_text()
    assert (tmp_path / "state" / "zach.json").exists()
