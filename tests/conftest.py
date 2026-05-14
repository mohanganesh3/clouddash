"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from clouddash.models import (
    AgentType,
    AttemptOutcome,
    AttemptRecord,
    Citation,
    ConversationState,
    CustomerProfile,
    HandoverPacket,
    HandoverReason,
    Message,
    MessageRole,
    Plan,
    Sentiment,
    Urgency,
)


@pytest.fixture(autouse=True)
def _isolate_logs(tmp_path, monkeypatch):
    """Redirect logs to a tmp dir so tests don't pollute logs/."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setenv("LOG_DIR", str(log_dir))
    monkeypatch.setenv("AUDIT_LOG_PATH", str(log_dir / "audit.jsonl"))
    monkeypatch.setenv("APP_ENV", "test")
    # Don't try to actually call LLM providers in unit tests
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test-not-real")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GROQ_API_KEY", "gsk-test-not-real")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")

    # Clear settings cache so the new env is picked up
    from clouddash.settings import reload_settings

    reload_settings()


@pytest.fixture
def sample_customer() -> CustomerProfile:
    return CustomerProfile(
        customer_id="cust_acme_42",
        plan=Plan.PRO,
        org_name="Acme Corp",
        email="ops@acme.example",
    )


@pytest.fixture
def sample_user_message() -> Message:
    return Message(
        role=MessageRole.USER,
        content="My CloudDash alerts stopped firing after I updated my AWS credentials yesterday.",
        turn_id=1,
    )


@pytest.fixture
def sample_citation() -> Citation:
    return Citation(
        kb_id="KB-007",
        title="How to Configure AWS CloudWatch Integration",
        section=3,
        chunk_id="KB-007-chunk-3",
        relevance_score=0.92,
        snippet="To re-link AWS credentials, navigate to Settings → Integrations → AWS...",
    )


@pytest.fixture
def sample_handover_packet(
    sample_customer: CustomerProfile,
    sample_citation: Citation,
) -> HandoverPacket:
    trace_id = uuid4()
    return HandoverPacket(
        trace_id=trace_id,
        turn_id=2,
        from_agent=AgentType.TECHNICAL,
        to_agent=AgentType.BILLING,
        reason=HandoverReason.MULTI_INTENT,
        user_intent="Customer wants to verify SSO fix and upgrade Pro → Enterprise",
        conversation_summary="User reported SSO issue last week; today asks if resolved AND wants to upgrade.",
        customer_profile=sample_customer,
        extracted_entities={"target_plan": "Enterprise", "current_plan": "Pro"},
        prior_attempts=[
            AttemptRecord(
                agent=AgentType.TECHNICAL,
                turn_id=1,
                summary="Verified SSO config; confirmed last week's fix is live.",
                outcome=AttemptOutcome.PARTIAL_SUCCESS,
                citations=[sample_citation],
                confidence=0.85,
            )
        ],
        confidence_state=0.85,
        sentiment=Sentiment.NEUTRAL,
        urgency=Urgency.MEDIUM,
    )


@pytest.fixture
def sample_conversation_state(
    sample_customer: CustomerProfile,
    sample_user_message: Message,
) -> ConversationState:
    return ConversationState(
        customer_profile=sample_customer,
        messages=[sample_user_message],
        turn_id=1,
    )
