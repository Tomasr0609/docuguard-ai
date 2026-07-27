"""Shared state TypedDict for the LangGraph agent graph.

This is the contract between all agents. Every field is optional
so nodes can write only what they produce.
"""
from typing import TypedDict, Optional


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
    findings: list[Finding]
    risk_level: Optional[str]
    risk_score: Optional[float]
    executive_summary: Optional[str]
    errors: list[str]
