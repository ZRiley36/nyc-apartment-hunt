from __future__ import annotations
import json
from pathlib import Path


def load_state(name: str, dir: Path = Path("state")) -> dict[str, str]:
    path = Path(dir) / f"{name}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_state(name: str, seen: dict[str, str], dir: Path = Path("state")) -> Path:
    Path(dir).mkdir(parents=True, exist_ok=True)
    path = Path(dir) / f"{name}.json"
    path.write_text(json.dumps(seen, indent=2, sort_keys=True) + "\n")
    return path


def record_seen(seen: dict[str, str], listing_ids: list[str], today: str) -> dict[str, str]:
    out = dict(seen)
    for lid in listing_ids:
        out.setdefault(lid, today)
    return out
