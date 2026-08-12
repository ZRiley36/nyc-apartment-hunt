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
    required = profile.required_amenities()
    instruction = (
        "You are verifying a NYC rental listing for a renter. Using the details and "
        "photos below, determine: (1) does it look like a real, currently-active listing "
        "(is_active); (2) scam_risk (low/medium/high) with scam_reasons — flag implausibly "
        "low price for the area, no real address, requests to pay/wire off-platform, or "
        "recycled/stock-looking photos; (3) for EACH required amenity, mark confirmed / "
        "unconfirmed (not mentioned) / contradicted (evidence it's absent); (4) a <=2 "
        "sentence summary. Required amenities: " + ", ".join(required or ["(none)"]) + ".\n\n"
        f"Address: {listing.address}\nNeighborhood: {listing.neighborhood}\n"
        f"Price: {listing.price}  Beds: {listing.bedrooms}  Baths: {listing.bathrooms}\n"
        f"Provider amenity flags: {listing.amenities_raw}\n"
        f"Description: {listing.description}\nURL: {listing.url}"
    )
    content: list[dict] = [{"type": "text", "text": instruction}]
    for url in listing.photos[:4]:
        content.append({"type": "image", "source": {"type": "url", "url": url}})
    return [{"role": "user", "content": content}]
