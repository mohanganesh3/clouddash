"""Triage Agent — first point of contact, classifies intent and routes.

Per ADR-001, Triage is the orchestrator's lead-agent. It does NOT respond to
the customer directly — it produces a structured classification and emits a
HandoverPacket to the appropriate specialist.

For multi-intent queries (Scenario 2), Triage routes to the FIRST intent's
specialist and stores `secondary_intents` in extracted_entities so the
specialist can hand off to the next.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from clouddash.agents.base import BaseAgent
from clouddash.agents.registry import get_registry
from clouddash.logging_setup import get_logger
from clouddash.models import (
    AgentResponse,
    AgentType,
    ConversationState,
    HandoverReason,
    IntentCategory,
    IntentClassification,
    Sentiment,
    Urgency,
)

logger = get_logger(__name__)


class _TriageOutput(BaseModel):
    """Structured-output schema enforced on the LLM call."""

    primary_intent: IntentCategory
    secondary_intents: list[IntentCategory] = Field(default_factory=list)
    is_multi_intent: bool = False
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., max_length=600)
    suggested_agent: AgentType
    extracted_entities: dict[str, Any] = Field(default_factory=dict)
    sentiment: Sentiment = Sentiment.NEUTRAL
    urgency: Urgency = Urgency.MEDIUM
    user_intent_summary: str = Field(..., max_length=400)


class TriageAgent(BaseAgent):
    agent_type = AgentType.TRIAGE

    async def handle(self, state: ConversationState) -> AgentResponse:
        latest = state.latest_user_message()
        if latest is None or not latest.content.strip():
            # Empty conversation — bounce to knowledge with a low-confidence packet
            return self._empty_message_response(state)

        prompt = self.system_prompt(
            customer_profile=_render_customer_profile(state),
            conversation=state.conversation_text(last_n_turns=5),
            latest_message=latest.content,
        )

        structured = self.llm.with_structured_output(_TriageOutput)
        try:
            output: _TriageOutput = await structured.ainvoke(prompt)  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "triage.llm_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            # Graceful fallback: route to Knowledge with low confidence
            return self._fallback_response(state, error=str(exc))

        # Convert to canonical IntentClassification
        intent = IntentClassification(
            primary_intent=output.primary_intent,
            secondary_intents=output.secondary_intents,
            confidence=output.confidence,
            reasoning=output.reasoning,
            suggested_agent=output.suggested_agent,
            is_multi_intent=output.is_multi_intent,
            extracted_entities=output.extracted_entities,
            sentiment=output.sentiment,
            urgency=output.urgency,
        )

        # Use registry routing as the source of truth (don't blindly trust the LLM)
        registry = get_registry()
        target_agent = registry.route_intent(intent.primary_intent)

        # If LLM disagrees with registry routing, log it but trust the registry —
        # this keeps routing purely YAML-driven (ADR-004)
        if output.suggested_agent != target_agent:
            logger.info(
                "triage.routing_override",
                llm_suggested=output.suggested_agent.value,
                registry_target=target_agent.value,
                intent=intent.primary_intent.value,
            )

        # Carry secondary intents into the packet so the specialist can chain
        carry_entities = dict(output.extracted_entities)
        if intent.is_multi_intent and intent.secondary_intents:
            carry_entities["secondary_intents"] = [i.value for i in intent.secondary_intents]

        # Build the handover packet
        packet = self.make_handover_packet(
            state,
            to=target_agent,
            reason=(
                HandoverReason.MULTI_INTENT if intent.is_multi_intent else HandoverReason.INITIAL_ROUTE
            ),
            summary=output.reasoning,
            user_intent=output.user_intent_summary,
            confidence=output.confidence,
            sentiment=output.sentiment,
            urgency=output.urgency,
            extracted_entities=carry_entities,
        )

        logger.info(
            "triage.routed",
            primary_intent=intent.primary_intent.value,
            secondary=[i.value for i in intent.secondary_intents],
            is_multi_intent=intent.is_multi_intent,
            target_agent=target_agent.value,
            confidence=output.confidence,
            sentiment=output.sentiment.value,
            urgency=output.urgency.value,
        )

        return AgentResponse(
            agent=self.agent_type,
            response_text="",  # Triage does not respond to customer
            handover_packet=packet,
            next_agent=target_agent,
            confidence=output.confidence,
            metadata={
                "intent_classification": intent.model_dump(mode="json"),
            },
        )

    # -------------------------------------------------------------------------

    def _empty_message_response(self, state: ConversationState) -> AgentResponse:
        registry = get_registry()
        target = registry.route_intent(IntentCategory.GENERAL)
        packet = self.make_handover_packet(
            state,
            to=target,
            reason=HandoverReason.INITIAL_ROUTE,
            summary="Customer sent empty/whitespace-only message. Greet and prompt.",
            user_intent="Customer sent an empty message — engage and ask how to help.",
            confidence=0.3,
        )
        return AgentResponse(
            agent=self.agent_type,
            response_text="",
            handover_packet=packet,
            next_agent=target,
            confidence=0.3,
        )

    def _fallback_response(self, state: ConversationState, *, error: str) -> AgentResponse:
        registry = get_registry()
        target = registry.route_intent(IntentCategory.UNKNOWN)
        latest = state.latest_user_message()
        packet = self.make_handover_packet(
            state,
            to=target,
            reason=HandoverReason.LOW_CONFIDENCE,
            summary=f"Triage classifier failed: {error}. Treat as general inquiry.",
            user_intent=(latest.content if latest else "Customer needs help."),
            confidence=0.2,
        )
        return AgentResponse(
            agent=self.agent_type,
            response_text="",
            handover_packet=packet,
            next_agent=target,
            confidence=0.2,
            metadata={"triage_error": error},
        )


def _render_customer_profile(state: ConversationState) -> str:
    p = state.customer_profile
    fields = []
    if p.customer_id:
        fields.append(f"customer_id={p.customer_id}")
    if p.plan:
        fields.append(f"plan={p.plan.value}")
    if p.org_name:
        fields.append(f"org={p.org_name}")
    if p.email:
        fields.append(f"email={p.email}")
    return ", ".join(fields) if fields else "(no profile yet)"
