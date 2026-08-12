import json
from pathlib import Path
from apthunt.sources.apify import run_actor
from apthunt.sources.fixtures import FixtureClient
from apthunt.pipeline.normalize import RawListing

FX = Path(__file__).parent / "fixtures"

class _FakeActor:
    def __init__(self, items): self._items = items
    def call(self, run_input=None): return {"defaultDatasetId": "ds1"}

class _FakeDataset:
    def __init__(self, items): self._items = items
    def iterate_items(self): yield from self._items

class _FakeApify:
    def __init__(self, items): self._items = items
    def actor(self, actor_id): return _FakeActor(self._items)
    def dataset(self, ds_id): return _FakeDataset(self._items)

def test_run_actor_returns_items():
    items = json.loads((FX / "agg_dataset.json").read_text())
    out = run_actor("x/y", {"q": "z"}, token="t", client=_FakeApify(items))
    assert out == items

def test_fixture_client_filters_by_location():
    recs = [RawListing("aggregator", {"url": "u1", "price": 3000, "neighborhood": "Bushwick",
                                       "formattedAddress": "1 A St"}),
            RawListing("aggregator", {"url": "u2", "price": 3000, "neighborhood": "Harlem",
                                      "formattedAddress": "2 B St"})]
    client = FixtureClient(recs)
    got = client.search(["Bushwick"], 2000, 4000)
    assert [r.data["url"] for r in got] == ["u1"]
