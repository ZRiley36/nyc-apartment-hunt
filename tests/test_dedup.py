from datetime import date
from apthunt.pipeline.normalize import Listing
from apthunt.pipeline.dedup import split_new, dedupe_within

def _l(id, source="aggregator"):
    return Listing(id=id, source=source, url="u", address="a", neighborhood=None,
                   price=3000, bedrooms=1, bathrooms=1, sqft=None, available_date=None)

def test_split_new():
    new, old = split_new([_l("a"), _l("b")], {"a": "2026-08-01"})
    assert [x.id for x in new] == ["b"]
    assert [x.id for x in old] == ["a"]

def test_dedupe_within_keeps_one():
    out = dedupe_within([_l("a"), _l("a")])
    assert [x.id for x in out] == ["a"]
