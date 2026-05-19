"""CRAG — Corrective RAG as a LangGraph sub-graph.

The retrieval pipeline is a first-class graph, not a function call.
That means it shows up in LangSmith traces with its own node timeline,
and I can checkpoint retrieval state independently from the agent state.

Flow:
  rewrite → [bm25 || dense] (parallel) → fuse → rerank → eval → branch:
    confidence > 0.7  →  done (DIRECT)
    0.3–0.7           →  broader query → retrieve again → merge → done (SUPPLEMENT)
    < 0.3             →  Tavily web search → done (WEB_FALLBACK)

The subgraph input/output is a simple TypedDict that the parent graph
reads from state["retrieved_chunks"] and state["crag_path"].

XXX: the relevance evaluator prompt is sensitive to chunk ordering.
The reranker partially handles this but not always — worth investigating.
"""
from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel
from typing_extensions import TypedDict

from clouddash.models import CRAGPath, CRAGEvalResult, RetrievedChunk
from clouddash.retrieval import bm25_store, vector_store
from clouddash.retrieval.reranker import rerank
from clouddash.settings import get_settings


# sub-graph state — isolated from parent graph state
class CRAGState(TypedDict):
    query: str
    history_context: str  # last 2 turns summarized, for query rewriting
    rewritten_queries: list[str]
    bm25_results: list[dict[str, Any]]
    dense_results: list[dict[str, Any]]
    fused_chunks: list[dict[str, Any]]
    reranked_chunks: list[RetrievedChunk]
    eval_result: CRAGEvalResult | None
    final_chunks: list[RetrievedChunk]
    crag_path: CRAGPath
    retry_count: int


class _QueryRewriteOutput(BaseModel):
    queries: list[str]  # 1-3 standalone queries


class _RelevanceEvalOutput(BaseModel):
    overall_confidence: float
    reasoning: str


def _rewrite_node(state: CRAGState) -> dict:
    from clouddash.providers import get_fast_llm

    llm = get_fast_llm().with_structured_output(_QueryRewriteOutput)
    prompt = (
        f"Conversation context: {state['history_context']}\n\n"
        f"Latest query: {state['query']}\n\n"
        "Rewrite as 1-3 standalone search queries for a cloud monitoring KB. "
        "Resolve pronouns, be specific (e.g. 'AWS CloudWatch', not 'it'). "
        "Return just the queries, no explanation."
    )
    try:
        out: _QueryRewriteOutput = llm.invoke(prompt)
        queries = [q.strip() for q in out.queries if q.strip()][:3]
    except Exception:
        queries = [state["query"]]  # fallback: use original

    return {"rewritten_queries": queries or [state["query"]]}


async def _parallel_retrieve_node(state: CRAGState) -> dict:
    cfg = get_settings()
    queries = state["rewritten_queries"]
    # use the first query for retrieval (multi-query merge adds latency, revisit later)
    q = queries[0]

    bm25_res, dense_res = await asyncio.gather(
        asyncio.to_thread(bm25_store.search, q, cfg.retrieval_top_k_bm25),
        asyncio.to_thread(vector_store.similarity_search, q, cfg.retrieval_top_k_dense),
    )
    return {"bm25_results": bm25_res, "dense_results": dense_res}


