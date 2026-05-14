"""End-to-end retrieval smoke test against the 4 official assignment scenarios.

Usage:
    python -m clouddash.scripts.smoke_retrieval

This exercises the full pipeline (rewrite + hybrid + RRF + LLM rerank) with
the user's actual GOOGLE_API_KEY. Prints per-scenario results so we can
verify retrieval quality BEFORE wiring up the agents on top.
"""

from __future__ import annotations

import sys
from typing import NamedTuple

from rich.console import Console
from rich.table import Table

from clouddash.logging_setup import configure_logging
from clouddash.models import ConversationState, Message, MessageRole
from clouddash.retrieval.retriever import Retriever


class _Scenario(NamedTuple):
    name: str
    user_message: str
    expected_kb_ids: set[str]
    must_be_low_score: bool = False  # for Scenario 4 KB-miss


SCENARIOS: list[_Scenario] = [
    _Scenario(
        name="Scenario 1 — Alerts after AWS credential update",
        user_message=(
            "My CloudDash alerts stopped firing after I updated my AWS integration "
            "credentials yesterday. I'm on the Pro plan."
        ),
        expected_kb_ids={"KB-005", "KB-007", "KB-008"},
    ),
    _Scenario(
        name="Scenario 2 — Cross-agent: upgrade + SSO",
        user_message=(
            "I want to upgrade from Pro to Enterprise, but first can you check if "
            "the SSO integration issue I reported last week has been resolved?"
        ),
        expected_kb_ids={"KB-009", "KB-010", "KB-017", "KB-004"},
    ),
    _Scenario(
        name="Scenario 3 — Escalation: double charge",
        user_message=(
            "I've been charged twice for April. I need an immediate refund and "
            "I want to speak to a manager."
        ),
        expected_kb_ids={"KB-011", "KB-012", "KB-013"},
    ),
    _Scenario(
        name="Scenario 4 — KB MISS: Datadog support",
        user_message=(
            "Does CloudDash support integration with Datadog for cross-platform alerting?"
        ),
        expected_kb_ids=set(),  # we expect NOT to find a great match
        must_be_low_score=True,
    ),
]


def main() -> int:
    configure_logging(level="WARNING", json_format=False)
    console = Console()
    retriever = Retriever()

    console.rule("[bold]CloudDash Retrieval Smoke Test")
    console.print(f"Testing {len(SCENARIOS)} scenarios end-to-end (rewrite + hybrid + LLM rerank)\n")

    overall_pass = True

    for scenario in SCENARIOS:
        console.rule(f"[cyan]{scenario.name}")
        console.print(f"[dim]Query:[/dim] {scenario.user_message}\n")

        # Build a conversation state so the rewriter has context to work with
        state = ConversationState(
            messages=[Message(role=MessageRole.USER, content=scenario.user_message, turn_id=1)],
            turn_id=1,
        )

        try:
            chunks = retriever.retrieve(scenario.user_message, state=state, top_k=5)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]ERROR:[/red] {exc}")
            overall_pass = False
            continue

        if not chunks:
            console.print("[yellow]No chunks returned.[/yellow]")
            if not scenario.must_be_low_score:
                overall_pass = False
            continue

        # Render a table of top results
        table = Table(show_header=True, header_style="bold magenta", show_lines=False)
        table.add_column("#", style="dim", width=3)
        table.add_column("KB", style="cyan", width=10)
        table.add_column("§", width=4)
        table.add_column("Title", style="green", width=42)
        table.add_column("Rerank", justify="right", width=8)
        table.add_column("RRF", justify="right", width=7)
        table.add_column("Rationale", style="dim", width=40)

        retrieved_ids: set[str] = set()
        top_score = 0.0
        for i, c in enumerate(chunks, 1):
            retrieved_ids.add(c.kb_id)
            score = c.rerank_score if c.rerank_score is not None else 0.0
            top_score = max(top_score, score)
            table.add_row(
                str(i),
                c.kb_id,
                str(c.section) if c.section else "-",
                c.title[:40] + ("…" if len(c.title) > 40 else ""),
                f"{score:.2f}" if c.rerank_score is not None else "-",
                f"{c.rrf_score:.3f}" if c.rrf_score is not None else "-",
                (c.rerank_rationale or "")[:38] + (
                    "…" if c.rerank_rationale and len(c.rerank_rationale) > 38 else ""
                ),
            )

        console.print(table)

        # Verdict
        if scenario.must_be_low_score:
            # Scenario 4: top score should be LOW (i.e. reranker should mark as off-topic)
            if top_score < 0.5:
                console.print(
                    f"[bold green]PASS[/bold green] — top score {top_score:.2f} < 0.5 "
                    "(reranker correctly flagged Datadog query as off-topic).\n"
                )
            else:
                console.print(
                    f"[bold yellow]REVIEW[/bold yellow] — top score {top_score:.2f} ≥ 0.5; "
                    "we may be retrieving plausibly-related but actually off-topic content.\n"
                )
        else:
            hit_count = len(retrieved_ids & scenario.expected_kb_ids)
            expected = len(scenario.expected_kb_ids)
            if hit_count >= 1:
                console.print(
                    f"[bold green]PASS[/bold green] — retrieved {hit_count}/{expected} "
                    f"expected KB IDs: {sorted(retrieved_ids & scenario.expected_kb_ids)}\n"
                )
            else:
                console.print(
                    f"[bold red]FAIL[/bold red] — none of the expected KB IDs "
                    f"{sorted(scenario.expected_kb_ids)} were retrieved.\n"
                )
                overall_pass = False

    console.rule()
    if overall_pass:
        console.print("[bold green]✓ All scenarios passed retrieval smoke test.[/bold green]")
        return 0
    console.print("[bold red]✗ One or more scenarios failed.[/bold red]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
