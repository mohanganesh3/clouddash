"""Knowledge Agent — general inquiries + Scenario 4 KB-miss handler.

Owns the refusal-to-fabricate path. When KB grounding is insufficient, this
agent transparently acknowledges the gap and offers to file a feature
request via `tools.escalation_tools.create_feature_request`.
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
from clouddash.tools.escalation_tools import create_feature_request

logger = get_logger(__name__)


class _KnowledgeOutput(BaseModel):
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
    should_create_feature_request: bool = False
    feature_request_summary: str | None = Field(default=None, max_length=400)
    extracted_entities: dict[str, Any] = Field(default_factory=dict)


class KnowledgeAgent(BaseAgent):
    agent_type = AgentType.KNOWLEDGE

    async def handle(self, state: ConversationState) -> AgentResponse:
        if state.pending_handover is not None and state.pending_handover.to_agent == self.agent_type:
            self.acknowledge_handover(state.pending_handover)

        latest = state.latest_user_message()
        latest_text = latest.content if latest else ""

        chunks = get_retriever().retrieve(latest_text, state=state, top_k=4)
        is_grounded, top_score = grounding_signal(chunks)

        logger.info(
            "knowledge.retrieval_done",
            chunks=len(chunks),
            top_score=top_score,
            is_grounded=is_grounded,
        )

        prompt = self.system_prompt(
            customer_profile=render_customer_profile(state),
            handover_context=render_handover_context(state),
            conversation=state.conversation_text(last_n_turns=8),
            latest_message=latest_text,
            kb_chunks=render_kb_chunks(chunks),
        )

        structured = self.llm.with_structured_output(_KnowledgeOutput)
        try:
            output: _KnowledgeOutput = await structured.ainvoke(prompt)  # type: ignore[assignment]
        except Exception as exc:  # noqa: BLE001
            logger.error("knowledge.llm_failed", error=str(exc))
            return AgentResponse(
                agent=self.agent_type,
                response_text=(
                    "I'm having trouble looking up that information right now. "
                    "I can connect you with a human teammate if that helps — would you like me to escalate?"
                ),
                citations=[],
                confidence=0.2,
            )

        citations = chunks_to_used_citations(output.response_text, chunks)

        # Feature-request creation (Scenario 4)
        feature_request_id: str | None = None
        if output.should_create_feature_request and output.feature_request_summary:
            try:
                fr = create_feature_request(
                    title=output.feature_request_summary[:200],
                    summary=output.feature_request_summary,
                    customer_id=state.customer_profile.customer_id,
                    org_name=state.customer_profile.org_name,
                )
                feature_request_id = fr["feature_request_id"]
                logger.info(
                    "knowledge.feature_request_filed",
                    fr_id=feature_request_id,
                    summary=output.feature_request_summary,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("knowledge.feature_request_failed", error=str(exc))

        # Escalation
        if output.needs_escalation:
            prior = list(state.pending_handover.prior_attempts if state.pending_handover else [])
            prior.append(
                self.make_attempt_record(
                    state,
                    summary=output.response_text[:300],
                    outcome=AttemptOutcome.KB_INSUFFICIENT,
                    confidence=output.confidence,
                    citations=citations,
                )
            )
            sentiment = (
                state.pending_handover.sentiment if state.pending_handover else Sentiment.NEUTRAL
            )
            urgency = state.pending_handover.urgency if state.pending_handover else Urgency.MEDIUM
            packet = self.make_handover_packet(
                state,
                to=AgentType.ESCALATION,
                reason=HandoverReason.KB_MISS,
                summary=output.handover_summary or "Knowledge Agent escalating after KB miss.",
                user_intent=(
                    state.pending_handover.user_intent
                    if state.pending_handover
                    else "Customer asked about something not covered in the KB."
                ),
                confidence=output.confidence,
                prior_attempts=prior,
                sentiment=sentiment,
                urgency=urgency,
            )
            return AgentResponse(
                agent=self.agent_type,
                response_text="",
                citations=citations,
                confidence=output.confidence,
                handover_packet=packet,
                next_agent=AgentType.ESCALATION,
            )

        # Final answer (typical Scenario 4 path: refusal + feature request offered)
        metadata: dict[str, Any] = {
            "extracted_entities": output.extracted_entities,
            "kb_top_score": top_score,
            "is_grounded": is_grounded,
            "should_create_feature_request": output.should_create_feature_request,
        }
        if feature_request_id:
            metadata["feature_request_id"] = feature_request_id

        return AgentResponse(
            agent=self.agent_type,
            response_text=output.response_text,
            citations=citations,
            retrieved_chunks=chunks,
            confidence=output.confidence,
            metadata=metadata,
        )
