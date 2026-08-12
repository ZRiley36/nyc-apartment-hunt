from __future__ import annotations
from .normalize import Listing
from ..config.schema import Profile


def _location_ok(listing: Listing, profile: Profile) -> bool:
    if not listing.neighborhood:
        return True  # unknown — let verification decide, don't drop
    hood = listing.neighborhood.lower()
    return any(loc.lower() in hood or hood in loc.lower() for loc in profile.locations)


def matches(listing: Listing, profile: Profile) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if listing.price is not None and not (profile.budget.min <= listing.price <= profile.budget.max):
        reasons.append(f"price {listing.price} outside {profile.budget.min}-{profile.budget.max}")
    if listing.bedrooms is not None:
        if profile.bedrooms.min is not None and listing.bedrooms < profile.bedrooms.min:
            reasons.append("too few bedrooms")
        if profile.bedrooms.max is not None and listing.bedrooms > profile.bedrooms.max:
            reasons.append("too many bedrooms")
    if listing.bathrooms is not None and profile.bathrooms.min is not None:
        if listing.bathrooms < profile.bathrooms.min:
            reasons.append("too few bathrooms")
    if not _location_ok(listing, profile):
        reasons.append("neighborhood mismatch")
    if listing.available_date and profile.move_in.latest and listing.available_date > profile.move_in.latest:
        reasons.append("available after move-in window")
    return (not reasons, reasons)


def apply_filters(listings: list[Listing], profile: Profile) -> list[Listing]:
    return [l for l in listings if matches(l, profile)[0]]
