"""Output guardrails — grounding check via LLM.

The key insight: you can't do grounding validation with string matching.
"CloudDash supports GCP integration" and a chunk that says "CloudDash monitors
Google Cloud workloads" are semantically identical but string-match fails.
LLM understands it fine.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from clouddash.models import RetrievedChunk


@dataclass
class OutputCheckResult:
    passed: bool
    action: str  # allow | self_correct
    failures: list[str] = field(default_factory=list)
    correction_hint: str = ""


class _GroundingCheck(BaseModel):
    is_grounded: bool
    unsupported_claims: list[str]
    correction_hint: str


def check_grounding(response_text: str, chunks: list[RetrievedChunk]) -> OutputCheckResult:
    """All substantive claims about CloudDash must be supported by retrieved chunks."""
    if not chunks or not response_text.strip():
        return OutputCheckResult(passed=True, action="allow")

    from clouddash.providers import get_fast_llm

    llm = get_fast_llm().with_structured_output(_GroundingCheck)
    ctx = "\n\n".join(f"[{c.kb_id}] {c.content[:400]}" for c in chunks[:5])
    prompt = (
        f"Response to check:\n{response_text[:1000]}\n\n"
        f"Retrieved context:\n{ctx}\n\n"
        "Are all factual claims about CloudDash supported by the context? "
        "List any unsupported claims. If none, return is_grounded=True. "
        "If is_grounded is False, give a correction_hint telling the agent what to fix."
    )
    try:
        res: _GroundingCheck = llm.invoke(prompt)
        if not res.is_grounded and res.unsupported_claims:
            return OutputCheckResult(
                passed=False,
                action="self_correct",
                failures=res.unsupported_claims,
                correction_hint=res.correction_hint,
            )
    except Exception:
        pass  # grounding check failure → allow through, log warning elsewhere
    return OutputCheckResult(passed=True, action="allow")
