from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any

router = APIRouter()


class HITLResumeRequest(BaseModel):
    decision: str  # "approve" | "edit" | "reject"
    ticket: dict[str, Any] | None = None


@router.post("/hitl/{conversation_id}/resume")
async def resume_hitl(conversation_id: str, req: HITLResumeRequest):
    from clouddash.orchestrator.graph import aget_orchestrator
    orch = await aget_orchestrator()

    payload = req.decision
    if req.decision == "edit" and req.ticket:
        payload = {"decision": "approve", "ticket": req.ticket}

    try:
        state = await orch.resume_hitl(conversation_id, payload)
        last_response = state.get("last_response") if isinstance(state, dict) else None
        if isinstance(last_response, dict):
            message = last_response.get("response_text", "")
            agent = last_response.get("agent", "escalation")
            latency_ms = last_response.get("latency_ms", 0)
        else:
            message = getattr(last_response, "response_text", "")
            agent_obj = getattr(last_response, "agent", None)
            agent = getattr(agent_obj, "value", agent_obj) or "escalation"
            latency_ms = getattr(last_response, "latency_ms", 0)

        return {
            "status": "resumed",
            "conversation_id": conversation_id,
            "message": message,
            "agent": agent,
            "latency_ms": latency_ms,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
