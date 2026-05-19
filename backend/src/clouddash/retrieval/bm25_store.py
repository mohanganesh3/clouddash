"""In-memory BM25 index over KB chunks.

Rebuilt on every ingest. Not persisted — fast enough to rebuild on startup
given our corpus size (< 500 chunks).
May 15: rank_bm25 crashes on empty token lists. Added the guard.
"""
from __future__ import annotations

from typing import Any

from rank_bm25 import BM25Okapi


_INDEX: BM25Okapi | None = None
_CHUNKS: list[dict[str, Any]] = []


def build_index(chunks: list[dict[str, Any]]) -> None:
    global _INDEX, _CHUNKS
    tokenized = []
    _CHUNKS = []
    for c in chunks:
        tokens = c["content"].lower().split()
        if not tokens:
            continue  # rank_bm25 chokes on empty docs
        tokenized.append(tokens)
        _CHUNKS.append(c)
    _INDEX = BM25Okapi(tokenized)


def search(query: str, k: int = 10) -> list[dict[str, Any]]:
    if _INDEX is None or not _CHUNKS:
        return []
    tokens = query.lower().split()
    if not tokens:
        return []
    scores = _INDEX.get_scores(tokens)
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [
        {**_CHUNKS[i], "bm25_score": float(scores[i])}
        for i in ranked
        if scores[i] > 0
    ]
