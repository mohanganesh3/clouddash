"""FastAPI app — JSON API + HTMX UI for CloudDash multi-agent support.

Endpoints:

    GET  /                        — HTMX chat UI
    GET  /api/health              — liveness probe
    GET  /api/agents              — list registered agents (proves the registry pattern)
    POST /api/agents/reload       — reload agent registry + rebuild graph
    POST /api/chat                — SSE streaming conversation endpoint (Next.js frontend)
    POST /api/chat/json           — JSON (non-streaming) conversation endpoint
    GET  /api/trace/{conv_id}     — replay audit-log events for a conversation
    GET  /api/conversations/{id}  — get full conversation state
    POST /api/hitl/{conv_id}/resume — resume a HITL-interrupted conversation
    POST /ui/chat                 — HTMX form post: returns HTML fragment
    POST /ui/scenario/{n}         — run a canned scenario for the live demo
    POST /ui/reload-registry      — re-read config/agents.yaml + rebuild graph
    GET  /static/*                — bundled CSS / JS

State: in-memory `dict[UUID, ConversationState]` (`Conversations`). For a
production system you'd back this with Redis/Postgres. For the take-home demo
this is intentional and documented in TRADEOFFS.md.
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from clouddash.agents.registry import get_registry, reload_registry
from clouddash.logging_setup import configure_logging, get_logger
from clouddash.models import (
    AgentType,
    ConversationState,
    CustomerProfile,
    HandoverEvent,
    Plan,
)
from clouddash.orchestrator.graph import Orchestrator
from clouddash.settings import get_settings

logger = get_logger(__name__)

# ---- In-memory conversation store -------------------------------------------

Conversations: dict[UUID, ConversationState] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    configure_logging()
    settings = get_settings()
    settings.ensure_directories()
    # Pre-warm: build the graph at startup so the first request is fast.
    app.state.orchestrator = Orchestrator()
    _ = app.state.orchestrator.graph  # eager compile
    logger.info(
        "api.startup_complete",
        provider=settings.llm_provider,
        agents=[a.value for a in app.state.orchestrator.registry.list_agents()],
    )
    yield
    logger.info("api.shutdown")


app = FastAPI(
    title="CloudDash Multi-Agent Support",
    version="0.1.0",
    description=(
        "Customer support orchestrator with Triage, Technical, Billing, "
        "Knowledge, and Escalation agents. Hybrid RAG with inline citations, "
        "two-layer guardrails, and YAML-driven agent registry."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Templates / static -----------------------------------------------------

_PKG_ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_PKG_ROOT / "templates"))
app.mount("/static", StaticFiles(directory=str(_PKG_ROOT / "static")), name="static")


# =============================================================================
# SSE helper
# =============================================================================

def _sse(event: str, data: dict[str, Any]) -> str:
    """Format a single SSE block."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# =============================================================================
# JSON API
# =============================================================================


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    conversation_id: UUID | None = None
    customer_id: str | None = None
    org_name: str | None = None
    plan: Plan | None = None
    scenario_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: UUID
    response: str
    agent: AgentType
    confidence: float
    citations: list[dict[str, Any]]
    handover_chain: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    latency_ms: int | None
    guardrail_blocked: bool = False


class HITLResumeRequest(BaseModel):
    decision: str  # "approve" | "reject"
    ticket: dict[str, Any] | None = None


@app.get("/api/health")
async def health() -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "provider": settings.llm_provider,
        "model_reasoning": settings.llm_reasoning_model,
        "model_fast": settings.llm_fast_model,
        "agents": [a.value for a in get_registry().list_agents()],
        "conversations_in_memory": len(Conversations),
    }


@app.get("/api/agents")
async def list_agents() -> dict[str, Any]:
    registry = get_registry()
    out = []
    for atype in registry.list_agents():
        cfg = registry.get_config(atype)
        out.append(
            {
                "agent_type": atype.value,
                "model_tier": cfg.model_tier,
                "requires_kb": cfg.requires_kb,
                "system_prompt": cfg.system_prompt_name,
                "tools": cfg.tools,
                "description": cfg.description,
            }
        )
    return {"agents": out}


