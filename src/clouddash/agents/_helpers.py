"""Shared helpers for KB-grounded specialist agents.

Pure functions — no state, no side effects beyond logging. Used by Technical,
Billing, and Knowledge agents to keep their handle() methods clean.
"""

from __future__ import annotations

from clouddash.logging_setup import get_logger
from clouddash.models import (
    AgentType,
    Citation,
    GraphState,
    HandoverPacket,
    HandoverReason,
    RetrievedChunk,
)
from clouddash.retrieval.citations import (
    extract_citations,
    has_sufficient_grounding,
    validate_citations,
)

logger = get_logger(__name__)


def render_customer_profile(state: GraphState) -> str:
    """Render the customer profile for inclusion in agent prompts."""
    p = state.customer_profile
    parts: list[str] = []
    if p.customer_id:
        parts.append(f"customer_id={p.customer_id}")
    if p.plan:
        parts.append(f"plan={p.plan.value}")
    if p.org_name:
        parts.append(f"org={p.org_name}")
    if p.email:
        parts.append(f"email={p.email}")
    if p.extracted_entities:
        for k, v in p.extracted_entities.items():
            parts.append(f"{k}={v}")
    return ", ".join(parts) if parts else "(no profile yet)"


def render_handover_context(state: GraphState) -> str:
    """Render the incoming HandoverPacket for the receiving agent's prompt."""
    pkt = state.pending_handover
    if pkt is None:
        return "(none — direct routing)"

    lines = [
        f"Handed over by: {pkt.from_agent.value}",
        f"Reason: {pkt.reason.value}",
        f"User intent: {pkt.user_intent}",
        f"Sentiment: {pkt.sentiment.value} | Urgency: {pkt.urgency.value}",
        f"Source confidence: {pkt.confidence_state:.2f}",
        f"Conversation summary: {pkt.conversation_summary}",
    ]
    if pkt.extracted_entities:
        lines.append(f"Extracted entities: {pkt.extracted_entities}")
    if pkt.prior_attempts:
        lines.append("Prior attempts:")
        for att in pkt.prior_attempts:
            cit_str = " ".join(c.render_inline() for c in att.citations) if att.citations else ""
            lines.append(
                f"  - {att.agent.value} (turn {att.turn_id}, "
                f"conf={att.confidence:.2f}, outcome={att.outcome.value}): {att.summary} {cit_str}"
            )
    if pkt.audit_chain:
        chain = " → ".join(
            f"{e.from_agent.value}→{e.to_agent.value}({e.reason.value})"
            for e in pkt.audit_chain
        )
        lines.append(f"Audit chain: {chain}")
    return "\n".join(lines)


def render_kb_chunks(chunks: list[RetrievedChunk]) -> str:
    """Format retrieved chunks for inclusion in an agent prompt.

    Each chunk gets a clear identifier so the LLM can cite it by `[KB-XXX § N]`.
    Includes the rerank rationale when available — helps the LLM understand WHY
    each chunk is here.
    """
    if not chunks:
        return "(no relevant KB chunks retrieved — you may need to admit you don't know)"

    blocks: list[str] = []
    for i, c in enumerate(chunks, 1):
        section_marker = f" § {c.section}" if c.section else ""
        score = c.composite_score
        rationale = (
            f" [rerank rationale: {c.rerank_rationale}]"
            if c.rerank_rationale and not c.rerank_rationale.startswith("(")
            else ""
        )
        blocks.append(
            f"--- Chunk {i} | [{c.kb_id}{section_marker}] {c.title} "
            f"(category={c.category}, score={score:.2f}){rationale}\n{c.content}"
        )
    return "\n\n".join(blocks)


def chunks_to_used_citations(
    response_text: str,
    available_chunks: list[RetrievedChunk],
) -> list[Citation]:
    """Return Citation objects ONLY for the KB IDs the response actually cites.

    This is what we return in the API response — the customer sees only the
    sources the agent actually used, not every chunk we retrieved.
    """
    cited_pairs = set(extract_citations(response_text))
    citations: list[Citation] = []
    seen: set[tuple[str, int | None]] = set()

    for chunk in available_chunks:
        # Match exact section
        if (chunk.kb_id, chunk.section) in cited_pairs and (chunk.kb_id, chunk.section) not in seen:
            citations.append(chunk.to_citation())
            seen.add((chunk.kb_id, chunk.section))
            continue
        # Match KB without section if cited that way
        if (chunk.kb_id, None) in cited_pairs and (chunk.kb_id, None) not in seen:
            citations.append(chunk.to_citation())
            seen.add((chunk.kb_id, None))

    return citations


def grounding_signal(
    chunks: list[RetrievedChunk],
    *,
    min_score: float | None = None,
) -> tuple[bool, float]:
    """Returns (is_grounded, top_score). Used to decide if we should attempt
    a grounded answer or trigger the 'I don't know' path."""
    if not chunks:
        return False, 0.0
    top = max(c.composite_score for c in chunks)
    return has_sufficient_grounding(chunks, min_score=min_score), top


def validate_response_citations(
    response_text: str,
    available_chunks: list[RetrievedChunk],
) -> tuple[bool, list[str]]:
    """Validate every [KB-XXX § N] in the response. Used for guardrail check."""
    return validate_citations(response_text, available_chunks)


# -----------------------------------------------------------------------------
# Enum coercion — Gemini structured-output sometimes returns sentences instead
# of enum values. Coerce defensively.
# -----------------------------------------------------------------------------


def coerce_agent_type(v: str | AgentType | None) -> AgentType | None:
    """Best-effort string → AgentType conversion. Returns None on failure."""
    if v is None:
        return None
    if isinstance(v, AgentType):
        return v
    if not isinstance(v, str):
        return None
    candidate = v.lower().strip()
    # Exact match first
    try:
        return AgentType(candidate)
    except ValueError:
        pass
    # Substring match — handles "technical agent" -> technical
    for at in AgentType:
        if at.value in candidate:
            return at
    return None


def coerce_handover_reason(v: str | HandoverReason | None) -> HandoverReason | None:
    """Best-effort string → HandoverReason conversion."""
    if v is None:
        return None
    if isinstance(v, HandoverReason):
        return v
    if not isinstance(v, str):
        return None
    candidate = v.lower().strip()
    try:
        return HandoverReason(candidate)
    except ValueError:
        pass
    for hr in HandoverReason:
        if hr.value in candidate:
            return hr
    return None
