"""Main orchestrator graph.

Builds the LangGraph StateGraph from the agent registry.
Adding a new agent = YAML entry + one file. Nothing here changes.

Key LangGraph features used:
- SqliteSaver checkpointing — conversations persist across requests (thread_id = convo_id)
- interrupt() in EscalationAgent — graph pauses, frontend shows HITL dialog, resumes via Command
- Conditional edges — driven by agent LLM output, not hardcoded strings
- sub-graph composition — CRAG is a sub-graph called from within agent nodes
- astream_events() for SSE streaming — every token + node event emitted to frontend

May 16: LangGraph's checkpointer expects thread_id in config['configurable']['thread_id'],
NOT in state. Spent an hour debugging why memory wasn't persisting across requests.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from clouddash.agents.registry import AgentRegistry, get_registry
from clouddash.guardrails import build_blocked_response, evaluate_input, evaluate_output
from clouddash.logging_setup import get_logger, set_trace_context, write_audit_event
from clouddash.models import AgentResponse, AgentType, CustomerProfile, GraphState, IntentCategory, IntentClassification, Plan, make_initial_state
from clouddash.multilingual.sarvam_detect import detect_language
from clouddash.settings import get_settings

logger = get_logger(__name__)


class Orchestrator:
    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or get_registry()
        cfg = get_settings()
        cfg.ensure_dirs()
        self._checkpoint_conn = None
        self._checkpointer = self._build_checkpointer(cfg.graph_checkpoint_path)
        self._graph = self._build()

    def _build_checkpointer(self, path: str):
        """Use async SQLite under FastAPI; keep sync construction usable for smoke tests."""
        try:
            import asyncio
            asyncio.get_running_loop()
        except RuntimeError:
            self._checkpoint_conn = sqlite3.connect(path, check_same_thread=False)
            checkpointer = SqliteSaver(self._checkpoint_conn)
            checkpointer.setup()
            return checkpointer

        import aiosqlite
        self._checkpoint_conn = aiosqlite.connect(path)
        return AsyncSqliteSaver(self._checkpoint_conn)

    def _build(self):
        g = StateGraph(GraphState)

        # language detection node — first thing that runs for new conversations
        g.add_node("language_detect", self._language_detect_node)

        # triage always runs after language detection
        g.add_node("triage", self._make_agent_node(AgentType.TRIAGE))

        # specialist nodes
        for atype in [AgentType.TECHNICAL, AgentType.BILLING, AgentType.KNOWLEDGE, AgentType.ESCALATION]:
            if atype in self.registry.list_agents():
                g.add_node(atype.value, self._make_agent_node(atype))

        # guardrails wrapper node — runs after each specialist
        g.add_node("output_guard", self._output_guard_node)

        g.add_edge(START, "language_detect")
        g.add_edge("language_detect", "triage")

        # triage routes to specialist
        g.add_conditional_edges("triage", self._route_from_triage, {
            "technical": "technical",
            "billing": "billing",
            "knowledge": "knowledge",
            "escalation": "escalation",
            END: END,
        })

        # each specialist → output guard
        for atype in [AgentType.TECHNICAL, AgentType.BILLING, AgentType.KNOWLEDGE]:
            if atype.value in [n for n in g.nodes]:
                g.add_edge(atype.value, "output_guard")

        # escalation goes straight to END (interrupt handles the pause/resume)
        g.add_edge("escalation", END)

        # after guard: either done or hand to another specialist
        g.add_conditional_edges("output_guard", self._route_after_guard, {
            "technical": "technical",
            "billing": "billing",
            "knowledge": "knowledge",
            "escalation": "escalation",
            END: END,
        })

        return g.compile(checkpointer=self._checkpointer)

    async def _language_detect_node(self, state: GraphState) -> dict:
        # only run on turn 1 — don't re-detect every message
        if state.get("greeting_sent") or state.get("turn_id", 0) > 1:
            return {}

        msgs = state.get("messages", [])
        if not msgs:
            return {}

        last = msgs[-1]
        text = last.content if hasattr(last, "content") else ""
        if not text:
            return {}

        detection = await detect_language(text)
        update: dict = {"language_detection": detection}

        if detection.is_indian_language and detection.greeting and not state.get("greeting_sent"):
            update["messages"] = [AIMessage(content=detection.greeting, name="system")]
            update["greeting_sent"] = True

        return update

    def _make_agent_node(self, atype: AgentType):
        async def node(state: GraphState) -> dict:
            set_trace_context(
                trace_id=state.get("trace_id", ""),
                turn_id=state.get("turn_id", 0),
                agent=atype.value,
            )
            agent = self.registry.get(atype)
            t0 = time.time()
            try:
                response: AgentResponse = await agent.handle(state)
            except GraphInterrupt:
                raise
            except Exception as exc:
                logger.exception("agent_node_failed", agent=atype.value, error=str(exc))
                fallback = self.registry.next_fallback(atype, tried={atype})
                return {
                    "current_agent": atype,
                    "last_response": AgentResponse(
                        agent=atype,
                        next_agent=fallback,
                        confidence=0.1,
                        metadata={"error": str(exc)},
                    ),
                    "next_route": fallback.value if fallback else "",
                }

            latency = int((time.time() - t0) * 1000)
            response.latency_ms = latency

            write_audit_event(
                "agent.completed",
                agent=atype.value,
                latency_ms=latency,
                next_agent=response.next_agent.value if response.next_agent else None,
                has_handover=response.handover_packet is not None,
            )

            update: dict[str, Any] = {
                "current_agent": atype,
                "last_response": response,
                "retrieved_chunks": response.retrieved_chunks,
                "crag_path": response.crag_path,
            }

            if atype == AgentType.TRIAGE:
                update.update(self._triage_context_update(state, response))

            if response.response_text:
                update["messages"] = [AIMessage(
                    content=response.response_text,
                    name=atype.value,
                    additional_kwargs={
                        "citations": [c.model_dump() for c in response.citations],
                        "agent": atype.value,
                        "latency_ms": latency,
                        "crag_path": response.crag_path.value if response.crag_path else None,
                    },
                )]

            # store routing as a simple string — checkpoint serializers can turn Pydantic
            # models to dicts, so reading resp.next_agent after checkpointing fails.
            # Use empty string for "no handover" — LangGraph may drop None updates
            update["next_route"] = response.next_agent.value if response.next_agent else ""

            if response.handover_packet:
                update["pending_handover"] = response.handover_packet
                hchain = list(state.get("handover_chain") or [])
                hchain.append(response.handover_packet)
                update["handover_chain"] = hchain
                write_audit_event(
                    "handover.emitted",
                    from_agent=atype.value,
                    to_agent=response.next_agent.value if response.next_agent else None,
                    reason=response.handover_packet.reason.value,
                )

            return update

        node.__name__ = f"node_{atype.value}"
        return node

    def _triage_context_update(self, state: GraphState, response: AgentResponse) -> dict[str, Any]:
        metadata = response.metadata or {}
        entities = metadata.get("entities") or {}
        update: dict[str, Any] = {}

        intent = metadata.get("intent")
        if intent in IntentCategory._value2member_map_:
            update["intent"] = IntentCategory(intent)

        classification = metadata.get("classification")
        if classification:
            update["intent_classification"] = IntentClassification(**classification)

        existing = state.get("customer_profile") or CustomerProfile()
        profile_data = existing.model_dump() if hasattr(existing, "model_dump") else dict(existing)

        if customer_id := entities.get("customer_id"):
            profile_data["customer_id"] = str(customer_id)
        if org_name := entities.get("org_name"):
            profile_data["org_name"] = str(org_name)
        if plan := entities.get("plan"):
            plan_value = str(plan).lower()
            if plan_value in Plan._value2member_map_:
                profile_data["plan"] = Plan(plan_value)

        update["customer_profile"] = CustomerProfile(**profile_data)
        return update

    async def _output_guard_node(self, state: GraphState) -> dict:
        resp = state.get("last_response")
        if not resp:
            return {}
        # checkpoint serializers may deserialize to dict — handle both cases
        text = resp.response_text if hasattr(resp, "response_text") else (resp.get("response_text") if isinstance(resp, dict) else "")
        chunks = resp.retrieved_chunks if hasattr(resp, "retrieved_chunks") else (resp.get("retrieved_chunks") or [])
        if not text:
            return {}

        decision = evaluate_output(text, chunks)
        if decision.action == "self_correct":
            write_audit_event("guardrail.self_correct", failures=decision.failures)
            logger.warning("output_guard.correction_needed", failures=decision.failures)

        if hasattr(resp, "next_agent"):
            has_handover = resp.next_agent is not None
        elif isinstance(resp, dict):
            has_handover = bool(resp.get("next_agent") or resp.get("handover_packet"))
        else:
            has_handover = False

        # Terminal responses must not re-dispatch; handovers must preserve next_route.
        return {} if has_handover else {"next_route": ""}

    def _route_from_triage(self, state: GraphState) -> str:
        route = state.get("next_route")
        return route if route else END

    def _route_after_guard(self, state: GraphState) -> str:
        route = state.get("next_route") or ""
        # allow specialist-to-specialist handovers (not back to triage)
        valid = {"technical", "billing", "knowledge", "escalation"}
        return route if route in valid else END

    def _make_config(self, conversation_id: str) -> dict:
        # thread_id in configurable — this is what the checkpointer keys on
        return {"configurable": {"thread_id": conversation_id}}

    async def run_turn(self, conversation_id: str, user_message: str) -> GraphState:
        config = self._make_config(conversation_id)

        # input guardrails before anything touches an LLM
        decision = evaluate_input(user_message)
        if not decision.is_allowed:
            blocked_msg = build_blocked_response(decision)
            # still update the graph state so conversation history is preserved
            current = await self._graph.aget_state(config)
            input_state = make_initial_state(conversation_id) if not current.values else {}
            input_state.update({"messages": [HumanMessage(content=user_message)], "turn_id": 1})
            await self._graph.ainvoke(
                input_state,
                config=config,
            )
            return {"__blocked__": True, "__blocked_msg__": blocked_msg}  # type: ignore

        sanitized = decision.sanitized_text
        current = await self._graph.aget_state(config)
        turn = (current.values.get("turn_id", 0) if current.values else 0) + 1
        input_state = make_initial_state(conversation_id) if not current.values else {}
        input_state.update({"messages": [HumanMessage(content=sanitized)], "turn_id": turn})

        result = await self._graph.ainvoke(
            input_state,
            config=config,
        )
        return result

    async def stream_turn(self, conversation_id: str, user_message: str):
        """Yield astream_events for SSE endpoint. Each event maps to a frontend update."""
        config = self._make_config(conversation_id)
        decision = evaluate_input(user_message)
        if not decision.is_allowed:
            yield {"event": "blocked", "data": {"message": build_blocked_response(decision)}}
            return

        sanitized = decision.sanitized_text
        current = await self._graph.aget_state(config)
        turn = (current.values.get("turn_id", 0) if current.values else 0) + 1
        input_state = make_initial_state(conversation_id) if not current.values else {}
        input_state.update({"messages": [HumanMessage(content=sanitized)], "turn_id": turn})

        async for event in self._graph.astream_events(
            input_state,
            config=config,
            version="v2",
        ):
            yield event

    async def resume_hitl(self, conversation_id: str, decision: Any) -> GraphState:
        """Resume a graph that was paused at interrupt() in EscalationAgent."""
        config = self._make_config(conversation_id)
        result = await self._graph.ainvoke(Command(resume=decision), config=config)
        return result

    async def get_state(self, conversation_id: str) -> dict:
        config = self._make_config(conversation_id)
        state = await self._graph.aget_state(config)
        return state.values if state.values else {}

    def rebuild(self) -> None:
        self.registry.reload()
        self._graph = self._build()


_ORCHESTRATOR: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = Orchestrator()
    return _ORCHESTRATOR
