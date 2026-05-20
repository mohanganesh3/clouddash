from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from clouddash.logging_setup import setup_logging
from clouddash.settings import get_settings


def _reload_bm25() -> None:
    """Pull all docs from ChromaDB and rebuild the BM25 index. Takes ~1s, worth it."""
    try:
        from clouddash.retrieval.vector_store import get_vector_store
        from clouddash.retrieval.bm25_store import build_index
        store = get_vector_store()
        result = store.get(include=["documents", "metadatas"])
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []
        if not docs:
            return
        chunks = []
        for doc, meta in zip(docs, metas):
            chunks.append({
                "content": doc,
                "chunk_id": (meta or {}).get("chunk_id", ""),
                "kb_id": (meta or {}).get("kb_id", ""),
                "title": (meta or {}).get("title", ""),
                "category": (meta or {}).get("category", ""),
                "section": (meta or {}).get("section", 0),
            })
        build_index(chunks)
    except Exception as e:
        import structlog
        structlog.get_logger(__name__).warning("bm25_reload_failed", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    cfg.ensure_dirs()
    setup_logging(cfg.log_level, cfg.audit_log_path)

    # set LangSmith env vars before any LangChain imports touch them
    if cfg.langchain_tracing_v2 and cfg.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = cfg.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = cfg.langchain_project
        os.environ["LANGCHAIN_ENDPOINT"] = cfg.langchain_endpoint

    async def warmup() -> None:
        # Keep Render health checks fast: open the port first, then warm retrieval/graph.
        await asyncio.to_thread(_reload_bm25)
        from clouddash.orchestrator.graph import get_orchestrator
        await asyncio.to_thread(get_orchestrator)

    task = asyncio.create_task(warmup())
    try:
        yield
    finally:
        if not task.done():
            task.cancel()


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(
        title="CloudDash Support API",
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs" if not cfg.is_production else None,
    )

    # CORS — allow Vercel previews and localhost
    origins = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3003",
        "http://localhost:3010",
        "http://localhost:3020",
        "http://127.0.0.1:3003",
        "http://127.0.0.1:3020",
        "http://10.36.190.67:3010",
        "https://*.vercel.app",
        "https://*.onrender.com",
    ]
    frontend_url = os.environ.get("FRONTEND_URL", "")
    if frontend_url:
        origins.append(frontend_url)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=r"https://.*\.(vercel\.app|onrender\.com)",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", include_in_schema=False)
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

    from clouddash.api.routes import agents, chat, health, hitl, trace
    app.include_router(health.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(trace.router, prefix="/api")
    app.include_router(agents.router, prefix="/api")
    app.include_router(hitl.router, prefix="/api")

    return app


app = create_app()
