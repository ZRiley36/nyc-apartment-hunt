from __future__ import annotations
from typing import Protocol
from ..pipeline.normalize import RawListing, Listing

__all__ = ["SourceClient", "RawListing", "Listing"]


class SourceClient(Protocol):
    def search(self, locations: list[str], price_min: int, price_max: int) -> list[RawListing]: ...
    def fetch_detail(self, listing: Listing) -> Listing | None: ...
