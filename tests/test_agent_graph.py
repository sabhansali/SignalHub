import pytest

langgraph = pytest.importorskip("langgraph")
from app.agents.graph import build_research_graph


def test_graph_runs_in_order() -> None:
    graph = build_research_graph()
    result = graph.invoke({"account_name": "Example"})
    assert result["status"] == "BRIEF_COMPLETE"
