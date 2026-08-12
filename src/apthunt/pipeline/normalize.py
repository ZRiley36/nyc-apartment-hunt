from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from datetime import date

# TODO(verify): field names are best-guess; confirm against a real actor run


@dataclass
class RawListing:
    source: str
    data: dict


@dataclass
class Listing:
    id: str
    source: str
    url: str
    address: str
    neighborhood: str | None
    price: int | None
    bedrooms: float | None
    bathrooms: float | None
    sqft: int | None
    available_date: date | None
    amenities_raw: dict[str, bool] = field(default_factory=dict)
    photos: list[str] = field(default_factory=list)
    description: str = ""
    is_active: bool = True


def canonical_id(source: str, address: str, price: int | None) -> str:
    key = f"{source}|{address.strip().lower()}|{price}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def _date(value) -> date | None:
    if not value:
        return None
    return date.fromisoformat(str(value)[:10])


def _agg(data: dict) -> Listing:
    addr = data.get("formattedAddress", "")
    price = data.get("price")
    feats = data.get("features", {}) or {}
    amenities = {
        "gym": bool(feats.get("gym")),
        "laundry_in_building": feats.get("laundry") in ("building", "in_building"),
        "laundry_in_unit": feats.get("laundry") in ("unit", "in_unit"),
    }
    return Listing(
        id=canonical_id("aggregator", addr, price), source="aggregator",
        url=data["url"], address=addr, neighborhood=data.get("neighborhood"),
        price=price, bedrooms=data.get("bedrooms"), bathrooms=data.get("bathrooms"),
        sqft=data.get("squareFootage"), available_date=_date(data.get("availableDate")),
        amenities_raw=amenities, photos=data.get("photos", []) or [],
        description=data.get("description", "") or "",
    )


def _se(data: dict) -> Listing:
    addr = data.get("address", "")
    price = data.get("price")
    tags = set(data.get("amenities", []) or [])
    amenities = {
        "rooftop": "roof_deck" in tags or "roofdeck" in tags,
        "dishwasher": "dishwasher" in tags,
        "gym": "gym" in tags,
        "no_fee": "no_fee" in tags or bool(data.get("noFee")),
    }
    return Listing(
        id=canonical_id("streeteasy", addr, price), source="streeteasy",
        url=data["url"], address=addr, neighborhood=data.get("area"),
        price=price, bedrooms=data.get("beds"), bathrooms=data.get("baths"),
        sqft=data.get("sqft"), available_date=_date(data.get("availableOn")),
        amenities_raw=amenities, photos=data.get("images", []) or [],
        description=data.get("description", "") or "",
    )


_MAPPERS = {"aggregator": _agg, "streeteasy": _se}


def normalize(raw: RawListing) -> Listing | None:
    if not raw.data.get("url") or raw.data.get("price") in (None, ""):
        return None
    return _MAPPERS[raw.source](raw.data)
