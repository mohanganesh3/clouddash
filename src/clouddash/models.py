"""Core typed data models — the single source of truth for all in-memory state.

Per ADR-002: every cross-component message is a Pydantic model. This file
defines: enums, conversation primitives, the HandoverPacket contract,
agent I/O schemas, KB/retrieval types, eval types.

Design principles:
- Pydantic v2 with strict typing — no `Any` except where genuinely free-form.
- Every model has a docstring explaining WHY it exists, not just WHAT it is.
- Enums for closed sets — string values match what we expect from LLM outputs.
- Default factories use UTC timestamps and uuid4 — never naive `datetime.now()`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow() -> datetime:
    """Always-aware UTC timestamp. Use everywhere instead of datetime.utcnow()."""
    return datetime.now(timezone.utc)


# =============================================================================
# Enums
# =============================================================================


class AgentType(str, Enum):
    """Identifiers for every agent in the system. Drives routing + audit logs."""

    TRIAGE = "triage"
    TECHNICAL = "technical"
    BILLING = "billing"
    KNOWLEDGE = "knowledge"
    ESCALATION = "escalation"
    HUMAN = "human"  # simulated human operator (Scenario 3)


class IntentCategory(str, Enum):
    """High-level intent labels emitted by the Triage classifier.

    Maps to (but is not identical to) AgentType — see config/routing.yaml.
    """

    TECHNICAL = "technical"
    BILLING = "billing"
    ACCOUNT = "account"
    GENERAL = "general"
    UNKNOWN = "unknown"


class HandoverReason(str, Enum):
    """Why one agent handed off to another. Required by §2.3 audit log."""

    INITIAL_ROUTE = "initial_route"  # Triage → first specialist
    OUT_OF_SCOPE = "out_of_scope"  # specialist hit a domain it doesn't own
    REQUIRES_ESCALATION = "requires_escalation"  # need human
    LOW_CONFIDENCE = "low_confidence"  # specialist not sure
    MULTI_INTENT = "multi_intent"  # query has multiple intents (Scenario 2)
    CUSTOMER_REQUEST = "customer_request"  # user asked for a manager
    TARGET_REJECTED = "target_rejected"  # fallback after Reject
    KB_MISS = "kb_miss"  # no grounded answer (Scenario 4)


class HandoverStatus(str, Enum):
    """Lifecycle state of a single handover."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"


class Sentiment(str, Enum):
    """Customer sentiment — required for Scenario 3 escalation packet."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    FRUSTRATED = "frustrated"
    ANGRY = "angry"


class Urgency(str, Enum):
    """Issue urgency — required for Scenario 3 escalation packet."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Plan(str, Enum):
    """CloudDash subscription tiers. Used by KB filtering + Billing agent."""

    FREE = "Free"
    STARTER = "Starter"
    PRO = "Pro"
    ENTERPRISE = "Enterprise"


class MessageRole(str, Enum):
    """Conversation message roles."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AttemptOutcome(str, Enum):
    """Result of a specialist's attempt before handing off."""

    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    OUT_OF_SCOPE = "out_of_scope"
    KB_INSUFFICIENT = "kb_insufficient"


# =============================================================================
# Retrieval primitives
# =============================================================================


class Citation(BaseModel):
    """A single citation embedded in an agent response.

    Format used inline in text: `[KB-XXX § N]`.
    The full Citation object is also returned in the API response so the
    customer can verify the source (per §2.2).
    """

    model_config = ConfigDict(frozen=True)

    kb_id: str = Field(..., description="KB article identifier (e.g. KB-007).")
    title: str
    section: int | None = Field(default=None, description="§ N within the article.")
    chunk_id: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    snippet: str = Field(..., max_length=400)

    def render_inline(self) -> str:
        """How this citation appears in an agent's text response."""
        if self.section is not None:
            return f"[{self.kb_id} § {self.section}]"
        return f"[{self.kb_id}]"


