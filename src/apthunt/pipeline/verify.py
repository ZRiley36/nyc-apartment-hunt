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
