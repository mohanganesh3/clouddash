from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from clouddash.agents.base import AgentConfig, BaseAgent
from clouddash.models import (
    AgentResponse,
    AgentType,
    GraphState,
    IntentClassification,
    IntentCategory,
)


class TriageAgent(BaseAgent):
    """Classifies intent and routes. Never replies directly to the customer."""

    def __init__(self, config: AgentConfig) -> None:
        super().__init__(config)

    async def handle(self, state: GraphState) -> AgentResponse:
        user_msg = self._last_user_message(state)
        history = self._history_context(state)

        llm = self.get_llm("fast").with_structured_output(IntentClassification)
        sys_prompt = self.load_prompt()

        msgs = [
            SystemMessage(content=sys_prompt),
            HumanMessage(content=f"Conversation history:\n{history}\n\nLatest message: {user_msg}"),
        ]
        classification: IntentClassification = await llm.ainvoke(msgs)
        primary_intent = _heuristic_primary_intent(user_msg) or classification.primary_intent
        escalate_immediately = classification.escalate_immediately and primary_intent == IntentCategory.ESCALATION

        secondary = classification.secondary_intent
        if isinstance(secondary, list):
            secondary_intents = [intent.value for intent in secondary]
        elif secondary:
            secondary_intents = [secondary.value]
        else:
            secondary_intents = []

        # direct escalation shortcut — customer is already upset, skip the runaround
        next_agent = AgentType.ESCALATION if escalate_immediately else (
            _intent_to_agent(primary_intent)
        )

        return AgentResponse(
            agent=AgentType.TRIAGE,
            response_text="",  # triage never talks to the customer
            confidence=classification.confidence,
            next_agent=next_agent,
            metadata={
                "intent": primary_intent.value,
                "secondary_intent": secondary_intents[0] if secondary_intents else None,
                "secondary_intents": secondary_intents,
                "classification": classification.model_copy(
                    update={
                        "primary_intent": primary_intent,
                        "escalate_immediately": escalate_immediately,
                    }
                ).model_dump(mode="json"),
                "sentiment": classification.sentiment.value,
                "urgency": classification.urgency.value,
                "entities": classification.entities,
                "reasoning": classification.reasoning,
            },
        )


def _intent_to_agent(intent: IntentCategory) -> AgentType:
    return {
        IntentCategory.TECHNICAL: AgentType.TECHNICAL,
        IntentCategory.BILLING: AgentType.BILLING,
        IntentCategory.ACCOUNT: AgentType.TECHNICAL,  # SSO/RBAC lives with technical
        IntentCategory.GENERAL: AgentType.KNOWLEDGE,
        IntentCategory.ESCALATION: AgentType.ESCALATION,
        IntentCategory.UNKNOWN: AgentType.KNOWLEDGE,
    }.get(intent, AgentType.KNOWLEDGE)


def _heuristic_primary_intent(message: str) -> IntentCategory | None:
    text = message.lower()

    explicit_escalation = any(
        token in text
        for token in (
            "speak to a manager",
            "talk to a manager",
            "human manager",
            "escalate",
            "unacceptable",
            "production monitoring has been down",
        )
    )
    if explicit_escalation:
        return IntentCategory.ESCALATION

    billing_terms = (
        "invoice",
        "charged",
        "double charged",
        "duplicate charge",
        "refund",
        "billing",
        "payment",
        "plan upgrade",
        "downgrade",
    )
    if any(term in text for term in billing_terms):
        return IntentCategory.BILLING

    technical_terms = (
        "alert",
        "alerts",
        "aws",
        "gcp",
        "azure",
        "cloudwatch",
        "credential",
        "credentials",
        "integration",
        "webhook",
        "api",
        "dashboard",
        "sso",
        "rbac",
        "kubernetes",
    )
    if any(term in text for term in technical_terms):
        return IntentCategory.TECHNICAL

    return None
