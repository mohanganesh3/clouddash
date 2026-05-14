"""Smoke tests for the LangGraph orchestrator — structure without real LLM calls."""

from __future__ import annotations

from clouddash.orchestrator.graph import Orchestrator


class TestOrchestratorStructure:
    def test_orchestrator_instantiates(self) -> None:
        orch = Orchestrator()
        assert orch is not None
        # Graph should have nodes for each registered agent
        nodes = set(orch.graph.nodes)
        assert "triage" in nodes
        assert "technical" in nodes
        assert "billing" in nodes
        assert "knowledge" in nodes
        assert "escalation" in nodes

    def test_graph_is_compiled(self) -> None:
        orch = Orchestrator()
        g = orch.graph
        # CompiledStateGraph should have nodes and be callable
        assert hasattr(g, "nodes")
        assert len(g.nodes) >= 5  # all 5 agents + __start__ + __end__
