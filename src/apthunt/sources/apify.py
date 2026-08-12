from __future__ import annotations


def _default_dataset_id(run) -> str | None:
    """Extract the run's default dataset id across apify-client versions.

    apify-client 3.x returns a `Run` model (attribute `default_dataset_id`);
    older 1.x/2.x returned a plain dict (`defaultDatasetId`). Handle both.
    """
    ds = getattr(run, "default_dataset_id", None)
    if ds is None and isinstance(run, dict):
        ds = run.get("defaultDatasetId") or run.get("default_dataset_id")
    return ds


def run_actor(actor_id: str, run_input: dict, token: str, client=None) -> list[dict]:
    if client is None:
        from apify_client import ApifyClient
        client = ApifyClient(token)
    run = client.actor(actor_id).call(run_input=run_input)
    if run is None:  # actor run did not complete
        return []
    dataset_id = _default_dataset_id(run)
    if dataset_id is None:
        raise RuntimeError(
            f"apify actor {actor_id!r} run returned no default dataset id "
            f"(got {type(run).__name__})"
        )
    return list(client.dataset(dataset_id).iterate_items())
