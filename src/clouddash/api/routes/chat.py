"""Chat endpoint with SSE streaming.

POST /api/chat returns a text/event-stream response.
Each line is: `event: <type>\ndata: <json>\n\n`

Event types emitted:
  meta      — conversation_id, trace_id (first event always)
  node      — {name, status: start|end, ts}
  tool      — {name, args}
  token     — {content, agent} — one per LLM token
  chunks    — retrieved KB chunks with rerank scores
  handover  — {from, to, reason}
  interrupt — {ticket_draft} — HITL pause
  final     — {message, citations, agent, crag_path, latency_ms}
  done      — {total_latency_ms}
  error     — {message}
"""
from __future__ import annotations

import json
import time
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langgraph.errors import GraphInterrupt
from pydantic import BaseModel

from clouddash.logging_setup import get_logger

router = APIRouter()
logger = get_logger(__name__)


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    scenario_id: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


PHASE_LABELS = {
    "language_detect": "Detecting customer language",
    "triage": "Classifying intent, urgency, and sentiment",
    "technical": "Running technical support specialist",
    "billing": "Checking billing policy and account context",
    "knowledge": "Grounding answer in product knowledge",
    "escalation": "Preparing human handoff package",
    "rewrite": "Rewriting query with conversation context",
    "parallel_retrieve": "Searching dense and BM25 indexes",
    "fuse": "Fusing retrieval candidates with RRF",
    "rerank": "Re-ranking evidence",
    "relevance_eval": "Evaluating grounding confidence",
    "supplement": "Supplementing weak retrieval",
    "web_fallback": "Checking web fallback path",
    "output_guard": "Validating grounded final answer",
}

SPECIALIST_NODES = {"technical", "billing", "knowledge", "escalation"}


def _phase_payload(name: str, status: str) -> dict | None:
    label = PHASE_LABELS.get(name)
    if not label:
        return None
    return {"name": name, "label": label, "status": status, "ts": time.time()}


def _as_dict(value) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {}


def _response_payload(raw_resp, agent_name: str) -> dict:
    if isinstance(raw_resp, dict):
        resp_text = raw_resp.get("response_text", "")
        resp_chunks = raw_resp.get("retrieved_chunks", [])
        resp_crag = raw_resp.get("crag_path")
        resp_citations = raw_resp.get("citations", [])
        resp_latency = raw_resp.get("latency_ms", 0)
        resp_handover = raw_resp.get("handover_packet")
    else:
        resp_text = getattr(raw_resp, "response_text", "")
        resp_chunks = getattr(raw_resp, "retrieved_chunks", [])
        resp_crag = getattr(raw_resp, "crag_path", None)
        resp_citations = getattr(raw_resp, "citations", [])
        resp_latency = getattr(raw_resp, "latency_ms", 0)
        resp_handover = getattr(raw_resp, "handover_packet", None)

    crag_val = resp_crag.value if hasattr(resp_crag, "value") else (resp_crag or "direct")
    return {
        "message": resp_text,
        "chunks": resp_chunks,
        "crag_path": crag_val,
        "citations": resp_citations,
        "latency_ms": resp_latency,
        "handover": resp_handover,
        "agent": agent_name,
    }


def _chunk_payload(chunk) -> dict:
    if isinstance(chunk, dict):
        return {
            "chunk_id": chunk.get("chunk_id", ""),
            "kb_id": chunk.get("kb_id", ""),
            "title": chunk.get("title", ""),
            "section": chunk.get("section", 0),
            "score": chunk.get("rerank_score", 0),
            "why": chunk.get("rerank_rationale", ""),
            "source": chunk.get("source", "kb"),
            "url": (chunk.get("metadata") or {}).get("url", ""),
        }
    return {
        "chunk_id": chunk.chunk_id,
        "kb_id": chunk.kb_id,
        "title": chunk.title,
        "section": chunk.section,
        "score": chunk.rerank_score,
        "why": chunk.rerank_rationale,
        "source": chunk.source,
        "url": chunk.metadata.get("url", ""),
    }


def _handover_payload(handover) -> dict:
    if isinstance(handover, dict):
        return {
            "from": handover.get("from_agent", ""),
            "to": handover.get("to_agent", ""),
            "reason": handover.get("reason", ""),
            "summary": (handover.get("conversation_summary", "") or "")[:200],
        }
    return {
        "from": handover.from_agent.value,
        "to": handover.to_agent.value,
        "reason": handover.reason.value,
        "summary": handover.conversation_summary[:200],
    }


def _citation_payload(citation) -> dict:
    return citation if isinstance(citation, dict) else citation.model_dump()


def _find_interrupt_payload(value) -> dict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if "ticket_draft" in value:
            return value
        for item in value.values():
            found = _find_interrupt_payload(item)
            if found:
                return found
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _find_interrupt_payload(item)
            if found:
                return found
    if hasattr(value, "value"):
        return _find_interrupt_payload(value.value)
    return None


