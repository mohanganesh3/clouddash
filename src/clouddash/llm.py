"""Thin LLM provider wrapper.

Per ADR-009: Gemini via `langchain-google-genai`. We isolate the provider here
so swapping to Claude/GPT-4o is a one-line change in this module.

Two model tiers per Anthropic's research-system pattern:
- `reasoning` — strong, used by specialist agents and the eval judge.
- `fast`     — cheap, used by Triage, query rewriter, reranker, guardrails.

Both expose `.with_structured_output(PydanticModel)` for native JSON-schema
constrained outputs (Gemini supports this natively via `response_schema`).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from clouddash.exceptions import ConfigurationError, LLMError
from clouddash.logging_setup import get_logger
from clouddash.settings import get_settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = get_logger(__name__)


def _build_chat_model(model_name: str, *, temperature: float | None = None) -> BaseChatModel:
    """Create a LangChain-compatible chat model bound to the configured provider.

    Provider is selected by `llm_provider` setting. The agent abstractions
    are LLM-agnostic — swapping providers is a one-env-var change.
    """
    settings = get_settings()
    temp = temperature if temperature is not None else settings.llm_temperature

    if settings.llm_provider == "groq":
        if not settings.groq_api_key or settings.groq_api_key.startswith("gsk_..."):
            raise ConfigurationError(
                "GROQ_API_KEY is not set. Add it to your .env file.",
                context={"model": model_name},
            )
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "langchain-groq is not installed",
                cause=exc,
            ) from exc
        return ChatGroq(
            model=model_name,
            api_key=settings.groq_api_key,
            temperature=temp,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    if settings.llm_provider == "nvidia":
        if not settings.nvidia_api_key or settings.nvidia_api_key.startswith("nvapi-...your"):
            raise ConfigurationError(
                "NVIDIA_API_KEY is not set. Add it to your .env file (get one at build.nvidia.com).",
                context={"model": model_name},
            )
        try:
            from langchain_nvidia_ai_endpoints import ChatNVIDIA
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "langchain-nvidia-ai-endpoints is not installed. "
                "Run: pip install 'langchain-nvidia-ai-endpoints<1.0'",
                cause=exc,
            ) from exc
        return ChatNVIDIA(
            model=model_name,
            api_key=settings.nvidia_api_key,
            temperature=temp,
        )

    # Default: google
    if not settings.google_api_key or settings.google_api_key.startswith("AIza...your"):
        raise ConfigurationError(
            "GOOGLE_API_KEY is not set. Add it to your .env file.",
            context={"model": model_name},
        )

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError as exc:  # pragma: no cover
        raise LLMError(
            "langchain-google-genai is not installed",
            cause=exc,
        ) from exc

    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=settings.google_api_key,
        temperature=temp,
        timeout=settings.llm_timeout_seconds,
        max_retries=settings.llm_max_retries,
    )


@lru_cache(maxsize=4)
def get_llm(tier: Literal["reasoning", "fast", "judge"] = "fast") -> BaseChatModel:
    """Return a cached LangChain chat model for the given tier."""
    settings = get_settings()
    model_name = {
        "reasoning": settings.llm_reasoning_model,
        "fast": settings.llm_fast_model,
        "judge": settings.llm_judge_model,
    }[tier]
    logger.info("llm.created", tier=tier, model=model_name)
    return _build_chat_model(model_name)


# ---- Prompt loading ----------------------------------------------------------


@lru_cache(maxsize=64)
def load_prompt(name: str) -> str:
    """Load a prompt from `src/clouddash/prompts/<name>.md`.

    Prompts are markdown files with optional `{var}` placeholders to be
    .format()-ed by the caller. Markdown lets us diff prompts in PRs.
    """
    settings = get_settings()
    path = Path(settings.prompts_dir) / f"{name}.md"
    if not path.exists():
        raise ConfigurationError(
            f"Prompt template not found: {name}",
            context={"path": str(path)},
        )
    return path.read_text(encoding="utf-8")
