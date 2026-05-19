"""YAML-driven agent registry with importlib.

Adding an agent = YAML entry + one file. Zero changes here.
May 16: LangGraph checkpointer expects thread_id in config, not state.
Spent an hour debugging why memory wasn't persisting.
"""
from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from clouddash.agents.base import AgentConfig, BaseAgent
from clouddash.models import AgentType
from clouddash.settings import get_settings


class AgentRegistry:
    def __init__(self) -> None:
        self._configs: dict[AgentType, AgentConfig] = {}
        self._instances: dict[AgentType, BaseAgent] = {}
        self._routing: dict[str, AgentType] = {}
        self._fallback_chain: list[AgentType] = []
        self._load()

    def _load(self) -> None:
        cfg = get_settings()
        agents_cfg = yaml.safe_load(Path(cfg.agents_config_path).read_text())
        for name, spec in agents_cfg.get("agents", {}).items():
            try:
                atype = AgentType(name)
            except ValueError:
                continue
            self._configs[atype] = AgentConfig(
                agent_type=atype,
                class_path=spec["class"],
                system_prompt=spec.get("system_prompt", name),
                model_tier=spec.get("model_tier", "reasoning"),
                tools=spec.get("tools", []),
                requires_kb=spec.get("requires_kb", False),
                description=spec.get("description", ""),
            )

        routing_cfg = yaml.safe_load(Path(cfg.routing_config_path).read_text())
        for intent, agent_name in routing_cfg.get("intent_routing", routing_cfg.get("routing", {})).items():
            try:
                self._routing[intent] = AgentType(agent_name)
            except ValueError:
                pass
        self._fallback_chain = [
            AgentType(a)
            for a in routing_cfg.get("fallback_chain", [])
            if a in AgentType._value2member_map_
        ]

    def get(self, atype: AgentType) -> BaseAgent:
        if atype not in self._instances:
            self._instances[atype] = self._instantiate(atype)
        return self._instances[atype]

    def get_config(self, atype: AgentType) -> AgentConfig:
        return self._configs[atype]

    def list_agents(self) -> list[AgentType]:
        return list(self._configs.keys())

    def route_for_intent(self, intent: str) -> AgentType:
        return self._routing.get(intent, AgentType.KNOWLEDGE)

    def next_fallback(self, failed: AgentType, tried: set[AgentType]) -> AgentType | None:
        for a in self._fallback_chain:
            if a not in tried and a != failed:
                return a
        return None

    def _instantiate(self, atype: AgentType) -> BaseAgent:
        config = self._configs[atype]
        module_path, cls_name = config.class_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, cls_name)
        return cls(config)

    def reload(self) -> None:
        self._instances.clear()
        self._configs.clear()
        self._routing.clear()
        self._load()


@lru_cache(maxsize=1)
def get_registry() -> AgentRegistry:
    return AgentRegistry()
