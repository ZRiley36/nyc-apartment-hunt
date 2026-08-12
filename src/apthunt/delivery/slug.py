from __future__ import annotations
import hashlib


def report_slug(profile_name: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{profile_name}".encode()).hexdigest()[:10]
