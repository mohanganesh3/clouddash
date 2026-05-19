from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from clouddash.agents.base import AgentConfig, BaseAgent
from clouddash.agents.technical import _parse_citations
from clouddash.models import (
    AgentResponse,
    AgentType,
    GraphState,
    HandoverPacket,
    HandoverReason,
)
from clouddash.retrieval.crag_graph import run_crag
from clouddash.tools.crm import crm_lookup, list_plans


class _BillingResponse(BaseModel):
    answer: str
    citations: list[str]
    needs_escalation: bool = False
    escalation_reason: str = ""
    # $1k refund limit — anything over requires human approval
    refund_amount_requested: float = 0.0
    confidence: float


class BillingAgent(BaseAgent):
    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)

    async def handle(self, state: GraphState) -> AgentResponse:
        user_msg = self._last_user_message(state)
        history = self._history_context(state)

        chunks, crag_path = await run_crag(user_msg, history)
        ctx = "\n\n".join(f"[{c.kb_id} § {c.section}] {c.content[:500]}" for c in chunks)

        # try to get CRM data if we have a customer_id
        crm_data = ""
        cust = state.get("customer_profile")
        if cust and cust.customer_id:
            try:
                crm_result = crm_lookup.invoke({"customer_id": cust.customer_id})
                if "error" not in crm_result:
                    crm_data = f"\nCRM data: {crm_result}"
            except Exception:
                pass

        prior = ""
        if state.get("pending_handover"):
            ho = state["pending_handover"]
            prior = f"\n\n[HANDOVER FROM TECHNICAL]\n{ho.conversation_summary}"

        llm = self.get_llm("reasoning").with_structured_output(_BillingResponse)
        sys_prompt = self.load_prompt()
        msgs = [
            SystemMessage(content=sys_prompt),
            HumanMessage(
                content=(
                    f"Customer message: {user_msg}\n"
                    f"History:\n{history}{prior}\n"
                    f"{crm_data}\n\n"
                    f"KB context:\n{ctx or 'No relevant articles found.'}"
                )
            ),
        ]
        resp: _BillingResponse = await llm.ainvoke(msgs)

        handover = None
        next_agent = None

        if resp.needs_escalation or resp.refund_amount_requested > 1000:
            reason = resp.escalation_reason or f"refund ${resp.refund_amount_requested:.0f} exceeds $1k authority"
            next_agent = AgentType.ESCALATION
            handover = HandoverPacket(
                trace_id=state["trace_id"],
                turn_id=state["turn_id"],
                from_agent=AgentType.BILLING,
                to_agent=AgentType.ESCALATION,
                reason=HandoverReason.REQUIRES_ESCALATION,
                user_intent=user_msg,
                conversation_summary=f"Billing: {reason}. Response draft: {resp.answer[:200]}",
                customer_profile=cust,
                extracted_entities={"refund_amount": resp.refund_amount_requested},
                confidence_state=resp.confidence,
            )

        citations = _parse_citations(resp.citations, chunks)
        return AgentResponse(
            agent=AgentType.BILLING,
            response_text=resp.answer,
            citations=citations,
            retrieved_chunks=chunks,
            confidence=resp.confidence,
            handover_packet=handover,
            next_agent=next_agent,
            crag_path=crag_path,
        )
