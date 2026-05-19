from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool


# simulated queue — in production this would be Zendesk/Jira/ServiceNow
_TICKET_QUEUE: list[dict[str, Any]] = []


@tool
def create_ticket(
    customer_id: str,
    priority: str,
    issue_summary: str,
    recommended_actions: list[str],
    conversation_summary: str,
    sentiment: str = "neutral",
) -> dict[str, Any]:
    """Create a human support ticket for escalated issues requiring human intervention."""
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"
    ticket = {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "priority": priority,
        "issue_summary": issue_summary,
        "recommended_actions": recommended_actions,
        "conversation_summary": conversation_summary,
        "sentiment": sentiment,
        "status": "open",
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "estimated_response_hours": {"critical": 1, "high": 4, "medium": 24, "low": 72}.get(priority, 24),
    }
    _TICKET_QUEUE.append(ticket)
    return {
        "ticket_id": ticket_id,
        "status": "created",
        "estimated_response_hours": ticket["estimated_response_hours"],
        "message": f"Your ticket {ticket_id} has been created. A support engineer will contact you within {ticket['estimated_response_hours']} hours.",
    }


def get_all_tickets() -> list[dict[str, Any]]:
    return list(_TICKET_QUEUE)
