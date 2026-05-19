from fastapi import APIRouter
from clouddash.logging_setup import read_trace_events

router = APIRouter()


@router.get("/trace/{trace_id}")
async def get_trace(trace_id: str):
    events = read_trace_events(trace_id)
    return {"trace_id": trace_id, "events": events, "count": len(events)}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    from clouddash.orchestrator.graph import get_orchestrator
    state = await get_orchestrator().get_state(conversation_id)
    if not state:
        return {"conversation_id": conversation_id, "messages": [], "turn_id": 0}
    msgs = state.get("messages", [])
    return {
        "conversation_id": conversation_id,
        "turn_id": state.get("turn_id", 0),
        "current_agent": state.get("current_agent", {}).value if state.get("current_agent") else None,
        "messages": [
            {
                "role": "user" if m.__class__.__name__ == "HumanMessage" else "assistant",
                "content": m.content,
                "agent": getattr(m, "name", None),
                "additional": getattr(m, "additional_kwargs", {}),
            }
            for m in msgs
        ],
        "handover_chain": [
            {
                "from": h.from_agent.value,
                "to": h.to_agent.value,
                "reason": h.reason.value,
                "ts": h.timestamp.isoformat(),
            }
            for h in state.get("handover_chain", [])
        ],
    }
