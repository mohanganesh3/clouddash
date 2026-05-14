"""Local embedding model wrapper — `BAAI/bge-small-en-v1.5` by default.

Decision (ADR-003): local sentence-transformers model — no API cost, fast, runs
on Render free tier (~130 MB). The model is loaded lazily and cached per process.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import TYPE_CHECKING

from clouddash.exceptions import RetrievalError
from clouddash.logging_setup import get_logger
from clouddash.settings import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_embedder() -> SentenceTransformer:
    """Singleton embedder. First call downloads the model (~130 MB, one-time)."""
    settings = get_settings()
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover
        raise RetrievalError(
            "sentence-transformers is not installed",
            cause=exc,
        ) from exc

    t0 = time.time()
    logger.info("embedder.loading", model=settings.embedding_model)
    model = SentenceTransformer(settings.embedding_model)
    logger.info(
        "embedder.loaded",
        model=settings.embedding_model,
        load_seconds=round(time.time() - t0, 2),
    )
    return model


def embed_texts(texts: list[str], *, batch_size: int = 32) -> list[list[float]]:
    """Embed a list of strings. Returns list of float vectors."""
    if not texts:
        return []
    model = get_embedder()
    t0 = time.time()
    # BGE recommends normalizing for cosine similarity
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    logger.debug(
        "embedder.embed",
        count=len(texts),
        batch_size=batch_size,
        latency_ms=int((time.time() - t0) * 1000),
    )
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    """Embed a single query string. BGE recommends a query-specific instruction."""
    # BGE small v1.5 query instruction — improves retrieval quality
    instructed = f"Represent this sentence for searching relevant passages: {text}"
    return embed_texts([instructed])[0]
