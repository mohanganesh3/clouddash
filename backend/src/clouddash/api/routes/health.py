import os

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from clouddash.settings import get_settings

router = APIRouter()


@router.get("/")
async def root():
    frontend_url = os.environ.get("FRONTEND_URL", "").strip()
    if frontend_url:
        return RedirectResponse(frontend_url)
    return {
        "service": "CloudDash Support API",
        "status": "ok",
        "frontend": "Deploy the Next.js app from /frontend and set FRONTEND_URL to its URL.",
        "health": "/api/health",
    }


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
