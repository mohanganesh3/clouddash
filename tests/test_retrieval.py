"""Tests for the RAG pipeline — chunker, citation parser, grounding heuristics."""

from __future__ import annotations

import pytest

from clouddash.models import KBArticle, RetrievedChunk
from clouddash.retrieval.chunker import Chunk, chunk_article, chunk_articles
from clouddash.retrieval.citations import (
    _looks_like_refusal_or_escalation,
    assert_grounded,
    extract_citations,
    has_sufficient_grounding,
    validate_citations,
)
from clouddash.exceptions import GroundingFailure


def _make_article() -> KBArticle:
    return KBArticle(
        id="KB-001",
        title="Test Article",
        category="faq",
        tags=["test"],
        last_updated="2026-05-01",
        applies_to=["Pro"],
        content=(
            "# Test Article\n\n"
            "Preamble text about this article.\n\n"
            "## Section 1 — Introduction\n\n"
            "This is the intro content.\n\n"
            "## Section 2 — Details\n\n"
            "Here are the detailed steps to fix the issue.\n"
            "First do this. Then do that.\n\n"
            "## Section 3 — Wrap-up\n\n"
            "Finally, verify everything works."
        ),
    )


class TestChunker:
    def test_chunk_article_splits_by_sections(self) -> None:
        article = _make_article()
        chunks = chunk_article(article)

        # Should have preamble + 3 sections
        assert len(chunks) >= 4
        # Every chunk should have a kb_id
        assert all(c.kb_id == "KB-001" for c in chunks)
        # Every chunk should have contextual text
        assert all(len(c.contextual_text) > 50 for c in chunks)

    def test_chunk_prefix_contains_article_title(self) -> None:
        article = _make_article()
        chunks = chunk_article(article)
        for c in chunks:
            assert "Test Article" in c.context_prefix
            assert "Category: faq" in c.context_prefix

    def test_section_chunks_have_section_numbers(self) -> None:
        article = _make_article()
        chunks = chunk_article(article)
        section_chunks = [c for c in chunks if c.section is not None]
        assert len(section_chunks) >= 3
        # Check that section numbers match
        sections = sorted({c.section for c in section_chunks})
        assert sections[0] == 1

    def test_chunk_articles_counts(self) -> None:
        articles = [_make_article(), _make_article()]
        # Change ids so they don't collide
        articles[1] = articles[1].model_copy(update={"id": "KB-002"})
        chunks = chunk_articles(articles)
        assert len(chunks) >= 8  # 2 articles × ≥4 chunks each
        assert all(isinstance(c, Chunk) for c in chunks)


class TestCitations:
    def test_extract_citations_finds_markers(self) -> None:
        text = "Check [KB-005 § 2] and [KB-008 § 5] for details. Also [KB-001]."
        found = extract_citations(text)
        assert len(found) == 3
        assert found[0] == ("KB-005", 2)
        assert found[1] == ("KB-008", 5)
        assert found[2] == ("KB-001", None)

    def test_validate_citations_all_valid(self) -> None:
        chunks = [
            RetrievedChunk(
                chunk_id="c1",
                kb_id="KB-005",
                title="Alerts",
                category="troubleshooting",
                section=2,
                content="steps...",
                rerank_score=0.5,
                metadata={},
            ),
        ]
        ok, bad = validate_citations("See [KB-005 § 2] for help.", chunks)
        assert ok is True
        assert bad == []

    def test_validate_citations_invalid_kb(self) -> None:
        chunks = [
            RetrievedChunk(
                chunk_id="c1",
                kb_id="KB-005",
                title="Alerts",
                category="troubleshooting",
                section=2,
                content="steps...",
                rerank_score=0.5,
                metadata={},
            ),
        ]
        ok, bad = validate_citations("See [KB-999 § 1] for help.", chunks)
        assert ok is False
        assert "[KB-999 § 1]" in bad

    def test_grounding_threshold_passes(self) -> None:
        chunks = [
            RetrievedChunk(
                chunk_id="c1",
                kb_id="KB-005",
                title="Alerts",
                category="troubleshooting",
                section=2,
                content="steps...",
                rerank_score=0.9,
                metadata={},
            ),
        ]
        assert has_sufficient_grounding(chunks, min_score=0.25) is True

    def test_grounding_threshold_fails(self) -> None:
        chunks = [
            RetrievedChunk(
                chunk_id="c1",
                kb_id="KB-005",
                title="Alerts",
                category="troubleshooting",
                section=2,
                content="steps...",
                rerank_score=0.1,
                metadata={},
            ),
        ]
        assert has_sufficient_grounding(chunks, min_score=0.25) is False

    def test_assert_grounded_raises_on_no_citations(self) -> None:
        chunks = [
            RetrievedChunk(
                chunk_id="c1",
                kb_id="KB-005",
                title="Alerts",
                category="troubleshooting",
                section=2,
                content="steps...",
                rerank_score=0.5,
                metadata={},
            ),
        ]
        with pytest.raises(GroundingFailure):
            assert_grounded("This is an answer with no citation.", chunks)

    def test_assert_grounded_allows_refusal(self) -> None:
        chunks = []
        # Should NOT raise — refusals don't need citations
        assert_grounded("I don't have information about that topic.", chunks)

    def test_refusal_phrase_detection(self) -> None:
        assert _looks_like_refusal_or_escalation("I don't have that info") is True
        assert _looks_like_refusal_or_escalation("I can escalate this to a manager") is True
        assert _looks_like_refusal_or_escalation("Here are the steps to fix it.") is False
