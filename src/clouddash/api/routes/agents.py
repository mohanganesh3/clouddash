from fastapi import APIRouter
router = APIRouter()


@router.get("/agents")
async def list_agents():
    from clouddash.agents.registry import get_registry
    reg = get_registry()
    return {
        "agents": [
            {
                "type": a.value,
                "description": reg.get_config(a).description,
                "model_tier": reg.get_config(a).model_tier,
                "requires_kb": reg.get_config(a).requires_kb,
                "tools": reg.get_config(a).tools,
            }
            for a in reg.list_agents()
        ]
    }


@router.post("/agents/reload")
async def reload_agents():
    from clouddash.orchestrator.graph import get_orchestrator
    get_orchestrator().rebuild()
    return {"status": "reloaded"}
