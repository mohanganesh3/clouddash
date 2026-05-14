"""Billing Agent — handles plan changes, invoices, refunds, duplicate charges.

Has $1,000 refund authority limit (KB-011 § 1, § 2). Escalates when:
- Customer explicitly asks for a manager
- Refund > $1,000
- Sentiment=angry AND urgency=high
- Authority does not cover the request
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from clouddash.agents._helpers import (
    chunks_to_used_citations,
    coerce_agent_type,
    coerce_handover_reason,
    grounding_signal,
    render_customer_profile,
    render_handover_context,
    render_kb_chunks,
)
from clouddash.agents.base import BaseAgent
from clouddash.logging_setup import get_logger
from clouddash.models import (
    AgentResponse,
    AgentType,
    AttemptOutcome,
    ConversationState,
    HandoverReason,
    Sentiment,
    Urgency,
)
from clouddash.retrieval import get_retriever
from clouddash.tools.crm import lookup_customer

logger = get_logger(__name__)


class _BillingOutput(BaseModel):
    """Enum fields are str-typed; coerced in handle()."""

    response_text: str = Field(..., min_length=1, max_length=4000)
    confidence: float = Field(..., ge=0.0, le=1.0)
    requires_handover_to: str | None = Field(
        default=None,
        description="One of: triage, technical, billing, knowledge, escalation, or null.",
    )
    handover_reason: str | None = Field(
        default=None,
        description="One of: initial_route, out_of_scope, requires_escalation, low_confidence, multi_intent, customer_request, target_rejected, kb_miss.",
    )
    handover_summary: str | None = Field(default=None, max_length=1500)
    needs_escalation: bool = False
    escalation_reason: str | None = Field(default=None, max_length=600)
    extracted_entities: dict[str, Any] = Field(default_factory=dict)


class BillingAgent(BaseAgent):
    agent_type = AgentType.BILLING

    async def handle(self, state: ConversationState) -> AgentResponse:
        if state.pending_handover is not None and state.pending_handover.to_agent == self.agent_type:
            self.acknowledge_handover(state.pending_handover)

        latest = state.latest_user_message()
        latest_text = latest.content if latest else ""

        # CRM lookup if we have any customer hints
        crm_data = self._maybe_lookup_customer(state)

        # Retrieve KB
        chunks = get_retriever().retrieve(latest_text, state=state, top_k=4)
        is_grounded, top_score = grounding_signal(chunks)

        logger.info(
            "billing.retrieval_done",
            chunks=len(chunks),
            top_kb=chunks[0].kb_id if chunks else None,
            top_score=top_score,
            crm_hit=crm_data is not None,
        )

        prompt = self.system_prompt(
            customer_profile=render_customer_profile(state),
            handover_context=render_handover_context(state),
            crm_data=_render_crm_data(crm_data),
            conversation=state.conversation_text(last_n_turns=8),
            latest_message=latest_text,
            kb_chunks=render_kb_chunks(chunks),
        )

        structured = self.llm.with_structured_output(_BillingOutput)
        try:
            output: _BillingOutput = await structured.ainvoke(prompt)  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.error("billing.llm_failed", error=str(exc))
            return self._escalation_handover(
                state,
                reason="Billing Agent LLM failure",
                attempt_summary=f"LLM error: {exc}",
                confidence=0.2,
            )

        citations = chunks_to_used_citations(output.response_text, chunks)

        # Coerce LLM-emitted enum strings
        target_agent = coerce_agent_type(output.requires_handover_to)
        coerced_reason = coerce_handover_reason(output.handover_reason)

        # Escalation triggers
        if output.needs_escalation:
            return self._escalation_handover(
                state,
                reason=output.escalation_reason or "Billing Agent triggered escalation.",
                attempt_summary=output.response_text[:300],
                citations=citations,
                confidence=output.confidence,
            )

        # Domain handover (rare — billing→technical for tech-specific question)
        if target_agent is not None and target_agent != self.agent_type:
            return self._handover_to(
                state,
                target=target_agent,
                reason=coerced_reason or HandoverReason.OUT_OF_SCOPE,
                summary=output.handover_summary or output.response_text[:300],
                attempt_summary=output.response_text[:300],
                citations=citations,
                confidence=output.confidence,
                extracted_entities=output.extracted_entities,
            )

        # Final answer
        return AgentResponse(
            agent=self.agent_type,
            response_text=output.response_text,
            citations=citations,
            retrieved_chunks=chunks,
            confidence=output.confidence,
            metadata={
                "extracted_entities": output.extracted_entities,
                "crm_hit": crm_data is not None,
                "kb_top_score": top_score,
            },
        )

    # -------------------------------------------------------------------------

    def _maybe_lookup_customer(self, state: ConversationState) -> dict[str, Any] | None:
        cust_id = state.customer_profile.customer_id
        org = state.customer_profile.org_name
        if not cust_id and not org:
            # Try to extract from extracted_entities
            ent = (
                state.pending_handover.extracted_entities
                if state.pending_handover
                else state.metadata
            )
            cust_id = cust_id or ent.get("customer_id")
            org = org or ent.get("org_name")
        if not cust_id and not org:
            return None
        return lookup_customer(customer_id=cust_id, org_name=org)

    def _handover_to(
        self,
        state: ConversationState,
        *,
        target: AgentType,
        reason: HandoverReason,
        summary: str,
        attempt_summary: str,
        citations,
        confidence: float,
        extracted_entities: dict[str, Any],
    ) -> AgentResponse:
        prior = list(state.pending_handover.prior_attempts if state.pending_handover else [])
        prior.append(
            self.make_attempt_record(
                state,
                summary=attempt_summary,
                outcome=AttemptOutcome.PARTIAL_SUCCESS,
                confidence=confidence,
                citations=citations,
            )
        )
        sentiment = state.pending_handover.sentiment if state.pending_handover else Sentiment.NEUTRAL
        urgency = state.pending_handover.urgency if state.pending_handover else Urgency.MEDIUM
        user_intent = (
            state.pending_handover.user_intent
            if state.pending_handover
            else "Customer billing flow."
        )
        packet = self.make_handover_packet(
            state,
            to=target,
            reason=reason,
            summary=summary,
            user_intent=user_intent,
            confidence=confidence,
            prior_attempts=prior,
            sentiment=sentiment,
            urgency=urgency,
            extracted_entities=extracted_entities,
        )
        return AgentResponse(
            agent=self.agent_type,
            response_text="",
            citations=citations,
            confidence=confidence,
            handover_packet=packet,
            next_agent=target,
        )

    def _escalation_handover(
        self,
        state: ConversationState,
        *,
        reason: str,
        attempt_summary: str,
        citations=None,
        confidence: float = 0.5,
    ) -> AgentResponse:
        prior = list(state.pending_handover.prior_attempts if state.pending_handover else [])
        prior.append(
            self.make_attempt_record(
                state,
                summary=attempt_summary,
                outcome=AttemptOutcome.FAILED,
                confidence=confidence,
                citations=citations or [],
            )
        )
        sentiment = state.pending_handover.sentiment if state.pending_handover else Sentiment.FRUSTRATED
        urgency = state.pending_handover.urgency if state.pending_handover else Urgency.HIGH
        user_intent = (
            state.pending_handover.user_intent
            if state.pending_handover
            else "Customer billing escalation."
        )

        packet = self.make_handover_packet(
            state,
            to=AgentType.ESCALATION,
            reason=HandoverReason.REQUIRES_ESCALATION,
            summary=f"Billing Agent escalating: {reason}",
            user_intent=user_intent,
            confidence=confidence,
            prior_attempts=prior,
            sentiment=sentiment,
            urgency=urgency,
        )
        return AgentResponse(
            agent=self.agent_type,
            response_text="",
            confidence=confidence,
            handover_packet=packet,
            next_agent=AgentType.ESCALATION,
            metadata={"escalation_reason": reason},
        )


def _render_crm_data(crm: dict[str, Any] | None) -> str:
    if crm is None:
        return "(no customer record found — ask the customer for their customer ID or org name)"
    invoices = crm.get("current_invoices", [])
    inv_lines = [
        f"  - {i['invoice_id']} | ${i['amount_usd']} | {i['status']} | {i['billing_period']}"
        + (f" | NOTE: {i['note']}" if "note" in i else "")
        for i in invoices
    ]
    return (
        f"customer_id={crm['customer_id']} | org={crm['org_name']} | plan={crm['plan']}\n"
        f"email={crm.get('email')}\n"
        f"signup_date={crm.get('signup_date')}\n"
        f"sso_enabled={crm.get('sso_enabled')}\n"
        f"current invoices:\n" + ("\n".join(inv_lines) if inv_lines else "  (none)")
    )
