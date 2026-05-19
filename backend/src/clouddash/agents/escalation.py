"""Escalation agent — packages context for human handoff.

This is where interrupt() fires. The graph pauses here, the frontend shows
the HITL approval dialog, and the graph resumes when the human clicks approve.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import interrupt
from pydantic import BaseModel

from clouddash.agents.base import AgentConfig, BaseAgent
from clouddash.models import (
    AgentResponse,
    AgentType,
    EscalationTicket,
    GraphState,
    Sentiment,
    Urgency,
)
from clouddash.tools.tickets import create_ticket


class _EscalationOutput(BaseModel):
    customer_message: str  # what to tell the customer
    issue_summary: str
    recommended_actions: list[str]
    priority: str  # critical | high | medium | low
    estimated_resolution_hours: int = 24


class EscalationAgent(BaseAgent):
    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)

    async def handle(self, state: GraphState) -> AgentResponse:
        user_msg = self._last_user_message(state)
        history = self._history_context(state, turns=5)

        ho = state.get("pending_handover")
        prior_summary = ho.conversation_summary if ho else ""

        llm = self.get_llm("fast").with_structured_output(_EscalationOutput)
        msgs = [
            SystemMessage(content=self.load_prompt()),
            HumanMessage(
                content=(
                    f"Customer message: {user_msg}\n"
                    f"History: {history}\n"
                    f"Prior agent summary: {prior_summary}"
                )
            ),
        ]
        out: _EscalationOutput = await llm.ainvoke(msgs)

        cust = state.get("customer_profile")
        urgency = _state_urgency(state) or _classify_urgency(out.priority)
        sentiment = _classify_sentiment(state)
        team_label = _handoff_team_label(state)
        approval_message = _approval_message(team_label, sentiment)
        recommended_actions = _recommended_actions(team_label)

        ticket = EscalationTicket(
            priority=urgency,
            customer_id=cust.customer_id if cust else "unknown",
            issue_summary=out.issue_summary,
            recommended_actions=recommended_actions,
            conversation_summary=prior_summary or history[:500],
            sentiment=sentiment,
            estimated_resolution_hours=out.estimated_resolution_hours,
        )

        # HITL — graph pauses here. Frontend shows approval dialog.
        # hitl_decision will be "approve" | "edit" | "reject" on resume.
        hitl_decision = interrupt({
            "ticket_draft": ticket.model_dump(),
            "customer_message": approval_message,
            "reason": "Escalation requires human approval before ticket creation",
        })

        # if reviewer rejected, don't create the ticket
        if hitl_decision == "reject":
            return AgentResponse(
                agent=AgentType.ESCALATION,
                response_text="I've reviewed your case and will continue to work on resolving it. Please give me a moment.",
                escalate=False,
            )

        # if edited, the frontend sends back the modified ticket
        if isinstance(hitl_decision, dict) and "ticket" in hitl_decision:
            ticket_data = hitl_decision["ticket"]
            ticket = EscalationTicket(**ticket_data)

        # actually create the ticket now
        try:
            result = create_ticket.invoke({
                "customer_id": ticket.customer_id,
                "priority": ticket.priority.value,
                "issue_summary": ticket.issue_summary,
                "recommended_actions": ticket.recommended_actions,
                "conversation_summary": ticket.conversation_summary,
                "sentiment": ticket.sentiment.value,
            })
            ticket_id = result.get("ticket_id", ticket.ticket_id)
            est_hours = result.get("estimated_response_hours", ticket.estimated_resolution_hours)
        except Exception:
            ticket_id = ticket.ticket_id
            est_hours = ticket.estimated_resolution_hours

        customer_msg = _final_customer_message(team_label, ticket_id, est_hours)

        return AgentResponse(
            agent=AgentType.ESCALATION,
            response_text=customer_msg,
            escalate=True,
            escalation_ticket=ticket,
            confidence=1.0,
        )


def _classify_urgency(priority_str: str) -> Urgency:
    return {
        "critical": Urgency.CRITICAL,
        "high": Urgency.HIGH,
        "medium": Urgency.MEDIUM,
        "low": Urgency.LOW,
    }.get(priority_str.lower(), Urgency.MEDIUM)


def _classify_sentiment(state: GraphState) -> Sentiment:
    ho = state.get("pending_handover")
    if ho:
        return ho.sentiment
    # crude heuristic from last message — the Triage intent_classification is more accurate
    ic = state.get("intent_classification")
    if ic:
        return ic.sentiment
    return Sentiment.NEUTRAL


def _state_urgency(state: GraphState) -> Urgency | None:
    ho = state.get("pending_handover")
    if ho:
        return ho.urgency
    ic = state.get("intent_classification")
    if ic:
        return ic.urgency
    return None


def _handoff_team_label(state: GraphState) -> str:
    ho = state.get("pending_handover")
    if ho:
        if ho.from_agent == AgentType.TECHNICAL:
            return "Technical Support Engineer"
        if ho.from_agent == AgentType.BILLING:
            return "Billing Manager"
        if ho.from_agent == AgentType.KNOWLEDGE:
            return "Support Specialist"

    intent = state.get("intent")
    intent_value = getattr(intent, "value", intent)
    if intent_value == "technical":
        return "Technical Support Engineer"
    if intent_value == "billing":
        return "Billing Manager"
    return "Support Manager"


def _approval_message(team_label: str, sentiment: Sentiment) -> str:
    prefix = ""
    if sentiment in {Sentiment.FRUSTRATED, Sentiment.ANGRY}:
        prefix = "I understand this is urgent. "
    return (
        f"{prefix}I'm preparing a handoff to a {team_label}. "
        "Once approved, I'll create the ticket and share the ticket ID here."
    )


def _final_customer_message(team_label: str, ticket_id: str, est_hours: int) -> str:
    hour_label = "hour" if est_hours == 1 else "hours"
    return (
        f"I've escalated your case to a {team_label}.\n\n"
        f"Your ticket ID is **{ticket_id}**. "
        f"A {team_label.lower()} will contact you within {est_hours} {hour_label}."
    )


def _recommended_actions(team_label: str) -> list[str]:
    if team_label == "Technical Support Engineer":
        return [
            "Review the affected workspace's monitoring ingestion and alert delivery health.",
            "Check recent integration credential changes and CloudDash collector authentication failures.",
            "Confirm restoration steps with the customer and attach the conversation context to the ticket.",
        ]
    if team_label == "Billing Manager":
        return [
            "Review the customer account, invoice IDs, and duplicate-charge evidence.",
            "Confirm refund or credit eligibility under the billing policy.",
            "Update the customer with the approved billing resolution and any follow-up timeline.",
        ]
    return [
        "Review the incident severity, customer impact, and conversation context.",
        "Assign the case to the correct support owner with the recommended next action.",
        "Send the customer a clear follow-up timeline after ownership is confirmed.",
    ]
