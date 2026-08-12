from __future__ import annotations
# Verified against tri_angle/real-estate-aggregator (2026-08-12): the actor takes
# a SINGLE `location` per run and has NO price filter, so we fan out one run per
# neighborhood and let apply_filters enforce budget client-side.
from .base import RawListing, Listing
from .apify import run_actor

_PROVIDERS = ["apartments", "zillow", "zumper", "redfin", "realtor"]


class AggregatorClient:
    def __init__(self, token: str, actor_id: str = "tri_angle/real-estate-aggregator",
                 max_results: int = 40, radius_miles: float | None = 1.5, client=None):
        self.token = token
        self.actor_id = actor_id
        self.max_results = max_results          # per-provider cap — the main cost lever
        self.radius_miles = radius_miles        # tightens each per-neighborhood search;
                                                # calibrate against a live run
        self._client = client                   # injectable ApifyClient for tests

    def search(self, locations, price_min, price_max) -> list[RawListing]:
        # price_min/price_max are unused: the actor has no price filter (budget is
        # enforced downstream in apply_filters). One run per location.
        out: list[RawListing] = []
        for loc in locations:
            run_input = {"location": loc, "offerType": "rent",
                         "maxResults": self.max_results, "providers": _PROVIDERS}
            if self.radius_miles is not None:
                run_input["radiusMiles"] = self.radius_miles
            for it in run_actor(self.actor_id, run_input, self.token, client=self._client):
                rec = dict(it)
                rec["_searched_location"] = loc  # actor omits neighborhood; tag what we searched
                out.append(RawListing("aggregator", rec))
        return out

    def fetch_detail(self, listing: Listing) -> Listing | None:
        # Aggregator records already carry description/photos; trust the record for v1.
        return listing
