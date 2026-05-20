from __future__ import annotations

from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from clouddash.settings import get_settings


@lru_cache(maxsize=1)
def get_embedder() -> HuggingFaceEmbeddings:
    cfg = get_settings()
    # TODO(mohan): swap to text-embedding-004 via Google when we need multilingual.
    # bge-small is fine for English-only KB but it'll struggle with Hinglish queries.
    return HuggingFaceEmbeddings(
        model_name=cfg.embedding_model,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
