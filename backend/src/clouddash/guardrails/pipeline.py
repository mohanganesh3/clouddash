from __future__ import annotations

from dataclasses import dataclass

from clouddash.guardrails.input import (
    InputCheckResult,
    check_injection,
    check_length,
    redact_pii,
)
from clouddash.guardrails.output import OutputCheckResult, check_grounding
from clouddash.models import RetrievedChunk
from clouddash.settings import get_settings


@dataclass
class InputDecision:
    is_allowed: bool
    sanitized_text: str
    was_redacted: bool = False
    blocked_by: InputCheckResult | None = None


def evaluate_input(text: str) -> InputDecision:
    cfg = get_settings()

    # 1. length (cheap, no LLM)
    length_check = check_length(text, cfg.max_input_length)
    if not length_check.passed:
        return InputDecision(is_allowed=False, sanitized_text=text, blocked_by=length_check)

    # 2. injection (LLM — stop here if blocked, don't bother redacting)
    inj_check = check_injection(text)
    if not inj_check.passed:
        return InputDecision(is_allowed=False, sanitized_text=text, blocked_by=inj_check)

    # 3. PII redaction (always runs, doesn't block)
    pii_check = redact_pii(text)
    sanitized = pii_check.sanitized or text

    return InputDecision(
        is_allowed=True,
        sanitized_text=sanitized,
        was_redacted=pii_check.action == "redact",
    )


def evaluate_output(
    response_text: str,
    chunks: list[RetrievedChunk],
) -> OutputCheckResult:
    return check_grounding(response_text, chunks)


def build_blocked_response(decision: InputDecision) -> str:
    if decision.blocked_by and "injection" in (decision.blocked_by.reason or ""):
        return (
            "I can only help with CloudDash support questions. "
            "Please rephrase your message."
        )
    if decision.blocked_by and "too long" in (decision.blocked_by.reason or ""):
        return "Your message is too long. Please keep it under 4000 characters."
    return "I wasn't able to process that message. Please try again."