class RetrievedChunk(BaseModel):
    """A chunk pulled from the vector store + reranker.

    Returned alongside agent responses for verification AND fed into the
    grounding guardrail (ADR-005).
    """

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    kb_id: str
    title: str
    category: str
    section: int | None = None
    content: str
    bm25_score: float | None = None
    dense_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None
    rerank_rationale: str | None = Field(
        default=None,
        description="Why the LLM reranker rated this chunk — debugging gold.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def composite_score(self) -> float:
        """Final score used for the grounding threshold."""
        return self.rerank_score if self.rerank_score is not None else (self.rrf_score or 0.0)

    def to_citation(self) -> Citation:
        return Citation(
            kb_id=self.kb_id,
            title=self.title,
            section=self.section,
            chunk_id=self.chunk_id,
            relevance_score=self.composite_score,
            snippet=self.content[:300],
        )


class KBArticle(BaseModel):
    """A canonical KB article (pre-chunking).

    Loaded from `knowledge_base/**/*.md` with YAML frontmatter.
    """

    id: str = Field(..., pattern=r"^KB-\d{3,4}$")
    title: str
    category: str
    tags: list[str] = Field(default_factory=list)
    content: str
    last_updated: str  # ISO date
    applies_to: list[str] = Field(default_factory=list)  # plan tiers
    source_path: str | None = None


# =============================================================================
# Conversation primitives
# =============================================================================


class CustomerProfile(BaseModel):
    """Entities extracted about the customer over the conversation."""

    customer_id: str | None = None
    plan: Plan | None = None
    org_name: str | None = None
    email: str | None = None
    extracted_entities: dict[str, Any] = Field(default_factory=dict)
    extracted_at: datetime = Field(default_factory=utcnow)

    def merge(self, other: CustomerProfile) -> CustomerProfile:
        """Merge new info into the profile, preferring existing non-null values."""
        return CustomerProfile(
            customer_id=self.customer_id or other.customer_id,
            plan=self.plan or other.plan,
            org_name=self.org_name or other.org_name,
            email=self.email or other.email,
            extracted_entities={**other.extracted_entities, **self.extracted_entities},
            extracted_at=utcnow(),
        )


class Message(BaseModel):
    """One message in the conversation transcript."""

    message_id: UUID = Field(default_factory=uuid4)
    role: MessageRole
    content: str
    agent: AgentType | None = None  # None for user messages
    turn_id: int
    timestamp: datetime = Field(default_factory=utcnow)
    citations: list[Citation] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Handover Protocol (the core differentiator for §2.3)
# =============================================================================


class AttemptRecord(BaseModel):
    """What a specialist tried before handing off — preserves history per §2.3."""

    agent: AgentType
    turn_id: int
    summary: str = Field(..., description="One-paragraph summary of what was attempted.")
    outcome: AttemptOutcome
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=utcnow)


class HandoverEvent(BaseModel):
    """One entry in the audit chain.

    These are written to the JSONL audit log AND attached to subsequent
    HandoverPackets so the full chain travels with the conversation.
    """

    event_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    turn_id: int
    from_agent: AgentType
    to_agent: AgentType
    reason: HandoverReason
    status: HandoverStatus = HandoverStatus.PENDING
    note: str | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class HandoverPacket(BaseModel):
    """THE typed contract between agents.

    Per ADR-002. Receiving agents read this exclusively — they do NOT inspect
    raw conversation history. This forces clean information transfer and
    prevents context pollution.

    Required fields satisfy the §2.3 checklist:
    - Full conversation summary (preserves history)
    - extracted_entities (preserves entities)
    - prior_attempts (so receiving agent doesn't repeat work)
    - audit_chain (timestamp, source, target, reason, snapshot)
    - sentiment / urgency (Scenario 3 requirement, baked in)
    """

    packet_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    turn_id: int

    from_agent: AgentType
    to_agent: AgentType
    reason: HandoverReason

    user_intent: str = Field(
        ...,
        description="One-sentence statement of what the user is trying to accomplish.",
    )
    conversation_summary: str = Field(
        ...,
        description="LLM-generated structured summary of the conversation so far.",
    )
    customer_profile: CustomerProfile

    # Captured signals
    extracted_entities: dict[str, Any] = Field(default_factory=dict)
    prior_attempts: list[AttemptRecord] = Field(default_factory=list)
    confidence_state: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Source agent's confidence after their attempt.",
    )
    sentiment: Sentiment = Sentiment.NEUTRAL
    urgency: Urgency = Urgency.MEDIUM

    # Provenance
    audit_chain: list[HandoverEvent] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _validate_distinct_agents(self) -> HandoverPacket:
        if self.from_agent == self.to_agent:
            raise ValueError(
                f"Handover from_agent and to_agent must differ (both={self.from_agent})"
            )
        return self

    def with_audit_event(self, event: HandoverEvent) -> HandoverPacket:
        """Return a new packet with the event appended to the audit chain."""
        return self.model_copy(update={"audit_chain": [*self.audit_chain, event]})


