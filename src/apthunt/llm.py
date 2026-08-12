from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class VerificationResult(BaseModel):
    is_active: bool
    scam_risk: Literal["low", "medium", "high"]
    scam_reasons: list[str] = Field(default_factory=list)
    amenity_findings: dict[str, Literal["confirmed", "unconfirmed", "contradicted"]] = Field(default_factory=dict)
    summary: str


def default_anthropic():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def build_verify_messages(listing, profile) -> list[dict]:
    # Text-only: we do NOT send photo URLs as image blocks. Listing CDNs
    # (Redfin/Zillow/apartments.com) disallow bot image fetching via robots.txt,
    # which makes the Anthropic image fetch return 400 and fails the whole call.
    # Scam/amenity signal lives in the description/price/address anyway. Passing
    # photos as base64 (download-then-attach) is a possible future enhancement.
    want = profile.required_amenities() + profile.preferred_amenities()
    amenity_line = ("Amenities to assess: " + ", ".join(want) + "."
                    if want else "No specific amenities to assess.")
    instruction = (
        "You are verifying a NYC rental listing for a renter. Using the details below, "
        "determine: (1) whether it looks like a real, currently-active listing (is_active); "
        "(2) scam_risk (low/medium/high) with scam_reasons — flag an implausibly low price "
        "for the area, a missing or fake-looking address, or a description pushing "
        "off-platform payment or contact; (3) for EACH amenity listed below, mark confirmed "
        "/ unconfirmed (not mentioned) / contradicted (evidence it is absent), from the "
        "description and provider flags; (4) a <=2 sentence summary. " + amenity_line + "\n\n"
        f"Address: {listing.address}\nNeighborhood: {listing.neighborhood}\n"
        f"Price: {listing.price}  Beds: {listing.bedrooms}  Baths: {listing.bathrooms}\n"
        f"Provider amenity flags: {listing.amenities_raw}\n"
        f"Description: {listing.description}\nURL: {listing.url}"
    )
    return [{"role": "user", "content": [{"type": "text", "text": instruction}]}]
