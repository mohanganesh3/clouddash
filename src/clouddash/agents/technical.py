"""Technical Support Agent — KB-grounded troubleshooting.

Domain: alerts, integrations (AWS/GCP/Azure/K8s), dashboards, API, webhooks,
SDK, SSO troubleshooting, RBAC questions, audit logs.

Flow:
1. Acknowledge incoming handover (if any).
2. Retrieve KB chunks via the hybrid retriever.
3. Build prompt with chunks + handover context + conversation.
4. LLM structured output with citation requirements.
5. Validate citations against retrieved chunks.
6. If multi-intent: emit handover to next specialist; else respond.
7. If can't resolve: handover to escalation.
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
    IntentCategory,
    Sentiment,
    Urgency,
)
from clouddash.retrieval import get_retriever

logger = get_logger(__name__)


class _TechnicalOutput(BaseModel):
    """Structured output. Enum fields are str-typed to be resilient to LLM
    mistakes (Gemini occasionally returns sentences for enum fields). We
    coerce them to AgentType / HandoverReason in handle()."""

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
    extracted_entities: dict[str, Any] = Field(default_factory=dict)


class TechnicalAgent(BaseAgent):
    agent_type = AgentType.TECHNICAL

    async def handle(self, state: ConversationState) -> AgentResponse:
        # 1. Acknowledge handover
        if state.pending_handover is not None and state.pending_handover.to_agent == self.agent_type:
            self.acknowledge_handover(state.pending_handover)

        latest = state.latest_user_message()
        latest_text = latest.content if latest else ""

        # 2. Retrieve KB chunks
        chunks = get_retriever().retrieve(latest_text, state=state, top_k=4)
        is_grounded, top_score = grounding_signal(chunks)

        logger.info(
            "technical.retrieval_done",
            chunks=len(chunks),
            top_score=top_score,
            is_grounded=is_grounded,
            top_kb=chunks[0].kb_id if chunks else None,
        )

        # 3. Build prompt
        prompt = self.system_prompt(
            customer_profile=render_customer_profile(state),
            handover_context=render_handover_context(state),
            conversation=state.conversation_text(last_n_turns=8),
            latest_message=latest_text,
            kb_chunks=render_kb_chunks(chunks),
        )

        # 4. LLM call
        structured = self.llm.with_structured_output(_TechnicalOutput)
        try:
            output: _TechnicalOutput = await structured.ainvoke(prompt)  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.error("technical.llm_failed", error=str(exc))
            return self._escalation_handover(
                state, chunks, reason_text=f"Technical Agent LLM failure: {exc}"
            )

        # 5. Build citations from response_text
        citations = chunks_to_used_citations(output.response_text, chunks)

        # 6. Coerce LLM-emitted enums (Gemini sometimes returns sentences)
        target_agent = coerce_agent_type(output.requires_handover_to)
        coerced_reason = coerce_handover_reason(output.handover_reason)
        secondary_intents = self._extract_secondary_intents(state)

        # 7. Decide: handover to billing (multi-intent), to escalation, or final answer
        if output.needs_escalation:
            return self._escalation_handover(
                state,
                chunks,
                summary=output.handover_summary
                or f"Technical Agent could not resolve. {output.response_text[:200]}",
                attempt_summary=output.response_text[:300],
                citations=citations,
                confidence=output.confidence,
            )

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

        # Multi-intent chaining: if state's prior packet listed secondary intents,
        # AND the agent answered without explicit handover, chain to the next intent
        if secondary_intents:
            next_intent = secondary_intents[0]
            from clouddash.agents.registry import get_registry
            target = get_registry().route_intent(next_intent)
            if target != self.agent_type:
                # Pass remaining intents forward
                remaining = secondary_intents[1:]
                fwd_entities = {**output.extracted_entities}
                if remaining:
                    fwd_entities["secondary_intents"] = [i.value for i in remaining]
                return self._handover_to(
                    state,
                    target=target,
                    reason=HandoverReason.MULTI_INTENT,
                    summary=(
                        output.handover_summary
                        or f"Technical Agent resolved its part ({output.response_text[:200]}). "
                        f"Customer also has a {next_intent.value} intent — please handle that."
                    ),
                    attempt_summary=output.response_text[:300],
                    citations=citations,
                    confidence=output.confidence,
                    extracted_entities=fwd_entities,
                    response_text=output.response_text,  # carry the partial answer forward
                )

        # 7. Final answer
        return AgentResponse(
            agent=self.agent_type,
            response_text=output.response_text,
            citations=citations,
            retrieved_chunks=chunks,
            confidence=output.confidence,
            metadata={
                "extracted_entities": output.extracted_entities,
                "kb_top_score": top_score,
                "is_grounded": is_grounded,
            },
        )

    # -------------------------------------------------------------------------

    def _extract_secondary_intents(self, state: ConversationState) -> list[IntentCategory]:
        if state.pending_handover is None:
            return []
        raw = state.pending_handover.extracted_entities.get("secondary_intents")
        if not raw:
            return []
        intents: list[IntentCategory] = []
        for item in raw:
            try:
                intents.append(IntentCategory(item))
            except ValueError:
                continue
        return intents

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
        response_text: str = "",
    ) -> AgentResponse:
        prior_attempts = list(
            state.pending_handover.prior_attempts if state.pending_handover else []
        )
        prior_attempts.append(
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
            state.pending_handover.user_intent if state.pending_handover else "Continued from technical agent."
        )

        packet = self.make_handover_packet(
            state,
            to=target,
            reason=reason,
            summary=summary,
            user_intent=user_intent,
            confidence=confidence,
            prior_attempts=prior_attempts,
            sentiment=sentiment,
            urgency=urgency,
            extracted_entities=extracted_entities,
        )

        return AgentResponse(
            agent=self.agent_type,
            response_text=response_text,  # may be empty or carry partial answer
            citations=citations,
            retrieved_chunks=[],  # downstream will retrieve again
            confidence=confidence,
            handover_packet=packet,
            next_agent=target,
        )

    def _escalation_handover(
        self,
        state: ConversationState,
        chunks,
        *,
        reason_text: str = "",
        summary: str | None = None,
        attempt_summary: str | None = None,
        citations=None,
        confidence: float = 0.4,
    ) -> AgentResponse:
        prior_attempts = list(
            state.pending_handover.prior_attempts if state.pending_handover else []
        )
        if attempt_summary:
            prior_attempts.append(
                self.make_attempt_record(
                    state,
                    summary=attempt_summary,
                    outcome=AttemptOutcome.FAILED,
                    confidence=confidence,
                    citations=citations or [],
                )
            )

        sentiment = state.pending_handover.sentiment if state.pending_handover else Sentiment.NEUTRAL
        urgency = state.pending_handover.urgency if state.pending_handover else Urgency.MEDIUM
        user_intent = (
            state.pending_handover.user_intent
            if state.pending_handover
            else "Customer needs human assistance."
        )

        packet = self.make_handover_packet(
            state,
            to=AgentType.ESCALATION,
            reason=HandoverReason.REQUIRES_ESCALATION,
            summary=summary or f"Technical Agent escalating. {reason_text}",
            user_intent=user_intent,
            confidence=confidence,
            prior_attempts=prior_attempts,
            sentiment=sentiment,
            urgency=urgency,
        )

        return AgentResponse(
            agent=self.agent_type,
            response_text="",
            confidence=confidence,
            handover_packet=packet,
            next_agent=AgentType.ESCALATION,
            metadata={"escalation_reason": reason_text},
        )