class HandoverAck(BaseModel):
    """Receiving agent acknowledges and accepts the packet.

    §2.3: 'Allow the receiving agent to acknowledge the handover'. Without
    an explicit ack step, agents silently take over — we surface this signal
    so it's visible in audit logs and demos.
    """

    packet_id: UUID
    accepted_by: AgentType
    note: str | None = None
    timestamp: datetime = Field(default_factory=utcnow)


class HandoverReject(BaseModel):
    """Receiving agent rejects the packet.

    Triggers the §2.3 'Handle failed handovers gracefully' fallback chain
    (defined in handover/failover.py).
    """

    packet_id: UUID
    rejected_by: AgentType
    reason: str
    suggest_route_to: AgentType | None = None
    timestamp: datetime = Field(default_factory=utcnow)


# =============================================================================
# Triage / Classification
# =============================================================================


class IntentClassification(BaseModel):
    """Output of the Triage classifier.

    Drives the routing decision. `is_multi_intent=True` triggers Scenario 2
    cross-agent handover (we route to first intent's agent, then chain).
    """

    primary_intent: IntentCategory
    secondary_intents: list[IntentCategory] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., max_length=1000)
    suggested_agent: AgentType
    is_multi_intent: bool = False
    extracted_entities: dict[str, Any] = Field(default_factory=dict)
    sentiment: Sentiment = Sentiment.NEUTRAL
    urgency: Urgency = Urgency.MEDIUM


# =============================================================================
# Guardrails
# =============================================================================


GuardrailAction = Literal["allow", "block", "redact", "self_correct"]


