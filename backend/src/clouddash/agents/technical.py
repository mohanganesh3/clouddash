"""Technical support agent — handles alerts, integrations, SSO, API, dashboards.

Uses CRAG for retrieval. Hands over to Billing if the conversation drifts
(happens a lot with Pro→Enterprise upgrades mid-troubleshooting).
"""
from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool  # noqa: F401 (used in bind_tools)
from pydantic import BaseModel

from clouddash.agents.base import AgentConfig, BaseAgent
from clouddash.models import (
    AgentResponse,
    AgentType,
    Citation,
    CRAGPath,
    GraphState,
    HandoverPacket,
    HandoverReason,
)
from clouddash.retrieval.crag_graph import run_crag


class _TechResponse(BaseModel):
    answer: str
    citations: list[str]  # list of "KB-XXX § N" strings
    needs_billing_handover: bool = False
    needs_escalation: bool = False
    confidence: float


class TechnicalAgent(BaseAgent):
    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)

    async def handle(self, state: GraphState) -> AgentResponse:
        user_msg = self._last_user_message(state)
        history = self._history_context(state)

        chunks, crag_path = await run_crag(user_msg, history)

        ctx = "\n\n".join(f"[{c.kb_id} § {c.section}] {c.content[:600]}" for c in chunks)

        llm = self.get_llm("reasoning").with_structured_output(_TechResponse)
        sys_prompt = self.load_prompt()

        prior_context = ""
        if state.get("pending_handover"):
            ho = state["pending_handover"]
            prior_context = f"\n\n[HANDOVER CONTEXT]\n{ho.conversation_summary}\nPrior attempts: {[a.summary for a in ho.prior_attempts]}"

        msgs = [
            SystemMessage(content=sys_prompt),
            HumanMessage(
                content=(
                    f"Customer message: {user_msg}\n\n"
                    f"Conversation history:\n{history}{prior_context}\n\n"
                    f"Retrieved KB context:\n{ctx or 'No relevant KB articles found.'}"
                )
            ),
        ]
        resp: _TechResponse = await llm.ainvoke(msgs)

        citations = _parse_citations(resp.citations, chunks)
        next_agent = None
        handover = None

        if resp.needs_billing_handover:
            next_agent = AgentType.BILLING
            handover = HandoverPacket(
                trace_id=state["trace_id"],
                turn_id=state["turn_id"],
                from_agent=AgentType.TECHNICAL,
                to_agent=AgentType.BILLING,
                reason=HandoverReason.MULTI_INTENT,
                user_intent=user_msg,
                conversation_summary=f"Technical resolved: {resp.answer[:200]}. Now needs billing.",
                customer_profile=state.get("customer_profile"),
                confidence_state=resp.confidence,
            )
        elif resp.needs_escalation:
            next_agent = AgentType.ESCALATION
            handover = HandoverPacket(
                trace_id=state["trace_id"],
                turn_id=state["turn_id"],
                from_agent=AgentType.TECHNICAL,
                to_agent=AgentType.ESCALATION,
                reason=HandoverReason.LOW_CONFIDENCE,
                user_intent=user_msg,
                conversation_summary=resp.answer[:300],
                customer_profile=state.get("customer_profile"),
                confidence_state=resp.confidence,
            )

        return AgentResponse(
            agent=AgentType.TECHNICAL,
            response_text=resp.answer,
            citations=citations,
            retrieved_chunks=chunks,
            confidence=resp.confidence,
            handover_packet=handover,
            next_agent=next_agent,
            crag_path=crag_path,
        )


def _parse_citations(raw: list[str], chunks) -> list[Citation]:
    result = []
    seen: set[tuple[str, int, str]] = set()
    for ref in raw:
        match = re.search(r"\b(KB-\d+|WEB)(?:\s*§\s*(-?\d+))?", ref)
        kb_id = match.group(1) if match else ""
        section = int(match.group(2)) if match and match.group(2) is not None else None

        exact = [
            chunk for chunk in chunks
            if chunk.kb_id == kb_id and (section is None or chunk.section == section)
        ]
        candidates = exact or [chunk for chunk in chunks if chunk.kb_id in ref]
        for chunk in chunks:
            if chunk in candidates:
                key = (chunk.kb_id, chunk.section, chunk.chunk_id)
                if key in seen:
                    break
                seen.add(key)
                result.append(Citation(
                    kb_id=chunk.kb_id,
                    title=chunk.title,
                    section=chunk.section,
                    chunk_id=chunk.chunk_id,
                    relevance_score=chunk.rerank_score,
                    snippet=chunk.content[:150],
                ))
                break
    return result
