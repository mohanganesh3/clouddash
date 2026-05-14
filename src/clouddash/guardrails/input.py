"""Layer-1 guardrails — applied to user input BEFORE any LLM call.

Per ADR-005: cheap, deterministic, fast. We check four things:

1. Length cap   (settings.max_input_length) → block if exceeded.
2. Prompt injection signatures → block + audit log.
3. PII redaction (CC numbers, SSN, long digit runs) → redact in place.
4. Optional LLM-based off-topic check (disabled by default for latency).

Each check returns a `GuardrailResult`. The caller aggregates them via
`apply_input_guardrails()` which returns the (possibly sanitized) text plus
all results. If any result has action='block', the orchestrator refuses the
turn and replies with a polite, hard-coded refusal — never asks the LLM.
"""

from __future__ import annotations

import re

from clouddash.logging_setup import get_logger, write_audit_event
from clouddash.models import GuardrailResult
from clouddash.settings import get_settings

logger = get_logger(__name__)


# ---- Static signatures -------------------------------------------------------

# Prompt-injection patterns. Conservative — these are obvious attacks; we don't
# block borderline cases here, the agent's system prompt is the second line.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above|earlier|preceding)\s+(?:instructions?|prompt|context|rules?|directives?)",
        r"disregard\s+(?:all\s+)?(?:the\s+)?(?:previous|prior|above)\s+(?:instructions?|rules?|prompt)",
        r"forget\s+(?:everything|all|your\s+(?:instructions?|rules?|prompt))",
        r"</?\s*(?:system|admin|developer|user|assistant)\s*>",
        r"\[\[?\s*(?:system|admin|/system)\s*\]?\]",
        r"reveal\s+(?:your|the)\s+(?:system\s+)?prompt",
        r"show\s+me\s+your\s+(?:system\s+)?(?:prompt|instructions?)",
        r"\bDAN\s+mode\b",
        r"\bjailbreak\b",
        r"pretend\s+(?:you\s+are|to\s+be)\s+(?:a\s+different|another)\s+(?:ai|assistant|model)",
        r"act\s+as\s+(?:if\s+you\s+are|though\s+you\s+are)\s+(?:a\s+)?(?:different|another)\s+(?:ai|assistant|model)",
    )
)


# PII patterns we redact. Conservative — we redact long digit runs that look
# like card/account numbers, plus SSN. We DO NOT redact email — emails are part
# of the legitimate support conversation.
_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    # 13–19 digit runs (CC numbers can include separators)
    "credit_card": re.compile(r"\b(?:\d[ \-]?){13,19}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    # 10+ consecutive digits (likely account / card / phone)
    "long_digits": re.compile(r"\b\d{10,}\b"),
}


# ---- Individual checks -------------------------------------------------------


def check_length(text: str) -> GuardrailResult:
    """Reject inputs above the configured cap. Cheap, deterministic."""
    settings = get_settings()
    if len(text) <= settings.max_input_length:
        return GuardrailResult(
            guardrail_name="length",
            layer="input",
            passed=True,
            action="allow",
        )
    return GuardrailResult(
        guardrail_name="length",
        layer="input",
        passed=False,
        action="block",
        reason=(
            f"Input is {len(text)} characters, max allowed is "
            f"{settings.max_input_length}."
        ),
        metadata={"length": len(text), "max": settings.max_input_length},
    )


def check_prompt_injection(text: str) -> GuardrailResult:
    """Match against known injection signatures. Conservative — false positives
    here are user-visible refusals, so we only flag obvious attacks."""
    matches: list[str] = []
    for pat in _INJECTION_PATTERNS:
        m = pat.search(text)
        if m:
            matches.append(m.group(0))

    if not matches:
        return GuardrailResult(
            guardrail_name="prompt_injection",
            layer="input",
            passed=True,
            action="allow",
        )

    write_audit_event(
        "guardrail.input.prompt_injection_blocked",
        matched_patterns=matches[:3],
        text_preview=text[:160],
    )
    return GuardrailResult(
        guardrail_name="prompt_injection",
        layer="input",
        passed=False,
        action="block",
        reason="Input matches a prompt-injection signature.",
        metadata={"matches": matches[:5]},
    )


def redact_pii(text: str) -> GuardrailResult:
    """Redact PII patterns in-place. Returns sanitized_content if anything changed."""
    sanitized = text
    found: dict[str, int] = {}

    for kind, pat in _PII_PATTERNS.items():
        # Only redact long-digit if not already redacted by a more specific rule
        new, n = pat.subn(f"[REDACTED:{kind}]", sanitized)
        if n > 0:
            sanitized = new
            found[kind] = n

    if not found:
        return GuardrailResult(
            guardrail_name="pii_redaction",
            layer="input",
            passed=True,
            action="allow",
        )

    write_audit_event(
        "guardrail.input.pii_redacted",
        kinds=list(found.keys()),
        counts=found,
    )
    return GuardrailResult(
        guardrail_name="pii_redaction",
        layer="input",
        passed=True,  # not a block — redaction is a soft action
        action="redact",
        reason=f"Redacted PII patterns: {', '.join(found)}.",
        sanitized_content=sanitized,
        metadata={"redactions": found},
    )


# ---- Aggregator --------------------------------------------------------------


def apply_input_guardrails(text: str) -> tuple[str, list[GuardrailResult]]:
    """Run every input guardrail. Returns (sanitized_text, results).

    The caller inspects results — if any has action='block', it must NOT
    forward the (possibly sanitized) text to the LLM.
    """
    results: list[GuardrailResult] = []

    # 1. Length first — cheapest.
    length = check_length(text)
    results.append(length)
    if length.action == "block":
        return text, results

    # 2. Injection.
    inj = check_prompt_injection(text)
    results.append(inj)
    if inj.action == "block":
        return text, results

    # 3. PII redaction (only on non-blocked content).
    pii = redact_pii(text)
    results.append(pii)

    sanitized = pii.sanitized_content if pii.sanitized_content else text
    return sanitized, results


def is_blocked(results: list[GuardrailResult]) -> GuardrailResult | None:
    """Return the first blocking result (if any)."""
    for r in results:
        if r.action == "block":
            return r
    return None
