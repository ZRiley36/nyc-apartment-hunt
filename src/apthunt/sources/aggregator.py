from __future__ import annotations
# Verified against tri_angle/real-estate-aggregator (2026-08-12): the actor takes
# a SINGLE `location` per run and has NO price filter, so we fan out one run per
# neighborhood and let apply_filters enforce budget client-side. The actor's
# `radiusMiles` is a soft hint some providers ignore (a "Williamsburg" search
# returned Sheepshead Bay / Cypress Hills listings), so we ALSO enforce the
# radius ourselves from each record's gps coordinates — see _within_radius.
import math
from .base import RawListing, Listing
from .apify import run_actor

_PROVIDERS = ["apartments", "zillow", "zumper", "redfin", "realtor"]

# Approximate neighborhood centroids (lat, lng). Add entries as profiles use new
# neighborhoods; an unknown neighborhood simply skips geo-filtering (kept).
_CENTROIDS: dict[str, tuple[float, float]] = {
    "williamsburg": (40.7081, -73.9571),
    "greenpoint": (40.7304, -73.9510),
    "east village": (40.7265, -73.9815),
    "bushwick": (40.6942, -73.9212),
    "astoria": (40.7644, -73.9235),
    "jackson heights": (40.7557, -73.8831),
    "long island city": (40.7447, -73.9485),
}


def _centroid_for(location: str) -> tuple[float, float] | None:
    # "Williamsburg, Brooklyn, NY" -> "williamsburg"; bare "Williamsburg" -> "williamsburg"
    return _CENTROIDS.get(location.split(",")[0].strip().lower())


def _haversine_miles(lat1, lng1, lat2, lng2) -> float:
    r = 3958.8  # earth radius, miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _within_radius(record: dict, center: tuple[float, float] | None, radius_miles) -> bool:
    # Keep when we can't judge: no centroid for this location, no radius set, or the
    # record carries no usable coordinates. Only drop when we can prove it's too far.
    if center is None or radius_miles is None:
        return True
    gps = record.get("gps") or {}
    lat, lng = gps.get("lat"), gps.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return True
    return _haversine_miles(center[0], center[1], lat, lng) <= radius_miles


class AggregatorClient:
    def __init__(self, token: str, actor_id: str = "tri_angle/real-estate-aggregator",
                 max_results: int = 40, radius_miles: float | None = 1.5, client=None):
        self.token = token
        self.actor_id = actor_id
        self.max_results = max_results          # per-provider cap — the main cost lever
        self.radius_miles = radius_miles        # enforced client-side from gps (below)
        self._client = client                   # injectable ApifyClient for tests

    def search(self, locations, price_min, price_max) -> list[RawListing]:
        # price_min/price_max are unused: the actor has no price filter (budget is
        # enforced downstream in apply_filters). One run per location.
        out: list[RawListing] = []
        for loc in locations:
            center = _centroid_for(loc)
            run_input = {"location": loc, "offerType": "rent",
                         "maxResults": self.max_results, "providers": _PROVIDERS}
            if self.radius_miles is not None:
                run_input["radiusMiles"] = self.radius_miles
            for it in run_actor(self.actor_id, run_input, self.token, client=self._client):
                if not _within_radius(it, center, self.radius_miles):
                    continue  # actor ignored the radius — drop by true gps distance
                rec = dict(it)
                rec["_searched_location"] = loc  # actor omits neighborhood; tag what we searched
                out.append(RawListing("aggregator", rec))
        return out

    def fetch_detail(self, listing: Listing) -> Listing | None:
        # Aggregator records already carry description/photos; trust the record for v1.
        return listing
