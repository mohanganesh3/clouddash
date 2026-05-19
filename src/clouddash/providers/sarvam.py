"""Sarvam AI provider — OpenAI-compatible endpoint, Indian LLM.

Wired via LangChain's ChatOpenAI with a custom base_url.
Auth: May 14 — verified that standard Bearer token works fine here despite
the docs saying api-subscription-key. Both work. Keeping Bearer for simplicity.

sarvam-105b has reasoning_effort which is nice for the specialist agents.
sarvam-105b is used for every tier in the final demo configuration.
Sarvam docs expose reasoning_effort as a top-level chat-completions field:
low | medium | high, default medium. Use high only for reasoning-tier calls.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from langchain_openai import ChatOpenAI  # noqa: I001 (added after verifying compat)

from clouddash.settings import get_settings


class WrappedSarvamChatOpenAI(ChatOpenAI):
    def with_structured_output(self, schema, *args, **kwargs):
        if "method" not in kwargs or kwargs["method"] is None:
            kwargs["method"] = "function_calling"
        return super().with_structured_output(schema, *args, **kwargs)


@lru_cache(maxsize=4)
def build_sarvam(model: str, temperature: float = 0.0, reasoning: bool = False) -> ChatOpenAI:
    cfg = get_settings()
    kwargs: dict[str, Any] = {
        "model": model,
        "base_url": cfg.sarvam_base_url,
        "api_key": cfg.sarvam_api_key,
        "temperature": temperature,
        "max_retries": cfg.llm_max_retries,
        "timeout": cfg.llm_timeout_seconds,
    }
    if reasoning and model == cfg.sarvam_reasoning_model:
        kwargs["reasoning_effort"] = cfg.sarvam_reasoning_effort
    return WrappedSarvamChatOpenAI(**kwargs)
