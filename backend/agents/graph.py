"""LangGraph StateGraph orchestrating the 4 agents with conditional routing.

Graph structure:
    extractor -> verifier -> { findings? -> critic -> writer | no findings? -> writer }
"""
from typing import Literal

from langgraph.graph import StateGraph, START, END

from backend.agents.state import AgentState
from backend.agents.extractor_agent import extractor_agent
from backend.agents.verifier_agent import verifier_agent
from backend.agents.critic_agent import critic_agent
from backend.agents.writer_agent import writer_agent


async def run_extractor(state: AgentState) -> dict:
    try:
        return await extractor_agent(state)
    except Exception as e:
        return {"errors": [f"extractor node failed: {e}"]}


async def run_verifier(state: AgentState) -> dict:
    try:
        return await verifier_agent(state)
    except Exception as e:
        return {"errors": [f"verifier node failed: {e}"]}


async def run_critic(state: AgentState) -> dict:
    try:
        return await critic_agent(state)
    except Exception as e:
        return {"errors": [f"critic node failed: {e}"]}


async def run_writer(state: AgentState) -> dict:
    try:
        return await writer_agent(state)
    except Exception as e:
        return {"errors": [f"writer node failed: {e}"]}


def route_after_verifier(state: AgentState) -> Literal["critic", "writer"]:
    """If verifier found no risks, skip critic and go directly to writer."""
    findings = state.get("findings", [])
    if not findings:
        return "writer"
    return "critic"


def build_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("extractor", run_extractor)
    builder.add_node("verifier", run_verifier)
    builder.add_node("critic", run_critic)
    builder.add_node("writer", run_writer)

    builder.add_edge(START, "extractor")
    builder.add_edge("extractor", "verifier")
    builder.add_conditional_edges(
        "verifier",
        route_after_verifier,
        {"critic": "critic", "writer": "writer"},
    )
    builder.add_edge("critic", "writer")
    builder.add_edge("writer", END)

    return builder.compile()


compiled_graph = build_graph()