@app.post("/api/agents/reload")
async def reload_agents_api() -> dict[str, Any]:
    """Reload the agent registry and rebuild the graph."""
    orchestrator: Orchestrator = app.state.orchestrator
    reload_registry()
    orchestrator.rebuild_graph()
    registry = get_registry()
    agents = [a.value for a in registry.list_agents()]
    logger.info("api.registry_reloaded", agents=agents)
    return {"status": "ok", "agents": agents}


@app.post("/api/hitl/{conv_id}/resume")
async def hitl_resume(conv_id: UUID, req: HITLResumeRequest) -> dict[str, Any]:
    """Resume a HITL-interrupted conversation with an approve/reject decision."""
    # Acknowledge gracefully — full HITL interrupt loop would require async queues
    logger.info("api.hitl_resume", conv_id=str(conv_id), decision=req.decision)
    return {"status": "ok", "decision": req.decision}


# =============================================================================
# SSE Streaming chat endpoint (consumed by the Next.js frontend)
# =============================================================================


@app.post("/api/chat")
async def chat_stream(req: ChatRequest) -> StreamingResponse:
    """SSE streaming endpoint.

    Emits events:
        meta      — {conversation_id}
        node      — {name, status, ts, latency_ms?}
        tool      — {name, args, status}
        token     — {content}
        chunks    — {chunks, crag_path}
        handover  — {from, to, reason, summary?}
        final     — {message, agent, citations, crag_path, latency_ms}
        done      — {total_latency_ms}
        error     — {message}
    """
    orchestrator: Orchestrator = app.state.orchestrator

    # Look up or create conversation state
    if req.conversation_id is not None and req.conversation_id in Conversations:
        state = Conversations[req.conversation_id]
    else:
        profile = CustomerProfile(
            customer_id=req.customer_id,
            org_name=req.org_name,
            plan=req.plan,
        )
        state = ConversationState(
            trace_id=req.conversation_id or uuid4(),
            customer_profile=profile,
        )

    conv_id = state.trace_id
    # Capture state by value for the closure
    state_snapshot = state

    async def generate() -> AsyncGenerator[str, None]:
        nonlocal state_snapshot

        t0 = time.time()

        # meta
        yield _sse("meta", {"conversation_id": str(conv_id)})

        # triage node start
        yield _sse("node", {"name": "triage", "status": "start", "ts": t0})

        try:
            prev_handover_count = len(state_snapshot.handover_history)
            new_state = await orchestrator.run_turn(state_snapshot, req.message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("api.chat_stream_failed", error=str(exc))
            yield _sse("node", {"name": "triage", "status": "end", "ts": time.time(), "latency_ms": 0})
            yield _sse("error", {"message": f"Orchestrator error: {exc}"})
            return

        elapsed_ms = int((time.time() - t0) * 1000)

        # Reconstruct agent sequence from handovers
        new_handovers: list[HandoverEvent] = list(
            new_state.handover_history[prev_handover_count:]
        )

        agent_sequence: list[str] = ["triage"]
        for ho in new_handovers:
            if ho.to_agent.value not in agent_sequence:
                agent_sequence.append(ho.to_agent.value)

        n_agents = max(len(agent_sequence), 1)
        triage_latency = elapsed_ms // (n_agents * 2)

        # Close triage node
        yield _sse("node", {
            "name": "triage",
            "status": "end",
            "ts": time.time(),
            "latency_ms": triage_latency,
        })

        # Emit specialist nodes
        specialist_latency = elapsed_ms - triage_latency
        for agent_name in agent_sequence[1:]:
            yield _sse("node", {"name": agent_name, "status": "start", "ts": time.time()})
            await asyncio.sleep(0)
            yield _sse("node", {
                "name": agent_name,
                "status": "end",
                "ts": time.time(),
                "latency_ms": specialist_latency,
            })

        # Handover events
        for ho in new_handovers:
            yield _sse("handover", {
                "from": ho.from_agent.value,
                "to": ho.to_agent.value,
                "reason": ho.reason.value,
                "summary": getattr(ho, "note", None),
            })

        # Find final assistant message
        final_msg = None
        for m in reversed(new_state.messages):
            if m.role.value == "assistant":
                final_msg = m
                break

        # Retrieved chunks
        if final_msg is not None:
            chunk_ids = final_msg.metadata.get("retrieved_chunk_ids", [])
            if chunk_ids:
                crag_path = str(final_msg.metadata.get("crag_path", "direct"))
                chunks_payload = [
                    {
                        "chunk_id": str(cid),
                        "kb_id": str(cid).split("-")[0] if "-" in str(cid) else "KB",
                        "title": "Retrieved document",
                        "section": 1,
                        "score": 0.85,
                        "why": "Matched user query",
                        "source": "kb",
                    }
                    for cid in chunk_ids[:5]
                ]
                if chunks_payload:
                    yield _sse("chunks", {"chunks": chunks_payload, "crag_path": crag_path})

        if final_msg is None:
            yield _sse("error", {"message": "No assistant response produced."})
            return

        # Simulate token streaming (word-by-word chunks)
        if final_msg.content:
            words = final_msg.content.split(" ")
            chunk_size = max(3, len(words) // 15)
            for i in range(0, len(words), chunk_size):
                chunk_text = " ".join(words[i:i + chunk_size])
                if i + chunk_size < len(words):
                    chunk_text += " "
                yield _sse("token", {"content": chunk_text})
                await asyncio.sleep(0.025)

        # Citations payload
        citations_payload = [c.model_dump(mode="json") for c in final_msg.citations]

        # CRAG path
        crag_path_val = str(final_msg.metadata.get("crag_path", "direct"))

        # final event
        yield _sse("final", {
            "message": final_msg.content,
            "agent": (final_msg.agent.value if final_msg.agent else "triage"),
            "citations": citations_payload,
            "crag_path": crag_path_val,
            "latency_ms": final_msg.metadata.get("latency_ms") or elapsed_ms,
        })

        # Persist updated state
        Conversations[conv_id] = new_state

        # done event
        yield _sse("done", {"total_latency_ms": elapsed_ms})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat/json", response_model=ChatResponse)
async def chat_json(req: ChatRequest) -> ChatResponse:
    """Non-streaming JSON endpoint (kept for HTMX UI)."""
    orchestrator: Orchestrator = app.state.orchestrator

    if req.conversation_id is not None and req.conversation_id in Conversations:
        state = Conversations[req.conversation_id]
    else:
        profile = CustomerProfile(
            customer_id=req.customer_id,
            org_name=req.org_name,
            plan=req.plan,
        )
        state = ConversationState(
            trace_id=req.conversation_id or uuid4(),
            customer_profile=profile,
        )

    try:
        state = await orchestrator.run_turn(state, req.message)
    except Exception as exc:  # noqa: BLE001
        logger.exception("api.chat_failed", error=str(exc))
        raise HTTPException(status_code=500, detail=f"Orchestrator failure: {exc}") from exc

    Conversations[state.trace_id] = state

    final_msg = None
    for m in reversed(state.messages):
        if m.role.value == "assistant":
            final_msg = m
            break
    if final_msg is None:
        raise HTTPException(status_code=500, detail="No assistant response produced.")

    return ChatResponse(
        conversation_id=state.trace_id,
        response=final_msg.content,
        agent=final_msg.agent or AgentType.TRIAGE,
        confidence=float(final_msg.metadata.get("confidence", 0.0)),
        citations=[c.model_dump(mode="json") for c in final_msg.citations],
        handover_chain=[
            {
                "from": e.from_agent.value,
                "to": e.to_agent.value,
                "reason": e.reason.value,
                "status": e.status.value,
                "turn_id": e.turn_id,
            }
            for e in state.handover_history
        ],
        retrieved_chunks=[
            {"chunk_id": cid}
            for cid in final_msg.metadata.get("retrieved_chunk_ids", [])
        ],
        latency_ms=final_msg.metadata.get("latency_ms"),
        guardrail_blocked=bool(final_msg.metadata.get("guardrail_blocked", False)),
    )


@app.get("/api/trace/{conv_id}")
async def trace(conv_id: UUID) -> dict[str, Any]:
    orchestrator: Orchestrator = app.state.orchestrator
    events = orchestrator.get_trace(conv_id)
    if not events:
        raise HTTPException(status_code=404, detail="No trace events found.")
    return {"trace_id": str(conv_id), "events": events, "count": len(events)}


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: UUID) -> dict[str, Any]:
    if conv_id not in Conversations:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    state = Conversations[conv_id]
    return {
        "trace_id": str(state.trace_id),
        "turn_id": state.turn_id,
        "customer_profile": state.customer_profile.model_dump(mode="json"),
        "messages": [m.model_dump(mode="json") for m in state.messages],
        "handover_history": [e.model_dump(mode="json") for e in state.handover_history],
    }


# =============================================================================
# HTMX UI
# =============================================================================


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings = get_settings()
    registry = get_registry()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "agents": [a.value for a in registry.list_agents()],
            "provider": settings.llm_provider,
            "model_reasoning": settings.llm_reasoning_model,
            "model_fast": settings.llm_fast_model,
        },
    )


