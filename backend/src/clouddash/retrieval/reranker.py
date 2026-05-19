"""Reranker — Cohere Rerank v3.5 by default, LLM fallback.

Cohere has way better latency than the LLM reranker approach (200ms vs 4s+).
The LLM reranker was clever but completely unusable for streaming UX.
"""
from __future__ import annotations

from typing import Any

from clouddash.models import RetrievedChunk
from clouddash.settings import get_settings


def rerank(query: str, chunks: list[dict[str, Any]], top_n: int | None = None) -> list[RetrievedChunk]:
    cfg = get_settings()
    k = top_n or cfg.retrieval_top_k_reranked

    if not chunks:
        return []

    if cfg.reranker_type == "cohere":
        return _cohere_rerank(query, chunks, k)
    if cfg.reranker_type == "llm":
        return _llm_rerank(query, chunks, k)
    # none — just return top-k by fused score
    return _no_rerank(chunks, k)


def _cohere_rerank(query: str, chunks: list[dict[str, Any]], k: int) -> list[RetrievedChunk]:
    import cohere
    cfg = get_settings()
    if not cfg.cohere_api_key or "YOUR_" in cfg.cohere_api_key:
        return _no_rerank(chunks, k)
    co = cohere.Client(cfg.cohere_api_key)
    docs = [c["content"] for c in chunks]
    try:
        resp = co.rerank(
            model="rerank-v3.5",
            query=query,
            documents=docs,
            top_n=k,
            return_documents=True,
        )
    except Exception as e:
        # FIXME: Cohere sometimes returns 429 during cold starts. Falling back.
        import structlog
        structlog.get_logger(__name__).warning("cohere_rerank_failed", error=str(e))
        return _no_rerank(chunks, k)

    result = []
    for hit in resp.results:
        c = chunks[hit.index]
        result.append(RetrievedChunk(
            chunk_id=c.get("chunk_id", ""),
            kb_id=c.get("kb_id", ""),
            title=c.get("title", ""),
            category=c.get("category", ""),
            section=c.get("section", 0),
            content=c.get("content", ""),
            rerank_score=hit.relevance_score,
            source=c.get("source", "kb"),
        ))
    return result


def _llm_rerank(query: str, chunks: list[dict[str, Any]], k: int) -> list[RetrievedChunk]:
    """Fallback: use fast LLM to score chunks. Slow but works without Cohere."""
    from clouddash.providers import get_fast_llm
    from clouddash.models import RelevanceScore
    from pydantic import BaseModel

    class RerankOutput(BaseModel):
        scores: list[RelevanceScore]

    llm = get_fast_llm().with_structured_output(RerankOutput)
    candidates = "\n\n".join(
        f"[{i}] {c['content'][:500]}" for i, c in enumerate(chunks)
    )
    prompt = (
        f"Query: {query}\n\nRank these chunks by relevance (0-1):\n\n{candidates}"
    )
    try:
        out: RerankOutput = llm.invoke(prompt)
        scored = sorted(out.scores, key=lambda s: s.score, reverse=True)[:k]
        result = []
        for s in scored:
            try:
                idx = int(s.chunk_id)
                c = chunks[idx]
            except (ValueError, IndexError):
                continue
            result.append(RetrievedChunk(
                chunk_id=c.get("chunk_id", ""),
                kb_id=c.get("kb_id", ""),
                title=c.get("title", ""),
                category=c.get("category", ""),
                section=c.get("section", 0),
                content=c.get("content", ""),
                rerank_score=s.score,
                rerank_rationale=s.rationale,
            ))
        return result
    except Exception:
        return _no_rerank(chunks, k)


def _no_rerank(chunks: list[dict[str, Any]], k: int) -> list[RetrievedChunk]:
    sorted_chunks = sorted(chunks, key=lambda c: c.get("fused_score", 0), reverse=True)[:k]
    return [
        RetrievedChunk(
            chunk_id=c.get("chunk_id", ""),
            kb_id=c.get("kb_id", ""),
            title=c.get("title", ""),
            category=c.get("category", ""),
            section=c.get("section", 0),
            content=c.get("content", ""),
            rerank_score=c.get("fused_score", 0.0),
        )
        for c in sorted_chunks
    ]
