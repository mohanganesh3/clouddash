"""Smoke tests for typed models — establishes the foundation works before agents."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from clouddash.models import (
    AgentResponse,
    AgentType,
    Citation,
    ConversationState,
    CustomerProfile,
    HandoverEvent,
    HandoverPacket,
    HandoverReason,
    HandoverStatus,
    Message,
    MessageRole,
    Plan,
    Sentiment,
    Urgency,
)


class TestCitation:
    def test_inline_with_section(self) -> None:
        cit = Citation(
            kb_id="KB-007",
            title="AWS Integration",
            section=3,
            chunk_id="x",
            relevance_score=0.9,
            snippet="...",
        )
        assert cit.render_inline() == "[KB-007 § 3]"

    def test_inline_without_section(self) -> None:
        cit = Citation(
            kb_id="KB-007",
            title="AWS Integration",
            chunk_id="x",
            relevance_score=0.9,
            snippet="...",
        )
        assert cit.render_inline() == "[KB-007]"


class TestCustomerProfile:
    def test_merge_prefers_existing_non_null(self) -> None:
        a = CustomerProfile(customer_id="A", plan=Plan.PRO)
        b = CustomerProfile(customer_id="B", org_name="Acme")
        merged = a.merge(b)
        assert merged.customer_id == "A"  # a wins
        assert merged.plan == Plan.PRO
        assert merged.org_name == "Acme"  # filled from b


class TestHandoverPacket:
    def test_rejects_self_handover(self, sample_customer: CustomerProfile) -> None:
        with pytest.raises(ValidationError, match="must differ"):
            HandoverPacket(
                trace_id=uuid4(),
                turn_id=1,
                from_agent=AgentType.TECHNICAL,
                to_agent=AgentType.TECHNICAL,
                reason=HandoverReason.OUT_OF_SCOPE,
                user_intent="x",
                conversation_summary="y",
                customer_profile=sample_customer,
            )

    def test_with_audit_event_appends(
        self, sample_handover_packet: HandoverPacket
    ) -> None:
        event = HandoverEvent(
            trace_id=sample_handover_packet.trace_id,
            turn_id=2,
            from_agent=AgentType.TECHNICAL,
            to_agent=AgentType.BILLING,
            reason=HandoverReason.MULTI_INTENT,
            status=HandoverStatus.ACCEPTED,
        )
        new = sample_handover_packet.with_audit_event(event)
        assert len(new.audit_chain) == len(sample_handover_packet.audit_chain) + 1
        # original is unchanged (immutability via model_copy)
        assert new.audit_chain[-1].event_id == event.event_id

    def test_default_sentiment_and_urgency(
        self, sample_handover_packet: HandoverPacket
    ) -> None:
        # Scenario 3 requires these to exist in the packet schema
        assert sample_handover_packet.sentiment == Sentiment.NEUTRAL
        assert sample_handover_packet.urgency == Urgency.MEDIUM


class TestAgentResponse:
    def test_requires_terminal_signal(self) -> None:
        with pytest.raises(ValidationError, match="must either provide"):
            AgentResponse(agent=AgentType.TECHNICAL)  # no text, no handover, no escalate

    def test_text_only_is_valid(self) -> None:
        resp = AgentResponse(agent=AgentType.TECHNICAL, response_text="Here's the fix.")
        assert resp.response_text == "Here's the fix."

    def test_handover_only_is_valid(self, sample_handover_packet: HandoverPacket) -> None:
        resp = AgentResponse(
            agent=AgentType.TRIAGE,
            handover_packet=sample_handover_packet,
            next_agent=AgentType.TECHNICAL,
        )
        assert resp.next_agent == AgentType.TECHNICAL

    def test_escalate_only_is_valid(self) -> None:
        resp = AgentResponse(agent=AgentType.ESCALATION, escalate=True)
        assert resp.escalate is True


class TestConversationState:
    def test_latest_user_message(self) -> None:
        msgs = [
            Message(role=MessageRole.USER, content="hi", turn_id=1),
            Message(role=MessageRole.ASSISTANT, content="hello", turn_id=1, agent=AgentType.TRIAGE),
            Message(role=MessageRole.USER, content="alerts broken", turn_id=2),
        ]
        state = ConversationState(messages=msgs, turn_id=2)
        latest = state.latest_user_message()
        assert latest is not None
        assert latest.content == "alerts broken"

    def test_conversation_text_renders(
        self, sample_conversation_state: ConversationState
    ) -> None:
        text = sample_conversation_state.conversation_text()
        assert "[user]" in text
        assert "alerts" in text


class TestSettings:
    def test_settings_load(self) -> None:
        """Ensure pydantic-settings loads cleanly from env."""
        from clouddash.settings import get_settings

        s = get_settings()
        assert s.app_env == "test"
        # Model names come from env (.env.example) — just assert they're strings
        assert isinstance(s.llm_reasoning_model, str)
        assert len(s.llm_reasoning_model) > 0
        assert s.retrieval_top_k_reranked == 3
