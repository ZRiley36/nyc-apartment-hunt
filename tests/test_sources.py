import json
from pathlib import Path
from apthunt.sources.apify import run_actor
from apthunt.sources.aggregator import AggregatorClient
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

class _CapturingActor:
    def __init__(self, items, sink): self._items, self._sink = items, sink
    def call(self, run_input=None):
        self._sink.append(run_input)
        return {"defaultDatasetId": "ds1"}

class _CapturingApify:
    def __init__(self, items):
        self._items, self.inputs, self.actor_calls = items, [], 0
    def actor(self, actor_id):
        self.actor_calls += 1
        return _CapturingActor(self._items, self.inputs)
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

def test_aggregator_fans_out_per_location():
    fake = _CapturingApify([{"source": {"url": "u"}, "price": {"value": 3000},
                             "address": {"formattedAddress": "1 A St"}}])
    client = AggregatorClient(token="t", max_results=40, client=fake)
    out = client.search(["Bushwick", "Greenpoint"], 2000, 4700)
    # one actor run per location, each returned record tagged with what we searched
    assert fake.actor_calls == 2
    assert {r.data["_searched_location"] for r in out} == {"Bushwick", "Greenpoint"}
    # correct single-location input, no invalid price/listingType keys
    assert {ri["location"] for ri in fake.inputs} == {"Bushwick", "Greenpoint"}
    for ri in fake.inputs:
        assert ri["offerType"] == "rent" and ri["maxResults"] == 40
        assert "priceMin" not in ri and "priceMax" not in ri and "listingType" not in ri
