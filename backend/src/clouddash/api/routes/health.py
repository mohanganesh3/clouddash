from fastapi import APIRouter
from clouddash.settings import get_settings

router = APIRouter()


@router.get("/health")
async def health():
    cfg = get_settings()
    reasoning_model = cfg.llm_reasoning_model
    fast_model = cfg.llm_fast_model
    if cfg.llm_provider == "sarvam":
        reasoning_model = cfg.sarvam_reasoning_model
        fast_model = cfg.sarvam_fast_model

    return {
        "status": "ok",
        "provider": cfg.llm_provider,
        "reasoning_model": reasoning_model,
        "fast_model": fast_model,
        "reasoning_effort": cfg.sarvam_reasoning_effort if cfg.llm_provider == "sarvam" else None,
        "langsmith": cfg.langchain_tracing_v2,
        "reranker": cfg.reranker_type,
    }
