# NYC Apartment Hunt — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A scheduled multi-profile NYC apartment finder that pulls listings from paid data providers, verifies each candidate with an LLM, and publishes a per-person HTML report (plus email) of graded, legit matches.

**Architecture:** A deterministic 3-stage LangGraph pipeline runs once per enabled user profile. Stage 1 (no LLM) fetches listings from an Apify aggregator + a StreetEasy scraper, normalizes them to one schema, pools results by location across profiles, and filters against the profile's criteria in our own code — never relying on a site's search UI. Stage 2 fans out one Claude Haiku call per new candidate to re-check the live listing, scan for scam signals, verify each required amenity, and grade Apply/Consider/Probably-not. Stage 3 ranks the verified listings, renders a self-contained HTML report to an unguessable path (published via GitHub Pages), emails the new matches, and commits updated per-profile "seen" state back to the repo. The whole thing runs on a GitHub Actions cron.

**Tech Stack:** Python 3.11+, LangGraph (orchestration), the official `anthropic` SDK (Claude calls via `messages.parse()` with Pydantic structured outputs — LangGraph nodes are plain functions, so no LangChain LLM wrapper is needed), `apify-client` (data providers), Pydantic v2 (schema), PyYAML (profiles), Jinja2 (report), httpx, pytest.

## Global Constraints

Every task's requirements implicitly include this section. Values are copied verbatim from the design.