def _fuse_node(state: CRAGState) -> dict:
    """RRF fusion. k=60 is the standard; higher k flattens the top-rank advantage."""
    K = 60
    scores: dict[str, float] = {}
    chunk_map: dict[str, dict] = {}

    for rank, chunk in enumerate(state["bm25_results"]):
        cid = chunk["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (K + rank + 1)
        chunk_map[cid] = chunk

    for rank, chunk in enumerate(state["dense_results"]):
        cid = chunk["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (K + rank + 1)
        chunk_map.setdefault(cid, chunk)

    fused = sorted(
        [{"fused_score": s, **chunk_map[cid]} for cid, s in scores.items()],
        key=lambda c: c["fused_score"],
        reverse=True,
    )
    return {"fused_chunks": fused}


def _rerank_node(state: CRAGState) -> dict:
    cfg = get_settings()
    q = state["rewritten_queries"][0]
    chunks = state["fused_chunks"][: cfg.retrieval_top_k_fused]
    reranked = rerank(q, chunks, top_n=cfg.retrieval_top_k_reranked + 5)
    return {"reranked_chunks": reranked}


def _relevance_eval_node(state: CRAGState) -> dict:
    """LLM-based relevance evaluation. Not a heuristic — needs semantic understanding."""
    from clouddash.providers import get_fast_llm

    chunks = state["reranked_chunks"]
    if not chunks:
        return {
            "eval_result": CRAGEvalResult(
                overall_confidence=0.0,
                path=CRAGPath.WEB_FALLBACK,
            )
        }

    llm = get_fast_llm().with_structured_output(_RelevanceEvalOutput)
    chunk_text = "\n\n".join(
        f"[{c.kb_id}] {c.content[:300]}" for c in chunks[:5]
    )
    prompt = (
        f"Query: {state['query']}\n\n"
        f"Retrieved chunks:\n{chunk_text}\n\n"
        "Score 0.0–1.0: how well do these chunks answer the query? "
        ">0.7 = directly answers; 0.3–0.7 = partially relevant; <0.3 = off-topic. "
        "Return overall_confidence and one sentence reasoning."
    )
    try:
        out: _RelevanceEvalOutput = llm.invoke(prompt)
        conf = max(0.0, min(1.0, out.overall_confidence))
    except Exception:
        # if evaluator fails, assume mid-confidence — better than nothing
        conf = 0.5
        out = _RelevanceEvalOutput(overall_confidence=conf, reasoning="evaluator failed")

    if conf > 0.7:
        path = CRAGPath.DIRECT
    elif conf > 0.3:
        path = CRAGPath.SUPPLEMENT
    else:
        path = CRAGPath.WEB_FALLBACK

    return {
        "eval_result": CRAGEvalResult(
            overall_confidence=conf,
            path=path,
        )
    }


def _route_after_eval(state: CRAGState) -> str:
    ev = state.get("eval_result")
    if ev is None or ev.path == CRAGPath.WEB_FALLBACK:
        return "web_fallback"
    if ev.path == CRAGPath.SUPPLEMENT:
        return "supplement"
    return "done"


def _supplement_node(state: CRAGState) -> dict:
    """Broaden query and fetch a few more chunks, merge with existing."""
    q = state["query"]
    broader = f"{q} CloudDash overview documentation"
    extra_dense = vector_store.similarity_search(broader, k=5)
    extra_bm25 = bm25_store.search(broader, k=5)

    # merge with existing, dedup by chunk_id
    seen = {c.chunk_id for c in state["reranked_chunks"]}
    merged = list(state["reranked_chunks"])
    for c in extra_dense + extra_bm25:
        cid = c.get("chunk_id", "")
        if cid and cid not in seen:
            merged.append(RetrievedChunk(
                chunk_id=cid,
                kb_id=c.get("kb_id", ""),
                title=c.get("title", ""),
                category=c.get("category", ""),
                section=c.get("section", 0),
                content=c.get("content", ""),
                rerank_score=c.get("dense_score", c.get("bm25_score", 0.0)),
            ))
            seen.add(cid)

    cfg = get_settings()
    final = sorted(merged, key=lambda c: c.rerank_score, reverse=True)[:cfg.retrieval_top_k_reranked]
    return {"final_chunks": final, "crag_path": CRAGPath.SUPPLEMENT}


def _web_fallback_node(state: CRAGState) -> dict:
    """Tavily web search when KB confidence is too low."""
    cfg = get_settings()
    if not cfg.tavily_api_key:
        # no key → return whatever we have with a low-confidence flag
        return {
            "final_chunks": state["reranked_chunks"][:cfg.retrieval_top_k_reranked],
            "crag_path": CRAGPath.WEB_FALLBACK,
        }

    from tavily import TavilyClient
    client = TavilyClient(api_key=cfg.tavily_api_key)
    q = f"CloudDash {state['query']}"
    try:
        resp = client.search(q, max_results=3, include_raw_content=False)
        web_chunks = []
        for r in resp.get("results", []):
            web_chunks.append(RetrievedChunk(
                chunk_id=f"web-{hash(r['url']) & 0xFFFF:04x}",
                kb_id="WEB",
                title=r.get("title", "Web result"),
                category="web",
                section=0,
                content=r.get("content", "")[:800],
                rerank_score=r.get("score", 0.5),
                source="web",
            ))
        # merge web + any decent KB chunks we had
        final = web_chunks + list(state["reranked_chunks"])[:2]
    except Exception:
        final = list(state["reranked_chunks"])[:cfg.retrieval_top_k_reranked]

    return {"final_chunks": final, "crag_path": CRAGPath.WEB_FALLBACK}


def _done_node(state: CRAGState) -> dict:
    cfg = get_settings()
    chunks = state["reranked_chunks"][:cfg.retrieval_top_k_reranked]
    return {"final_chunks": chunks, "crag_path": CRAGPath.DIRECT}


def build_crag_graph():
    """Compile the CRAG sub-graph. Called once at startup."""
    g = StateGraph(CRAGState)
    g.add_node("rewrite", _rewrite_node)
    g.add_node("parallel_retrieve", _parallel_retrieve_node)
    g.add_node("fuse", _fuse_node)
    g.add_node("rerank", _rerank_node)
    g.add_node("relevance_eval", _relevance_eval_node)
    g.add_node("supplement", _supplement_node)
    g.add_node("web_fallback", _web_fallback_node)
    g.add_node("done", _done_node)

    g.add_edge(START, "rewrite")
    g.add_edge("rewrite", "parallel_retrieve")
    g.add_edge("parallel_retrieve", "fuse")
    g.add_edge("fuse", "rerank")
    g.add_edge("rerank", "relevance_eval")
    g.add_conditional_edges("relevance_eval", _route_after_eval, {
        "done": "done",
        "supplement": "supplement",
        "web_fallback": "web_fallback",
    })
    g.add_edge("supplement", END)
    g.add_edge("web_fallback", END)
    g.add_edge("done", END)

    return g.compile()


_CRAG_GRAPH = None


def get_crag_graph():
    global _CRAG_GRAPH
    if _CRAG_GRAPH is None:
        _CRAG_GRAPH = build_crag_graph()
    return _CRAG_GRAPH


async def run_crag(query: str, history_context: str = "") -> tuple[list[RetrievedChunk], CRAGPath]:
    """Main entry point — run CRAG and return (chunks, path_taken)."""
    graph = get_crag_graph()
    initial: CRAGState = {
        "query": query,
        "history_context": history_context,
        "rewritten_queries": [],
        "bm25_results": [],
        "dense_results": [],
        "fused_chunks": [],
        "reranked_chunks": [],
        "eval_result": None,
        "final_chunks": [],
        "crag_path": CRAGPath.DIRECT,
        "retry_count": 0,
    }
    result = await graph.ainvoke(initial)
    chunks = result.get("final_chunks") or result.get("reranked_chunks") or []
    path = result.get("crag_path", CRAGPath.DIRECT)
    return chunks, path
