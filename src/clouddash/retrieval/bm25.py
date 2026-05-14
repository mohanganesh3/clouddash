"""BM25 keyword retriever — companion to dense retrieval (ADR-003).

We rebuild BM25 in-memory at startup from the chunks already in ChromaDB.
This keeps a single source of truth (Chroma) and avoids syncing two stores.
"""

from __future__ import annotations

import re
from typing import Any

from clouddash.exceptions import RetrievalError
from clouddash.logging_setup import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric. Simple and deterministic."""
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """Lazily-built BM25 index over a list of chunk dicts."""

    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:  # pragma: no cover
            raise RetrievalError("rank-bm25 not installed", cause=exc) from exc

        self.chunks = chunks
        self.chunk_ids = [c["chunk_id"] for c in chunks]
        # Tokenize the contextual document (prefix + raw_content) for BM25
        self.tokenized = [tokenize(c.get("document") or c.get("raw_content", "")) for c in chunks]
        self._bm25 = BM25Okapi(self.tokenized)
        logger.info("bm25.built", chunks=len(chunks))

    def query(self, text: str, *, top_k: int = 10) -> list[dict[str, Any]]:
        """Return top_k chunks with bm25_score, sorted descending."""
        if not self.chunks:
            return []
        tokens = tokenize(text)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        # argsort descending
        ranked = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]

        # Normalize scores to [0, 1] for downstream comparison (only for ranking; not used as similarity)
        max_score = max(scores) if max(scores) > 0 else 1.0
        results: list[dict[str, Any]] = []
        for idx in ranked:
            if scores[idx] <= 0:
                continue
            chunk = dict(self.chunks[idx])  # shallow copy
            chunk["bm25_score"] = float(scores[idx] / max_score)
            chunk["bm25_raw_score"] = float(scores[idx])
            results.append(chunk)
        return results

    def __len__(self) -> int:
        return len(self.chunks)
