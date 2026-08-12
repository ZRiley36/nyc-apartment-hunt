from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from datetime import date

# Field mappings verified against a real tri_angle/real-estate-aggregator run
# (2026-08-12, 395 records). Aggregator nests everything (source.url,
# address.formattedAddress, price.value) and several numeric fields arrive as
# either a scalar or a {min,max} range — see _num.


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


def _num(v) -> float | None:
    """Coerce a scalar / {min,max|value} range / None to a single number.

    The aggregator returns bedrooms, bathrooms and price.value as an int, a
    float, or a {"min":..,"max":..} range depending on the underlying provider.
    Passing a dict on to the filters would crash the `<`/`>` comparisons.
    """
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, dict):
        for k in ("min", "value", "max"):
            inner = v.get(k)
            if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                return inner
    return None


# substring patterns (matched against lowercased amenity strings)
_AGG_AMENITY_MATCH = {
    "laundry_in_unit": ("in unit", "in-unit", "washer"),
    "laundry_in_building": ("laundry facility", "laundry room", "laundry in building",
                            "on-site laundry", "shared laundry", "community laundry"),
    "gym": ("fitness", "gym"),
    "rooftop": ("roof deck", "roof-deck", "rooftop", "roof top"),
    "dishwasher": ("dishwasher",),
    "ac": ("air conditioning", "central air", "central a/c", "a/c"),
    "no_fee": ("no fee", "no-fee", "no broker fee"),
}


def _agg(data: dict) -> Listing | None:
    src = data.get("source") or {}
    url = src.get("url") or data.get("url")
    raw_price = data.get("price")
    price = _num(raw_price.get("value")) if isinstance(raw_price, dict) else _num(raw_price)
    if not url or price is None:
        return None  # unusable without a link or a price
    if isinstance(price, float):
        price = int(price)

    addr_obj = data.get("address") or {}
    addr = addr_obj.get("formattedAddress") or addr_obj.get("street") or ""

    am = data.get("amenities") or {}
    strings = [str(s).lower() for s in (am.get("unit") or []) + (am.get("community") or [])]
    blob = " | ".join(strings)
    amenities = {key: any(pat in blob for pat in pats) for key, pats in _AGG_AMENITY_MATCH.items()}
    if amenities["laundry_in_unit"]:
        amenities["laundry_in_building"] = True  # in-unit laundry trivially satisfies in-building

    return Listing(
        id=canonical_id("aggregator", addr, price), source="aggregator",
        url=url, address=addr,
        neighborhood=data.get("_searched_location") or data.get("neighborhood"),
        price=price, bedrooms=_num(data.get("bedrooms")), bathrooms=_num(data.get("bathrooms")),
        sqft=_int_or_none(_num(data.get("livingArea"))),
        available_date=_date((data.get("extras") or {}).get("availableFrom")),
        amenities_raw=amenities, photos=data.get("pictures") or [],
        description=data.get("description") or "",
    )


def _int_or_none(v):
    return int(v) if isinstance(v, (int, float)) else None


def _se(data: dict) -> Listing | None:
    url = data.get("url")
    price = _num(data.get("price"))
    if not url or price is None:
        return None
    tags = set(data.get("amenities", []) or [])
    amenities = {
        "rooftop": "roof_deck" in tags or "roofdeck" in tags,
        "dishwasher": "dishwasher" in tags,
        "gym": "gym" in tags,
        "no_fee": "no_fee" in tags or bool(data.get("noFee")),
    }
    return Listing(
        id=canonical_id("streeteasy", data.get("address", ""), int(price)), source="streeteasy",
        url=url, address=data.get("address", ""), neighborhood=data.get("area"),
        price=int(price), bedrooms=_num(data.get("beds")), bathrooms=_num(data.get("baths")),
        sqft=_int_or_none(_num(data.get("sqft"))), available_date=_date(data.get("availableOn")),
        amenities_raw=amenities, photos=data.get("images", []) or [],
        description=data.get("description", "") or "",
    )


_MAPPERS = {"aggregator": _agg, "streeteasy": _se}


def normalize(raw: RawListing) -> Listing | None:
    return _MAPPERS[raw.source](raw.data)