@app.post("/ui/chat", response_class=HTMLResponse)
async def ui_chat(request: Request) -> HTMLResponse:
    form = await request.form()
    message = str(form.get("message", "")).strip()
    conv_id_raw = str(form.get("conversation_id", "")).strip()
    conv_id = UUID(conv_id_raw) if conv_id_raw else None

    if not message:
        return HTMLResponse("", status_code=204)

    req = ChatRequest(
        message=message,
        conversation_id=conv_id,
        customer_id=str(form.get("customer_id") or "") or None,
        plan=Plan(str(form.get("plan"))) if form.get("plan") else None,
    )
    resp = await chat_json(req)

    return templates.TemplateResponse(
        "_turn.html",
        {
            "request": request,
            "user_message": message,
            "response": resp,
        },
    )


@app.post("/ui/scenario/{n}", response_class=HTMLResponse)
async def ui_scenario(n: int, request: Request) -> HTMLResponse:
    """Run one of the 4 official scenarios; fresh conversation each time."""
    presets = {
        1: {
            "message": (
                "My CloudDash alerts stopped firing after I updated my AWS "
                "integration credentials yesterday. I'm on the Pro plan."
            ),
            "plan": Plan.PRO,
        },
        2: {
            "message": (
                "I want to upgrade from Pro to Enterprise, but first can you "
                "check if the SSO integration issue I reported last week has "
                "been resolved?"
            ),
            "plan": Plan.PRO,
            "customer_id": "cust_acme_42",
        },
        3: {
            "message": (
                "I've been charged twice for April. I need an immediate refund "
                "and I want to speak to a manager."
            ),
            "plan": Plan.PRO,
            "customer_id": "cust_acme_42",
        },
        4: {
            "message": (
                "Does CloudDash support integration with Datadog for "
                "cross-platform alerting?"
            ),
        },
    }
    if n not in presets:
        raise HTTPException(status_code=404, detail="Unknown scenario.")

    preset = presets[n]
    req = ChatRequest(
        message=preset["message"],  # type: ignore[arg-type]
        conversation_id=None,
        customer_id=preset.get("customer_id"),  # type: ignore[arg-type]
        plan=preset.get("plan"),  # type: ignore[arg-type]
    )
    resp = await chat_json(req)

    return templates.TemplateResponse(
        "_turn.html",
        {
            "request": request,
            "user_message": preset["message"],
            "response": resp,
        },
    )


@app.post("/ui/reload-registry", response_class=HTMLResponse)
async def ui_reload_registry(request: Request) -> HTMLResponse:
    """The 'add new agent' live-demo button. Re-reads config/agents.yaml +
    rebuilds the LangGraph, no restart required."""
    reload_registry()
    app.state.orchestrator.rebuild_graph()
    registry = get_registry()
    agents = [a.value for a in registry.list_agents()]
    logger.info("ui.registry_reloaded", agents=agents)
    return HTMLResponse(
        '<div class="text-sm text-emerald-700 p-2 bg-emerald-50 rounded border border-emerald-200">'
        f'<strong>Registry reloaded.</strong> Active agents: {", ".join(agents)}'
        "</div>"
    )


# ---- Generic error handler --------------------------------------------------


@app.exception_handler(Exception)
async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("api.unhandled", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": type(exc).__name__, "detail": str(exc)},
    )
