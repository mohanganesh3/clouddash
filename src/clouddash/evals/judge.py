"""LLM-as-judge — scores a single EvalScenario run on the 6-axis rubric.

Per ADR-007: we use the configured `judge` model tier (defaults to a strong
model). The judge prompt lives in `prompts/judge.md` so we can iterate on it
without editing code.

Falls back to a deterministic rule-based score if the LLM call fails — so eval
runs never hard-crash on quota errors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from clouddash.llm import _build_chat_model, load_prompt
from clouddash.logging_setup import get_logger
from clouddash.models import (
    Citation,
    ConversationState,
    EvalRubricScore,
    EvalScenario,
    HandoverEvent,
)
from clouddash.settings import get_settings

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = get_logger(__name__)


def _build_judge_model() -> BaseChatModel:
    """Build the judge model explicitly (not via lru_cache so we can swap it
    in tests). We deliberately use the `llm_judge_model` from settings — it
    can be a different model than the agents use."""
    settings = get_settings()
    return _build_chat_model(settings.llm_judge_model, temperature=0.0)


def _render_handover_chain(events: list[HandoverEvent]) -> str:
    if not events:
        return "(none — direct response)"
    return "; ".join(
        f"{e.from_agent.value}→{e.to_agent.value} [{e.reason.value}/{e.status.value}]"
        for e in events
    )


def _render_citations(citations: list[Citation]) -> str:
    if not citations:
        return "(none)"
    return ", ".join(c.render_inline() + (f" ({c.title})" if c.title else "") for c in citations)


async def judge_scenario(
    scenario: EvalScenario,
    final_state: ConversationState,
    final_response: str,
    citations: list[Citation],
    actual_route: list[str],
    escalated: bool,
    retrieved_chunk_ids: list[str],
) -> EvalRubricScore:
    """Score one scenario run using the judge LLM. Defensive on failure."""
    prompt = load_prompt("judge").format(
        scenario_id=scenario.scenario_id,
        scenario_name=scenario.name,
        scenario_description=scenario.description.strip(),
        expected_route=[a.value for a in scenario.expected_route],
        must_cite=scenario.must_cite,
        must_escalate=scenario.must_escalate,
        must_refuse=scenario.must_refuse,
        user_messages="\n".join(f"- {m}" for m in scenario.user_messages),
        actual_route=actual_route,
        escalated=escalated,
        final_response=final_response[:2000],
        citations=_render_citations(citations),
        handover_chain=_render_handover_chain(final_state.handover_history),
        retrieved_chunks=", ".join(retrieved_chunk_ids[:8]) or "(none)",
    )

    try:
        model = _build_judge_model().with_structured_output(EvalRubricScore)
        result: EvalRubricScore = await model.ainvoke(prompt)  # type: ignore[assignment]
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("eval.judge_failed_falling_back_to_rules", error=str(exc))
        return _rule_based_fallback(
            scenario, final_response, citations, actual_route, escalated
        )


def _rule_based_fallback(
    scenario: EvalScenario,
    final_response: str,
    citations: list[Citation],
    actual_route: list[str],
    escalated: bool,
) -> EvalRubricScore:
    """Deterministic backstop so a quota-killed judge call doesn't fail the
    whole eval run. Conservative: prefers to PASS borderline cases since the
    primary scoring is the judge."""
    expected = {a.value for a in scenario.expected_route}
    actual = set(actual_route)
    missing = expected - actual

    routing = 1.0 if not missing else max(0.0, 1 - 0.3 * len(missing))
    citation_acc = 1.0 if (not scenario.must_cite or citations) else 0.0
    grounding = 1.0
    if scenario.must_refuse:
        lower = final_response.lower()
        # If response affirms support for the unsupported thing, big penalty.
        bad_phrases = ("yes, we support", "yes we support", "yes, clouddash supports")
        grounding = 0.0 if any(p in lower for p in bad_phrases) else 1.0
    escalation_ok = (
        1.0 if (scenario.must_escalate == escalated) else 0.0
    )

    axes = [routing, 0.7, citation_acc, 0.8, grounding, 0.7]
    overall = sum(axes) / len(axes) * (0.5 if any(a < 0.3 for a in axes) else 1.0)

    pass_fail = (
        overall >= 0.75
        and (not scenario.must_cite or bool(citations))
        and (scenario.must_escalate == escalated)
        and (grounding >= 0.9)
    )

    return EvalRubricScore(
        routing_correctness=routing,
        retrieval_relevance=0.7,
        citation_accuracy=citation_acc,
        handover_quality=0.8,
        grounding_safety=grounding,
        completeness=0.7,
        overall=overall,
        reasoning=(
            "[fallback rule-based] judge LLM unavailable; scoring used route, "
            "citation presence, refusal alignment, and escalation match. "
            f"missing_route={list(missing)}; escalation_match={escalation_ok}."
        ),
        pass_fail=bool(pass_fail),
    )
