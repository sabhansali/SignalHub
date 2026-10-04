from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.state import ResearchState


def research_node(state: ResearchState) -> ResearchState:
    """v1 placeholder: real source discovery is added in the next milestone."""
    return {**state, "status": "RESEARCH_COMPLETE"}


def signal_node(state: ResearchState) -> ResearchState:
    return {**state, "status": "SIGNALS_COMPLETE"}


def opportunity_node(state: ResearchState) -> ResearchState:
    return {**state, "status": "OPPORTUNITIES_COMPLETE"}


def brief_node(state: ResearchState) -> ResearchState:
    return {**state, "status": "BRIEF_COMPLETE"}


def build_research_graph():
    """Deterministic workflow skeleton; agent logic will be inserted node-by-node."""
    graph = StateGraph(ResearchState)
    graph.add_node("research", research_node)
    graph.add_node("signals", signal_node)
    graph.add_node("opportunities", opportunity_node)
    graph.add_node("brief", brief_node)
    graph.add_edge(START, "research")
    graph.add_edge("research", "signals")
    graph.add_edge("signals", "opportunities")
    graph.add_edge("opportunities", "brief")
    graph.add_edge("brief", END)
    return graph.compile()
