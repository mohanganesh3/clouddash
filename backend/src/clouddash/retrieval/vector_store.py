from __future__ import annotations

from functools import lru_cache
from typing import Any

import chromadb
from chromadb.config import Settings

from clouddash.retrieval.embedder import get_embedder
from clouddash.settings import get_settings


@lru_cache(maxsize=1)
def get_vector_store():
    cfg = get_settings()
    client = chromadb.PersistentClient(
        path=cfg.chroma_persist_dir,
        settings=Settings(anonymized_telemetry=False),
    )
    return client.get_or_create_collection(name=cfg.chroma_collection_name)


def add_chunks(chunks: list[dict[str, Any]]) -> None:
    collection = get_vector_store()
    embedder = get_embedder()
    documents = [c["content"] for c in chunks]
    embeddings = embedder.embed_documents(documents)
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
    collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )


def similarity_search(query: str, k: int = 10) -> list[dict[str, Any]]:
    collection = get_vector_store()
    query_embedding = get_embedder().embed_query(query)
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    out = []
    docs = (results.get("documents") or [[]])[0]
    metas = (results.get("metadatas") or [[]])[0]
    distances = (results.get("distances") or [[]])[0]
    for doc, meta, distance in zip(docs, metas, distances):
        metadata = meta or {}
        score = 1.0 / (1.0 + float(distance or 0.0))
        out.append({
            "chunk_id": metadata.get("chunk_id", ""),
            "kb_id": metadata.get("kb_id", ""),
            "title": metadata.get("title", ""),
            "category": metadata.get("category", ""),
            "section": metadata.get("section", 0),
            "content": doc,
            "dense_score": score,
        })
    return out
