"""Shared state TypedDict for the LangGraph agent graph.

This is the contract between all agents. Every field is optional
so nodes can write only what they produce.
"""
from typing import TypedDict, Optional, Annotated


def _replace_list(current: list, new: list) -> list:
    """LangGraph reducer: replace list instead of extending it."""
    return new

# Controlled vocabulary for finding types — used by verifier and critic agents.
# Must match the taxonomy in data/eval/ground_truth.jsonl exactly.
FINDING_TYPE_TAXONOMY: list[str] = [
    "amount_inconsistency",
    "excessive_interest",
    "missing_jurisdiction",
    "missing_required_fields",
    "missing_standard_exclusions",
    "missing_termination_clause",
    "missing_termination_notice",
    "no_cap_liability",
    "no_data_protection",
    "overbroad_confidentiality",
    "penalty_ambiguous",
    "perpetual_confidentiality",
    "unfavorable_penalty",
    "unusual_jurisdiction",
]


class Finding(TypedDict, total=False):
    type: str
    severity: str
    description: str
    source_page: Optional[int]
    source_line: Optional[int]
    source_snippet: Optional[str]
    reference_clause: Optional[str]
    agent_name: str
    ambiguous: bool


class ExtractedInfo(TypedDict, total=False):
    parties: list[str]
    dates: dict[str, str]
    amounts: dict[str, float]
    doc_type: str
    clauses: dict[str, str]


class AgentState(TypedDict):
    doc_id: str
    raw_text: str
    doc_type: Optional[str]
    extracted_info: Optional[ExtractedInfo]
    findings: Annotated[list[Finding], _replace_list]
    risk_level: Optional[str]
    risk_score: Optional[float]
    executive_summary: Optional[str]
    errors: Annotated[list[str], _replace_list]
