"""Escalation Agent — packages context + simulates human handoff.

Receives a HandoverPacket. Produces:
- A customer-facing message confirming the handoff with ticket ID + ETA.
- A structured EscalationTicket persisted via tools.create_ticket.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from clouddash.agents._helpers import render_customer_profile, render_handover_context
from clouddash.agents.base import BaseAgent
from clouddash.logging_setup import get_logger
from clouddash.models import (
    AgentResponse,
    AgentType,
    ConversationState,
    EscalationTicket,
    HandoverPacket,
    Sentiment,
    Urgency,
)
from clouddash.tools.escalation_tools import create_ticket

logger = get_logger(__name__)


class _EscalationOutput(BaseModel):
    response_text: str = Field(..., min_length=1, max_length=2000)
    priority: Literal["P0", "P1", "P2", "P3"]
    issue_summary: str = Field(..., max_length=1500)
    recommended_actions: list[str] = Field(default_factory=list, max_length=8)


class EscalationAgent(BaseAgent):
    agent_type = AgentType.ESCALATION

    async def handle(self, state: ConversationState) -> AgentResponse:
        # ALWAYS acknowledge an incoming handover (this is the terminal node)
        if state.pending_handover is not None:
            self.acknowledge_handover(state.pending_handover, note="terminal escalation")

        # Synthesize a packet if we somehow got here without one (defensive)
        packet = state.pending_handover or self._synthesize_packet(state)

        # Pre-allocate a ticket ID so the LLM can include it in response_text
        from uuid import uuid4

        ticket_uuid = uuid4()
        short_id = ticket_uuid.hex[:10].upper()

        prompt = self.system_prompt(
            customer_profile=render_customer_profile(state),
            handover_context=render_handover_context(state),
            conversation=state.conversation_text(last_n_turns=10),
            ticket_id=short_id,
        )

        structured = self.llm.with_structured_output(_EscalationOutput)
        try:
            output: _EscalationOutput = await structured.ainvoke(prompt)  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.error("escalation.llm_failed", error=str(exc))
            output = _EscalationOutput(
                response_text=(
                    f"I've escalated your case to a human teammate (ticket ESC-{short_id}). "
                    "You'll hear back within 1 business day. Thank you for your patience."
                ),
                priority="P2",
                issue_summary=(packet.conversation_summary or "Escalation requested.")[:1500],
                recommended_actions=["Review conversation history", "Reach out to customer"],
            )

        # Build and persist the ticket
        ticket = EscalationTicket(
            ticket_id=ticket_uuid,
            trace_id=state.trace_id,
            customer_profile=state.customer_profile,
            issue_summary=output.issue_summary,
            sentiment=packet.sentiment,
            urgency=packet.urgency,
            recommended_priority=output.priority,
            full_handover_packet=packet,
            suggested_actions=output.recommended_actions,
        )
        result = create_ticket(ticket)

        logger.info(
            "escalation.handoff_done",
            ticket_id=str(ticket.ticket_id),
            priority=output.priority,
            sentiment=packet.sentiment.value,
            urgency=packet.urgency.value,
            actions=len(output.recommended_actions),
        )

        return AgentResponse(
            agent=self.agent_type,
            response_text=output.response_text,
            confidence=0.95,  # the handoff itself is reliable; the resolution is the human's
            escalate=True,
            metadata={
                "ticket_id": str(ticket.ticket_id),
                "ticket_short_id": short_id,
                "priority": output.priority,
                "expected_response": result["expected_response"],
                "recommended_actions": output.recommended_actions,
            },
        )

    # -------------------------------------------------------------------------

    def _synthesize_packet(self, state: ConversationState) -> HandoverPacket:
        """If something routed here without a packet, make one from state."""
        latest = state.latest_user_message()
        return HandoverPacket(
            trace_id=state.trace_id,
            turn_id=state.turn_id,
            from_agent=state.current_agent,
            to_agent=AgentType.ESCALATION,
            reason=(
                __import__("clouddash.models", fromlist=["HandoverReason"]).HandoverReason.REQUIRES_ESCALATION  # type: ignore[attr-defined]
            ),
            user_intent=(latest.content[:200] if latest else "Customer needs human assistance."),
            conversation_summary="(synthesized — no upstream packet)",
            customer_profile=state.customer_profile,
            sentiment=Sentiment.NEUTRAL,
            urgency=Urgency.MEDIUM,
        )
