"""KB ingestion script.

Usage:
    python -m clouddash.scripts.ingest_kb           # incremental upsert
    python -m clouddash.scripts.ingest_kb --rebuild  # drop + re-embed everything

Reads `knowledge_base/**/*.md`, parses frontmatter, chunks with the markdown-
aware section splitter, embeds with `bge-small-en-v1.5`, and persists to
ChromaDB at `data/chroma/`.
"""

from __future__ import annotations

import argparse
import sys
import time

from clouddash.logging_setup import configure_logging, get_logger
from clouddash.retrieval.chunker import chunk_articles
from clouddash.retrieval.loader import load_articles
from clouddash.retrieval.vector_store import VectorStore
from clouddash.settings import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest CloudDash KB into ChromaDB.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Drop the existing collection and re-ingest everything.",
    )
    parser.add_argument(
        "--kb-root",
        default=None,
        help="Override the KB root directory.",
    )
    args = parser.parse_args(argv)

    configure_logging(json_format=False)  # Pretty console for the script
    log = get_logger(__name__)
    settings = get_settings()
    settings.ensure_directories()

    kb_root = args.kb_root or settings.kb_root_dir
    log.info("ingest.start", kb_root=kb_root, rebuild=args.rebuild)
    t0 = time.time()

    articles = load_articles(kb_root)
    chunks = chunk_articles(articles)

    store = VectorStore()
    if args.rebuild:
        store.reset()
    store.upsert_chunks(chunks)

    elapsed = time.time() - t0
    log.info(
        "ingest.done",
        articles=len(articles),
        chunks=len(chunks),
        store_count=store.count(),
        seconds=round(elapsed, 2),
    )

    print("\n" + "=" * 60)
    print(f"  Ingested {len(articles)} articles → {len(chunks)} chunks")
    print(f"  Vector store: {store.count()} entries at {store.persist_dir}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