def _answer_deltas(text: str):
    """Small word-group chunks: readable streaming without raw structured JSON."""
    if not text:
        return
    parts = text.replace("\r\n", "\n").split(" ")
    buf: list[str] = []
    for part in parts:
        buf.append(part)
        if len(buf) >= 4 or "\n" in part:
            yield " ".join(buf) + " "
            buf = []
    if buf:
        yield " ".join(buf)


async def _stream_generator(
    conversation_id: str,
    message: str,
) -> AsyncGenerator[str, None]:
    from clouddash.orchestrator.graph import aget_orchestrator

    orch = await aget_orchestrator()
    t0 = time.time()

    yield _sse("meta", {"conversation_id": conversation_id})
    yield _sse("phase", {"name": "input_guard", "label": "Checking input guardrails", "status": "start", "ts": time.time()})
    yield _sse("phase", {"name": "input_guard", "label": "Checking input guardrails", "status": "end", "ts": time.time()})

    try:
        async for event in orch.stream_turn(conversation_id, message):
            etype = event.get("event", "")
            data = event.get("data", {})
            name = event.get("name", "")

            if etype == "blocked":
                yield _sse("error", {"message": data.get("message", "blocked")})
                return

            # node lifecycle
            if etype == "on_chain_start" and name not in ("", "LangGraph"):
                yield _sse("node", {"name": name, "status": "start", "ts": time.time()})
                phase = _phase_payload(name, "start")
                if phase:
                    yield _sse("phase", phase)
                # HITL interrupt detection
                if "interrupt" in str(data).lower():
                    int_data = data.get("input", {})
                    if isinstance(int_data, dict) and "ticket_draft" in int_data:
                        yield _sse("interrupt", int_data)

            elif etype == "on_chain_end" and name not in ("", "LangGraph"):
                yield _sse("node", {"name": name, "status": "end", "ts": time.time()})
                phase = _phase_payload(name, "end")
                if phase:
                    yield _sse("phase", phase)

                # extract final response + chunks from specialist node completions
                if name in SPECIALIST_NODES:
                    output = data.get("output", {}) or {}
                    # output is the state update dict returned by the node
                    raw_resp = output.get("last_response")
                    if raw_resp is not None:
                        payload = _response_payload(raw_resp, name)
                        resp_text = payload["message"]
                        resp_chunks = payload["chunks"]
                        resp_crag_val = payload["crag_path"]
                        resp_citations = payload["citations"]
                        resp_latency = payload["latency_ms"]
                        resp_handover = payload["handover"]

                        # emit chunks
                        if resp_chunks:
                            chunks_data = [_chunk_payload(c) for c in resp_chunks]
                            yield _sse("chunks", {"chunks": chunks_data, "crag_path": resp_crag_val})

                        # emit handover
                        if resp_handover:
                            yield _sse("handover", _handover_payload(resp_handover))

                        # emit final response
                        if resp_text:
                            citations_out = [_citation_payload(c) for c in resp_citations]
                            yield _sse("answer_start", {"agent": name})
                            for delta in _answer_deltas(resp_text):
                                yield _sse("token", {"content": delta, "agent": name, "kind": "answer"})
                            yield _sse("final", {"message": resp_text, "citations": citations_out, "agent": name, "crag_path": resp_crag_val, "latency_ms": resp_latency})

            # Do not forward structured-output JSON fragments as answer text.
            # The UI receives phase events for live thinking and answer deltas
            # after the specialist has produced a validated response.
            elif etype == "on_chat_model_stream":
                continue

            # tool calls
            elif etype == "on_chain_stream":
                interrupt_payload = _find_interrupt_payload(data)
                if interrupt_payload:
                    yield _sse("interrupt", interrupt_payload)

            # tool calls
            elif etype == "on_tool_start":
                yield _sse("tool", {"name": name, "args": _as_dict(data.get("input", {})), "status": "start"})
                yield _sse("phase", {"name": f"tool:{name}", "label": f"Calling tool: {name}", "status": "start", "ts": time.time()})
            elif etype == "on_tool_end":
                yield _sse("tool", {"name": name, "status": "end"})
                yield _sse("phase", {"name": f"tool:{name}", "label": f"Calling tool: {name}", "status": "end", "ts": time.time()})

    except GraphInterrupt as exc:
        interrupt_payload = _find_interrupt_payload(exc.args)
        if interrupt_payload:
            yield _sse("interrupt", interrupt_payload)
    except Exception as exc:
        import traceback
        print(f"[stream_failed] {conversation_id}: {exc}\n{traceback.format_exc()}", flush=True)
        yield _sse("error", {"message": "something went wrong, please try again"})

    yield _sse("done", {"total_latency_ms": int((time.time() - t0) * 1000)})


@router.post("/chat")
async def chat(req: ChatRequest):
    conversation_id = req.conversation_id or str(uuid.uuid4())
    return StreamingResponse(
        _stream_generator(conversation_id, req.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx buffering kills SSE
            "Connection": "keep-alive",
        },
    )
