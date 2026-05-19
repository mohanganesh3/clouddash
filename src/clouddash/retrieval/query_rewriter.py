"""Conversation-aware query rewriter (per §2.2).

Given a (multi-turn) conversation + the latest user message, produce 1–3
standalone search queries that retrieve the most relevant KB chunks. We use
Gemini Flash with structured output (Pydantic schema) to avoid parse fragility.

If the LLM call fails for any reason, we fall back to the raw user message.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from clouddash.exceptions import LLMError
from clouddash.llm import get_llm, load_prompt
from clouddash.logging_setup import get_logger

if TYPE_CHECKING:
    from clouddash.models import GraphState

logger = get_logger(__name__)


class _RewrittenQueries(BaseModel):
    """Structured output schema for the rewriter."""

    queries: list[str] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="1–3 standalone search queries.",
    )
    reasoning: str = Field(
        ...,
        max_length=400,
        description="Brief rationale for the decomposition.",
    )


def rewrite_query(
    state: GraphState,
    *,
    latest_message: str | None = None,
    last_n_turns: int = 5,
) -> list[str]:
    """Decompose the latest user message into 1–3 retrieval queries.

    Uses recent conversation context to resolve pronouns / ellipses.
    Falls back to the raw message if the LLM call fails.
    """
    if latest_message is None:
        msg = state.latest_user_message()
        latest_message = msg.content if msg else ""

    if not latest_message.strip():
        return []

    conversation = state.conversation_text(last_n_turns=last_n_turns)
    prompt_template = load_prompt("query_rewriter")
    prompt = prompt_template.format(
        conversation=conversation or "(no prior context)",
        latest_message=latest_message,
    )

    t0 = time.time()
    try:
        llm = get_llm("fast")
        structured = llm.with_structured_output(_RewrittenQueries)
        result: _RewrittenQueries = structured.invoke(prompt)  # type: ignore[assignment]
        latency_ms = int((time.time() - t0) * 1000)
        logger.info(
            "query_rewriter.success",
            queries=result.queries,
            reasoning=result.reasoning,
            latency_ms=latency_ms,
        )
        # Defensive: ensure queries are non-empty strings
        cleaned = [q.strip() for q in result.queries if q and q.strip()]
        return cleaned or [latest_message]
    except Exception as exc:  # noqa: BLE001 — graceful fallback
        logger.warning(
            "query_rewriter.fallback",
            error=str(exc),
            error_type=type(exc).__name__,
            latency_ms=int((time.time() - t0) * 1000),
        )
        # Don't raise — degrade gracefully to the raw message
        if isinstance(exc, LLMError):
            raise
        return [latest_message]
