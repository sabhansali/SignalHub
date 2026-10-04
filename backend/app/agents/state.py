from __future__ import annotations

from typing import TypedDict


class ResearchState(TypedDict, total=False):
    account_id: str
    account_name: str
    industry: str
    market: str
    request_type: str

    source_ids: list[str]
    document_ids: list[str]
    claim_ids: list[str]
    signal_ids: list[str]
    opportunity_ids: list[str]
    brief_ids: list[str]

    research_gaps: list[str]
    errors: list[str]
    status: str
