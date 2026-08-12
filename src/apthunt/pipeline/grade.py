from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class Grade(str, Enum):
    APPLY = "Apply now"
    CONSIDER = "Consider"
    NOPE = "Probably not"


@dataclass
class Graded:
    listing: object
    verification: object
    grade: Grade
    rationale: str
    score: int


def grade_listing(listing, verification, profile) -> Graded:
    findings = verification.amenity_findings
    required = profile.required_amenities()
    contradicted = [a for a in required if findings.get(a) == "contradicted"]
    unconfirmed = [a for a in required if findings.get(a) in (None, "unconfirmed")]

    if verification.scam_risk == "high" or not verification.is_active or contradicted:
        why = []
        if not verification.is_active:
            why.append("listing not active")
        if verification.scam_risk == "high":
            why.append("high scam risk: " + "; ".join(verification.scam_reasons))
        if contradicted:
            why.append("missing required: " + ", ".join(contradicted))
        return Graded(listing, verification, Grade.NOPE, "; ".join(why) or "excluded", score=-10)

    confirmed_req = [a for a in required if findings.get(a) == "confirmed"]
    confirmed_pref = [a for a in profile.preferred_amenities() if findings.get(a) == "confirmed"]
    score = len(confirmed_req) * 2 + len(confirmed_pref)

    if unconfirmed:
        return Graded(listing, verification, Grade.CONSIDER,
                      f"Looks good but verify: {', '.join(unconfirmed)}.", score)

    # all required confirmed — "near top of whole-apartment budget" tie-break
    # (skipped for per-room-share profiles, which have no whole-apartment max)
    top_band = (profile.budget.max is not None and listing.price is not None
                and listing.price >= profile.budget.min
                + 0.85 * (profile.budget.max - profile.budget.min))
    if top_band and not confirmed_pref:
        return Graded(listing, verification, Grade.CONSIDER,
                      "Meets must-haves but near top of budget with few extras.", score)
    return Graded(listing, verification, Grade.APPLY,
                  "All required amenities confirmed; within budget.", score + 3)
