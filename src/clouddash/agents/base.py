from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from clouddash.models import AgentResponse, AgentType, GraphState
from clouddash.settings import get_settings


class AgentConfig(BaseModel):
    agent_type: AgentType
    class_path: str
    system_prompt: str
    model_tier: str = "reasoning"
    tools: list[str] = []
    requires_kb: bool = False
    description: str = ""


class BaseAgent(ABC):
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self._prompt: str | None = None

    @abstractmethod
    async def handle(self, state: GraphState) -> AgentResponse: ...

    def get_llm(self, tier: str | None = None):
        from clouddash.providers import get_llm
        return get_llm(tier or self.config.model_tier)

    def load_prompt(self) -> str:
        if self._prompt is None:
            p = Path(get_settings().prompts_dir) / f"{self.config.system_prompt}.md"
            if p.exists():
                self._prompt = p.read_text()
            else:
                self._prompt = f"You are the {self.config.agent_type.value} agent for CloudDash."
        return self._prompt

    def _last_user_message(self, state: GraphState) -> str:
        from langchain_core.messages import HumanMessage
        for msg in reversed(state["messages"]):
            if isinstance(msg, HumanMessage):
                return msg.content
        return ""

    def _history_context(self, state: GraphState, turns: int = 3) -> str:
        from langchain_core.messages import AIMessage, HumanMessage
        lines = []
        for msg in state["messages"][-(turns * 2):]:
            if isinstance(msg, HumanMessage):
                lines.append(f"User: {msg.content[:200]}")
            elif isinstance(msg, AIMessage):
                lines.append(f"Agent: {msg.content[:200]}")
        return "\n".join(lines)
