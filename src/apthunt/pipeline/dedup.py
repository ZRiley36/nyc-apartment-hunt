from __future__ import annotations
from .normalize import Listing


def dedupe_within(listings: list[Listing]) -> list[Listing]:
    by_id: dict[str, Listing] = {}
    for lst in listings:
        existing = by_id.get(lst.id)
        # Prefer streeteasy detail when the same id shows up twice.
        if existing is None or (existing.source != "streeteasy" and lst.source == "streeteasy"):
            by_id[lst.id] = lst
    return list(by_id.values())


def split_new(
    listings: list[Listing], seen: dict[str, str]
) -> tuple[list[Listing], list[Listing]]:
    new = [l for l in listings if l.id not in seen]
    old = [l for l in listings if l.id in seen]
    return new, old
