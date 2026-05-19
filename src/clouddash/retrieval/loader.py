"""Markdown KB loader with YAML frontmatter parsing.

Walks knowledge_base/ recursively. Each file = one article.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def load_articles(kb_dir: str) -> list[dict[str, Any]]:
    articles = []
    for path in sorted(Path(kb_dir).rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        m = _FRONTMATTER_RE.match(raw)
        if m:
            try:
                meta = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError:
                meta = {}
            content = raw[m.end():]
        else:
            meta = {}
            content = raw

        meta.setdefault("id", path.stem.upper())
        meta.setdefault("title", path.stem.replace("-", " ").title())
        meta.setdefault("category", path.parent.name)
        articles.append({**meta, "content": content.strip(), "path": str(path)})
    return articles
