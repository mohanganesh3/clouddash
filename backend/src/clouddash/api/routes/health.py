from fastapi import APIRouter
from clouddash.settings import get_settings

router = APIRouter()


@router.get("/health")
async def health():
    cfg = get_settings()
    return {
        "status": "ok",
        "provider": cfg.llm_provider,
        "reasoning_model": cfg.llm_reasoning_model,
        "fast_model": cfg.llm_fast_model,
        "langsmith": cfg.langchain_tracing_v2,
        "reranker": cfg.reranker_type,
    }
