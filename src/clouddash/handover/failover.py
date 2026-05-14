"""Handover failover chain — handles HandoverReject and agent-error cases.

Per §2.3: 'Handle failed handovers gracefully — if the target agent rejects
or errors, the system should fall back to the Triage Agent or Escalation Agent.'

The fallback chain is configured in `config/routing.yaml` under
`fallback_chain:` (default: triage → escalation). When a handover fails,
the orchestrator consults this module to choose the next target.
"""

from __future__ import annotations

from clouddash.agents.registry import AgentRegistry, get_registry
from clouddash.handover.audit import log_fallback_invoked
from clouddash.logging_setup import get_logger
from clouddash.models import AgentType

logger = get_logger(__name__)


def next_fallback(
    failed_agent: AgentType,
    *,
    already_tried: set[AgentType] | None = None,
    registry: AgentRegistry | None = None,
) -> AgentType | None:
    """Pick the next agent to try after a failure.

    Walks the configured fallback_chain skipping any agent we've already tried
    in this conversation. Returns None when the chain is exhausted (orchestrator
    should then surface the error to the customer).
    """
    reg = registry or get_registry()
    tried = already_tried or set()
    tried.add(failed_agent)

    chain = reg.fallback_chain()
    for candidate in chain:
        if candidate not in tried:
            log_fallback_invoked(
                from_agent=failed_agent,
                fallback_agent=candidate,
                reason=f"failover from {failed_agent.value}; already_tried={[a.value for a in tried]}",
            )
            logger.info(
                "failover.next",
                failed=failed_agent.value,
                next=candidate.value,
                tried=[a.value for a in tried],
            )
            return candidate

    logger.warning(
        "failover.exhausted",
        failed=failed_agent.value,
        tried=[a.value for a in tried],
        chain=[a.value for a in chain],
    )
    return None
