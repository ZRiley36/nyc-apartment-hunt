from __future__ import annotations
from datetime import date
from enum import Enum
from pydantic import BaseModel, Field


class Amenity(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    IGNORE = "ignore"


class Budget(BaseModel):
    min: int = 0
    max: int | None = None          # whole-apartment cap; omit when using per_room_max
    per_room_max: int | None = None # cap on rent-per-bedroom (each roommate's share)


class RangeInt(BaseModel):
    min: int | None = None
    max: int | None = None


class MoveIn(BaseModel):
    earliest: date | None = None
    latest: date | None = None


class RunConfig(BaseModel):
    sources: list[str] = Field(default_factory=lambda: ["aggregator", "streeteasy"])
    max_verify_per_run: int = 25
    radius_miles: float = 1.5   # aggregator search radius per location; lower = tighter


class Profile(BaseModel):
    name: str
    email: str
    enabled: bool = True
    budget: Budget
    locations: list[str]
    bedrooms: RangeInt = RangeInt()
    bathrooms: RangeInt = RangeInt()
    min_bath_per_bed: float | None = None   # e.g. 0.5 = at least 1 bath per 2 bedrooms
    move_in: MoveIn = MoveIn()
    amenities: dict[str, Amenity] = Field(default_factory=dict)
    run: RunConfig = RunConfig()

    def required_amenities(self) -> list[str]:
        return [k for k, v in self.amenities.items() if v is Amenity.REQUIRED]

    def preferred_amenities(self) -> list[str]:
        return [k for k, v in self.amenities.items() if v is Amenity.PREFERRED]
