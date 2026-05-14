"""ChromaDB vector store wrapper.

Persists to disk under `data/chroma/` so we don't re-embed on every restart.
We bypass langchain-chroma's higher-level wrappers and use the chromadb client
directly — fewer abstractions, easier to reason about, and the LangChain
EnsembleRetriever wires together at a higher level via our `Retriever` class.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from clouddash.exceptions import RetrievalError
from clouddash.logging_setup import get_logger
from clouddash.retrieval.chunker import Chunk
from clouddash.retrieval.embedder import embed_query, embed_texts
from clouddash.settings import get_settings

logger = get_logger(__name__)


def _flatten_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Chroma 0.5+ requires str/int/float/bool values. Stringify lists."""
    flat: dict[str, Any] = {}
    for k, v in meta.items():
        if isinstance(v, (str, int, float, bool)):
            flat[k] = v
        elif isinstance(v, list):
            flat[k] = ",".join(str(x) for x in v)
        elif v is None:
            flat[k] = ""
        else:
            flat[k] = str(v)
    return flat


def _unflatten_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [s for s in value.split(",") if s]


class VectorStore:
    """Thin wrapper around chromadb.PersistentClient + a single collection."""

    def __init__(self, persist_dir: str | None = None, collection_name: str | None = None) -> None:
        settings = get_settings()
        self.persist_dir = Path(persist_dir or settings.chroma_persist_dir)
        self.collection_name = collection_name or settings.chroma_collection_name
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = None
        self._collection = None

    def _ensure_client(self) -> None:
        if self._client is not None:
            return
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings
        except ImportError as exc:  # pragma: no cover
            raise RetrievalError("chromadb not installed", cause=exc) from exc

        self._client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            "vector_store.opened",
            persist_dir=str(self.persist_dir),
            collection=self.collection_name,
            count=self._collection.count(),
        )

    def reset(self) -> None:
        """Drop and recreate the collection. Used by ingest --rebuild."""
        self._ensure_client()
        assert self._client is not None
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:  # noqa: BLE001 — chromadb raises generic when missing
            pass
        self._collection = self._client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("vector_store.reset", collection=self.collection_name)

    def upsert_chunks(self, chunks: list[Chunk]) -> None:
        """Embed and upsert. Idempotent on chunk_id."""
        if not chunks:
            return
        self._ensure_client()
        assert self._collection is not None

        ids = [c.chunk_id for c in chunks]
        documents = [c.contextual_text for c in chunks]  # prefix + content
        metadatas = [
            _flatten_metadata(
                {
                    "chunk_id": c.chunk_id,
                    "kb_id": c.kb_id,
                    "title": c.title,
                    "category": c.category,
                    "section": c.section if c.section is not None else -1,
                    "section_title": c.section_title or "",
                    "tags": c.metadata.get("tags", []),
                    "applies_to": c.metadata.get("applies_to", []),
                    "last_updated": c.metadata.get("last_updated", ""),
                    "raw_content": c.raw_content,  # store raw for citations
                }
            )
            for c in chunks
        ]
        embeddings = embed_texts(documents)
        self._collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        logger.info("vector_store.upserted", count=len(chunks))

    def query(self, text: str, *, top_k: int = 10) -> list[dict[str, Any]]:
        """Embed query, return top_k chunks with metadata + cosine distance.

        Result schema:
            [{chunk_id, kb_id, title, category, section, raw_content, score, ...}]
            where score is cosine similarity in [0, 1] (1 = identical).
        """
        self._ensure_client()
        assert self._collection is not None

        if self._collection.count() == 0:
            logger.warning("vector_store.empty", collection=self.collection_name)
            return []

        embedding = embed_query(text)
        result = self._collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            include=["metadatas", "documents", "distances"],
        )

        hits: list[dict[str, Any]] = []
        ids = result.get("ids", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        documents = result.get("documents", [[]])[0]
        distances = result.get("distances", [[]])[0]

        for cid, meta, doc, dist in zip(ids, metadatas, documents, distances, strict=False):
            # ChromaDB returns L2 distance for cosine — convert to similarity
            # For normalized vectors with cosine: similarity = 1 - distance/2
            similarity = max(0.0, min(1.0, 1.0 - (dist / 2.0)))
            hits.append(
                {
                    "chunk_id": cid,
                    "kb_id": meta.get("kb_id", ""),
                    "title": meta.get("title", ""),
                    "category": meta.get("category", ""),
                    "section": (
                        int(meta.get("section", -1)) if meta.get("section", -1) != -1 else None
                    ),
                    "section_title": meta.get("section_title", "") or None,
                    "raw_content": meta.get("raw_content", doc or ""),
                    "tags": _unflatten_list(meta.get("tags")),
                    "applies_to": _unflatten_list(meta.get("applies_to")),
                    "score": similarity,
                    "document": doc or "",
                }
            )
        return hits

    def all_chunks(self) -> list[dict[str, Any]]:
        """Return every chunk in the collection — used to bootstrap BM25."""
        self._ensure_client()
        assert self._collection is not None

        if self._collection.count() == 0:
            return []

        # Chroma's get() returns everything when no IDs are passed
        result = self._collection.get(include=["metadatas", "documents"])
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        documents = result.get("documents", [])

        chunks: list[dict[str, Any]] = []
        for cid, meta, doc in zip(ids, metadatas, documents, strict=False):
            chunks.append(
                {
                    "chunk_id": cid,
                    "kb_id": meta.get("kb_id", ""),
                    "title": meta.get("title", ""),
                    "category": meta.get("category", ""),
                    "section": (
                        int(meta.get("section", -1)) if meta.get("section", -1) != -1 else None
                    ),
                    "section_title": meta.get("section_title", "") or None,
                    "raw_content": meta.get("raw_content", doc or ""),
                    "tags": _unflatten_list(meta.get("tags")),
                    "applies_to": _unflatten_list(meta.get("applies_to")),
                    "document": doc or "",
                }
            )
        return chunks

    def count(self) -> int:
        self._ensure_client()
        assert self._collection is not None
        return self._collection.count()