class GuardrailResult(BaseModel):
    """Outcome of one guardrail check.

    Multiple results can be aggregated by the orchestrator — any single
    `passed=False` with action='block' halts the operation.
    """

    guardrail_name: str
    layer: Literal["input", "output"]
    passed: bool
    action: GuardrailAction = "allow"
    reason: str | None = None
    sanitized_content: str | None = Field(
        default=None,
        description="Redacted version when action='redact'.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utcnow)


# =============================================================================
# Tool calls (for Billing agent's mock CRM, etc.)
# =============================================================================


class ToolCall(BaseModel):
    """An agent's request to invoke a tool."""

    tool_name: str
    arguments: dict[str, Any]
    call_id: UUID = Field(default_factory=uuid4)


class ToolResult(BaseModel):
    """Result of a tool invocation."""

    call_id: UUID
    tool_name: str
    success: bool
    output: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: int | None = None


# =============================================================================
# Agent I/O
# =============================================================================


class AgentResponse(BaseModel):
    """Standard structured output from any agent.

    Every agent.handle() returns this. Three terminal signals:
    - response_text non-empty + handover_packet None → final answer to user
    - handover_packet not None → need to route to another agent
    - escalate=True → trigger human handoff
    """

    agent: AgentType
    response_text: str = ""
    citations: list[Citation] = Field(default_factory=list)
    retrieved_chunks: list[RetrievedChunk] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    tool_calls: list[ToolCall] = Field(default_factory=list)

    # Handover signals
    handover_packet: HandoverPacket | None = None
    next_agent: AgentType | None = None
    escalate: bool = False

    # Observability
    latency_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_terminal_signal(self) -> AgentResponse:
        # Must have either text OR a handover/escalate signal
        has_text = bool(self.response_text.strip())
        has_handover = self.handover_packet is not None or self.next_agent is not None
        if not has_text and not has_handover and not self.escalate:
            raise ValueError(
                "AgentResponse must either provide response_text, request handover, or escalate"
            )
        return self


# =============================================================================
# Conversation state (LangGraph state schema)
# =============================================================================


def _add_messages(left: list[Message], right: list[Message]) -> list[Message]:
    """Reducer for LangGraph: append new messages to the list."""
    return [*left, *right]


def _add_handover_events(
    left: list[HandoverEvent], right: list[HandoverEvent]
) -> list[HandoverEvent]:
    """Reducer for LangGraph: append new handover events."""
    return [*left, *right]


class ConversationState(BaseModel):
    """The state object carried through the LangGraph state machine.

    LangGraph reads/writes this on every node transition. Mutable fields
    that accumulate (messages, handover_history) use Annotated reducers so
    LangGraph merges updates correctly across parallel/sequential nodes.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    trace_id: UUID = Field(default_factory=uuid4)
    turn_id: int = 0

    # Accumulating fields with reducers
    messages: Annotated[list[Message], _add_messages] = Field(default_factory=list)
    handover_history: Annotated[list[HandoverEvent], _add_handover_events] = Field(
        default_factory=list
    )

    # Mutable scalar/object fields — LangGraph replaces by default
    customer_profile: CustomerProfile = Field(default_factory=CustomerProfile)
    current_agent: AgentType = AgentType.TRIAGE
    last_intent: IntentClassification | None = None
    pending_handover: HandoverPacket | None = None
    last_response: AgentResponse | None = None

    # Lifecycle flags
    awaiting_human: bool = False
    is_terminated: bool = False
    self_correction_attempts: int = 0

    # Observability
    started_at: datetime = Field(default_factory=utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("turn_id")
    @classmethod
    def _validate_turn_id(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"turn_id must be >= 0, got {v}")
        return v

    def latest_user_message(self) -> Message | None:
        for msg in reversed(self.messages):
            if msg.role == MessageRole.USER:
                return msg
        return None

    def conversation_text(self, last_n_turns: int | None = None) -> str:
        """Plain-text rendering for prompt context."""
        msgs = self.messages
        if last_n_turns is not None:
            msgs = msgs[-last_n_turns * 2 :]  # rough turn = user + assistant
        lines = []
        for m in msgs:
            speaker = m.role.value if m.agent is None else f"{m.agent.value}_agent"
            lines.append(f"[{speaker}] {m.content}")
        return "\n".join(lines)


# =============================================================================
# Escalation
# =============================================================================


class EscalationTicket(BaseModel):
    """The packaged hand-off to a (simulated) human operator.

    Created by the Escalation Agent and returned to the customer + written to
    audit log. In production this would be an API call to Zendesk/Intercom.
    """

    ticket_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    created_at: datetime = Field(default_factory=utcnow)

    customer_profile: CustomerProfile
    issue_summary: str
    sentiment: Sentiment
    urgency: Urgency
    recommended_priority: Literal["P0", "P1", "P2", "P3"]

    full_handover_packet: HandoverPacket
    suggested_actions: list[str] = Field(default_factory=list)


# =============================================================================
# Eval harness types (ADR-007)
# =============================================================================


class EvalScenario(BaseModel):
    """One eval case — defined in evals/scenarios.yaml."""

    scenario_id: str
    name: str
    description: str
    user_messages: list[str]  # multi-turn supported
    expected_route: list[AgentType]  # the agent path we expect
    expected_intents: list[IntentCategory] = Field(default_factory=list)
    must_cite: bool = True
    must_escalate: bool = False
    must_refuse: bool = False  # Scenario 4 KB miss
    expected_entities: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class EvalRubricScore(BaseModel):
    """LLM-as-judge scores per Anthropic's research-system rubric."""

    routing_correctness: float = Field(..., ge=0.0, le=1.0)
    retrieval_relevance: float = Field(..., ge=0.0, le=1.0)
    citation_accuracy: float = Field(..., ge=0.0, le=1.0)
    handover_quality: float = Field(..., ge=0.0, le=1.0)
    grounding_safety: float = Field(..., ge=0.0, le=1.0)  # no hallucination
    completeness: float = Field(..., ge=0.0, le=1.0)
    overall: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    pass_fail: bool


class EvalResult(BaseModel):
    """Result of running one EvalScenario through the system."""

    scenario_id: str
    trace_id: UUID
    timestamp: datetime = Field(default_factory=utcnow)

    actual_route: list[AgentType]
    final_response: str
    citations: list[Citation]
    handover_events: list[HandoverEvent]
    escalated: bool

    rubric: EvalRubricScore
    latency_ms: int
    error: str | None = None
