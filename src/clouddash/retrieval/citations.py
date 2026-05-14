"""Citation utilities — convert RetrievedChunks into Citations and check
that an agent's response is grounded in the retrieved context (ADR-005).

Two purposes:
1. Build inline `[KB-XXX § N]` citation markers + the structured Citation
   list returned in the API response (per §2.2: "Retrieved chunks must be
   cited or referenced in the agent's response so the customer can verify").

2. Grounding check: for every factual claim in the response, verify it has
   at least one citation. If not, raise GroundingFailure so the orchestrator
   triggers self-correction or refusal-to-answer (Scenario 4 path).
"""

from __future__ import annotations

import re

from clouddash.exceptions import GroundingFailure
from clouddash.logging_setup import get_logger
from clouddash.models import Citation, RetrievedChunk
from clouddash.settings import get_settings

logger = get_logger(__name__)

_CITATION_RE = re.compile(r"\[(KB-\d{3,4})(?:\s*§\s*(\d+))?\]")


def chunks_to_citations(chunks: list[RetrievedChunk]) -> list[Citation]:
    """Convert a list of RetrievedChunks into Citation objects."""
    return [c.to_citation() for c in chunks]


def extract_citations(response_text: str) -> list[tuple[str, int | None]]:
    """Pull every [KB-XXX § N] reference out of an agent response."""
    return [(m.group(1), int(m.group(2)) if m.group(2) else None) for m in _CITATION_RE.finditer(response_text)]


def validate_citations(
    response_text: str,
    available_chunks: list[RetrievedChunk],
) -> tuple[bool, list[str]]:
    """Check that every [KB-XXX § N] in the response refers to a real chunk.

    Returns (all_valid, list_of_invalid_citations).
    """
    cited = extract_citations(response_text)
    valid_pairs = {(c.kb_id, c.section) for c in available_chunks}
    invalid: list[str] = []
    for kb_id, section in cited:
        # Allow citing the KB without a section if any chunk of that article was retrieved
        valid = (kb_id, section) in valid_pairs or (
            section is None and any(c.kb_id == kb_id for c in available_chunks)
        )
        if not valid:
            invalid.append(f"[{kb_id}{f' § {section}' if section else ''}]")
    return len(invalid) == 0, invalid


def has_sufficient_grounding(
    chunks: list[RetrievedChunk],
    *,
    min_score: float | None = None,
) -> bool:
    """True if at least one retrieved chunk passes the grounding score threshold.

    Used to decide whether to attempt a grounded answer or trigger the
    "I don't have info on that, want me to escalate?" path (Scenario 4).
    """
    threshold = min_score if min_score is not None else get_settings().grounding_min_score
    if not chunks:
        return False
    top_score = max(c.composite_score for c in chunks)
    return top_score >= threshold


def assert_grounded(
    response_text: str,
    chunks: list[RetrievedChunk],
    *,
    require_at_least_one_citation: bool = True,
) -> None:
    """Raise GroundingFailure if the response is not properly grounded.

    Three checks:
    1. If require_at_least_one_citation: response must contain ≥1 citation.
    2. Every citation in the response must reference a retrieved chunk.
    3. (light heuristic) The response shouldn't claim CloudDash specifics
       without any citation at all.
    """
    citations = extract_citations(response_text)

    if require_at_least_one_citation and not citations:
        # If the response is a refusal / escalation message, it doesn't need
        # citations — those are detected by certain stock phrases.
        if not _looks_like_refusal_or_escalation(response_text):
            raise GroundingFailure(
                "Response makes claims without any KB citations.",
                guardrail_name="citation_grounding",
                layer="output",
                context={"response_preview": response_text[:300]},
            )

    valid, invalid_refs = validate_citations(response_text, chunks)
    if not valid:
        raise GroundingFailure(
            f"Response cites unknown chunks: {invalid_refs}",
            guardrail_name="citation_validity",
            layer="output",
            context={"invalid": invalid_refs, "response_preview": response_text[:300]},
        )


_REFUSAL_PHRASES = (
    "i don't have",
    "i do not have",
    "no information",
    "not in our knowledge base",
    "not in our docs",
    "i'm not able to find",
    "we don't currently support",
    "i can escalate",
    "feature request",
    "create a feature request",
    "speak with a manager",
    "let me transfer you",
)


def _looks_like_refusal_or_escalation(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _REFUSAL_PHRASES)


def render_citations_block(chunks: list[RetrievedChunk]) -> str:
    """Render a 'Sources:' footer block for inclusion at the end of an agent response."""
    if not chunks:
        return ""
    lines = ["", "Sources:"]
    seen: set[str] = set()
    for c in chunks:
        key = f"{c.kb_id}-{c.section}"
        if key in seen:
            continue
        seen.add(key)
        section_part = f" § {c.section}" if c.section else ""
        lines.append(f"- [{c.kb_id}{section_part}] {c.title}")
    return "\n".join(lines)
