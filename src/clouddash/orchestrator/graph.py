"""LangGraph orchestrator — wires registered agents into a state machine.

Per ADR-001: the graph is built from `config/agents.yaml` at startup. The
orchestrator code does NOT name any specific agent — it iterates over the
registry. This is what makes the live "add new agent" demo work.

State flow:
    START → triage → conditional_routing → [specialist or escalation]
                                          ↓
                          [more handovers possible]
                                          ↓
                                         END

State updates per turn:
- `messages`: appended via reducer
- `handover_history`: appended via reducer
- `current_agent`, `last_response`, `pending_handover`: replaced

Failure handling: if an agent raises, the orchestrator routes to the
fallback chain (handover.failover.next_fallback).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from clouddash.agents.registry import AgentRegistry, get_registry
from clouddash.exceptions import HandoverChainExhaustedError
from clouddash.guardrails import (
    build_blocked_input_response,
    evaluate_input,
    evaluate_output,
)
from clouddash.handover.audit import (
    log_handover_failed,
    read_trace_events,
)
from clouddash.handover.failover import next_fallback
from clouddash.logging_setup import get_logger, set_trace_context, write_audit_event
from clouddash.models import (
    AgentResponse,
    AgentType,
    ConversationState,
    HandoverEvent,
    HandoverStatus,
    Message,
    MessageRole,
)

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph

logger = get_logger(__name__)


class Orchestrator:
    """The orchestrator owns the LangGraph state graph and runs turns through it."""

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or get_registry()
        self._graph: CompiledStateGraph | None = None

    @property
    def graph(self) -> CompiledStateGraph:
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    def rebuild_graph(self) -> None:
        """Force the graph to be rebuilt from the current registry. Used by the
        live 'add new agent' demo: edit YAML → reload registry → rebuild graph."""
        self._graph = None

    # -------------------------------------------------------------------------
    # Graph construction
    # -------------------------------------------------------------------------

    def _build_graph(self) -> CompiledStateGraph:
        from langgraph.graph import END, START, StateGraph

        graph: StateGraph = StateGraph(ConversationState)

        agent_types = self.registry.list_agents()

        # Add a node per registered agent
        for atype in agent_types:
            graph.add_node(atype.value, self._make_node(atype))

        # Entry: always Triage
        if AgentType.TRIAGE not in agent_types:
            raise ValueError("Triage agent must be registered (it's the entry node)")
        graph.add_edge(START, AgentType.TRIAGE.value)

        # Conditional routing from every agent — driven by `last_response.next_agent`
        node_map: dict[str, str] = {atype.value: atype.value for atype in agent_types}
        node_map["END"] = END

        for atype in agent_types:
            graph.add_conditional_edges(
                atype.value,
                self._route_after_agent,
                node_map,
            )

        compiled = graph.compile()
        logger.info(
            "orchestrator.graph_built",
            agents=[a.value for a in agent_types],
            entry="triage",
        )
        return compiled

    def _make_node(self, agent_type: AgentType):
        """Return an async LangGraph node function for the given agent."""

        async def node(state: ConversationState) -> dict[str, Any]:
            set_trace_context(
                trace_id=str(state.trace_id),
                turn_id=state.turn_id,
                agent=agent_type.value,
            )
            agent = self.registry.get(agent_type)
            t0 = time.time()

            try:
                response: AgentResponse = await agent.handle(state)
            except Exception as exc:  # noqa: BLE001
                response = self._handle_agent_exception(state, agent_type, exc, t0)

            # ---- Output guardrails + single self-correction --------------
            # Only run on KB-grounded agents that produced text. Skip:
            #   - handover-only / empty-text responses
            #   - non-KB agents (Triage, Escalation) — their outputs are
            #     classification or ticket acks and aren't expected to cite.
            cfg = self.registry.get_config(agent_type)
            if (
                response.response_text
                and response.retrieved_chunks is not None
                and cfg.requires_kb
            ):
                decision = evaluate_output(
                    response.response_text,
                    response.retrieved_chunks,
                )
                if decision.action == "self_correct":
                    logger.info(
                        "orchestrator.self_correcting",
                        agent=agent_type.value,
                        failures=[r.guardrail_name for r in decision.failures],
                    )
                    response = await self._self_correct(
                        agent, agent_type, state, decision.correction_hint, t0
                    )

            response.latency_ms = int((time.time() - t0) * 1000)
            return self._response_to_state_update(state, response)

        node.__name__ = f"node_{agent_type.value}"
        return node

    # -------------------------------------------------------------------------
    # Agent exception fallback + guardrail self-correction
    # -------------------------------------------------------------------------

    def _handle_agent_exception(
        self,
        state: ConversationState,
        agent_type: AgentType,
        exc: Exception,
        t0: float,
    ) -> AgentResponse:
        """Build a synthetic failover handover when an agent raises."""
        from clouddash.models import HandoverPacket, HandoverReason

        latency = int((time.time() - t0) * 1000)
        logger.exception(
            "orchestrator.agent_failed",
            agent=agent_type.value,
            error=str(exc),
            error_type=type(exc).__name__,
            latency_ms=latency,
        )
        fallback = next_fallback(
            agent_type,
            already_tried={
                e.from_agent for e in state.handover_history
            } | {agent_type},
        )
        if fallback is None:
            raise HandoverChainExhaustedError(
                "All fallback agents exhausted",
                context={"failed_agent": agent_type.value},
                cause=exc,
            ) from exc

        log_handover_failed(
            packet_id=(
                state.pending_handover.packet_id
                if state.pending_handover
                else state.trace_id
            ),
            error=str(exc),
            next_target=fallback,
        )

        synthetic = HandoverPacket(
            trace_id=state.trace_id,
            turn_id=state.turn_id,
            from_agent=agent_type,
            to_agent=fallback,
            reason=HandoverReason.TARGET_REJECTED,
            user_intent=(
                state.pending_handover.user_intent
                if state.pending_handover
                else "Recovering from agent failure."
            ),
            conversation_summary=(
                f"{agent_type.value} agent failed: {exc}. "
                f"Falling back to {fallback.value}."
            ),
            customer_profile=state.customer_profile,
            confidence_state=0.1,
        )
        return AgentResponse(
            agent=agent_type,
            response_text="",
            confidence=0.1,
            handover_packet=synthetic,
            next_agent=fallback,
            metadata={"failover": True, "error": str(exc)},
        )

    async def _self_correct(
        self,
        agent,
        agent_type: AgentType,
        state: ConversationState,
        correction_hint: str | None,
        t0: float,
    ) -> AgentResponse:
        """Re-call the agent ONCE with a corrective hint inlined into the
        most recent user message. We don't loop further — if the second
        attempt still fails, we accept the response and log a warning so
        the user is never left in an infinite-retry hole."""
        if not correction_hint:
            return await agent.handle(state)

        # Inline the hint into the latest user message so agents that already
        # use state.latest_user_message() pick it up without code changes.
        new_messages: list[Message] = list(state.messages)
        for i in range(len(new_messages) - 1, -1, -1):
            m = new_messages[i]
            if m.role == MessageRole.USER:
                new_messages[i] = m.model_copy(
                    update={
                        "content": (
                            f"{m.content}\n\n[INTERNAL — NOT USER VISIBLE]\n"
                            f"{correction_hint}"
                        ),
                    }
                )
                break

        corrected_state = state.model_copy(update={"messages": new_messages})
        try:
            response = await agent.handle(corrected_state)
        except Exception as exc:  # noqa: BLE001
            return self._handle_agent_exception(state, agent_type, exc, t0)

        # Re-evaluate; if still failing, accept and warn.
        if response.response_text and response.retrieved_chunks is not None:
            second = evaluate_output(response.response_text, response.retrieved_chunks)
            if not second.passed:
                logger.warning(
                    "orchestrator.self_correction_did_not_pass",
                    agent=agent_type.value,
                    failures=[r.guardrail_name for r in second.failures],
                )
                write_audit_event(
                    "guardrail.output.self_correction_failed",
                    agent=agent_type.value,
                    failures=[r.guardrail_name for r in second.failures],
                )
        return response

    def _response_to_state_update(
        self,
        state: ConversationState,
        response: AgentResponse,
    ) -> dict[str, Any]:
        """Convert an AgentResponse into a partial-state dict for LangGraph."""
        updates: dict[str, Any] = {
            "current_agent": response.agent,
            "last_response": response,
        }

        # Append assistant message if the agent produced text
        new_messages: list[Message] = []
        if response.response_text:
            new_messages.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=response.response_text,
                    agent=response.agent,
                    turn_id=state.turn_id,
                    citations=response.citations,
                    metadata={
                        "retrieved_chunk_ids": [c.chunk_id for c in response.retrieved_chunks],
                        "confidence": response.confidence,
                        "latency_ms": response.latency_ms,
                    },
                )
            )
        if new_messages:
            updates["messages"] = new_messages

        # Handover handling
        if response.handover_packet is not None:
            updates["pending_handover"] = response.handover_packet
            # Append the latest event from the audit chain (the new handover)
            new_event = response.handover_packet.audit_chain[-1] if response.handover_packet.audit_chain else None
            if new_event is not None:
                # Mark accepted (will be set to ACCEPTED when the receiving agent acknowledges)
                updates["handover_history"] = [
                    new_event.model_copy(update={"status": HandoverStatus.PENDING})
                ]
        elif response.escalate or response.response_text:
            # Terminal — clear any pending handover
            updates["pending_handover"] = None

        return updates

    @staticmethod
    def _route_after_agent(state: ConversationState) -> str:
        """Conditional edge: where to go after an agent node executes."""
        resp = state.last_response
        if resp is None:
            return "END"
        if resp.next_agent is not None:
            return resp.next_agent.value
        # No handover: either text response or escalation → END
        return "END"

    # -------------------------------------------------------------------------
    # Public API — run a turn
    # -------------------------------------------------------------------------

    async def run_turn(
        self,
        state: ConversationState,
        user_message: str,
    ) -> ConversationState:
        """Process one user turn through the full graph. Returns updated state."""
        next_turn = state.turn_id + 1
        set_trace_context(trace_id=str(state.trace_id), turn_id=next_turn)

        # ---- Input guardrails (Layer 1) ---------------------------------
        in_decision = evaluate_input(user_message)
        if not in_decision.is_allowed:
            # Block the turn entirely. Never feed flagged input to an LLM.
            refusal = build_blocked_input_response(in_decision)
            user_msg = Message(role=MessageRole.USER, content=user_message, turn_id=next_turn)
            assistant_msg = Message(
                role=MessageRole.ASSISTANT,
                content=refusal,
                agent=AgentType.TRIAGE,  # block is logically a Triage refusal
                turn_id=next_turn,
                metadata={
                    "guardrail_blocked": True,
                    "blocked_by": (
                        in_decision.blocked_by.guardrail_name
                        if in_decision.blocked_by
                        else "unknown"
                    ),
                },
            )
            blocked_response = AgentResponse(
                agent=AgentType.TRIAGE,
                response_text=refusal,
                confidence=1.0,
                metadata={"guardrail_blocked": True},
            )
            logger.info(
                "orchestrator.input_blocked",
                trace_id=str(state.trace_id),
                turn_id=next_turn,
                blocked_by=(
                    in_decision.blocked_by.guardrail_name
                    if in_decision.blocked_by
                    else None
                ),
            )
            return state.model_copy(
                update={
                    "turn_id": next_turn,
                    "messages": [*state.messages, user_msg, assistant_msg],
                    "last_response": blocked_response,
                }
            )

        # Use the (possibly redacted) sanitized text as the user message content.
        sanitized = in_decision.sanitized_text
        user_msg = Message(role=MessageRole.USER, content=sanitized, turn_id=next_turn)

        # Build initial state for this turn
        starting_state = state.model_copy(
            update={
                "turn_id": next_turn,
                "messages": [*state.messages, user_msg],
            }
        )

        logger.info(
            "orchestrator.turn_start",
            trace_id=str(state.trace_id),
            turn_id=next_turn,
            user_message_preview=sanitized[:120],
            input_redacted=in_decision.was_redacted,
        )

        t0 = time.time()
        result = await self.graph.ainvoke(starting_state)
        # LangGraph returns either a dict or a ConversationState depending on version
        if isinstance(result, dict):
            final_state = ConversationState(**result)
        else:
            final_state = result

        elapsed_ms = int((time.time() - t0) * 1000)
        logger.info(
            "orchestrator.turn_done",
            trace_id=str(state.trace_id),
            turn_id=next_turn,
            final_agent=final_state.current_agent.value,
            messages=len(final_state.messages),
            handovers=len(final_state.handover_history),
            elapsed_ms=elapsed_ms,
        )
        return final_state

    def get_trace(self, trace_id) -> list[dict[str, Any]]:
        """Read back the audit-log events for a given conversation."""
        return read_trace_events(trace_id)
