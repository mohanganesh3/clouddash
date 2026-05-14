"""Hybrid retriever — BM25 + dense + RRF fusion + LLM reranker (ADR-003).

Public API: `Retriever.retrieve(query|state) -> list[RetrievedChunk]`.

Pipeline:
    1. Rewrite the query using conversation context (1–3 queries out).
    2. For each rewritten query: dense search (top_k_dense) AND BM25 (top_k_bm25).
    3. Merge all candidate rankings via Reciprocal Rank Fusion (k=60).
    4. Take top_k_fused candidates.
    5. LLM-rerank (Gemini Flash) → top_k_reranked with per-chunk rationale.
    6. Convert to typed RetrievedChunk objects.

Graceful degradation:
    - If LLM rewriter fails → use raw user message.
    - If LLM reranker fails → fall back to RRF top-K.
    - If BM25 index is empty → use dense only.
"""

from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Any

from pydantic import BaseModel, Field

from clouddash.exceptions import RetrievalError
from clouddash.llm import get_llm, load_prompt
from clouddash.logging_setup import get_logger
from clouddash.models import ConversationState, RetrievedChunk
from clouddash.retrieval.bm25 import BM25Index
from clouddash.retrieval.query_rewriter import rewrite_query
from clouddash.retrieval.vector_store import VectorStore
from clouddash.settings import get_settings

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Reciprocal Rank Fusion
# -----------------------------------------------------------------------------


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    *,
    k: int = 60,
) -> dict[str, float]:
    """Fuse multiple ranked lists of chunk_ids into one score map.

    RRF score = sum over rankings of 1 / (k + rank + 1). Robust to score
    incompatibility between BM25 and cosine similarity — no calibration needed.
    """
    fused: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking):
            fused[chunk_id] += 1.0 / (k + rank + 1)
    return dict(fused)


# -----------------------------------------------------------------------------
# LLM reranker
# -----------------------------------------------------------------------------


class _RerankItem(BaseModel):
    chunk_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(..., max_length=300)


class _RerankResult(BaseModel):
    items: list[_RerankItem]