- **Python:** 3.11+ (uses `X | None` unions, `tomllib`, `match`).
- **Model IDs (configurable, these are the defaults):** verification = `claude-haiku-4-5`; report synthesis = `claude-sonnet-5`. Use the exact ID strings; never append date suffixes. Both support structured outputs via `client.messages.parse(..., output_format=<PydanticModel>)` → `.parsed_output`.
- **Claude calls:** use the official `anthropic` SDK only (`anthropic.Anthropic()`), never a raw `requests`/`httpx` call to the API and never an OpenAI-compatible shim. `max_tokens` ≥ 1024 on every call.
- **Secrets — never hard-coded, never committed.** Read from env only: `ANTHROPIC_API_KEY`, `APIFY_TOKEN`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`. `.env` is git-ignored; `.env.example` documents them.
- **All user criteria (budget, beds, baths, amenities, move-in) are filtered in our code.** Actors receive only location (and a coarse price band spanning all profiles) to reduce volume. Never drop a listing because a *site* lacked a filter.
- **Amenity model is tri-state per criterion:** `required` filters (must not be contradicted); `preferred` only boosts the grade; `ignore` is skipped. A required amenity **contradicted** by verification ⇒ excluded (graded Probably-not with reason). A required amenity **unconfirmed** (just not mentioned) ⇒ kept, graded at most Consider, with a "verify X" note — never silently dropped.
- **State:** one JSON file per profile at `state/<profile>.json`, committed back to the repo each run so "new" is meaningful across runs. `state/` data files are committed (not git-ignored).
- **Reports:** self-contained HTML (no external network calls at view time — inline CSS, `<img>` may point at listing CDN URLs which is acceptable), one per profile, written to `site/r/<profile>-<slug>.html` where `<slug>` is a stable per-profile unguessable hex derived from a secret salt. Repo is **private**; Pages site is public-but-obscure.
- **Multi-profile:** the pipeline runs once per enabled profile; profiles live in `profiles/*.yaml`; adding a person is dropping in a file.
- **Actor IDs are config, not hard-coded literals in logic.** Defaults live in `profiles/*.yaml` under `run.sources`; they may need adjustment at implementation time since Apify actor availability shifts — verify each actor exists and inspect one sample run's output shape before wiring normalization.

---

## Design & Decisions (captured from brainstorming)

- **Data:** Hybrid — Apify **Real Estate Aggregator** (Apartments.com, Zillow, Zumper, Redfin, Realtor.com) as the backbone **+** a dedicated **StreetEasy** Apify scraper (StreetEasy dominates NYC and isn't in the aggregator). PadMapper/HotPads/Nooklyn deferred (inventory overlaps Zillow; Nooklyn can be added later as its own `SourceClient`).
- **Runtime & delivery:** GitHub Actions cron (≈8am & 1pm ET), state committed to repo, report to GitHub Pages at an unguessable path, email on new matches.
- **Verification depth:** Thorough — re-fetch the listing detail, scam-signal scan, per-required-amenity check against full description + photos, grade with a one-line rationale.
- **Cost posture:** cheapest viable providers; verification on Haiku, synthesis on Sonnet; a hard per-run cap on listings verified.
- **Keys:** user has none yet — Task 15 documents signup + secret setup.

### Module layout

```
nyc-apartment-hunt/
  pyproject.toml            .gitignore  .env.example  README.md
  .github/workflows/hunt.yml
  profiles/{zach,natasha}.yaml
  src/apthunt/
    __init__.py
    config/{schema.py, loader.py}
    sources/{base.py, apify.py, aggregator.py, streeteasy.py, fixtures.py}
    pipeline/{normalize.py, dedup.py, filter.py, verify.py, grade.py, report.py, graph.py}
    state/store.py
    delivery/{render.py, email.py, slug.py}
    templates/report.html.j2
    llm.py                  # anthropic client + verify prompt/schema
    main.py                 # CLI: run per profile, --dry-run, --profile
  tests/
    fixtures/*.json
    test_*.py
```

Layout rules: files that change together live together; each file has one responsibility. `pipeline/*` are pure functions where possible (normalize/dedup/filter/grade/report) so they unit-test against fixtures with no network and no API key.

---

## Task 1: Project scaffold, dependencies, example profiles

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `README.md`, `src/apthunt/__init__.py`, `profiles/zach.yaml`, `profiles/natasha.yaml`, `tests/__init__.py`, `tests/test_smoke.py`
- Create empty package markers: `src/apthunt/{config,sources,pipeline,state,delivery}/__init__.py`

**Interfaces:**
- Produces: an installable `apthunt` package (`pip install -e .`), a passing `pytest` run, and two example profile files that later tasks parse.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "apthunt"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.2",
    "anthropic>=0.40",
    "apify-client>=1.7",
    "pydantic>=2.7",
    "pyyaml>=6",
    "jinja2>=3.1",
    "httpx>=0.27",
    "python-dotenv>=1",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-mock>=3", "ruff>=0.5"]

[project.scripts]
apthunt = "apthunt.main:cli"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write `.gitignore` and `.env.example`**

`.gitignore` (note: `state/` data is NOT ignored — it is committed):
```
__pycache__/
*.pyc
.env
.venv/
*.egg-info/
site/
.pytest_cache/
```

`.env.example`:
```
ANTHROPIC_API_KEY=sk-ant-...
APIFY_TOKEN=apify_api_...
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
MAIL_FROM="Apt Hunt <you@gmail.com>"
# Salt for unguessable report URLs (any long random string)
REPORT_SLUG_SALT=change-me-to-a-long-random-string
```

- [ ] **Step 3: Write the two example profiles** — `profiles/zach.yaml`:

```yaml
name: zach
email: zachriley36@gmail.com
enabled: true
budget: { min: 2000, max: 3800 }          # USD/month
locations: [Williamsburg, Bushwick, "Long Island City"]
bedrooms: { min: 1, max: 2 }
bathrooms: { min: 1 }
move_in: { earliest: 2026-09-01, latest: 2026-10-15 }
amenities:
  laundry_in_unit: preferred      # in_unit | in_building | none
  laundry_in_building: required
  gym: preferred
  rooftop: preferred
  ac: preferred                   # NYC AC is rarely a searchable filter
  dishwasher: ignore
  pets: required
  no_fee: preferred               # broker-fee-free
run:
  sources: [aggregator, streeteasy]
  max_verify_per_run: 25          # hard cost cap
```

`profiles/natasha.yaml`: same shape, `name: natasha`, her email/criteria as placeholders (`email: natasha@example.com`, different `locations`).

- [ ] **Step 4: Write `tests/test_smoke.py`**

```python
import importlib

def test_package_imports():
    assert importlib.import_module("apthunt") is not None
```

- [ ] **Step 5: Verify install + collection**

Run: `pip install -e ".[dev]" && pytest -q`
Expected: PASS (1 test).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore .env.example README.md src profiles tests
git commit -m "chore: scaffold apthunt package, deps, example profiles"
```

> **Prerequisite for committing:** the repo needs a git identity. If `git commit` errors with "Please tell me who you are", run once:
> `git config user.email "zachriley36@gmail.com" && git config user.name "ZRiley36"`

---

## Task 2: Config schema & loader

**Files:**
- Create: `src/apthunt/config/schema.py`, `src/apthunt/config/loader.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `class Amenity(str, Enum)`: `REQUIRED="required"`, `PREFERRED="preferred"`, `IGNORE="ignore"`.
  - `class Profile(BaseModel)`: `name: str`, `email: str`, `enabled: bool`, `budget: Budget`, `locations: list[str]`, `bedrooms: RangeInt`, `bathrooms: RangeInt`, `move_in: MoveIn`, `amenities: dict[str, Amenity]`, `run: RunConfig`. Helper `required_amenities() -> list[str]` and `preferred_amenities() -> list[str]`.
  - `class Budget(BaseModel)`: `min: int`, `max: int`.
  - `class RangeInt(BaseModel)`: `min: int | None = None`, `max: int | None = None`.
  - `class MoveIn(BaseModel)`: `earliest: date | None`, `latest: date | None`.
  - `class RunConfig(BaseModel)`: `sources: list[str] = ["aggregator","streeteasy"]`, `max_verify_per_run: int = 25`.
  - `load_profiles(dir: Path = Path("profiles"), only: str | None = None) -> list[Profile]` — parses every `*.yaml`, returns enabled ones (or just `only`).

- [ ] **Step 1: Write failing tests** in `tests/test_config.py`

```python
from pathlib import Path
from datetime import date
from apthunt.config.schema import Profile, Amenity
from apthunt.config.loader import load_profiles

def test_profile_parses_amenities_tristate(tmp_path: Path):
    (tmp_path / "z.yaml").write_text(
        "name: z\nemail: z@e.com\nenabled: true\n"
        "budget: {min: 2000, max: 3800}\nlocations: [Bushwick]\n"
        "bedrooms: {min: 1}\nbathrooms: {min: 1}\n"
        "move_in: {earliest: 2026-09-01, latest: 2026-10-15}\n"
        "amenities: {laundry_in_building: required, gym: preferred, dishwasher: ignore}\n"
        "run: {sources: [aggregator], max_verify_per_run: 10}\n"
    )
    profiles = load_profiles(tmp_path)
    assert len(profiles) == 1
    p = profiles[0]
    assert p.required_amenities() == ["laundry_in_building"]
    assert p.preferred_amenities() == ["gym"]
    assert p.move_in.earliest == date(2026, 9, 1)

def test_disabled_profiles_excluded(tmp_path: Path):
    (tmp_path / "z.yaml").write_text(
        "name: z\nemail: z@e.com\nenabled: false\n"
        "budget: {min: 1, max: 2}\nlocations: [X]\nbedrooms: {}\nbathrooms: {}\n"
        "move_in: {}\namenities: {}\nrun: {}\n"
    )
    assert load_profiles(tmp_path) == []

def test_only_filter(tmp_path: Path):
    for n in ("a", "b"):
        (tmp_path / f"{n}.yaml").write_text(
            f"name: {n}\nemail: {n}@e.com\nenabled: true\n"
            "budget: {min: 1, max: 2}\nlocations: [X]\nbedrooms: {}\nbathrooms: {}\n"
            "move_in: {}\namenities: {}\nrun: {}\n"
        )
    got = load_profiles(tmp_path, only="b")
    assert [p.name for p in got] == ["b"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -q` → Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `schema.py`**

```python
from __future__ import annotations
from datetime import date
from enum import Enum
from pydantic import BaseModel, Field


class Amenity(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"
    IGNORE = "ignore"


class Budget(BaseModel):
    min: int
    max: int


class RangeInt(BaseModel):
    min: int | None = None
    max: int | None = None


class MoveIn(BaseModel):
    earliest: date | None = None
    latest: date | None = None


class RunConfig(BaseModel):
    sources: list[str] = Field(default_factory=lambda: ["aggregator", "streeteasy"])
    max_verify_per_run: int = 25


class Profile(BaseModel):
    name: str
    email: str
    enabled: bool = True
    budget: Budget
    locations: list[str]
    bedrooms: RangeInt = RangeInt()
    bathrooms: RangeInt = RangeInt()
    move_in: MoveIn = MoveIn()
    amenities: dict[str, Amenity] = Field(default_factory=dict)
    run: RunConfig = RunConfig()

    def required_amenities(self) -> list[str]:
        return [k for k, v in self.amenities.items() if v is Amenity.REQUIRED]

    def preferred_amenities(self) -> list[str]:
        return [k for k, v in self.amenities.items() if v is Amenity.PREFERRED]
```

- [ ] **Step 4: Implement `loader.py`**

```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_config.py -q` → Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/apthunt/config tests/test_config.py
git commit -m "feat(config): profile schema + loader with tri-state amenities"
```

---

## Task 3: Canonical Listing model & normalization

**Files:**
- Create: `src/apthunt/pipeline/normalize.py`, `tests/test_normalize.py`, `tests/fixtures/aggregator_raw.json`, `tests/fixtures/streeteasy_raw.json`

**Interfaces:**
- Consumes: raw provider dicts (a `RawListing` is just `{"source": str, "data": dict}` from Task 7; here we only need the shape, so define `RawListing` here as a small dataclass and re-export from `sources/base.py` in Task 7).
- Produces:
  - `@dataclass Listing`: `id: str` (stable canonical id = sha1 of `source|address|price`), `source: str`, `url: str`, `address: str`, `neighborhood: str | None`, `price: int | None`, `bedrooms: float | None`, `bathrooms: float | None`, `sqft: int | None`, `available_date: date | None`, `amenities_raw: dict[str, bool]` (best-effort provider flags), `photos: list[str]`, `description: str`, `is_active: bool = True`.
  - `normalize(raw: RawListing) -> Listing | None` — returns `None` for records missing price+url (unusable). Maps each provider's field names; unknown providers raise `KeyError` (caught upstream).
  - `canonical_id(source, address, price) -> str`.

- [ ] **Step 1: Write fixtures.** `tests/fixtures/aggregator_raw.json` (one representative record from the Real Estate Aggregator actor — during implementation, run the actor once and paste a real record; for the test use this stand-in shape):

```json
{"source": "aggregator",
 "data": {"url": "https://apartments.com/x/1", "formattedAddress": "123 Main St, Brooklyn, NY",
          "neighborhood": "Bushwick", "price": 3200, "bedrooms": 1, "bathrooms": 1, "squareFootage": 650,
          "availableDate": "2026-09-15", "photos": ["https://cdn/x1.jpg"],
          "description": "Sunny 1BR with in-building laundry and a gym.",
          "features": {"gym": true, "laundry": "building"}}}
```

`tests/fixtures/streeteasy_raw.json`:
```json
{"source": "streeteasy",
 "data": {"url": "https://streeteasy.com/building/y/2", "address": "45 Bedford Ave #3, Brooklyn, NY",
          "area": "Williamsburg", "price": 3500, "beds": 2, "baths": 1, "sqft": 800,
          "availableOn": "2026-10-01", "images": ["https://cdn/y2.jpg"],
          "description": "No-fee 2BR, roof deck, dishwasher.", "amenities": ["roof_deck", "dishwasher"]}}
```

- [ ] **Step 2: Write failing tests** in `tests/test_normalize.py`

```python
import json
from datetime import date
from pathlib import Path
from apthunt.pipeline.normalize import normalize, RawListing, canonical_id

FX = Path(__file__).parent / "fixtures"

def _raw(name):
    d = json.loads((FX / name).read_text())
    return RawListing(source=d["source"], data=d["data"])

def test_normalize_aggregator():
    lst = normalize(_raw("aggregator_raw.json"))
    assert lst is not None
    assert lst.price == 3200 and lst.bedrooms == 1
    assert lst.neighborhood == "Bushwick"
    assert lst.available_date == date(2026, 9, 15)
    assert lst.id == canonical_id("aggregator", "123 Main St, Brooklyn, NY", 3200)

def test_normalize_streeteasy():
    lst = normalize(_raw("streeteasy_raw.json"))
    assert lst.price == 3500 and lst.bathrooms == 1
    assert lst.neighborhood == "Williamsburg"

def test_unusable_returns_none():
    assert normalize(RawListing(source="aggregator", data={"description": "no price no url"})) is None
```

- [ ] **Step 3: Run tests to verify they fail** — Run: `pytest tests/test_normalize.py -q` → Expected: FAIL.

- [ ] **Step 4: Implement `normalize.py`**

```python
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from datetime import date


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
```

> **Implementation note:** the field names above (`formattedAddress`, `features.laundry`, `roof_deck`, …) are best-guess mappings. Before trusting them, run each actor once, capture a real record into the fixtures, and adjust `_agg`/`_se` to the actual keys. Keep the tests green against whatever real shapes you capture.

- [ ] **Step 5: Run tests to verify they pass** — Run: `pytest tests/test_normalize.py -q` → Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/apthunt/pipeline/normalize.py tests/test_normalize.py tests/fixtures
git commit -m "feat(pipeline): canonical Listing model + provider normalization"
```

---

## Task 4: Per-profile state store

**Files:**
- Create: `src/apthunt/state/store.py`, `tests/test_state.py`

**Interfaces:**
- Produces:
  - `load_state(name: str, dir: Path = Path("state")) -> dict[str, str]` — maps `listing_id -> first_seen_iso`; `{}` if the file doesn't exist.
  - `save_state(name: str, seen: dict[str, str], dir: Path = Path("state")) -> Path` — writes `state/<name>.json` (pretty, sorted keys) and returns the path.
  - `record_seen(seen: dict[str, str], listing_ids: list[str], today: str) -> dict[str, str]` — returns a new dict adding any missing ids with `first_seen=today` (pure).

- [ ] **Step 1: Write failing tests** in `tests/test_state.py`

```python
from pathlib import Path
from apthunt.state.store import load_state, save_state, record_seen

def test_roundtrip(tmp_path: Path):
    save_state("zach", {"abc": "2026-08-11"}, tmp_path)
    assert load_state("zach", tmp_path) == {"abc": "2026-08-11"}

def test_missing_is_empty(tmp_path: Path):
    assert load_state("nobody", tmp_path) == {}

def test_record_seen_only_adds_new():
    seen = {"a": "2026-08-01"}
    out = record_seen(seen, ["a", "b"], "2026-08-11")
    assert out == {"a": "2026-08-01", "b": "2026-08-11"}
    assert seen == {"a": "2026-08-01"}  # input untouched
```

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_state.py -q` → FAIL.

- [ ] **Step 3: Implement `store.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass** — `pytest tests/test_state.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/apthunt/state tests/test_state.py
git commit -m "feat(state): per-profile seen-listing store"
```

---

## Task 5: Dedup (new vs. already-seen)

**Files:**
- Create: `src/apthunt/pipeline/dedup.py`, `tests/test_dedup.py`

**Interfaces:**
- Consumes: `Listing` (Task 3), state dict (Task 4).
- Produces: `split_new(listings: list[Listing], seen: dict[str, str]) -> tuple[list[Listing], list[Listing]]` returning `(new, already_seen)`, and `dedupe_within(listings: list[Listing]) -> list[Listing]` collapsing duplicate ids across sources (keep first, prefer `streeteasy` over `aggregator` when ids collide by address+price — see note).

- [ ] **Step 1: Write failing tests** in `tests/test_dedup.py`

```python
from datetime import date
from apthunt.pipeline.normalize import Listing
from apthunt.pipeline.dedup import split_new, dedupe_within

def _l(id, source="aggregator"):
    return Listing(id=id, source=source, url="u", address="a", neighborhood=None,
                   price=3000, bedrooms=1, bathrooms=1, sqft=None, available_date=None)

def test_split_new():
    new, old = split_new([_l("a"), _l("b")], {"a": "2026-08-01"})
    assert [x.id for x in new] == ["b"]
    assert [x.id for x in old] == ["a"]

def test_dedupe_within_keeps_one():
    out = dedupe_within([_l("a"), _l("a")])
    assert [x.id for x in out] == ["a"]
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement `dedup.py`**

```python
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
```

> **Note on cross-source dedup:** `canonical_id` incorporates `source`, so the *same* physical unit from two providers gets two ids and won't collide here. That's acceptable for v1 (a duplicate appears at most twice, once per site, each linking to its own listing). A future improvement is an address+price fuzzy key; out of scope now (YAGNI).

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/apthunt/pipeline/dedup.py tests/test_dedup.py
git commit -m "feat(pipeline): dedup new vs seen"
```

---

## Task 6: Client-side filtering against profile criteria

**Files:**
- Create: `src/apthunt/pipeline/filter.py`, `tests/test_filter.py`

**Interfaces:**
- Consumes: `Listing` (Task 3), `Profile` (Task 2).
- Produces: `apply_filters(listings: list[Listing], profile: Profile) -> list[Listing]` — keeps a listing iff: price within `[budget.min, budget.max]` (unknown price kept — don't drop for missing data); beds within `bedrooms` range if the listing states beds; baths ≥ `bathrooms.min` if stated; neighborhood case-insensitively matches one of `profile.locations` (substring either direction, since providers phrase areas differently) OR is unknown; and move-in `available_date` (if stated) ≤ `move_in.latest`. **Required amenities are NOT filtered here** — that's the verifier's job (a required amenity absent from provider flags must still go to verification, never dropped). Provide `matches(listing, profile) -> tuple[bool, list[str]]` returning `(kept, reasons_dropped)` for observability.

- [ ] **Step 1: Write failing tests** in `tests/test_filter.py`

```python
from datetime import date
from apthunt.config.schema import Profile
from apthunt.pipeline.normalize import Listing
from apthunt.pipeline.filter import apply_filters

def _profile():
    return Profile.model_validate({
        "name": "z", "email": "z@e.com", "enabled": True,
        "budget": {"min": 2000, "max": 3800}, "locations": ["Bushwick"],
        "bedrooms": {"min": 1, "max": 2}, "bathrooms": {"min": 1},
        "move_in": {"latest": "2026-10-15"},
        "amenities": {"laundry_in_building": "required"}, "run": {},
    })

def _l(**kw):
    base = dict(id="x", source="aggregator", url="u", address="a", neighborhood="Bushwick",
               price=3000, bedrooms=1, bathrooms=1, sqft=None, available_date=None)
    base.update(kw)
    return Listing(**base)

def test_price_out_of_band_dropped():
    assert apply_filters([_l(price=5000)], _profile()) == []

def test_unknown_price_kept():
    assert len(apply_filters([_l(price=None)], _profile())) == 1

def test_wrong_neighborhood_dropped():
    assert apply_filters([_l(neighborhood="Harlem")], _profile()) == []

def test_late_move_in_dropped():
    assert apply_filters([_l(available_date=date(2026, 12, 1))], _profile()) == []

def test_required_amenity_absent_still_kept():
    # provider flag says no in-building laundry, but we must NOT drop here
    lst = _l()
    lst.amenities_raw = {"laundry_in_building": False}
    assert len(apply_filters([lst], _profile())) == 1
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement `filter.py`**

```python
from __future__ import annotations
from .normalize import Listing
from ..config.schema import Profile


def _location_ok(listing: Listing, profile: Profile) -> bool:
    if not listing.neighborhood:
        return True  # unknown — let verification decide, don't drop
    hood = listing.neighborhood.lower()
    return any(loc.lower() in hood or hood in loc.lower() for loc in profile.locations)


def matches(listing: Listing, profile: Profile) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if listing.price is not None and not (profile.budget.min <= listing.price <= profile.budget.max):
        reasons.append(f"price {listing.price} outside {profile.budget.min}-{profile.budget.max}")
    if listing.bedrooms is not None:
        if profile.bedrooms.min is not None and listing.bedrooms < profile.bedrooms.min:
            reasons.append("too few bedrooms")
        if profile.bedrooms.max is not None and listing.bedrooms > profile.bedrooms.max:
            reasons.append("too many bedrooms")
    if listing.bathrooms is not None and profile.bathrooms.min is not None:
        if listing.bathrooms < profile.bathrooms.min:
            reasons.append("too few bathrooms")
    if not _location_ok(listing, profile):
        reasons.append("neighborhood mismatch")
    if listing.available_date and profile.move_in.latest and listing.available_date > profile.move_in.latest:
        reasons.append("available after move-in window")
    return (not reasons, reasons)


def apply_filters(listings: list[Listing], profile: Profile) -> list[Listing]:
    return [l for l in listings if matches(l, profile)[0]]
```

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/apthunt/pipeline/filter.py tests/test_filter.py
git commit -m "feat(pipeline): client-side criteria filtering (amenities deferred to verify)"
```

---

## Task 7: Apify helper + source clients + fixture client

**Files:**
- Create: `src/apthunt/sources/base.py`, `src/apthunt/sources/apify.py`, `src/apthunt/sources/aggregator.py`, `src/apthunt/sources/streeteasy.py`, `src/apthunt/sources/fixtures.py`, `tests/test_sources.py`, `tests/fixtures/agg_dataset.json`

**Interfaces:**
- Consumes: `RawListing` (Task 3).
- Produces:
  - `base.py`: `class SourceClient(Protocol)` with `search(self, locations: list[str], price_min: int, price_max: int) -> list[RawListing]` and `fetch_detail(self, listing: Listing) -> Listing | None` (returns an enriched copy, or `None` if the listing is delisted). Re-export `RawListing` from `..pipeline.normalize`.
  - `apify.py`: `run_actor(actor_id: str, run_input: dict, token: str, client=None) -> list[dict]` — starts the actor, waits, returns dataset items. Thin wrapper over `apify_client.ApifyClient`; `client` param injectable for tests.
  - `aggregator.py`: `AggregatorClient(token, actor_id="tri_angle/real-estate-aggregator")` implementing `SourceClient`.
  - `streeteasy.py`: `StreetEasyClient(token, actor_id="jupri/streeteasy-scraper")` implementing `SourceClient`.
  - `fixtures.py`: `FixtureClient(records: list[RawListing])` — offline client for `--dry-run` and tests; `search` returns its records (filtered to matching locations by substring), `fetch_detail` echoes the listing unchanged.
  - `get_client(name: str, token: str) -> SourceClient` factory.

- [ ] **Step 1: Write `tests/fixtures/agg_dataset.json`** — a 2-item array shaped like the aggregator actor's dataset output (reuse the record from Task 3's fixture, plus one more out-of-area record).

- [ ] **Step 2: Write failing tests** in `tests/test_sources.py`

```python
import json
from pathlib import Path
from apthunt.sources.apify import run_actor
from apthunt.sources.fixtures import FixtureClient
from apthunt.pipeline.normalize import RawListing

FX = Path(__file__).parent / "fixtures"

class _FakeActor:
    def __init__(self, items): self._items = items
    def call(self, run_input=None): return {"defaultDatasetId": "ds1"}

class _FakeDataset:
    def __init__(self, items): self._items = items
    def iterate_items(self): yield from self._items

class _FakeApify:
    def __init__(self, items): self._items = items
    def actor(self, actor_id): return _FakeActor(self._items)
    def dataset(self, ds_id): return _FakeDataset(self._items)

def test_run_actor_returns_items():
    items = json.loads((FX / "agg_dataset.json").read_text())
    out = run_actor("x/y", {"q": "z"}, token="t", client=_FakeApify(items))
    assert out == items

def test_fixture_client_filters_by_location():
    recs = [RawListing("aggregator", {"url": "u1", "price": 3000, "neighborhood": "Bushwick",
                                       "formattedAddress": "1 A St"}),
            RawListing("aggregator", {"url": "u2", "price": 3000, "neighborhood": "Harlem",
                                      "formattedAddress": "2 B St"})]
    client = FixtureClient(recs)
    got = client.search(["Bushwick"], 2000, 4000)
    assert [r.data["url"] for r in got] == ["u1"]
```

- [ ] **Step 3: Run to verify fail** — FAIL.

- [ ] **Step 4: Implement `base.py`**

```python
from __future__ import annotations
from typing import Protocol
from ..pipeline.normalize import RawListing, Listing

__all__ = ["SourceClient", "RawListing", "Listing"]


class SourceClient(Protocol):
    def search(self, locations: list[str], price_min: int, price_max: int) -> list[RawListing]: ...
    def fetch_detail(self, listing: Listing) -> Listing | None: ...
```

- [ ] **Step 5: Implement `apify.py`**

```python
from __future__ import annotations


def run_actor(actor_id: str, run_input: dict, token: str, client=None) -> list[dict]:
    if client is None:
        from apify_client import ApifyClient
        client = ApifyClient(token)
    run = client.actor(actor_id).call(run_input=run_input)
    dataset_id = run["defaultDatasetId"]
    return list(client.dataset(dataset_id).iterate_items())
```

- [ ] **Step 6: Implement `aggregator.py`, `streeteasy.py`, `fixtures.py`**

```python
# aggregator.py
from __future__ import annotations
from .base import RawListing, Listing
from .apify import run_actor


class AggregatorClient:
    def __init__(self, token: str, actor_id: str = "tri_angle/real-estate-aggregator"):
        self.token, self.actor_id = token, actor_id

    def search(self, locations, price_min, price_max) -> list[RawListing]:
        run_input = {"locations": locations, "listingType": "rent",
                     "priceMin": price_min, "priceMax": price_max,
                     "providers": ["apartments", "zillow", "zumper", "redfin", "realtor"]}
        items = run_actor(self.actor_id, run_input, self.token)
        return [RawListing("aggregator", it) for it in items]

    def fetch_detail(self, listing: Listing) -> Listing | None:
        # Aggregator records already carry description/photos; re-run a single-URL
        # scrape only if is_active must be re-confirmed. For v1, trust the record.
        return listing
```

```python
# streeteasy.py
from __future__ import annotations
from .base import RawListing, Listing
from .apify import run_actor


class StreetEasyClient:
    def __init__(self, token: str, actor_id: str = "jupri/streeteasy-scraper"):
        self.token, self.actor_id = token, actor_id

    def search(self, locations, price_min, price_max) -> list[RawListing]:
        run_input = {"areas": locations, "type": "rentals",
                     "minPrice": price_min, "maxPrice": price_max}
        items = run_actor(self.actor_id, run_input, self.token)
        return [RawListing("streeteasy", it) for it in items]

    def fetch_detail(self, listing: Listing) -> Listing | None:
        return listing
```

```python
# fixtures.py
from __future__ import annotations
from .base import RawListing, Listing


class FixtureClient:
    def __init__(self, records: list[RawListing]):
        self._records = records

    def search(self, locations, price_min, price_max) -> list[RawListing]:
        wanted = [loc.lower() for loc in locations]
        out = []
        for r in self._records:
            hood = str(r.data.get("neighborhood") or r.data.get("area") or "").lower()
            if not wanted or any(w in hood or hood in w for w in wanted):
                out.append(r)
        return out

    def fetch_detail(self, listing: Listing) -> Listing | None:
        return listing


def get_client(name: str, token: str):
    from .aggregator import AggregatorClient
    from .streeteasy import StreetEasyClient
    return {"aggregator": AggregatorClient, "streeteasy": StreetEasyClient}[name](token)
```

- [ ] **Step 7: Run to verify pass** — `pytest tests/test_sources.py -q` → PASS.

- [ ] **Step 8: Commit**

```bash
git add src/apthunt/sources tests/test_sources.py tests/fixtures/agg_dataset.json
git commit -m "feat(sources): apify helper, aggregator/streeteasy/fixture clients"
```

> **Implementation note:** actor IDs and `run_input` shapes are best-guess. Before wiring: confirm each actor on Apify, read its input schema, run it once, and adjust `run_input` keys + Task 3 normalization to the real output. If `jupri/streeteasy-scraper` is unavailable, substitute another StreetEasy actor and keep the `RawListing("streeteasy", ...)` contract.

---

## Task 8: Verification agent (Claude Haiku, structured output)

**Files:**
- Create: `src/apthunt/llm.py`, `src/apthunt/pipeline/verify.py`, `tests/test_verify.py`

**Interfaces:**
- Consumes: `Listing` (Task 3), `Profile` (Task 2).
- Produces:
  - `llm.py`: `class VerificationResult(BaseModel)` with `is_active: bool`, `scam_risk: Literal["low","medium","high"]`, `scam_reasons: list[str]`, `amenity_findings: dict[str, Literal["confirmed","unconfirmed","contradicted"]]`, `summary: str` (≤ 2 sentences). Also `build_verify_messages(listing, profile) -> list[dict]` (text + up to 4 image URL blocks) and `default_anthropic() -> anthropic.Anthropic`.
  - `verify.py`: `verify_listing(listing: Listing, profile: Profile, *, client, model="claude-haiku-4-5") -> VerificationResult` — calls `client.messages.parse(model=..., max_tokens=1024, messages=..., output_format=VerificationResult)` and returns `.parsed_output`. `client` is injectable so tests pass a fake.

- [ ] **Step 1: Write failing tests** in `tests/test_verify.py`

```python
from apthunt.llm import VerificationResult
from apthunt.pipeline.verify import verify_listing
from apthunt.pipeline.normalize import Listing
from apthunt.config.schema import Profile

def _profile():
    return Profile.model_validate({"name": "z", "email": "z@e.com", "enabled": True,
        "budget": {"min": 1, "max": 9999}, "locations": ["Bushwick"], "bedrooms": {},
        "bathrooms": {}, "move_in": {}, "amenities": {"laundry_in_building": "required"}, "run": {}})

def _listing():
    return Listing(id="x", source="aggregator", url="u", address="1 A St", neighborhood="Bushwick",
                   price=3000, bedrooms=1, bathrooms=1, sqft=None, available_date=None,
                   description="1BR with laundry in building", photos=["https://cdn/a.jpg"])

class _FakeParsed:
    def __init__(self, obj): self.parsed_output = obj

class _FakeMessages:
    def __init__(self, obj): self._obj = obj
    def parse(self, **kw):
        assert kw["model"] == "claude-haiku-4-5"
        assert kw["max_tokens"] >= 1024
        return _FakeParsed(self._obj)

class _FakeClient:
    def __init__(self, obj): self.messages = _FakeMessages(obj)

def test_verify_returns_parsed():
    vr = VerificationResult(is_active=True, scam_risk="low", scam_reasons=[],
                            amenity_findings={"laundry_in_building": "confirmed"}, summary="Nice 1BR.")
    out = verify_listing(_listing(), _profile(), client=_FakeClient(vr))
    assert out.amenity_findings["laundry_in_building"] == "confirmed"
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement `llm.py`**

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class VerificationResult(BaseModel):
    is_active: bool
    scam_risk: Literal["low", "medium", "high"]
    scam_reasons: list[str] = Field(default_factory=list)
    amenity_findings: dict[str, Literal["confirmed", "unconfirmed", "contradicted"]] = Field(default_factory=dict)
    summary: str


def default_anthropic():
    import anthropic
    return anthropic.Anthropic()  # reads ANTHROPIC_API_KEY


def build_verify_messages(listing, profile) -> list[dict]:
    required = profile.required_amenities()
    instruction = (
        "You are verifying a NYC rental listing for a renter. Using the details and "
        "photos below, determine: (1) does it look like a real, currently-active listing "
        "(is_active); (2) scam_risk (low/medium/high) with scam_reasons — flag implausibly "
        "low price for the area, no real address, requests to pay/wire off-platform, or "
        "recycled/stock-looking photos; (3) for EACH required amenity, mark confirmed / "
        "unconfirmed (not mentioned) / contradicted (evidence it's absent); (4) a <=2 "
        "sentence summary. Required amenities: " + ", ".join(required or ["(none)"]) + ".\n\n"
        f"Address: {listing.address}\nNeighborhood: {listing.neighborhood}\n"
        f"Price: {listing.price}  Beds: {listing.bedrooms}  Baths: {listing.bathrooms}\n"
        f"Provider amenity flags: {listing.amenities_raw}\n"
        f"Description: {listing.description}\nURL: {listing.url}"
    )
    content: list[dict] = [{"type": "text", "text": instruction}]
    for url in listing.photos[:4]:
        content.append({"type": "image", "source": {"type": "url", "url": url}})
    return [{"role": "user", "content": content}]
```

- [ ] **Step 4: Implement `verify.py`**

```python
from __future__ import annotations
from ..llm import VerificationResult, build_verify_messages


def verify_listing(listing, profile, *, client, model: str = "claude-haiku-4-5") -> VerificationResult:
    resp = client.messages.parse(
        model=model,
        max_tokens=1024,
        messages=build_verify_messages(listing, profile),
        output_format=VerificationResult,
    )
    return resp.parsed_output
```

- [ ] **Step 5: Run to verify pass** — PASS.

- [ ] **Step 6: Commit**

```bash
git add src/apthunt/llm.py src/apthunt/pipeline/verify.py tests/test_verify.py
git commit -m "feat(verify): Claude Haiku listing verification with structured output"
```

---

## Task 9: Grading rules (pure)

**Files:**
- Create: `src/apthunt/pipeline/grade.py`, `tests/test_grade.py`

**Interfaces:**
- Consumes: `VerificationResult` (Task 8), `Listing` (Task 3), `Profile` (Task 2).
- Produces:
  - `class Grade(str, Enum)`: `APPLY="Apply now"`, `CONSIDER="Consider"`, `NOPE="Probably not"`.
  - `@dataclass Graded`: `listing: Listing`, `verification: VerificationResult`, `grade: Grade`, `rationale: str`, `score: int`.
  - `grade_listing(listing, verification, profile) -> Graded` implementing the rules:
    - high scam risk OR not active OR any required amenity **contradicted** ⇒ `NOPE`.
    - any required amenity **unconfirmed** (none contradicted) ⇒ at most `CONSIDER`, rationale notes "verify: <amenities>".
    - all required amenities confirmed ⇒ `APPLY`, unless price is in the top 15% of budget with few preferred amenities → `CONSIDER` (mild tie-break).
    - `score` = count of confirmed required + confirmed/likely preferred amenities, minus scam penalty — used only for ranking.

- [ ] **Step 1: Write failing tests** in `tests/test_grade.py`

```python
from apthunt.pipeline.grade import grade_listing, Grade
from apthunt.pipeline.normalize import Listing
from apthunt.llm import VerificationResult
from apthunt.config.schema import Profile

def _p(required=("laundry_in_building",), preferred=("gym",)):
    am = {a: "required" for a in required} | {a: "preferred" for a in preferred}
    return Profile.model_validate({"name": "z", "email": "z@e.com", "enabled": True,
        "budget": {"min": 2000, "max": 4000}, "locations": ["Bushwick"], "bedrooms": {},
        "bathrooms": {}, "move_in": {}, "amenities": am, "run": {}})

def _l(price=3000):
    return Listing(id="x", source="aggregator", url="u", address="a", neighborhood="Bushwick",
                   price=price, bedrooms=1, bathrooms=1, sqft=None, available_date=None)

def _v(active=True, risk="low", findings=None):
    return VerificationResult(is_active=active, scam_risk=risk, scam_reasons=[],
                              amenity_findings=findings or {}, summary="s")

def test_contradicted_required_is_nope():
    g = grade_listing(_l(), _v(findings={"laundry_in_building": "contradicted"}), _p())
    assert g.grade == Grade.NOPE

def test_high_scam_is_nope():
    g = grade_listing(_l(), _v(risk="high"), _p())
    assert g.grade == Grade.NOPE

def test_unconfirmed_required_is_consider():
    g = grade_listing(_l(), _v(findings={"laundry_in_building": "unconfirmed"}), _p())
    assert g.grade == Grade.CONSIDER
    assert "verify" in g.rationale.lower()

def test_all_confirmed_is_apply():
    g = grade_listing(_l(price=2500), _v(findings={"laundry_in_building": "confirmed"}), _p())
    assert g.grade == Grade.APPLY
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement `grade.py`**

```python
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

    # all required confirmed
    top_band = listing.price is not None and listing.price >= profile.budget.min + \
        0.85 * (profile.budget.max - profile.budget.min)
    if top_band and not confirmed_pref:
        return Graded(listing, verification, Grade.CONSIDER,
                      "Meets must-haves but near top of budget with few extras.", score)
    return Graded(listing, verification, Grade.APPLY,
                  "All required amenities confirmed; within budget.", score + 3)
```

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/apthunt/pipeline/grade.py tests/test_grade.py
git commit -m "feat(grade): apply/consider/probably-not rules from verification"
```

---

## Task 10: Report ranking & context

**Files:**
- Create: `src/apthunt/pipeline/report.py`, `tests/test_report.py`

**Interfaces:**
- Consumes: `Graded` (Task 9), state (Task 4).
- Produces:
  - `build_report(graded: list[Graded], seen: dict[str, str], profile, generated_at: str) -> ReportContext`.
  - `@dataclass ReportContext`: `profile_name: str`, `generated_at: str`, `apply: list[Card]`, `consider: list[Card]`, `nope_count: int`, `new_ids: list[str]`. Excludes `NOPE` from the cards but reports how many were filtered out.
  - `@dataclass Card`: `url, address, neighborhood, price, beds, baths, grade, rationale, summary, photo, is_new, matched_amenities`.
  - Ranking: within Apply and Consider, sort by `score` desc, then price asc. `is_new` = id not in `seen` before this run (caller passes the pre-run `seen`).

- [ ] **Step 1: Write failing tests** in `tests/test_report.py`

```python
from apthunt.pipeline.report import build_report
from apthunt.pipeline.grade import Graded, Grade
from apthunt.pipeline.normalize import Listing
from apthunt.llm import VerificationResult
from apthunt.config.schema import Profile

def _p(): return Profile.model_validate({"name": "z", "email": "z@e.com", "enabled": True,
    "budget": {"min": 1, "max": 9999}, "locations": ["X"], "bedrooms": {}, "bathrooms": {},
    "move_in": {}, "amenities": {}, "run": {}})

def _graded(id, grade, score, price=3000):
    l = Listing(id=id, source="s", url="u", address="a", neighborhood="X", price=price,
                bedrooms=1, bathrooms=1, sqft=None, available_date=None, photos=["p"])
    v = VerificationResult(is_active=True, scam_risk="low", amenity_findings={}, summary="sum")
    return Graded(l, v, grade, "why", score)

def test_nope_excluded_but_counted():
    ctx = build_report([_graded("a", Grade.APPLY, 5), _graded("b", Grade.NOPE, -1)],
                       seen={}, profile=_p(), generated_at="2026-08-11T08:00")
    assert [c.address for c in ctx.apply] == ["a"]
    assert ctx.nope_count == 1

def test_new_flag_and_ranking():
    ctx = build_report([_graded("a", Grade.APPLY, 2, price=3000),
                        _graded("b", Grade.APPLY, 9, price=3500)],
                       seen={"a": "2026-08-01"}, profile=_p(), generated_at="t")
    assert [c.address for c in ctx.apply] == ["b", "a"]  # higher score first
    assert ctx.apply[1].is_new is False and ctx.apply[0].is_new is True
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement `report.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/apthunt/pipeline/report.py tests/test_report.py
git commit -m "feat(report): rank graded listings into report context"
```

---

## Task 11: Slug + HTML rendering

**Files:**
- Create: `src/apthunt/delivery/slug.py`, `src/apthunt/delivery/render.py`, `src/apthunt/templates/report.html.j2`, `tests/test_render.py`

**Interfaces:**
- Produces:
  - `slug.py`: `report_slug(profile_name: str, salt: str) -> str` = first 10 hex of `sha256(f"{salt}:{profile_name}")` — stable across runs, unguessable without the salt.
  - `render.py`: `render_report(ctx: ReportContext) -> str` (HTML string via Jinja2, autoescape on) and `report_path(profile_name, salt, root=Path("site")) -> Path` = `site/r/<name>-<slug>.html`.
  - Template: self-contained (inline `<style>`), theme-neutral, cards with photo/price/beds/baths/grade badge/summary/rationale/"NEW" badge/direct link; a "Consider" section; and a footer line "N listings filtered out as not-a-match this run."

- [ ] **Step 1: Write failing tests** in `tests/test_render.py`

```python
from apthunt.delivery.slug import report_slug
from apthunt.delivery.render import render_report, report_path
from apthunt.pipeline.report import ReportContext, Card

def test_slug_stable_and_unguessable():
    a = report_slug("zach", "salt1")
    assert a == report_slug("zach", "salt1")
    assert a != report_slug("zach", "salt2")
    assert a != report_slug("natasha", "salt1")

def test_render_contains_card_fields():
    card = Card(url="https://x/1", address="1 A St", neighborhood="Bushwick", price=3200,
               beds=1, baths=1, grade="Apply now", rationale="looks great", summary="Nice.",
               photo="https://cdn/a.jpg", is_new=True, matched_amenities=["gym"])
    ctx = ReportContext("zach", "2026-08-11T08:00", apply=[card], consider=[], nope_count=3, new_ids=[])
    html = render_report(ctx)
    assert "1 A St" in html and "Apply now" in html and "https://x/1" in html
    assert "NEW" in html and "3 listings" in html

def test_report_path():
    p = report_path("zach", "salt1")
    assert p.name.startswith("zach-") and p.suffix == ".html"
    assert p.parent.name == "r"
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement `slug.py`**

```python
from __future__ import annotations
import hashlib


def report_slug(profile_name: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{profile_name}".encode()).hexdigest()[:10]
```

- [ ] **Step 4: Implement `render.py`**

```python
from __future__ import annotations
import os
from pathlib import Path
from jinja2 import Environment, PackageLoader, select_autoescape
from .slug import report_slug

_env = Environment(loader=PackageLoader("apthunt", "templates"),
                   autoescape=select_autoescape(["html"]))


def render_report(ctx) -> str:
    return _env.get_template("report.html.j2").render(ctx=ctx)


def report_path(profile_name: str, salt: str | None = None, root: Path = Path("site")) -> Path:
    salt = salt if salt is not None else os.environ.get("REPORT_SLUG_SALT", "dev-salt")
    slug = report_slug(profile_name, salt)
    return Path(root) / "r" / f"{profile_name}-{slug}.html"
```

- [ ] **Step 5: Implement `templates/report.html.j2`**

```html
<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Apartment matches — {{ ctx.profile_name }}</title>
<style>
  :root{color-scheme:light dark}
  body{font:16px/1.5 system-ui,sans-serif;margin:0;padding:1.25rem;max-width:900px;margin-inline:auto}
  h1{font-size:1.4rem} h2{margin-top:2rem}
  .card{border:1px solid #8884;border-radius:12px;padding:1rem;margin:1rem 0;display:flex;gap:1rem}
  .card img{width:160px;height:120px;object-fit:cover;border-radius:8px;flex:none}
  .badge{display:inline-block;padding:.1rem .5rem;border-radius:999px;font-size:.8rem;font-weight:600}
  .apply{background:#1a7f4b;color:#fff}.consider{background:#b7791f;color:#fff}
  .new{background:#2563eb;color:#fff;margin-left:.4rem}
  .price{font-weight:700} .muted{opacity:.7;font-size:.9rem}
  a.btn{display:inline-block;margin-top:.5rem}
</style></head><body>
<h1>Apartment matches — {{ ctx.profile_name }}</h1>
<p class="muted">Generated {{ ctx.generated_at }}</p>
{% macro card(c) %}
  <div class="card">
    {% if c.photo %}<img src="{{ c.photo }}" alt="listing photo">{% endif %}
    <div>
      <span class="badge {{ 'apply' if c.grade=='Apply now' else 'consider' }}">{{ c.grade }}</span>
      {% if c.is_new %}<span class="badge new">NEW</span>{% endif %}
      <div><span class="price">${{ c.price or '?' }}/mo</span>
        · {{ c.beds }}bd/{{ c.baths }}ba · {{ c.neighborhood or 'NYC' }}</div>
      <div>{{ c.address }}</div>
      <div>{{ c.summary }}</div>
      <div class="muted">{{ c.rationale }}
        {% if c.matched_amenities %}· confirmed: {{ c.matched_amenities|join(', ') }}{% endif %}</div>
      <a class="btn" href="{{ c.url }}" target="_blank" rel="noopener">View listing →</a>
    </div>
  </div>
{% endmacro %}
<h2>Apply now ({{ ctx.apply|length }})</h2>
{% for c in ctx.apply %}{{ card(c) }}{% else %}<p class="muted">Nothing this run.</p>{% endfor %}
<h2>Consider ({{ ctx.consider|length }})</h2>
{% for c in ctx.consider %}{{ card(c) }}{% else %}<p class="muted">Nothing this run.</p>{% endfor %}
<p class="muted">{{ ctx.nope_count }} listings filtered out as not-a-match this run.</p>
</body></html>
```

- [ ] **Step 6: Run to verify pass** — `pytest tests/test_render.py -q` → PASS. (Ensure `templates/` ships in the package — it does via `PackageLoader`; add `[tool.setuptools.package-data]` `apthunt = ["templates/*.j2"]` to `pyproject.toml` if editable install can't find it.)

- [ ] **Step 7: Commit**

```bash
git add src/apthunt/delivery/slug.py src/apthunt/delivery/render.py src/apthunt/templates tests/test_render.py pyproject.toml
git commit -m "feat(render): unguessable slug + self-contained HTML report"
```

---

## Task 12: Email delivery

**Files:**
- Create: `src/apthunt/delivery/email.py`, `tests/test_email.py`

**Interfaces:**
- Produces:
  - `build_email(profile, ctx, report_url: str) -> EmailMessage` — subject `"N new apartment match(es) — <name>"`, HTML body listing new Apply/Consider cards + the report link; returns a `email.message.EmailMessage`.
  - `send_email(msg, *, smtp=None) -> None` — sends via `smtplib.SMTP` STARTTLS using env (`SMTP_HOST/PORT/USER/PASSWORD`, `MAIL_FROM`); `smtp` injectable for tests. No-op with a logged warning if SMTP env is unset (so `--dry-run` and CI without mail secrets don't crash).
  - `new_match_count(ctx) -> int` — number of `is_new` cards across Apply+Consider (drives "send or not").

- [ ] **Step 1: Write failing tests** in `tests/test_email.py`

```python
from apthunt.delivery.email import build_email, send_email, new_match_count
from apthunt.pipeline.report import ReportContext, Card
from apthunt.config.schema import Profile

def _ctx(new=True):
    c = Card(url="https://x/1", address="1 A St", neighborhood="Bushwick", price=3000, beds=1,
             baths=1, grade="Apply now", rationale="r", summary="s", photo=None, is_new=new)
    return ReportContext("zach", "t", apply=[c], consider=[], nope_count=0, new_ids=[])

def _p(): return Profile.model_validate({"name": "zach", "email": "z@e.com", "enabled": True,
    "budget": {"min": 1, "max": 2}, "locations": ["X"], "bedrooms": {}, "bathrooms": {},
    "move_in": {}, "amenities": {}, "run": {}})

def test_new_match_count():
    assert new_match_count(_ctx(new=True)) == 1
    assert new_match_count(_ctx(new=False)) == 0

def test_build_email_fields():
    msg = build_email(_p(), _ctx(), "https://site/r/zach-abc.html")
    assert msg["To"] == "z@e.com"
    assert "1 new" in msg["Subject"]
    assert "https://site/r/zach-abc.html" in msg.get_content()

class _FakeSMTP:
    sent = []
    def __init__(self, *a, **k): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self): pass
    def login(self, u, p): pass
    def send_message(self, m): _FakeSMTP.sent.append(m)

def test_send_uses_smtp(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "h"); monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "u"); monkeypatch.setenv("SMTP_PASSWORD", "p")
    monkeypatch.setenv("MAIL_FROM", "from@e.com")
    send_email(build_email(_p(), _ctx(), "url"), smtp=_FakeSMTP)
    assert len(_FakeSMTP.sent) == 1
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement `email.py`**

```python
from __future__ import annotations
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("apthunt.email")


def new_match_count(ctx) -> int:
    return sum(1 for c in (*ctx.apply, *ctx.consider) if c.is_new)


def build_email(profile, ctx, report_url: str) -> EmailMessage:
    n = new_match_count(ctx)
    msg = EmailMessage()
    msg["Subject"] = f"{n} new apartment match{'es' if n != 1 else ''} — {profile.name}"
    msg["To"] = profile.email
    lines = [f"<p>{n} new match(es). <a href='{report_url}'>Open full report</a></p><ul>"]
    for c in (*ctx.apply, *ctx.consider):
        if c.is_new:
            lines.append(f"<li><b>{c.grade}</b> — ${c.price}/mo, {c.beds}bd, "
                         f"{c.neighborhood} — <a href='{c.url}'>{c.address}</a><br>{c.summary}</li>")
    lines.append("</ul>")
    msg.set_content("New matches — open in an HTML-capable client.")
    msg.add_alternative("".join(lines), subtype="html")
    return msg


def send_email(msg: EmailMessage, *, smtp=None) -> None:
    host = os.environ.get("SMTP_HOST")
    if not host:
        log.warning("SMTP not configured; skipping email to %s", msg["To"])
        return
    smtp = smtp or smtplib.SMTP
    msg["From"] = os.environ["MAIL_FROM"]
    with smtp(host, int(os.environ.get("SMTP_PORT", "587"))) as server:
        server.starttls()
        server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        server.send_message(msg)
```

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/apthunt/delivery/email.py tests/test_email.py
git commit -m "feat(email): new-match email via SMTP (no-op when unconfigured)"
```

---

## Task 13: LangGraph pipeline wiring

**Files:**
- Create: `src/apthunt/pipeline/graph.py`, `tests/test_graph.py`, `tests/fixtures/pipeline_records.json`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `class HuntState(TypedDict)`: `profile`, `seen`, `clients` (list of `SourceClient`), `llm_client`, `raw` (list[RawListing]), `listings`, `candidates`, `graded`, `ctx`, `generated_at`, `verify_model`.
  - `build_graph() -> CompiledGraph` — nodes: `search` → `normalize_filter_dedup` → `verify_all` → `report`. `verify_all` iterates candidates up to `profile.run.max_verify_per_run`, calling `verify_listing` then `grade_listing` (LangGraph fan-out via a simple loop inside the node keeps it deterministic and easy to cap; a `Send`-based map is a future optimization).
  - `run_profile(profile, *, clients, llm_client, seen, generated_at, verify_model="claude-haiku-4-5") -> ReportContext` — convenience wrapper that invokes the compiled graph and returns `state["ctx"]`.

- [ ] **Step 1: Write `tests/fixtures/pipeline_records.json`** — an array of 3 `{"source","data"}` records: one clean Bushwick match, one out-of-area (Harlem), one over-budget. (Reuse Task 3/7 shapes.)

- [ ] **Step 2: Write failing test** in `tests/test_graph.py`

```python
import json
from pathlib import Path
from apthunt.pipeline.graph import run_profile
from apthunt.sources.fixtures import FixtureClient
from apthunt.pipeline.normalize import RawListing
from apthunt.llm import VerificationResult
from apthunt.config.schema import Profile

FX = Path(__file__).parent / "fixtures"

def _profile():
    return Profile.model_validate({"name": "zach", "email": "z@e.com", "enabled": True,
        "budget": {"min": 2000, "max": 3800}, "locations": ["Bushwick"], "bedrooms": {"min": 1},
        "bathrooms": {"min": 1}, "move_in": {}, "amenities": {"laundry_in_building": "required"},
        "run": {"sources": ["aggregator"], "max_verify_per_run": 25}})

class _FakeMessages:
    def parse(self, **kw):
        class R: parsed_output = VerificationResult(
            is_active=True, scam_risk="low",
            amenity_findings={"laundry_in_building": "confirmed"}, summary="Nice.")
        return R()

class _FakeLLM:
    messages = _FakeMessages()

def test_pipeline_end_to_end_dry():
    recs = [RawListing(r["source"], r["data"]) for r in json.loads((FX / "pipeline_records.json").read_text())]
    ctx = run_profile(_profile(), clients=[FixtureClient(recs)], llm_client=_FakeLLM(),
                      seen={}, generated_at="2026-08-11T08:00")
    # Only the in-area, in-budget listing survives filtering and grades Apply.
    assert len(ctx.apply) == 1
    assert ctx.apply[0].neighborhood.lower().startswith("bushwick")
    assert ctx.apply[0].is_new is True
```

- [ ] **Step 3: Run to verify fail** — FAIL.

- [ ] **Step 4: Implement `graph.py`**

```python
from __future__ import annotations
from typing import Any, TypedDict
from langgraph.graph import StateGraph, START, END
from .normalize import normalize
from .dedup import dedupe_within, split_new
from .filter import apply_filters
from .verify import verify_listing
from .grade import grade_listing
from .report import build_report


class HuntState(TypedDict, total=False):
    profile: Any
    seen: dict
    clients: list
    llm_client: Any
    verify_model: str
    generated_at: str
    raw: list
    listings: list
    candidates: list
    graded: list
    ctx: Any


def _search(state: HuntState) -> HuntState:
    profile = state["profile"]
    raw: list = []
    for client in state["clients"]:
        raw.extend(client.search(profile.locations, profile.budget.min, profile.budget.max))
    return {"raw": raw}


def _normalize_filter_dedup(state: HuntState) -> HuntState:
    profile = state["profile"]
    listings = [n for r in state["raw"] if (n := normalize(r)) is not None]
    listings = dedupe_within(listings)
    listings = apply_filters(listings, profile)
    new, _old = split_new(listings, state["seen"])
    return {"listings": listings, "candidates": new}


def _verify_all(state: HuntState) -> HuntState:
    profile = state["profile"]
    model = state.get("verify_model", "claude-haiku-4-5")
    graded = []
    for listing in state["candidates"][: profile.run.max_verify_per_run]:
        detail = listing
        for client in state["clients"]:
            if client.__class__.__name__.lower().startswith(listing.source[:4]) or True:
                enriched = client.fetch_detail(listing)
                if enriched is not None:
                    detail = enriched
                break
        vr = verify_listing(detail, profile, client=state["llm_client"], model=model)
        graded.append(grade_listing(detail, vr, profile))
    return {"graded": graded}


def _report(state: HuntState) -> HuntState:
    ctx = build_report(state["graded"], state["seen"], state["profile"], state["generated_at"])
    return {"ctx": ctx}


def build_graph():
    g = StateGraph(HuntState)
    g.add_node("search", _search)
    g.add_node("nfd", _normalize_filter_dedup)
    g.add_node("verify", _verify_all)
    g.add_node("report", _report)
    g.add_edge(START, "search")
    g.add_edge("search", "nfd")
    g.add_edge("nfd", "verify")
    g.add_edge("verify", "report")
    g.add_edge("report", END)
    return g.compile()


def run_profile(profile, *, clients, llm_client, seen, generated_at,
                verify_model: str = "claude-haiku-4-5"):
    state = build_graph().invoke({
        "profile": profile, "clients": clients, "llm_client": llm_client, "seen": seen,
        "generated_at": generated_at, "verify_model": verify_model,
    })
    return state["ctx"]
```

- [ ] **Step 5: Run to verify pass** — `pytest tests/test_graph.py -q` → PASS.

- [ ] **Step 6: Commit**

```bash
git add src/apthunt/pipeline/graph.py tests/test_graph.py tests/fixtures/pipeline_records.json
git commit -m "feat(pipeline): LangGraph wiring of search->filter->verify->report"
```

---

## Task 14: CLI entrypoint (real run + dry-run)

**Files:**
- Create: `src/apthunt/main.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: everything.
- Produces:
  - `run(profiles, *, dry_run: bool, clients_for, llm_client, salt, today, site_root, state_dir) -> list[Path]` — for each profile: load pre-run `seen`; run the graph; render + write the HTML report; record all surfaced ids into state and save; build + send email if there are new matches (skipped in dry-run). Returns written report paths. **Cross-profile fetch pooling:** `clients_for(profile)` returns clients; a caching wrapper (`PooledClient`) memoizes `search(locations,...)` by a frozenset(locations)+price key so two profiles sharing a location trigger one actor run.
  - `cli()` — argparse: `--dry-run`, `--profile NAME`, `--profiles-dir`, `--site`, `--state`. Loads `.env` via `python-dotenv`; builds real Apify + Anthropic clients unless `--dry-run` (which loads `tests/fixtures/pipeline_records.json` via `FixtureClient` and a canned LLM stub).

- [ ] **Step 1: Write failing test** in `tests/test_main.py`

```python
import json
from pathlib import Path
from apthunt.main import run
from apthunt.sources.fixtures import FixtureClient
from apthunt.pipeline.normalize import RawListing
from apthunt.llm import VerificationResult
from apthunt.config.schema import Profile

FX = Path(__file__).parent / "fixtures"

def _profile():
    return Profile.model_validate({"name": "zach", "email": "z@e.com", "enabled": True,
        "budget": {"min": 2000, "max": 3800}, "locations": ["Bushwick"], "bedrooms": {"min": 1},
        "bathrooms": {"min": 1}, "move_in": {}, "amenities": {"laundry_in_building": "required"},
        "run": {"sources": ["aggregator"], "max_verify_per_run": 25}})

class _LLM:
    class messages:
        @staticmethod
        def parse(**kw):
            class R: parsed_output = VerificationResult(is_active=True, scam_risk="low",
                amenity_findings={"laundry_in_building": "confirmed"}, summary="Nice.")
            return R()

def test_run_writes_report_and_state(tmp_path):
    recs = [RawListing(r["source"], r["data"]) for r in json.loads((FX / "pipeline_records.json").read_text())]
    paths = run([_profile()], dry_run=True, clients_for=lambda p: [FixtureClient(recs)],
                llm_client=_LLM(), salt="salt1", today="2026-08-11",
                site_root=tmp_path / "site", state_dir=tmp_path / "state")
    assert paths and paths[0].exists()
    assert "Apply now" in paths[0].read_text()
    assert (tmp_path / "state" / "zach.json").exists()
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement `main.py`**

```python
from __future__ import annotations
import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from .config.loader import load_profiles
from .pipeline.graph import run_profile
from .state.store import load_state, save_state, record_seen
from .delivery.render import render_report, report_path
from .delivery.email import build_email, send_email, new_match_count


class PooledClient:
    """Wrap a SourceClient so identical (locations, price) searches run the actor once."""
    _cache: dict = {}

    def __init__(self, inner):
        self.inner = inner

    def search(self, locations, price_min, price_max):
        key = (self.inner.__class__.__name__, frozenset(locations), price_min, price_max)
        if key not in PooledClient._cache:
            PooledClient._cache[key] = self.inner.search(locations, price_min, price_max)
        return PooledClient._cache[key]

    def fetch_detail(self, listing):
        return self.inner.fetch_detail(listing)


def run(profiles, *, dry_run, clients_for, llm_client, salt, today, site_root, state_dir):
    written: list[Path] = []
    generated_at = datetime.now(timezone.utc).isoformat(timespec="minutes")
    for profile in profiles:
        seen_before = load_state(profile.name, state_dir)
        clients = [PooledClient(c) for c in clients_for(profile)]
        ctx = run_profile(profile, clients=clients, llm_client=llm_client,
                          seen=seen_before, generated_at=generated_at)
        html = render_report(ctx)
        out = report_path(profile.name, salt, root=site_root)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html)
        written.append(out)

        updated = record_seen(seen_before, ctx.new_ids, today)
        save_state(profile.name, updated, state_dir)

        if not dry_run and new_match_count(ctx) > 0:
            url = os.environ.get("SITE_BASE_URL", "").rstrip("/") + "/r/" + out.name
            send_email(build_email(profile, ctx, url))
    return written


def _real_clients_for(profile):
    from .sources.fixtures import get_client
    token = os.environ["APIFY_TOKEN"]
    return [get_client(name, token) for name in profile.run.sources]


def _dry_clients_for(_profile):
    from .sources.fixtures import FixtureClient
    from .pipeline.normalize import RawListing
    fx = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "pipeline_records.json"
    recs = [RawListing(r["source"], r["data"]) for r in json.loads(fx.read_text())]
    return [FixtureClient(recs)]


class _DryLLM:
    class messages:
        @staticmethod
        def parse(**kw):
            from .llm import VerificationResult
            class R:
                parsed_output = VerificationResult(is_active=True, scam_risk="low",
                    amenity_findings={}, summary="(dry-run stub)")
            return R()


def cli() -> None:
    from dotenv import load_dotenv
    load_dotenv()
    ap = argparse.ArgumentParser(prog="apthunt")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--profile")
    ap.add_argument("--profiles-dir", default="profiles")
    ap.add_argument("--site", default="site")
    ap.add_argument("--state", default="state")
    args = ap.parse_args()

    profiles = load_profiles(Path(args.profiles_dir), only=args.profile)
    salt = os.environ.get("REPORT_SLUG_SALT", "dev-salt")
    today = date.today().isoformat()
    if args.dry_run:
        run(profiles, dry_run=True, clients_for=_dry_clients_for, llm_client=_DryLLM(),
            salt=salt, today=today, site_root=Path(args.site), state_dir=Path(args.state))
    else:
        from .llm import default_anthropic
        run(profiles, dry_run=False, clients_for=_real_clients_for, llm_client=default_anthropic(),
            salt=salt, today=today, site_root=Path(args.site), state_dir=Path(args.state))
    print(f"Wrote reports for {len(profiles)} profile(s).")


if __name__ == "__main__":
    cli()
```

- [ ] **Step 4: Run to verify pass** — `pytest tests/test_main.py -q` → PASS. Also smoke-test the CLI: `apthunt --dry-run --profile zach` writes `site/r/zach-*.html`.

- [ ] **Step 5: Commit**

```bash
git add src/apthunt/main.py tests/test_main.py
git commit -m "feat(cli): run pipeline per profile, dry-run, cross-profile fetch pooling"
```

---

## Task 15: GitHub Actions workflow, secrets & README

**Files:**
- Create: `.github/workflows/hunt.yml`, expand `README.md`
- Modify: none (state dir is created at run time)

**Interfaces:**
- Produces: a scheduled workflow that runs the hunt twice daily, commits updated `state/`, and publishes `site/` to GitHub Pages. This task is validated by (a) `yamllint`/`actionlint` if available and (b) a documented manual `workflow_dispatch` run — no unit test.

- [ ] **Step 1: Write `.github/workflows/hunt.yml`**

```yaml
name: apartment-hunt
on:
  schedule:
    - cron: "0 12 * * *"   # 08:00 America/New_York (EDT)
    - cron: "0 17 * * *"   # 13:00 America/New_York (EDT)
  workflow_dispatch: {}
permissions:
  contents: write   # to commit state back
  pages: write
  id-token: write
concurrency:
  group: apartment-hunt
  cancel-in-progress: false
jobs:
  hunt:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e .
      - name: Run hunt
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          APIFY_TOKEN: ${{ secrets.APIFY_TOKEN }}
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          MAIL_FROM: ${{ secrets.MAIL_FROM }}
          REPORT_SLUG_SALT: ${{ secrets.REPORT_SLUG_SALT }}
          SITE_BASE_URL: ${{ vars.SITE_BASE_URL }}   # e.g. https://ZRiley36.github.io/nyc-apartment-hunt
        run: apthunt
      - name: Commit updated state
        run: |
          git config user.name "apt-hunt-bot"
          git config user.email "actions@users.noreply.github.com"
          git add state/
          git diff --cached --quiet || git commit -m "chore: update seen-listing state [skip ci]"
          git push
      - uses: actions/upload-pages-artifact@v3
        with: { path: site }
  deploy:
    needs: hunt
    runs-on: ubuntu-latest
    environment: { name: github-pages, url: "${{ steps.deploy.outputs.page_url }}" }
    steps:
      - id: deploy
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Expand `README.md`** with: what it does; **one-time setup** — (1) create accounts + tokens: Anthropic Console (`ANTHROPIC_API_KEY`), Apify (`APIFY_TOKEN`, and subscribe/verify the aggregator + StreetEasy actors), a Gmail App Password for SMTP; (2) add all secrets under repo **Settings → Secrets and variables → Actions**, plus a repo **Variable** `SITE_BASE_URL`; (3) enable **Settings → Pages → Source: GitHub Actions**; (4) set repo **Private**; (5) edit `profiles/*.yaml`; (6) generate a long `REPORT_SLUG_SALT`. Include: local run (`pip install -e ".[dev]"; cp .env.example .env; apthunt --dry-run`), the bookmark URLs (`<SITE_BASE_URL>/r/<name>-<slug>.html` — print them with a one-liner `python -c "from apthunt.delivery.slug import report_slug; ..."`), and cost expectations (Haiku verify ≈ \$1/\$5 per MTok, Sonnet synthesis unused by default in v1; Apify actor runs billed per run — 2 runs/day).

- [ ] **Step 3: Validate the workflow** — Run `actionlint .github/workflows/hunt.yml` if available (else visual review). Confirm no secret is echoed and `state/` is committed but `site/` is not (it's an artifact).

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/hunt.yml README.md
git commit -m "ci: scheduled hunt workflow + Pages deploy + setup docs"
```

- [ ] **Step 5: Full test sweep** — Run `pytest -q` → all tasks' tests PASS. Run `apthunt --dry-run` → reports render for both example profiles.

---

## Self-Review

**1. Spec coverage** — every design element maps to a task:
- Sites/data (aggregator + StreetEasy) → Tasks 3, 7. Verification/scam/amenities → Task 8. Grading (Apply/Consider/Probably-not) → Task 9. Report webpage → Tasks 10, 11. Delivery (Pages + email) → Tasks 12, 15. Config inputs (budget/location/rooms/baths/laundry/gym/rooftop/AC/move-in/"anything else") → Task 2 schema. New-listing flagging → Tasks 4, 5, 10. Multi-profile + shared fetch → Tasks 2, 14. Unguessable private URLs → Task 11. 2×/day schedule + state commit → Task 15. LangGraph 3-agent flow → Task 13.
- "Don't omit a listing the user might want": required amenities are deferred to verification (Task 6 test `test_required_amenity_absent_still_kept`), unknown price/neighborhood are kept (Task 6), and unconfirmed required amenities grade Consider rather than dropping (Task 9).

**2. Placeholder scan** — the only intentional "fill from a real run" markers are the actor field mappings (Tasks 3, 7) and actor IDs — these are flagged as implementation notes with the exact adjustment step, not vague TODOs. All code steps contain real, runnable code.

**3. Type consistency** — `Listing`, `RawListing`, `Profile`, `VerificationResult`, `Graded`, `Grade`, `Card`, `ReportContext` names/signatures are used identically across tasks. `verify_listing(..., client=, model=)`, `grade_listing(listing, verification, profile)`, `build_report(graded, seen, profile, generated_at)`, `report_path(name, salt, root)`, `run_profile(profile, *, clients, llm_client, seen, generated_at, verify_model)` match their producers and consumers.

**Known follow-ups (out of v1 scope, intentionally deferred):** true `Send`-based parallel fan-out for verification; Sonnet-authored prose blurbs (v1 uses the verifier `summary` + deterministic template); Nooklyn/PadMapper sources; cross-source fuzzy dedup; photo-download vs URL image blocks. None block a working v1.
