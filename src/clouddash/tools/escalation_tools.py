"""Tools for the Escalation Agent — simulated human handoff.

`create_ticket` writes the EscalationTicket to the JSONL audit log and
returns the ticket_id. In production this would POST to Zendesk / Intercom
/ Salesforce.

`create_feature_request` does the same for product-roadmap requests
(used by the Knowledge Agent on Scenario 4 KB-miss path).
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from clouddash.logging_setup import get_logger, write_audit_event
from clouddash.models import EscalationTicket

logger = get_logger(__name__)


def create_ticket(ticket: EscalationTicket) -> dict[str, Any]:
    """Simulated human handoff. Writes ticket to audit log + returns confirmation."""
    write_audit_event(
        "escalation.ticket_created",
        ticket_id=str(ticket.ticket_id),
        priority=ticket.recommended_priority,
        sentiment=ticket.sentiment.value,
        urgency=ticket.urgency.value,
        customer_id=ticket.customer_profile.customer_id,
        org_name=ticket.customer_profile.org_name,
        issue_summary=ticket.issue_summary[:500],
        suggested_actions=ticket.suggested_actions,
    )
    logger.info(
        "escalation.ticket_created",
        ticket_id=str(ticket.ticket_id),
        priority=ticket.recommended_priority,
    )
    return {
        "ticket_id": str(ticket.ticket_id),
        "priority": ticket.recommended_priority,
        "status": "queued",
        "expected_response": (
            "1 business hour" if ticket.recommended_priority in ("P0", "P1") else "1 business day"
        ),
    }


def create_feature_request(
    *,
    title: str,
    summary: str,
    customer_id: str | None,
    org_name: str | None,
) -> dict[str, Any]:
    """Simulated feature-request creation (Scenario 4 KB-miss path)."""
    fr_id = f"FR-{uuid4().hex[:8].upper()}"
    write_audit_event(
        "feature_request.created",
        feature_request_id=fr_id,
        title=title[:200],
        summary=summary[:500],
        customer_id=customer_id,
        org_name=org_name,
    )
    logger.info("feature_request.created", id=fr_id, title=title)
    return {
        "feature_request_id": fr_id,
        "status": "submitted",
        "next_steps": (
            "Our product team reviews requests at the quarterly roadmap review. "
            "We'll notify the requesting customer when there's an update."
        ),
    }
