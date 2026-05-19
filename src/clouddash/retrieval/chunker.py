"""Section-aware markdown chunker.

Splits on ## headers, then trims by token count. Header hierarchy is
preserved in a contextual prefix so each chunk is self-contained.
May 15: added guard for empty sections — rank_bm25 chokes on empty strings.
"""
from __future__ import annotations

import re
from typing import Any


_HEADER_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
_MAX_TOKENS = 450  # rough char proxy: 1 token ≈ 4 chars → 1800 chars


def chunk_article(article: dict[str, Any]) -> list[dict[str, Any]]:
    content = article["content"]
    art_id = article.get("id", "UNKNOWN")
    title = article.get("title", "")
    category = article.get("category", "")

    sections = _split_sections(content)
    chunks = []
    for idx, (heading, body) in enumerate(sections):
        if not body.strip():
            continue  # empty section guard

        # chunk by max token size if section is huge
        sub_chunks = _split_by_size(body.strip())
        for sub_idx, text in enumerate(sub_chunks):
            chunk_id = f"{art_id}-s{idx}-c{sub_idx}"
            # contextual prefix: helps retrieval a lot — each chunk mentions
            # what article and section it's from so it's standalone
            prefix = f"[{art_id}] {title} — {heading}" if heading else f"[{art_id}] {title}"
            full_text = f"{prefix}\n\n{text}"
            chunks.append({
                "chunk_id": chunk_id,
                "kb_id": art_id,
                "title": title,
                "category": category,
                "section": idx,
                "heading": heading,
                "content": full_text,
                "raw_content": text,
            })
    return chunks


def _split_sections(content: str) -> list[tuple[str, str]]:
    """Split content by markdown headers. Returns (heading, body) pairs."""
    headers = list(_HEADER_RE.finditer(content))
    if not headers:
        return [("", content)]

    sections = []
    for i, m in enumerate(headers):
        heading = m.group(2).strip()
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        sections.append((heading, content[start:end]))

    # leading content before first header
    if headers[0].start() > 0:
        sections.insert(0, ("", content[:headers[0].start()]))
    return sections


def _split_by_size(text: str) -> list[str]:
    if len(text) <= _MAX_TOKENS * 4:
        return [text]
    # naive paragraph split for oversized sections
    paras = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
    chunks, current = [], []
    cur_len = 0
    for p in paras:
        if cur_len + len(p) > _MAX_TOKENS * 4 and current:
            chunks.append("\n\n".join(current))
            current, cur_len = [], 0
        current.append(p)
        cur_len += len(p)
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [text]
