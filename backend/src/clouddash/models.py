"""Core Pydantic models + LangGraph TypedDict state.

TypedDict is what LangGraph wants for graph state (it's faster than Pydantic
for state mutations and handles the reducer annotations cleanly).
Pydantic models are used everywhere else — API schemas, handover packets, etc.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# --- enums -------------------------------------------------------------------

class AgentType(str, Enum):
    TRIAGE = "triage"
    TECHNICAL = "technical"
    BILLING = "billing"
    KNOWLEDGE = "knowledge"
    ESCALATION = "escalation"


class IntentCategory(str, Enum):
    TECHNICAL = "technical"
    BILLING = "billing"
    ACCOUNT = "account"
    GENERAL = "general"
    ESCALATION = "escalation"
    UNKNOWN = "unknown"


class HandoverReason(str, Enum):
    MULTI_INTENT = "multi_intent"
    OUT_OF_SCOPE = "out_of_scope"
    LOW_CONFIDENCE = "low_confidence"
    REQUIRES_ESCALATION = "requires_escalation"
    CUSTOMER_REQUEST = "customer_request"
    AGENT_FAILURE = "agent_failure"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"


class Urgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Plan(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class CRAGPath(str, Enum):
    DIRECT = "direct"           # confidence > 0.7
    SUPPLEMENT = "supplement"   # 0.3 < c <= 0.7, broader query added
    WEB_FALLBACK = "web_fallback"  # c <= 0.3, Tavily kicked in


# --- retrieval models --------------------------------------------------------

class RetrievedChunk(BaseModel):
    chunk_id: str
    kb_id: str
    title: str
    category: str
    section: int
    content: str
    rerank_score: float = 0.0
    rerank_rationale: str = ""  # why the reranker picked this
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: str = "kb"  # "kb" | "web" — CRAG can pull web chunks


class Citation(BaseModel):
    kb_id: str
    title: str
    section: int
    chunk_id: str
    relevance_score: float
    snippet: str = ""


class RelevanceScore(BaseModel):
    """CRAG relevance evaluator output."""
    chunk_id: str
    score: float
    rationale: str


class CRAGEvalResult(BaseModel):
    overall_confidence: float
    path: CRAGPath
    chunk_scores: list[RelevanceScore] = Field(default_factory=list)
    rewrite_query: str | None = None  # set if path != DIRECT


# --- intent/triage models ----------------------------------------------------

class IntentClassification(BaseModel):
    """Structured output from the Triage agent LLM call."""
    primary_intent: IntentCategory
    secondary_intent: IntentCategory | list[IntentCategory] | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    entities: dict[str, Any] = Field(default_factory=dict)
    sentiment: Sentiment = Sentiment.NEUTRAL
    urgency: Urgency = Urgency.MEDIUM
    escalate_immediately: bool = False
    reasoning: str = ""  # not shown to user, for LangSmith traces


class LanguageDetection(BaseModel):
    """Sarvam language detection output."""
    detected_language: str  # ISO 639-1 code: "hi", "ta", "te", etc. or "en"
    is_indian_language: bool
    greeting: str = ""  # pre-generated greeting in detected language


# --- customer / CRM ----------------------------------------------------------

class CustomerProfile(BaseModel):
    customer_id: str = ""
    plan: Plan = Plan.FREE
    org_name: str = ""
    email: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- handover ----------------------------------------------------------------

class AttemptRecord(BaseModel):
    agent: AgentType
    turn_id: int
    summary: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = 0.0


class HandoverPacket(BaseModel):
    packet_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    trace_id: uuid.UUID
    turn_id: int
    from_agent: AgentType
    to_agent: AgentType
    reason: HandoverReason
    user_intent: str
    conversation_summary: str
    customer_profile: CustomerProfile = Field(default_factory=CustomerProfile)
    extracted_entities: dict[str, Any] = Field(default_factory=dict)
    prior_attempts: list[AttemptRecord] = Field(default_factory=list)
    confidence_state: float = 0.5
    sentiment: Sentiment = Sentiment.NEUTRAL
    urgency: Urgency = Urgency.MEDIUM
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


# --- escalation --------------------------------------------------------------

class EscalationTicket(BaseModel):
    ticket_id: str = Field(default_factory=lambda: f"TKT-{uuid.uuid4().hex[:8].upper()}")
    priority: Urgency
    customer_id: str
    issue_summary: str
    recommended_actions: list[str]
    conversation_summary: str
    sentiment: Sentiment
    estimated_resolution_hours: int = 24
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


# --- agent response ----------------------------------------------------------

class AgentResponse(BaseModel):
    agent: AgentType
    response_text: str = ""
    citations: list[Citation] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    confidence: float = 0.5
    handover_packet: HandoverPacket | None = None
    next_agent: AgentType | None = None
    escalate: bool = False
    escalation_ticket: EscalationTicket | None = None
    crag_path: CRAGPath | None = None
    latency_ms: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- LangGraph state ---------------------------------------------------------
# TypedDict because that's what LangGraph checkpointing works best with.
# add_messages is LangGraph's built-in reducer (appends, handles dedup by id).

class GraphState(TypedDict):
    # the actual chat messages — LangChain BaseMessage objects
    messages: Annotated[list[BaseMessage], add_messages]

    # conversation metadata
    conversation_id: str
    trace_id: str
    turn_id: int

    # customer context (populated after first CRM lookup or extracted from message)
    customer_profile: CustomerProfile

    # triage output — lives on state so downstream nodes can read routing info
    intent: IntentCategory | None
    intent_classification: IntentClassification | None

    # which agent is currently handling the turn
    current_agent: AgentType | None

    # the latest substantive response from a specialist
    last_response: AgentResponse | None

    # handover state
    pending_handover: HandoverPacket | None
    handover_chain: list[HandoverPacket]  # full trail, audit log

    # escalation HITL — set when interrupt() fires
    escalation_ticket_draft: EscalationTicket | None
    hitl_decision: str | None  # "approve" | "edit" | "reject", set on resume

    # multilingual
    language_detection: LanguageDetection | None
    greeting_sent: bool

    # retrieved context — passed between retrieval subgraph and specialist
    retrieved_chunks: list[RetrievedChunk]
    crag_path: CRAGPath | None

    # routing decision stored as simple string so checkpoint serializers don't mangle it
    # serializers can restore Pydantic models as dicts — routing from resp.next_agent
    # was failing because resp became a dict. Storing separately is cleaner.
    next_route: str  # "" = done, "technical"|"billing"|etc = handover


def make_initial_state(conversation_id: str) -> GraphState:
    """Build the starting state for a new conversation thread."""
    return GraphState(
        messages=[],
        conversation_id=conversation_id,
        trace_id=str(uuid.uuid4()),
        turn_id=0,
        customer_profile=CustomerProfile(),
        intent=None,
        intent_classification=None,
        current_agent=None,
        last_response=None,
        pending_handover=None,
        handover_chain=[],
        escalation_ticket_draft=None,
        hitl_decision=None,
        language_detection=None,
        greeting_sent=False,
        retrieved_chunks=[],
        crag_path=None,
        next_route="",
    )
