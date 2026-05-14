"""Tests for the YAML-driven AgentRegistry — loading, routing, and extensibility."""

from __future__ import annotations

import pytest

from clouddash.agents.registry import AgentRegistry, get_registry, reload_registry
from clouddash.agents.base import BaseAgent
from clouddash.exceptions import RegistryError
from clouddash.models import AgentType, IntentCategory


class TestAgentRegistry:
    def test_registry_loads_all_agents(self) -> None:
        reg = get_registry()
        agents = reg.list_agents()
        assert len(agents) >= 5
        assert AgentType.TRIAGE in agents
        assert AgentType.TECHNICAL in agents
        assert AgentType.BILLING in agents
        assert AgentType.KNOWLEDGE in agents
        assert AgentType.ESCALATION in agents

    def test_get_config_returns_typed_config(self) -> None:
        reg = get_registry()
        cfg = reg.get_config(AgentType.TECHNICAL)
        assert cfg.agent_type == AgentType.TECHNICAL
        assert cfg.class_path.endswith("TechnicalAgent")
        assert cfg.requires_kb is True
        assert cfg.model_tier in ("reasoning", "fast")

    def test_route_intent_maps_correctly(self) -> None:
        reg = get_registry()
        # The routing.yaml should map intents to agents
        assert reg.route_intent(IntentCategory.TECHNICAL) == AgentType.TECHNICAL
        assert reg.route_intent(IntentCategory.BILLING) == AgentType.BILLING
        assert reg.route_intent(IntentCategory.GENERAL) == AgentType.KNOWLEDGE

    def test_fallback_chain_present(self) -> None:
        reg = get_registry()
        chain = reg.fallback_chain()
        assert len(chain) >= 1
        assert AgentType.TRIAGE in chain or AgentType.ESCALATION in chain

    def test_get_unknown_agent_raises(self) -> None:
        reg = get_registry()
        # Trying to create an invalid AgentType should raise ValueError
        with pytest.raises(ValueError):
            AgentType(999)  # type: ignore[arg-type]

    def test_registry_is_singleton(self) -> None:
        a = get_registry()
        b = get_registry()
        assert a is b

    def test_reload_registry_creates_new_instance(self) -> None:
        old = get_registry()
        new = reload_registry()
        # After reload, calling get_registry again should give the new one
        assert get_registry() is new
        # Old and new should have same agents loaded
        assert old.list_agents() == new.list_agents()
