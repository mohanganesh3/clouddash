from __future__ import annotations

from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from clouddash.settings import get_settings


@lru_cache(maxsize=4)
def build_gemini(model: str, temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    cfg = get_settings()
    return ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        google_api_key=cfg.google_api_key,
        # structured outputs break if max_retries is too low on Pro — learned this the hard way
        max_retries=cfg.llm_max_retries,
        timeout=cfg.llm_timeout_seconds,
    )
