from __future__ import annotations

from functools import lru_cache
from typing import Any

import chromadb
from langchain_chroma import Chroma

from clouddash.retrieval.embedder import get_embedder
from clouddash.settings import get_settings


@lru_cache(maxsize=1)
def get_vector_store() -> Chroma:
    cfg = get_settings()
    client = chromadb.PersistentClient(path=cfg.chroma_persist_dir)
    return Chroma(
        client=client,
        collection_name=cfg.chroma_collection_name,
        embedding_function=get_embedder(),
    )


def add_chunks(chunks: list[dict[str, Any]]) -> None:
    store = get_vector_store()
    texts = [c["content"] for c in chunks]
    metadatas = [
        {
            "chunk_id": c["chunk_id"],
            "kb_id": c["kb_id"],
            "title": c["title"],
            "category": c["category"],
            "section": c["section"],
        }
        for c in chunks
    ]
    ids = [c["chunk_id"] for c in chunks]
    store.add_texts(texts=texts, metadatas=metadatas, ids=ids)


def similarity_search(query: str, k: int = 10) -> list[dict[str, Any]]:
    store = get_vector_store()
    results = store.similarity_search_with_relevance_scores(query, k=k)
    out = []
    for doc, score in results:
        out.append({
            "chunk_id": doc.metadata.get("chunk_id", ""),
            "kb_id": doc.metadata.get("kb_id", ""),
            "title": doc.metadata.get("title", ""),
            "category": doc.metadata.get("category", ""),
            "section": doc.metadata.get("section", 0),
            "content": doc.page_content,
            "dense_score": float(score),
        })
    return out
