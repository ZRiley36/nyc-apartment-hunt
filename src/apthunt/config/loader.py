from __future__ import annotations
from pathlib import Path
import yaml
from .schema import Profile


def load_profiles(dir: Path = Path("profiles"), only: str | None = None) -> list[Profile]:
    profiles: list[Profile] = []
    for path in sorted(Path(dir).glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        profile = Profile.model_validate(data)
        if only is not None and profile.name != only:
            continue
        if profile.enabled:
            profiles.append(profile)
    return profiles
