# nyc-apartment-hunt

Automated NYC apartment search. Twice a day it queries listing aggregators for
each person's criteria, flags brand-new matches, has a Claude agent verify each
one (real listing? scam? does it actually have the must-have amenities?), grades
it **Apply now / Consider / Probably not**, and publishes a private web report
plus an email when something new turns up.

Pipeline (LangGraph): **search → normalize/filter/dedup → verify (Claude Haiku) →
grade → report**. Runs once per profile; profiles that share a neighborhood share
a single fetch. See `docs/superpowers/plans/` for the full design.

## What you need

- **Anthropic API key** — [console.anthropic.com](https://console.anthropic.com) → `ANTHROPIC_API_KEY`.
- **Apify token** — [apify.com](https://apify.com) → `APIFY_TOKEN`. Subscribe to / verify the
  Real Estate Aggregator actor and a StreetEasy scraper actor (actor IDs and field
  mappings in `src/apthunt/sources/` and `src/apthunt/pipeline/normalize.py` are
  best-guess — run each actor once and adjust to the real output; the `# TODO(verify)`
  comments mark the spots).
- **SMTP for email** — e.g. a Gmail address + [App Password](https://support.google.com/accounts/answer/185833):
  `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER`, `SMTP_PASSWORD`, `MAIL_FROM`.
- **A long random `REPORT_SLUG_SALT`** — makes report URLs unguessable. Generate one:
  `python -c "import secrets; print(secrets.token_hex(24))"`.

## One-time setup (GitHub Actions + Pages)

1. **Keep the repo Private** (Settings → General → Danger Zone).
2. **Secrets** — Settings → Secrets and variables → Actions → *New repository secret*, for each of:
   `ANTHROPIC_API_KEY`, `APIFY_TOKEN`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
   `SMTP_PASSWORD`, `MAIL_FROM`, `REPORT_SLUG_SALT`.
3. **Variable** — same page, *Variables* tab → add `SITE_BASE_URL` =
   `https://ZRiley36.github.io/nyc-apartment-hunt`.
4. **Pages** — Settings → Pages → Source: **GitHub Actions**.
5. **Edit the profiles** — `profiles/zach.yaml`, `profiles/natasha.yaml` (budget,
   locations, bedrooms/bathrooms, move-in window, amenities as
   `required` / `preferred` / `ignore`, email). Add a `<name>.yaml` per person.
6. The workflow runs at 08:00 and 13:00 America/New_York, or on demand via
   Actions → apartment-hunt → **Run workflow**.

## Your report bookmarks

Report URLs are `<SITE_BASE_URL>/r/<name>-<slug>.html`, where `<slug>` is derived
from your `REPORT_SLUG_SALT`. Print your links (with the same salt the workflow uses):

```bash
REPORT_SLUG_SALT=... python -c "import os; from apthunt.delivery.slug import report_slug; \
[print(f'/r/{n}-{report_slug(n, os.environ[\"REPORT_SLUG_SALT\"])}.html') for n in ('zach','natasha')]"
```

Bookmark them — they're stable across runs and unguessable without the salt.

## Run locally

```bash
pip install -e ".[dev]"
cp .env.example .env          # fill in tokens (or leave blank for dry-run)
apthunt --dry-run             # renders reports from bundled fixtures into ./site
pytest -q                     # run the test suite
```

`apthunt --dry-run` uses local fixtures and a canned verifier — no API keys or
network needed. Drop `--dry-run` (with `.env` filled in) for a real run.
`--profile NAME` limits to one person; `--site` / `--state` override output dirs.

## Cost expectations

- **Claude verification** — Haiku (`claude-haiku-4-5`), ≈ $1 / $5 per million
  input / output tokens; only new listings are verified, capped per run by each
  profile's `run.max_verify_per_run`.
- **Apify** — billed per actor run; ~2 runs/day per subscribed actor.
- **SMTP / GitHub Actions / Pages** — free at this volume.
