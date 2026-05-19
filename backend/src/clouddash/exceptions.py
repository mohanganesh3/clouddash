from __future__ import annotations

from typing import Any


class CloudDashError(Exception):
    def __init__(self, msg: str, ctx: dict[str, Any] | None = None, cause: Exception | None = None):
        super().__init__(msg)
        self.ctx = ctx or {}
        self.cause = cause

    def to_dict(self) -> dict[str, Any]:
        return {"error": type(self).__name__, "message": str(self), **self.ctx}


class ConfigError(CloudDashError): ...
class RegistryError(CloudDashError): ...
class LLMError(CloudDashError): ...
class ToolError(CloudDashError): ...
class RetrievalError(CloudDashError): ...
class HandoverError(CloudDashError): ...
class HandoverChainExhaustedError(HandoverError): ...
class ConversationError(CloudDashError): ...


class GuardrailViolation(CloudDashError):
    def __init__(self, guardrail: str, msg: str, **ctx: Any):
        super().__init__(msg, ctx={"guardrail": guardrail, **ctx})
        self.guardrail = guardrail


class PromptInjectionError(GuardrailViolation):
    def __init__(self, confidence: float = 1.0):
        super().__init__("prompt_injection", "injection attempt detected", confidence=confidence)


class GroundingFailure(GuardrailViolation):
    def __init__(self, ungrounded_claims: int):
        super().__init__(
            "grounding", f"{ungrounded_claims} claims not supported by retrieved context"
        )
