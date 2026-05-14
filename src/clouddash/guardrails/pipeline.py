"""Guardrail aggregation + self-correction loop.

This module is the *only* place the orchestrator calls into for guardrails.
It hides:

- Which checks run (input vs output, deterministic vs LLM-judge).
- How results are aggregated into one decision.
- How a corrective hint is built when an output check fails (so the agent
  can re-run with extra context).

Public API:

    InputDecision   = evaluate_input(text)
    OutputDecision  = evaluate_output(response_text, chunks)
    refusal_message = build_blocked_input_response(decision)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from clouddash.guardrails.input import apply_input_guardrails, is_blocked
from clouddash.guardrails.output import apply_output_guardrails
from clouddash.logging_setup import get_logger, write_audit_event
from clouddash.models import GuardrailResult, RetrievedChunk

logger = get_logger(__name__)


# ---- Decisions ---------------------------------------------------------------


@dataclass(slots=True)
class InputDecision:
    """Outcome of all input guardrails."""

    sanitized_text: str
    results: list[GuardrailResult] = field(default_factory=list)
    blocked_by: GuardrailResult | None = None

    @property
    def is_allowed(self) -> bool:
        return self.blocked_by is None

    @property
    def was_redacted(self) -> bool:
        return any(r.action == "redact" for r in self.results)


@dataclass(slots=True)
class OutputDecision:
    """Outcome of all output guardrails."""

    results: list[GuardrailResult] = field(default_factory=list)
    action: Literal["allow", "self_correct", "block"] = "allow"
    correction_hint: str | None = None
    failures: list[GuardrailResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.action == "allow"


# ---- Input ------------------------------------------------------------------


def evaluate_input(text: str) -> InputDecision:
    """Run every input guardrail; aggregate."""
    sanitized, results = apply_input_guardrails(text)
    blocked = is_blocked(results)

    decision = InputDecision(
        sanitized_text=sanitized,
        results=results,
        blocked_by=blocked,
    )

    write_audit_event(
        "guardrail.input.decision",
        allowed=decision.is_allowed,
        redacted=decision.was_redacted,
        blocked_by=blocked.guardrail_name if blocked else None,
        results=[
            {
                "name": r.guardrail_name,
                "passed": r.passed,
                "action": r.action,
            }
            for r in results
        ],
    )
    return decision


def build_blocked_input_response(decision: InputDecision) -> str:
    """Hard-coded refusal text the orchestrator returns when input is blocked.
    Crucially, this NEVER touches an LLM — a blocked input must not feed back
    into the model under any circumstance."""
    blocked = decision.blocked_by
    if blocked is None:  # defensive
        return "I can't process this request."

    if blocked.guardrail_name == "length":
        max_len = blocked.metadata.get("max")
        return (
            f"Your message is too long. Please keep it under {max_len} characters "
            "or split it into smaller questions and I'll work through them."
        )

    if blocked.guardrail_name == "prompt_injection":
        return (
            "I can only help with CloudDash product questions — billing, "
            "technical issues, account access, and product features. Could you "
            "rephrase your question in those terms?"
        )

    return (
        "I'm not able to process that request. Could you rephrase it as a "
        "specific CloudDash question?"
    )


# ---- Output -----------------------------------------------------------------


def evaluate_output(
    response_text: str,
    chunks: list[RetrievedChunk],
    *,
    require_grounding_for_substantive: bool = True,
) -> OutputDecision:
    """Run every output guardrail; produce an action + correction hint."""
    results = apply_output_guardrails(
        response_text,
        chunks,
        require_grounding_for_substantive=require_grounding_for_substantive,
    )
    failures = [r for r in results if not r.passed]

    if not failures:
        decision = OutputDecision(results=results, action="allow")
    elif any(r.action == "block" for r in failures):
        decision = OutputDecision(
            results=results,
            action="block",
            failures=failures,
        )
    else:
        decision = OutputDecision(
            results=results,
            action="self_correct",
            correction_hint=_build_correction_hint(failures, chunks),
            failures=failures,
        )

    write_audit_event(
        "guardrail.output.decision",
        action=decision.action,
        failures=[r.guardrail_name for r in failures],
        results=[
            {
                "name": r.guardrail_name,
                "passed": r.passed,
                "action": r.action,
            }
            for r in results
        ],
    )
    return decision


def _build_correction_hint(
    failures: list[GuardrailResult],
    chunks: list[RetrievedChunk],
) -> str:
    """Compose a short, agent-readable hint to inject into the next attempt."""
    bullets: list[str] = []
    for f in failures:
        if f.guardrail_name == "citation_validity":
            invalid = f.metadata.get("invalid_citations", [])
            kb_ids_available = sorted({c.kb_id for c in chunks})
            bullets.append(
                f"You cited {invalid}, but those chunks were not retrieved. "
                f"Only cite from this list: {kb_ids_available}. "
                "Remove invalid citations and re-state the answer using only retrieved context."
            )
        elif f.guardrail_name == "grounding_presence":
            kb_ids_available = sorted({c.kb_id for c in chunks})
            bullets.append(
                f"Your response made product claims without citations. Either: "
                f"(a) cite from {kb_ids_available} for each claim, or "
                "(b) explicitly say you don't have that information in the KB and "
                "offer to file a feature request / escalate."
            )
        elif f.guardrail_name == "refusal_consistency":
            bullets.append(
                "Your response is internally inconsistent — it uses refusal "
                "phrasing while citing multiple sources confidently. Pick ONE "
                "stance: either commit to a confident answer with citations, or "
                "produce a clear refusal."
            )
        else:
            bullets.append(f"{f.guardrail_name}: {f.reason}")

    return (
        "GUARDRAIL CORRECTION: Your previous answer failed grounding checks. "
        "You MUST fix the following issues and produce a new answer:\n- "
        + "\n- ".join(bullets)
    )
