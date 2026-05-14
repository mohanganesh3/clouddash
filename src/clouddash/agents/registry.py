"""Agent Registry — YAML-driven, zero-code-extension agent management.

Per ADR-004: this is the §3.4 + §8 differentiator. Adding a new agent
(e.g. an Onboarding Agent for the live demo) requires:

    1. Create `agents/onboarding.py` with a class inheriting from BaseAgent.
    2. Add 5–6 lines to `config/agents.yaml`.
    3. Optionally add a routing rule in `config/routing.yaml`.

The orchestrator code does NOT change. The registry uses `importlib` to
dynamically load classes by their dotted path, which is what lets the
60-second live demo work.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

import yaml

from clouddash.agents.base import AgentConfig, BaseAgent
from clouddash.exceptions import RegistryError
from clouddash.logging_setup import get_logger
from clouddash.models import AgentType, IntentCategory
from clouddash.settings import get_settings

logger = get_logger(__name__)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise RegistryError(
            f"Config file not found: {path}",
            context={"path": str(path)},
        )
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise RegistryError(
            f"Invalid YAML in {path}: {exc}",
            context={"path": str(path)},
            cause=exc,
        ) from exc


def _import_class(class_path: str) -> type[BaseAgent]:
    """Import 'package.module.ClassName' and return the class."""
    if "." not in class_path:
        raise RegistryError(
            f"Invalid class_path '{class_path}' — must be module.ClassName",
            context={"class_path": class_path},
        )
    module_path, class_name = class_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise RegistryError(
            f"Could not import module {module_path} for agent class",
            context={"class_path": class_path},
            cause=exc,
        ) from exc
    cls = getattr(module, class_name, None)
    if cls is None:
        raise RegistryError(
            f"Class {class_name} not found in {module_path}",
            context={"class_path": class_path},
        )
    if not isinstance(cls, type) or not issubclass(cls, BaseAgent):
        raise RegistryError(
            f"{class_path} is not a BaseAgent subclass",
            context={"class_path": class_path},
        )
    return cls


class AgentRegistry:
    """Singleton registry of all agents in the system."""

    def __init__(
        self,
        agents_config_path: str | None = None,
        routing_config_path: str | None = None,
    ) -> None:
        settings = get_settings()
        self.agents_config_path = Path(agents_config_path or settings.agents_config_path)
        self.routing_config_path = Path(routing_config_path or settings.routing_config_path)
        self._configs: dict[AgentType, AgentConfig] = {}
        self._instances: dict[AgentType, BaseAgent] = {}
        self._routing: dict[IntentCategory, AgentType] = {}
        self._fallback_chain: list[AgentType] = []
        self._lock = Lock()
        self._load()

    # -------------------------------------------------------------------------
    # Loading
    # -------------------------------------------------------------------------

    def _load(self) -> None:
        agents_doc = _load_yaml(self.agents_config_path)
        routing_doc = _load_yaml(self.routing_config_path)

        agents_section = agents_doc.get("agents") or {}
        if not agents_section:
            raise RegistryError(
                "config/agents.yaml has no 'agents:' section",
                context={"path": str(self.agents_config_path)},
            )

        for key, raw in agents_section.items():
            try:
                atype = AgentType(key)
            except ValueError as exc:
                raise RegistryError(
                    f"Unknown agent_type '{key}' in agents.yaml. "
                    f"Valid: {[a.value for a in AgentType]}",
                    context={"key": key},
                    cause=exc,
                ) from exc

            cfg = AgentConfig(
                agent_type=atype,
                class_path=raw["class"],
                system_prompt_name=raw.get("system_prompt", key),
                model_tier=raw.get("model_tier", "reasoning"),
                tools=list(raw.get("tools", [])),
                requires_kb=bool(raw.get("requires_kb", False)),
                description=raw.get("description", ""),
            )
            self._configs[atype] = cfg

        # Routing
        routing_section = routing_doc.get("intent_routing") or {}
        for intent_key, agent_key in routing_section.items():
            try:
                intent = IntentCategory(intent_key)
                agent = AgentType(agent_key)
            except ValueError as exc:
                raise RegistryError(
                    f"Invalid routing entry: {intent_key} → {agent_key}",
                    cause=exc,
                ) from exc
            if agent not in self._configs:
                raise RegistryError(
                    f"Routing target '{agent.value}' has no config in agents.yaml"
                )
            self._routing[intent] = agent

        # Fallback chain (used when handover fails — Triage → Escalation by default)
        fallback = routing_doc.get("fallback_chain") or ["triage", "escalation"]
        try:
            self._fallback_chain = [AgentType(a) for a in fallback]
        except ValueError as exc:
            raise RegistryError(f"Invalid fallback_chain: {fallback}", cause=exc) from exc

        logger.info(
            "registry.loaded",
            agents=sorted(a.value for a in self._configs),
            routing={i.value: a.value for i, a in self._routing.items()},
            fallback_chain=[a.value for a in self._fallback_chain],
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def list_agents(self) -> list[AgentType]:
        return sorted(self._configs.keys(), key=lambda a: a.value)

    def get_config(self, agent_type: AgentType) -> AgentConfig:
        if agent_type not in self._configs:
            raise RegistryError(
                f"Agent {agent_type.value} not registered.",
                context={"available": [a.value for a in self._configs]},
            )
        return self._configs[agent_type]

    def get(self, agent_type: AgentType) -> BaseAgent:
        """Return a singleton instance of the agent. Lazy-loaded."""
        if agent_type in self._instances:
            return self._instances[agent_type]
        with self._lock:
            if agent_type not in self._instances:
                cfg = self.get_config(agent_type)
                cls = _import_class(cfg.class_path)
                self._instances[agent_type] = cls(config=cfg)
                logger.info(
                    "registry.instantiated",
                    agent=agent_type.value,
                    class_path=cfg.class_path,
                )
        return self._instances[agent_type]

    def route_intent(self, intent: IntentCategory) -> AgentType:
        """Map an intent category to its target agent."""
        target = self._routing.get(intent)
        if target is None:
            # Fallback to the first fallback agent (typically Triage)
            target = self._fallback_chain[0] if self._fallback_chain else AgentType.TRIAGE
            logger.warning(
                "registry.no_route",
                intent=intent.value,
                fallback=target.value,
            )
        return target

    def fallback_chain(self) -> list[AgentType]:
        return list(self._fallback_chain)


@lru_cache(maxsize=1)
def get_registry() -> AgentRegistry:
    """Singleton accessor."""
    return AgentRegistry()


def reload_registry() -> AgentRegistry:
    """For tests + the live 'add new agent' demo: clear cache and reload."""
    get_registry.cache_clear()
    return get_registry()
