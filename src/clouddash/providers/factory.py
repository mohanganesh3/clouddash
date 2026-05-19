"""LLM factory with automatic fallback chain.

Primary: whatever LLM_PROVIDER says. Falls back to google → groq → sarvam.
Groq is wired via ChatOpenAI (base_url trick) because langchain-groq requires
langchain-core>=1.x which breaks our 0.3.x pinning. Same trick as Sarvam.
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from clouddash.settings import get_settings


class WrappedChatOpenAI(ChatOpenAI):
    def with_structured_output(self, schema, *args, **kwargs):
        if "method" not in kwargs or kwargs["method"] is None:
            kwargs["method"] = "function_calling"
        return super().with_structured_output(schema, *args, **kwargs)


def _groq_llm(tier: str) -> ChatOpenAI:
    cfg = get_settings()
    model = cfg.llm_reasoning_model if tier == "reasoning" else cfg.llm_fast_model
    return WrappedChatOpenAI(
        model=model,
        base_url="https://api.groq.com/openai/v1",
        api_key=cfg.groq_api_key,
        temperature=cfg.llm_temperature,
        max_retries=cfg.llm_max_retries,
        timeout=cfg.llm_timeout_seconds,
    )


def get_llm(tier: str = "fast") -> BaseChatModel:
    cfg = get_settings()
    provider = cfg.llm_provider

    if provider == "google":
        from .gemini import build_gemini
        model = cfg.llm_reasoning_model if tier == "reasoning" else cfg.llm_fast_model
        return build_gemini(model, temperature=cfg.llm_temperature)

    if provider == "sarvam":
        from .sarvam import build_sarvam
        model = cfg.sarvam_reasoning_model if tier == "reasoning" else cfg.sarvam_fast_model
        return build_sarvam(model, temperature=cfg.llm_temperature, reasoning=(tier == "reasoning"))

    if provider in ("nvidia", "groq"):
        # both nvidia and groq use langchain-core>=1.x natively.
        # use ChatOpenAI with base_url instead — works with our 0.3.x pinning.
        if provider == "nvidia" and cfg.nvidia_api_key:
            try:
                model = cfg.llm_reasoning_model if tier == "reasoning" else cfg.llm_fast_model
                return WrappedChatOpenAI(
                    model=model,
                    base_url="https://integrate.api.nvidia.com/v1",
                    api_key=cfg.nvidia_api_key,
                    temperature=cfg.llm_temperature,
                    max_retries=cfg.llm_max_retries,
                    timeout=cfg.llm_timeout_seconds,
                )
            except Exception:
                pass
        # groq fallback
        if cfg.groq_api_key:
            return _groq_llm(tier)
        # final fallback: google
        from .gemini import build_gemini
        model = "gemini-2.5-pro" if tier == "reasoning" else "gemini-2.5-flash"
        return build_gemini(model, temperature=cfg.llm_temperature)

    raise ValueError(f"unknown provider: {provider}")


def get_fast_llm() -> BaseChatModel:
    return get_llm("fast")


def get_reasoning_llm() -> BaseChatModel:
    return get_llm("reasoning")


def get_judge_llm() -> BaseChatModel:
    """For evals — stronger model, deterministic."""
    cfg = get_settings()
    if cfg.llm_provider == "google":
        from .gemini import build_gemini
        return build_gemini(cfg.llm_judge_model, temperature=0.0)
    if cfg.llm_provider == "sarvam":
        from .sarvam import build_sarvam
        return build_sarvam(cfg.sarvam_reasoning_model, temperature=0.0, reasoning=True)
    return get_llm("reasoning")
