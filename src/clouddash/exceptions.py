"""Custom exception hierarchy for CloudDash.

Per ADR-005 / §3.1: meaningful errors with context, never bare try/except.
Every exception carries structured context that flows into the audit log.
"""

from __future__ import annotations

from typing import Any


class CloudDashError(Exception):
    """Base exception for all CloudDash-specific errors."""

    def __init__(
        self,
        message: str,
        *,
        context: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}
        self.cause = cause

    def to_dict(self) -> dict[str, Any]:
        """Serialize for structured logging."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "context": self.context,
            "cause": str(self.cause) if self.cause else None,
        }


# ---- Configuration / startup -------------------------------------------------


class ConfigurationError(CloudDashError):
    """Raised when configuration is missing, invalid, or inconsistent."""


class RegistryError(CloudDashError):
    """Raised when the AgentRegistry cannot load an agent definition."""


# ---- LLM / Tool layer --------------------------------------------------------


class LLMError(CloudDashError):
    """Raised when an LLM call fails (network, rate limit, parse error)."""


class LLMOutputValidationError(LLMError):
    """LLM output failed Pydantic schema validation after all retries."""


class ToolExecutionError(CloudDashError):
    """A tool invocation raised an unrecoverable error."""


# ---- Retrieval ---------------------------------------------------------------


class RetrievalError(CloudDashError):
    """Raised when the RAG pipeline fails (ingest, query, rerank)."""


class IngestionError(RetrievalError):
    """KB ingestion failed."""


# ---- Handover ----------------------------------------------------------------


class HandoverError(CloudDashError):
    """Base class for handover-related failures."""


class HandoverRejectedError(HandoverError):
    """Target agent rejected the handover packet (domain mismatch / validation)."""


class HandoverChainExhaustedError(HandoverError):
    """Fallback chain (Triage → Escalation) exhausted; no agent could handle."""


# ---- Guardrails --------------------------------------------------------------


class GuardrailViolation(CloudDashError):
    """A guardrail (input or output) blocked the operation."""

    def __init__(
        self,
        message: str,
        *,
        guardrail_name: str,
        layer: str,  # "input" | "output"
        context: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        ctx = {"guardrail": guardrail_name, "layer": layer, **(context or {})}
        super().__init__(message, context=ctx, cause=cause)
        self.guardrail_name = guardrail_name
        self.layer = layer


class PromptInjectionDetected(GuardrailViolation):
    """Input matches a prompt-injection signature."""


class OffTopicQuery(GuardrailViolation):
    """Input is unrelated to CloudDash."""


class GroundingFailure(GuardrailViolation):
    """Output makes claims not supported by retrieved KB chunks."""


# ---- Conversation lifecycle --------------------------------------------------


class ConversationNotFound(CloudDashError):
    """Trace ID does not correspond to any known conversation."""


class ConversationLimitExceeded(CloudDashError):
    """Conversation hit max-turns or other lifecycle limit."""
