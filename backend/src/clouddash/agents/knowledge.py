from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from clouddash.agents.base import AgentConfig, BaseAgent
from clouddash.agents.technical import _parse_citations
from clouddash.models import AgentResponse, AgentType, GraphState
from clouddash.retrieval.crag_graph import run_crag
from clouddash.tools.feature_request import file_feature_request


class _KnowledgeResponse(BaseModel):
    answer: str
    citations: list[str]
    kb_miss: bool = False  # true when CRAG returned web/low-conf results
    feature_request_summary: str = ""
    confidence: float


class KnowledgeAgent(BaseAgent):
    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)

    async def handle(self, state: GraphState) -> AgentResponse:
        user_msg = self._last_user_message(state)
        history = self._history_context(state)

        chunks, crag_path = await run_crag(user_msg, history)
        ctx = "\n\n".join(f"[{c.kb_id} § {c.section}] {c.content[:500]}" for c in chunks)

        llm = self.get_llm("reasoning").with_structured_output(_KnowledgeResponse)
        msgs = [
            SystemMessage(content=self.load_prompt()),
            HumanMessage(
                content=(
                    f"Customer: {user_msg}\nHistory: {history}\n\n"
                    f"KB context:\n{ctx or 'No relevant articles found.'}"
                )
            ),
        ]
        resp: _KnowledgeResponse = await llm.ainvoke(msgs)

        # KB miss path: file feature request if customer is asking about something we don't support
        if resp.kb_miss and resp.feature_request_summary:
            cust = state.get("customer_profile")
            try:
                file_feature_request.invoke({
                    "customer_id": cust.customer_id if cust else "unknown",
                    "feature_summary": resp.feature_request_summary,
                    "use_case": user_msg,
                })
            except Exception:
                pass

        citations = _parse_citations(resp.citations, chunks)
        return AgentResponse(
            agent=AgentType.KNOWLEDGE,
            response_text=resp.answer,
            citations=citations,
            retrieved_chunks=chunks,
            confidence=resp.confidence,
            crag_path=crag_path,
        )
