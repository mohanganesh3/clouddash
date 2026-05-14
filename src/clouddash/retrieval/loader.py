"""KB article loader.

Reads `knowledge_base/**/*.md`, parses YAML frontmatter + markdown body,
returns typed KBArticle objects ready for chunking.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from clouddash.exceptions import IngestionError
from clouddash.logging_setup import get_logger
from clouddash.models import KBArticle

logger = get_logger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_article(path: Path) -> KBArticle:
    """Parse one .md file with YAML frontmatter into a KBArticle."""
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise IngestionError(
            f"Article missing YAML frontmatter: {path}",
            context={"path": str(path)},
        )

    frontmatter_yaml, body = match.groups()
    try:
        meta = yaml.safe_load(frontmatter_yaml) or {}
    except yaml.YAMLError as exc:
        raise IngestionError(
            f"Invalid YAML frontmatter in {path}: {exc}",
            context={"path": str(path)},
            cause=exc,
        ) from exc

    required = {"id", "title", "category", "last_updated"}
    missing = required - meta.keys()
    if missing:
        raise IngestionError(
            f"Article {path.name} missing frontmatter fields: {sorted(missing)}",
            context={"path": str(path), "missing": sorted(missing)},
        )

    return KBArticle(
        id=meta["id"],
        title=meta["title"],
        category=meta["category"],
        tags=list(meta.get("tags", [])),
        content=body.strip(),
        last_updated=str(meta["last_updated"]),
        applies_to=list(meta.get("applies_to", [])),
        source_path=str(path),
    )


def load_articles(kb_root: str | Path) -> list[KBArticle]:
    """Load every .md file under kb_root recursively. Sorted by id for determinism."""
    root = Path(kb_root)
    if not root.exists():
        raise IngestionError(
            f"Knowledge base directory not found: {root}",
            context={"kb_root": str(root)},
        )

    files = sorted(root.rglob("*.md"))
    if not files:
        raise IngestionError(
            f"No .md articles under {root}",
            context={"kb_root": str(root)},
        )

    articles: list[KBArticle] = []
    seen_ids: set[str] = set()
    for fp in files:
        article = parse_article(fp)
        if article.id in seen_ids:
            raise IngestionError(
                f"Duplicate KB id: {article.id}",
                context={"id": article.id, "path": str(fp)},
            )
        seen_ids.add(article.id)
        articles.append(article)

    articles.sort(key=lambda a: a.id)
    logger.info(
        "kb.loaded",
        count=len(articles),
        categories=sorted({a.category for a in articles}),
        kb_root=str(root),
    )
    return articles
