"""Layer-2 guardrails — applied to agent OUTPUT, before the user sees it.

Per ADR-005: deterministic checks first (citation validity, grounding score,
length), then optionally an LLM-as-judge for nuanced grounding (off by default
to keep latency tight on the free tier).

Three deterministic checks here:

1. **Citation validity** — every `[KB-XXX § N]` in the response must
   correspond to a retrieved chunk. Unknown citations = hallucination.
2. **Grounding presence** — if the response makes substantive claims, it must
   include at least one citation OR be an explicit refusal/escalation.
3. **Refusal-consistency** — if the agent says "I don't have info on this",
   it should NOT also produce citations or definitive product claims; mixed
   signals confuse the user.

Each returns a `GuardrailResult`. The aggregator decides:
- Any deterministic violation with `passed=False, action="self_correct"` →
  the orchestrator re-runs the agent ONCE with a corrective hint.
- After max retries (settings.self_correction_max_attempts), we either return
  the response with a warning or block.
"""

from __future__ import annotations

from clouddash.logging_setup import get_logger, write_audit_event
from clouddash.models import GuardrailResult, RetrievedChunk
from clouddash.retrieval.citations import (
    _looks_like_refusal_or_escalation,  # type: ignore[attr-defined]
    extract_citations,
    has_sufficient_grounding,
    validate_citations,
)

logger = get_logger(__name__)


def check_citation_validity(
    response_text: str,
    chunks: list[RetrievedChunk],
) -> GuardrailResult:
    """Every cited [KB-XXX § N] must reference one of the retrieved chunks."""
    valid, invalid = validate_citations(response_text, chunks)
    if valid:
        return GuardrailResult(
            guardrail_name="citation_validity",
            layer="output",
            passed=True,
            action="allow",
            metadata={"citation_count": len(extract_citations(response_text))},
        )

    write_audit_event(
        "guardrail.output.invalid_citations",
        invalid=invalid,
        response_preview=response_text[:240],
    )
    return GuardrailResult(
        guardrail_name="citation_validity",
        layer="output",
        passed=False,
        action="self_correct",
        reason=f"Response cites unknown chunks: {invalid}.",
        metadata={"invalid_citations": invalid},
    )


def check_grounding_presence(
    response_text: str,
    chunks: list[RetrievedChunk],
) -> GuardrailResult:
    """If the response makes substantive claims, it must cite OR be a refusal.

    Heuristic — substantive means: not a refusal/escalation phrase AND length
    above a small threshold. We do NOT require citations on, say, "Yes, I can
    help with that — could you share the affected dashboard URL?"
    """
    has_citations = bool(extract_citations(response_text))
    looks_refusal = _looks_like_refusal_or_escalation(response_text)
    is_substantive = len(response_text.split()) >= 25 and not looks_refusal

    # Acceptable shapes:
    #   - has citations
    #   - is a refusal/escalation
    #   - is short (clarifying question, simple acknowledgement)
    if has_citations or looks_refusal or not is_substantive:
        return GuardrailResult(
            guardrail_name="grounding_presence",
            layer="output",
            passed=True,
            action="allow",
            metadata={
                "has_citations": has_citations,
                "is_refusal": looks_refusal,
            },
        )

    write_audit_event(
        "guardrail.output.no_grounding",
        response_preview=response_text[:240],
        chunks_available=len(chunks),
    )
    return GuardrailResult(
        guardrail_name="grounding_presence",
        layer="output",
        passed=False,
        action="self_correct",
        reason=(
            "Response makes substantive product claims without any [KB-XXX § N] "
            "citations. Either cite a retrieved chunk or admit you don't know."
        ),
        metadata={"chunks_available": len(chunks)},
    )


def check_refusal_consistency(
    response_text: str,
    chunks: list[RetrievedChunk],
) -> GuardrailResult:
    """If the response says 'I don't have info', the rest of it shouldn't
    contradict that with confident product claims."""
    if not _looks_like_refusal_or_escalation(response_text):
        return GuardrailResult(
            guardrail_name="refusal_consistency",
            layer="output",
            passed=True,
            action="allow",
        )

    # Refusal + grounding signal high + many citations is suspicious.
    citations = extract_citations(response_text)
    grounded = has_sufficient_grounding(chunks)

    # OK shapes for refusal:
    # - 0 citations or 1 citation that is a non-support article
    # - explicit feature-request offer
    if len(citations) <= 1:
        return GuardrailResult(
            guardrail_name="refusal_consistency",
            layer="output",
            passed=True,
            action="allow",
        )

    # Multiple citations + refusal phrasing = inconsistent
    if grounded:
        return GuardrailResult(
            guardrail_name="refusal_consistency",
            layer="output",
            passed=False,
            action="self_correct",
            reason=(
                "Response uses refusal language but cites multiple chunks. "
                "Either commit to an answer with the citations, or remove the "
                "refusal phrasing."
            ),
            metadata={"citations": len(citations)},
        )

    return GuardrailResult(
        guardrail_name="refusal_consistency",
        layer="output",
        passed=True,
        action="allow",
    )


def apply_output_guardrails(
    response_text: str,
    chunks: list[RetrievedChunk],
    *,
    require_grounding_for_substantive: bool = True,
) -> list[GuardrailResult]:
    """Run every output guardrail and return all results.

    Caller (`pipeline.evaluate_output`) aggregates them into a decision.
    """
    results = [
        check_citation_validity(response_text, chunks),
    ]
    if require_grounding_for_substantive:
        results.append(check_grounding_presence(response_text, chunks))
    results.append(check_refusal_consistency(response_text, chunks))
    return results
