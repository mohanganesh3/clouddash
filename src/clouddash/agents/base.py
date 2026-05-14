"""BaseAgent — the abstract contract every agent implements.

Per ADR-004: agents are framework-agnostic. They receive a `ConversationState`
and return an `AgentResponse`. The orchestrator (LangGraph) wraps them as
graph nodes — but agents themselves know nothing about LangGraph.

This abstraction makes the system trivially testable: you can call
`agent.handle(state)` directly in a unit test without spinning up a graph.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import uuid4

from pydantic import BaseModel, Field

from clouddash.exceptions import LLMError
from clouddash.llm import get_llm, load_prompt
from clouddash.logging_setup import get_logger, write_audit_event
from clouddash.models import (
    AgentResponse,
    AgentType,
    AttemptOutcome,
    AttemptRecord,
    Citation,
    ConversationState,
    HandoverEvent,
    HandoverPacket,
    HandoverReason,
    HandoverStatus,
    Sentiment,
    Urgency,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = get_logger(__name__)


class AgentConfig(BaseModel):
    """Per-agent config loaded from `config/agents.yaml`."""

    agent_type: AgentType
    class_path: str
    system_prompt_name: str
    model_tier: str = Field(default="reasoning")
    tools: list[str] = Field(default_factory=list)
    requires_kb: bool = False
    description: str = ""


class BaseAgent(ABC):
    """Every agent inherits from this.

    Subclasses implement only `handle()`. Common operations (LLM access,
    handover-packet construction, audit logging) live here.
    """

    agent_type: AgentType  # set by subclass

    def __init__(self, config: AgentConfig) -> None:
        if not hasattr(self, "agent_type"):
            raise TypeError(f"{self.__class__.__name__} must set agent_type as a class attribute")
        if config.agent_type != self.agent_type:
            raise ValueError(
                f"Config agent_type {config.agent_type} != class agent_type {self.agent_type}"
            )
        self.config = config

    # -------------------------------------------------------------------------
    # Subclass contract
    # -------------------------------------------------------------------------

    @abstractmethod
    async def handle(self, state: ConversationState) -> AgentResponse:
        """Process the conversation state and produce a response or handover."""
        ...

    # -------------------------------------------------------------------------
    # Shared helpers
    # -------------------------------------------------------------------------

    @property
    def llm(self) -> BaseChatModel:
        return get_llm(self.config.model_tier)  # type: ignore[arg-type]

    def system_prompt(self, **fmt_kwargs: object) -> str:
        """Load and format this agent's system prompt."""
        template = load_prompt(self.config.system_prompt_name)
        if fmt_kwargs:
            try:
                return template.format(**fmt_kwargs)
            except KeyError as exc:
                raise LLMError(
                    f"Prompt {self.config.system_prompt_name} missing placeholder: {exc}",
                    context={"prompt": self.config.system_prompt_name},
                ) from exc
        return template

    def make_handover_packet(
        self,
        state: ConversationState,
        *,
        to: AgentType,
        reason: HandoverReason,
        summary: str,
        user_intent: str,
        confidence: float,
        prior_attempts: list[AttemptRecord] | None = None,
        sentiment: Sentiment = Sentiment.NEUTRAL,
        urgency: Urgency = Urgency.MEDIUM,
        extracted_entities: dict[str, object] | None = None,
    ) -> HandoverPacket:
        """Build a HandoverPacket from this agent to another."""
        # Carry the existing audit chain forward and append a new event
        prior_events = list(state.handover_history)
        new_event = HandoverEvent(
            trace_id=state.trace_id,
            turn_id=state.turn_id,
            from_agent=self.agent_type,
            to_agent=to,
            reason=reason,
            status=HandoverStatus.PENDING,
        )

        packet = HandoverPacket(
            trace_id=state.trace_id,
            turn_id=state.turn_id,
            from_agent=self.agent_type,
            to_agent=to,
            reason=reason,
            user_intent=user_intent,
            conversation_summary=summary,
            customer_profile=state.customer_profile,
            extracted_entities=extracted_entities or {},
            prior_attempts=prior_attempts or [],
            confidence_state=confidence,
            sentiment=sentiment,
            urgency=urgency,
            audit_chain=[*prior_events, new_event],
        )

        write_audit_event(
            "handover.created",
            packet_id=str(packet.packet_id),
            from_agent=self.agent_type.value,
            to_agent=to.value,
            reason=reason.value,
            confidence=confidence,
            sentiment=sentiment.value,
            urgency=urgency.value,
            prior_attempts=len(packet.prior_attempts),
        )
        return packet

    def acknowledge_handover(
        self,
        packet: HandoverPacket,
        *,
        note: str | None = None,
    ) -> None:
        """Write the explicit HandoverAck event to the audit log (per §2.3)."""
        write_audit_event(
            "handover.accepted",
            packet_id=str(packet.packet_id),
            accepted_by=self.agent_type.value,
            from_agent=packet.from_agent.value,
            note=note,
        )

    def make_attempt_record(
        self,
        state: ConversationState,
        *,
        summary: str,
        outcome: AttemptOutcome,
        confidence: float,
        citations: list[Citation] | None = None,
    ) -> AttemptRecord:
        """Snapshot what this agent attempted — fed forward in a HandoverPacket."""
        return AttemptRecord(
            agent=self.agent_type,
            turn_id=state.turn_id,
            summary=summary,
            outcome=outcome,
            citations=citations or [],
            confidence=confidence,
        )

    async def time_call(
        self,
        coro_or_callable,
        *,
        op_name: str,
    ):
        """Wrap an async/sync call with timing + structured logging."""
        t0 = time.time()
        span_id = str(uuid4())
        try:
            result = (
                await coro_or_callable() if callable(coro_or_callable) else await coro_or_callable
            )
            logger.info(
                f"{self.agent_type.value}.{op_name}",
                latency_ms=int((time.time() - t0) * 1000),
                span_id=span_id,
                ok=True,
            )
            return result
        except Exception as exc:
            logger.error(
                f"{self.agent_type.value}.{op_name}",
                latency_ms=int((time.time() - t0) * 1000),
                span_id=span_id,
                ok=False,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise
