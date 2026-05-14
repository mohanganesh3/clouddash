"""Markdown-aware contextual chunker.

Each KB article has `## Section N — Title` headings. We split on these so
each chunk is a semantic unit (a "section"). For long sections we sub-split
with token overlap. Every chunk is prefixed with a one-line context header
("Anthropic-style contextual retrieval") so embeddings carry article+section
context independent of where the chunk lands in similarity space.

Output: list[Chunk] where each Chunk has chunk_id, parent article id, section
number, raw content (without context prefix), context prefix, and contextual
text (prefix + content) that gets embedded and indexed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from clouddash.logging_setup import get_logger
from clouddash.models import KBArticle

logger = get_logger(__name__)

_SECTION_RE = re.compile(r"^##\s+Section\s+(\d+)\s*[\u2014\-:]?\s*(.*)$", re.MULTILINE)
# Conservative chunk size — sentence-transformers BGE small max input is 512 tokens.
# We target ~400 tokens (≈ 1600 chars) per chunk to leave room for the prefix.
MAX_CHUNK_CHARS = 1800
SOFT_CHUNK_CHARS = 1500
SOFT_OVERLAP_CHARS = 200


@dataclass(frozen=True)
class Chunk:
    """One indexable unit of KB content."""

    chunk_id: str
    kb_id: str
    title: str
    category: str
    section: int | None
    section_title: str | None
    raw_content: str  # the chunk body itself
    context_prefix: str  # "Article: ... | Section: ... | Category: ..."
    contextual_text: str  # prefix + raw_content — what gets embedded
    metadata: dict[str, str | int | list[str]]


def _build_prefix(article: KBArticle, section: int | None, section_title: str | None) -> str:
    """The Anthropic-style context prefix prepended to every chunk."""
    parts = [f"Article {article.id}: {article.title}"]
    if section is not None:
        sec = f"Section {section}"
        if section_title:
            sec += f" — {section_title.strip()}"
        parts.append(sec)
    parts.append(f"Category: {article.category}")
    if article.applies_to:
        parts.append(f"Applies to: {', '.join(article.applies_to)}")
    return " | ".join(parts)


def _split_long_section(text: str, max_chars: int = MAX_CHUNK_CHARS) -> Iterator[str]:
    """Split a too-long section on paragraph boundaries with overlap."""
    if len(text) <= max_chars:
        yield text
        return

    paragraphs = re.split(r"\n\s*\n", text)
    buffer = ""
    for para in paragraphs:
        if len(buffer) + len(para) + 2 <= max_chars:
            buffer = f"{buffer}\n\n{para}".strip() if buffer else para
        else:
            if buffer:
                yield buffer
            # Start the next chunk with a small overlap from end of previous
            tail = buffer[-SOFT_OVERLAP_CHARS:] if buffer else ""
            buffer = f"{tail}\n\n{para}".strip() if tail else para

    if buffer:
        yield buffer


def chunk_article(article: KBArticle) -> list[Chunk]:
    """Split one article into Chunks based on `## Section N — Title` headings."""
    body = article.content
    matches = list(_SECTION_RE.finditer(body))

    chunks: list[Chunk] = []

    # Optional preamble (text before first ## Section)
    preamble_end = matches[0].start() if matches else len(body)
    preamble = body[:preamble_end].strip()
    if preamble:
        # Strip leading H1 if present (the article title)
        preamble = re.sub(r"^#\s+.*\n+", "", preamble).strip()
        if preamble:
            for i, sub in enumerate(_split_long_section(preamble)):
                cid = f"{article.id}-pre-{i}"
                prefix = _build_prefix(article, None, None)
                chunks.append(
                    Chunk(
                        chunk_id=cid,
                        kb_id=article.id,
                        title=article.title,
                        category=article.category,
                        section=None,
                        section_title=None,
                        raw_content=sub,
                        context_prefix=prefix,
                        contextual_text=f"{prefix}\n\n{sub}",
                        metadata={
                            "kb_id": article.id,
                            "title": article.title,
                            "category": article.category,
                            "section": -1,
                            "tags": article.tags,
                            "applies_to": article.applies_to,
                            "last_updated": article.last_updated,
                        },
                    )
                )

    # Each section
    for idx, m in enumerate(matches):
        section_num = int(m.group(1))
        section_title = m.group(2).strip()
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body)
        section_body = body[start:end].strip()
        if not section_body:
            continue

        for sub_i, sub in enumerate(_split_long_section(section_body)):
            cid = f"{article.id}-s{section_num}" if sub_i == 0 else f"{article.id}-s{section_num}-{sub_i}"
            prefix = _build_prefix(article, section_num, section_title)
            chunks.append(
                Chunk(
                    chunk_id=cid,
                    kb_id=article.id,
                    title=article.title,
                    category=article.category,
                    section=section_num,
                    section_title=section_title or None,
                    raw_content=sub,
                    context_prefix=prefix,
                    contextual_text=f"{prefix}\n\n{sub}",
                    metadata={
                        "kb_id": article.id,
                        "title": article.title,
                        "category": article.category,
                        "section": section_num,
                        "section_title": section_title or "",
                        "tags": article.tags,
                        "applies_to": article.applies_to,
                        "last_updated": article.last_updated,
                    },
                )
            )

    return chunks


def chunk_articles(articles: list[KBArticle]) -> list[Chunk]:
    """Chunk every article in the KB. Logs counts for sanity."""
    all_chunks: list[Chunk] = []
    for article in articles:
        all_chunks.extend(chunk_article(article))
    logger.info(
        "kb.chunked",
        articles=len(articles),
        chunks=len(all_chunks),
        avg_chunks_per_article=round(len(all_chunks) / max(len(articles), 1), 1),
    )
    return all_chunks
