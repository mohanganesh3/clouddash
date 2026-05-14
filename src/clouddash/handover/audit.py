"""Handover audit log helpers.

Per §2.3: every handover event must be logged with timestamp, source,
target, reason, context snapshot. This module provides typed wrappers
around the structured audit log so handover events have a consistent
schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from clouddash.logging_setup import get_logger, write_audit_event
from clouddash.models import (
    AgentType,
    HandoverEvent,
    HandoverPacket,
    HandoverReason,
    HandoverStatus,
)
from clouddash.settings import get_settings

logger = get_logger(__name__)


def log_handover_created(packet: HandoverPacket) -> None:
    """Log when a handover packet is created (BaseAgent already calls this)."""
    write_audit_event(
        "handover.created",
        packet_id=str(packet.packet_id),
        from_agent=packet.from_agent.value,
        to_agent=packet.to_agent.value,
        reason=packet.reason.value,
        confidence=packet.confidence_state,
        sentiment=packet.sentiment.value,
        urgency=packet.urgency.value,
        prior_attempts=len(packet.prior_attempts),
        audit_chain_depth=len(packet.audit_chain),
    )


def log_handover_accepted(
    packet_id: UUID,
    accepted_by: AgentType,
    *,
    note: str | None = None,
) -> None:
    write_audit_event(
        "handover.accepted",
        packet_id=str(packet_id),
        accepted_by=accepted_by.value,
        note=note,
    )


def log_handover_rejected(
    packet_id: UUID,
    rejected_by: AgentType,
    *,
    reason: str,
    suggest_route_to: AgentType | None = None,
) -> None:
    write_audit_event(
        "handover.rejected",
        packet_id=str(packet_id),
        rejected_by=rejected_by.value,
        reason=reason,
        suggest_route_to=suggest_route_to.value if suggest_route_to else None,
    )


def log_handover_failed(
    packet_id: UUID,
    *,
    error: str,
    next_target: AgentType | None = None,
) -> None:
    write_audit_event(
        "handover.failed",
        packet_id=str(packet_id),
        error=error,
        next_target=next_target.value if next_target else None,
    )


def log_fallback_invoked(
    *,
    from_agent: AgentType,
    fallback_agent: AgentType,
    reason: str,
) -> None:
    write_audit_event(
        "handover.fallback",
        from_agent=from_agent.value,
        fallback_agent=fallback_agent.value,
        reason=reason,
    )


# -----------------------------------------------------------------------------
# Audit replay — read events back for a given trace_id (used by /trace endpoint)
# -----------------------------------------------------------------------------


def read_trace_events(trace_id: UUID | str) -> list[dict[str, Any]]:
    """Stream the JSONL audit log and return all events for the given trace_id.

    Linear scan — fine for a prototype with thousands of events. In production
    you'd index by trace_id (e.g. ClickHouse, BigQuery) or push to OpenSearch.
    """
    path = Path(get_settings().audit_log_path)
    target = str(trace_id)
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("trace_id") == target:
                events.append(rec)
    return events