def _llm_rerank(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    top_k: int,
) -> list[dict[str, Any]]:
    """Send candidates to Gemini Flash for fine-grained reranking.

    On failure: return candidates as-is (already ordered by RRF), logging the error.
    """
    if not candidates:
        return []

    # Build the candidates section of the prompt
    candidate_lines = []
    for i, c in enumerate(candidates):
        section_marker = (
            f" § {c.get('section')}" if c.get("section") not in (None, -1) else ""
        )
        candidate_lines.append(
            f"[{i+1}] chunk_id={c['chunk_id']} | "
            f"{c['kb_id']}{section_marker}: {c['title']}\n"
            f"    {c['raw_content'][:600]}"
        )
    candidates_text = "\n\n".join(candidate_lines)

    prompt = load_prompt("reranker").format(
        query=query,
        candidates=candidates_text,
    )

    t0 = time.time()
    try:
        llm = get_llm("fast")
        structured = llm.with_structured_output(_RerankResult)
        result: _RerankResult = structured.invoke(prompt)  # type: ignore[assignment]

        # Map scores back to candidate dicts
        score_map = {item.chunk_id: item for item in result.items}
        for c in candidates:
            item = score_map.get(c["chunk_id"])
            if item is not None:
                c["rerank_score"] = item.score
                c["rerank_rationale"] = item.rationale
            else:
                c["rerank_score"] = 0.0
                c["rerank_rationale"] = "(reranker did not score this chunk)"

        ranked = sorted(candidates, key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        latency_ms = int((time.time() - t0) * 1000)
        logger.info(
            "reranker.success",
            candidates=len(candidates),
            top_chunk=ranked[0]["chunk_id"] if ranked else None,
            top_score=ranked[0].get("rerank_score") if ranked else None,
            latency_ms=latency_ms,
        )
        return ranked[:top_k]

    except Exception as exc:  # noqa: BLE001 — graceful degradation
        logger.warning(
            "reranker.fallback_to_rrf",
            error=str(exc),
            error_type=type(exc).__name__,
            latency_ms=int((time.time() - t0) * 1000),
        )
        # Fall through to RRF order
        for c in candidates[:top_k]:
            c.setdefault("rerank_score", c.get("rrf_score", 0.0))
            c.setdefault("rerank_rationale", "(reranker unavailable; using RRF score)")
        return candidates[:top_k]


# -----------------------------------------------------------------------------
# Retriever
# -----------------------------------------------------------------------------


class Retriever:
    """Owner of the RAG pipeline. Constructed once at app startup."""

    def __init__(self, vector_store: VectorStore | None = None) -> None:
        self.vector_store = vector_store or VectorStore()
        self._bm25: BM25Index | None = None
        self._bm25_lock = Lock()

    def _ensure_bm25(self) -> BM25Index:
        """Build BM25 lazily (on first query) from chunks already in Chroma."""
        if self._bm25 is not None:
            return self._bm25
        with self._bm25_lock:
            if self._bm25 is None:
                chunks = self.vector_store.all_chunks()
                if not chunks:
                    raise RetrievalError(
                        "Vector store is empty — run `make ingest` first.",
                        context={"persist_dir": str(self.vector_store.persist_dir)},
                    )
                self._bm25 = BM25Index(chunks)
        return self._bm25

    def reset_bm25(self) -> None:
        """Force BM25 rebuild on next query (after re-ingest)."""
        with self._bm25_lock:
            self._bm25 = None

    # -------------------------------------------------------------------------

    def retrieve(
        self,
        query: str | None = None,
        *,
        state: ConversationState | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunk]:
        """Run the full hybrid + rerank pipeline. Returns top_k RetrievedChunks."""
        settings = get_settings()
        top_k = top_k or settings.retrieval_top_k_reranked

        # ---- Step 1: rewrite ----
        if state is not None:
            queries = rewrite_query(state, latest_message=query)
        elif query:
            queries = [query]
        else:
            return []

        if not queries:
            return []

        logger.info("retriever.start", queries=queries, top_k=top_k)
        t0 = time.time()

        # ---- Step 2: hybrid search per rewritten query ----
        bm25 = self._ensure_bm25()
        # chunk_id → merged candidate dict (with all scores accumulated)
        candidates: dict[str, dict[str, Any]] = {}
        # rankings to feed RRF
        all_rankings: list[list[str]] = []

        for q in queries:
            dense_hits = self.vector_store.query(q, top_k=settings.retrieval_top_k_dense)
            bm25_hits = bm25.query(q, top_k=settings.retrieval_top_k_bm25)

            for hit in dense_hits:
                cid = hit["chunk_id"]
                cand = candidates.setdefault(cid, dict(hit))
                # keep best dense_score across queries
                cand["dense_score"] = max(cand.get("dense_score") or 0.0, hit["score"])

            for hit in bm25_hits:
                cid = hit["chunk_id"]
                cand = candidates.setdefault(cid, dict(hit))
                cand["bm25_score"] = max(
                    cand.get("bm25_score") or 0.0, hit.get("bm25_score", 0.0)
                )

            if dense_hits:
                all_rankings.append([h["chunk_id"] for h in dense_hits])
            if bm25_hits:
                all_rankings.append([h["chunk_id"] for h in bm25_hits])

        if not candidates:
            logger.info(
                "retriever.no_candidates",
                queries=queries,
                latency_ms=int((time.time() - t0) * 1000),
            )
            return []

        # ---- Step 3: RRF fusion ----
        rrf_scores = reciprocal_rank_fusion(all_rankings)
        for cid, cand in candidates.items():
            cand["rrf_score"] = rrf_scores.get(cid, 0.0)

        # Top top_k_fused by RRF for reranking
        fused = sorted(
            candidates.values(),
            key=lambda c: c.get("rrf_score", 0.0),
            reverse=True,
        )[: settings.retrieval_top_k_fused]

        # ---- Step 4: LLM rerank ----
        # Use the original (non-rewritten) query for reranking — best signal
        rerank_query = query if query else queries[0]
        if settings.reranker_type == "llm":
            reranked = _llm_rerank(rerank_query, fused, top_k=top_k)
        else:
            # No reranker: take top by RRF
            reranked = fused[:top_k]
            for c in reranked:
                c.setdefault("rerank_score", c.get("rrf_score", 0.0))
                c.setdefault("rerank_rationale", "(reranker disabled)")

        # ---- Step 5: convert to typed RetrievedChunks ----
        result = [
            RetrievedChunk(
                chunk_id=c["chunk_id"],
                kb_id=c["kb_id"],
                title=c["title"],
                category=c["category"],
                section=c.get("section"),
                content=c["raw_content"],
                bm25_score=c.get("bm25_score"),
                dense_score=c.get("dense_score"),
                rrf_score=c.get("rrf_score"),
                rerank_score=c.get("rerank_score"),
                rerank_rationale=c.get("rerank_rationale"),
                metadata={
                    "section_title": c.get("section_title"),
                    "tags": c.get("tags", []),
                    "applies_to": c.get("applies_to", []),
                },
            )
            for c in reranked
        ]

        logger.info(
            "retriever.done",
            n_returned=len(result),
            top_chunk=result[0].chunk_id if result else None,
            top_score=result[0].composite_score if result else None,
            total_latency_ms=int((time.time() - t0) * 1000),
        )
        return result
