"""RAG pipeline — chunking, embedding, hybrid retrieval, reranking, citations."""

from __future__ import annotations

from functools import lru_cache

from clouddash.retrieval.retriever import Retriever


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    """Singleton accessor for the retriever — cached so we share BM25 + vector store."""
    return Retriever()


def reload_retriever() -> Retriever:
    """For tests: clear cache and re-init."""
    get_retriever.cache_clear()
    return get_retriever()


__all__ = ["Retriever", "get_retriever", "reload_retriever"]
