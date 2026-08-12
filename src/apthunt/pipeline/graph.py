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
