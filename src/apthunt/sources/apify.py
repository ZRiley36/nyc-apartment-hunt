from __future__ import annotations


def run_actor(actor_id: str, run_input: dict, token: str, client=None) -> list[dict]:
    if client is None:
        from apify_client import ApifyClient
        client = ApifyClient(token)
    run = client.actor(actor_id).call(run_input=run_input)
    dataset_id = run["defaultDatasetId"]
    return list(client.dataset(dataset_id).iterate_items())
