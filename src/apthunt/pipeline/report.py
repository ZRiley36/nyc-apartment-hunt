from __future__ import annotations
from dataclasses import dataclass, field
from .grade import Graded, Grade


@dataclass
class Card:
    url: str
    address: str
    neighborhood: str | None
    price: int | None
    beds: float | None
    baths: float | None
    grade: str
    rationale: str
    summary: str
    photo: str | None
    is_new: bool
    matched_amenities: list[str] = field(default_factory=list)


@dataclass
class ReportContext:
    profile_name: str
    generated_at: str
    apply: list[Card]
    consider: list[Card]
    nope_count: int
    new_ids: list[str]


def _card(g: Graded, seen: dict[str, str]) -> Card:
    l = g.listing
    matched = [a for a, s in g.verification.amenity_findings.items() if s == "confirmed"]
    return Card(url=l.url, address=l.address, neighborhood=l.neighborhood, price=l.price,
                beds=l.bedrooms, baths=l.bathrooms, grade=g.grade.value, rationale=g.rationale,
                summary=g.verification.summary, photo=(l.photos[0] if l.photos else None),
                is_new=l.id not in seen, matched_amenities=matched)


def build_report(graded, seen, profile, generated_at) -> ReportContext:
    ranked = sorted(graded, key=lambda g: (-g.score, g.listing.price or 10**9))
    apply = [_card(g, seen) for g in ranked if g.grade == Grade.APPLY]
    consider = [_card(g, seen) for g in ranked if g.grade == Grade.CONSIDER]
    nope = sum(1 for g in ranked if g.grade == Grade.NOPE)
    new_ids = [g.listing.id for g in ranked]
    return ReportContext(profile.name, generated_at, apply, consider, nope, new_ids)
