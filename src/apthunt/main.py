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
    return [get_client(name, token, radius_miles=profile.run.radius_miles)
            for name in profile.run.sources]


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
