from __future__ import annotations
from .base import RawListing, Listing


class FixtureClient:
    def __init__(self, records: list[RawListing]):
        self._records = records

    def search(self, locations, price_min, price_max) -> list[RawListing]:
        wanted = [loc.lower() for loc in locations]
        out = []
        for r in self._records:
            hood = str(r.data.get("neighborhood") or r.data.get("area") or "").lower()
            if not wanted or any(w in hood or hood in w for w in wanted):
                out.append(r)
        return out

    def fetch_detail(self, listing: Listing) -> Listing | None:
        return listing


def get_client(name: str, token: str):
    from .aggregator import AggregatorClient
    from .streeteasy import StreetEasyClient
    return {"aggregator": AggregatorClient, "streeteasy": StreetEasyClient}[name](token)
