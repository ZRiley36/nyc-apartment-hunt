from __future__ import annotations
# TODO(verify): actor id + run_input keys are best-guess; confirm against real actor
from .base import RawListing, Listing
from .apify import run_actor


class AggregatorClient:
    def __init__(self, token: str, actor_id: str = "tri_angle/real-estate-aggregator"):
        self.token, self.actor_id = token, actor_id

    def search(self, locations, price_min, price_max) -> list[RawListing]:
        run_input = {"locations": locations, "listingType": "rent",
                     "priceMin": price_min, "priceMax": price_max,
                     "providers": ["apartments", "zillow", "zumper", "redfin", "realtor"]}
        items = run_actor(self.actor_id, run_input, self.token)
        return [RawListing("aggregator", it) for it in items]

    def fetch_detail(self, listing: Listing) -> Listing | None:
        # Aggregator records already carry description/photos; trust the record for v1.
        return listing
