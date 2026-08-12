from __future__ import annotations
# TODO(verify): actor id + run_input keys are best-guess; confirm against real actor
from .base import RawListing, Listing
from .apify import run_actor


class StreetEasyClient:
    def __init__(self, token: str, actor_id: str = "jupri/streeteasy-scraper"):
        self.token, self.actor_id = token, actor_id

    def search(self, locations, price_min, price_max) -> list[RawListing]:
        run_input = {"areas": locations, "type": "rentals",
                     "minPrice": price_min, "maxPrice": price_max}
        items = run_actor(self.actor_id, run_input, self.token)
        return [RawListing("streeteasy", it) for it in items]

    def fetch_detail(self, listing: Listing) -> Listing | None:
        return listing
