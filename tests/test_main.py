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

def _recs():
    return [RawListing(r["source"], r["data"]) for r in json.loads((FX / "pipeline_records.json").read_text())]

def test_run_writes_report_and_state(tmp_path):
    recs = _recs()
    paths = run([_profile()], dry_run=True, clients_for=lambda p: [FixtureClient(recs)],
                llm_client=_LLM(), salt="salt1", today="2026-08-11",
                site_root=tmp_path / "site", state_dir=tmp_path / "state")
    assert paths and paths[0].exists()
    assert "Apply now" in paths[0].read_text()
    assert (tmp_path / "state" / "zach.json").exists()

def test_second_run_has_no_new_matches(tmp_path):
    # The central promise: a listing surfaced on run 1 is not "new" on run 2.
    from apthunt.main import PooledClient
    PooledClient._cache.clear()
    kw = dict(dry_run=True, clients_for=lambda p: [FixtureClient(_recs())], llm_client=_LLM(),
              salt="salt1", today="2026-08-11", site_root=tmp_path / "site", state_dir=tmp_path / "state")
    run([_profile()], **kw)                 # run 1: surfaces + records the match
    paths = run([_profile()], **kw)         # run 2: same fixtures, state now has the id
    html = paths[0].read_text()
    assert html.count("Nothing this run.") == 2   # both Apply and Consider empty
    assert "NEW" not in html                       # no new-listing badges rendered
