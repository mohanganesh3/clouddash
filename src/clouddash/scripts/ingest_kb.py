"""KB ingestion — loads markdown articles, chunks them, embeds into ChromaDB.

Rough script. It works. Ship it.
Run: python -m clouddash.scripts.ingest_kb [--rebuild]
"""
from __future__ import annotations

import argparse
import sys
import time

from clouddash.retrieval.loader import load_articles
from clouddash.retrieval.chunker import chunk_article
from clouddash.retrieval.vector_store import add_chunks, get_vector_store
from clouddash.retrieval.bm25_store import build_index
from clouddash.settings import get_settings


def main(rebuild: bool = False) -> None:
    cfg = get_settings()
    cfg.ensure_dirs()

    print(f"Loading KB from {cfg.kb_root_dir}...")
    articles = load_articles(cfg.kb_root_dir)
    print(f"  {len(articles)} articles found")

    all_chunks = []
    for art in articles:
        chunks = chunk_article(art)
        all_chunks.extend(chunks)
    print(f"  {len(all_chunks)} chunks created")

    if rebuild:
        # nuke the collection and start over
        import chromadb
        client = chromadb.PersistentClient(path=cfg.chroma_persist_dir)
        try:
            client.delete_collection(cfg.chroma_collection_name)
            print("  existing collection deleted")
        except Exception:
            pass
        get_vector_store.cache_clear()

    t0 = time.time()
    print("  embedding and indexing...")
    add_chunks(all_chunks)
    build_index(all_chunks)
    print(f"  done in {time.time() - t0:.1f}s")
    print(f"Ingestion complete: {len(all_chunks)} chunks in ChromaDB + BM25")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--rebuild", action="store_true")
    args = p.parse_args()
    main(rebuild=args.rebuild)
