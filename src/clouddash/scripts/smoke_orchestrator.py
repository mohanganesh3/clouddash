"""End-to-end orchestrator smoke test against the 4 official scenarios.

Usage:
    python -m clouddash.scripts.smoke_orchestrator
    python -m clouddash.scripts.smoke_orchestrator --scenario 1
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from typing import NamedTuple
from uuid import uuid4

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from clouddash.logging_setup import setup_logging, get_logger
from clouddash.models import (
    AgentType,
    GraphState,
    CustomerProfile,
    Plan,
)
from clouddash.orchestrator.graph import Orchestrator

logger = get_logger(__name__)


class _Scenario(NamedTuple):
    sid: int
    name: str
    user_messages: list[str]
    initial_profile: CustomerProfile
    expected_route_includes: set[AgentType]
    must_escalate: bool = False
    must_offer_feature_request: bool = False


SCENARIOS: list[_Scenario] = [
    _Scenario(
        sid=1,
        name="Single-Agent Resolution — alerts after AWS update",
        user_messages=[
            "My CloudDash alerts stopped firing after I updated my AWS integration "
            "credentials yesterday. I'm on the Pro plan."
        ],
        initial_profile=CustomerProfile(plan=Plan.PRO),
        expected_route_includes={AgentType.TRIAGE, AgentType.TECHNICAL},
    ),
    _Scenario(
        sid=2,
        name="Cross-Agent Handover — upgrade + SSO",
        user_messages=[
            "I want to upgrade from Pro to Enterprise, but first can you check if "
            "the SSO integration issue I reported last week has been resolved?"
        ],
        initial_profile=CustomerProfile(
            customer_id="cust_acme_42",
            org_name="Acme Corp",
            plan=Plan.PRO,
        ),
        expected_route_includes={
            AgentType.TRIAGE,
            AgentType.TECHNICAL,
            AgentType.BILLING,
        },
    ),
    _Scenario(
        sid=3,
        name="Escalation to Human — double charge",
        user_messages=[
            "I've been charged twice for April. I need an immediate refund and "
            "I want to speak to a manager."
        ],
        initial_profile=CustomerProfile(
            customer_id="cust_acme_42",
            org_name="Acme Corp",
            plan=Plan.PRO,
        ),
        expected_route_includes={
            AgentType.TRIAGE,
            AgentType.BILLING,
            AgentType.ESCALATION,
        },
        must_escalate=True,
    ),
    _Scenario(
        sid=4,
        name="KB Retrieval Failure — Datadog support",
        user_messages=[
            "Does CloudDash support integration with Datadog for cross-platform alerting?"
        ],
        initial_profile=CustomerProfile(),
        expected_route_includes={AgentType.TRIAGE, AgentType.KNOWLEDGE},
        must_offer_feature_request=True,
    ),
]


async def run_scenario(orchestrator: Orchestrator, scenario: _Scenario, console: Console) -> bool:
    console.rule(f"[bold cyan]Scenario {scenario.sid} — {scenario.name}")
    state = GraphState(
        trace_id=uuid4(),
        customer_profile=scenario.initial_profile,
    )

    for i, user_msg in enumerate(scenario.user_messages, 1):
        console.print(f"\n[bold blue]User:[/bold blue] {user_msg}")
        t0 = time.time()
        try:
            state = await orchestrator.run_turn(state, user_msg)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[bold red]ORCHESTRATOR ERROR:[/bold red] {type(exc).__name__}: {exc}")
            return False
        elapsed = time.time() - t0

        # Find the final assistant message
        final_msg = None
        for m in reversed(state.messages):
            if m.role.value == "assistant":
                final_msg = m
                break

        if final_msg is None:
            console.print("[red]No assistant response produced.[/red]")
            return False

        agent_label = final_msg.agent.value if final_msg.agent else "?"
        console.print(
            f"\n[bold green]Agent ({agent_label}):[/bold green] "
            f"[dim](confidence={final_msg.metadata.get('confidence', '?')}, "
            f"latency={final_msg.metadata.get('latency_ms', '?')}ms, total turn={int(elapsed*1000)}ms)[/dim]"
        )
        console.print(Panel(Markdown(final_msg.content), border_style="green"))
        if final_msg.citations:
            cites_block = ", ".join(c.render_inline() for c in final_msg.citations[:6])
            console.print(f"[dim]Citations: {cites_block}[/dim]")

        # Show the handover trail
        console.print("\n[bold]Handover audit chain:[/bold]")
        if not state.handover_history:
            console.print("  [dim](direct response — no handovers)[/dim]")
        for evt in state.handover_history[-6:]:
            console.print(
                f"  • {evt.from_agent.value} → {evt.to_agent.value}  "
                f"[dim]({evt.reason.value}, {evt.status.value})[/dim]"
            )

    # Verdict
    routed = {e.from_agent for e in state.handover_history} | {
        e.to_agent for e in state.handover_history
    }
    routed.add(state.current_agent)

    missing = scenario.expected_route_includes - routed
    last_resp = state.last_response
    has_escalated = bool(last_resp and last_resp.escalate)
    fr_id = last_resp.metadata.get("feature_request_id") if last_resp else None

    console.print()
    if missing:
        console.print(f"[bold red]✗ FAIL[/bold red] — missing expected agents in route: {[a.value for a in missing]}")
        return False
    if scenario.must_escalate and not has_escalated:
        console.print("[bold red]✗ FAIL[/bold red] — scenario expected escalation, but escalate=False")
        return False
    if scenario.must_offer_feature_request and not fr_id:
        console.print(
            "[bold yellow]REVIEW[/bold yellow] — expected a feature_request_id in metadata; "
            "agent may have responded without filing one."
        )
    console.print(f"[bold green]✓ PASS[/bold green] — route covered {[a.value for a in scenario.expected_route_includes]}")
    return True


async def amain(scenario_id: int | None) -> int:
    setup_logging(log_level="WARNING")
    console = Console()
    console.rule("[bold]CloudDash Orchestrator Smoke Test")

    orchestrator = Orchestrator()

    scenarios = SCENARIOS if scenario_id is None else [s for s in SCENARIOS if s.sid == scenario_id]
    if not scenarios:
        console.print(f"[red]Unknown scenario id: {scenario_id}[/red]")
        return 1

    results: list[bool] = []
    for sc in scenarios:
        try:
            ok = await run_scenario(orchestrator, sc, console)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Scenario {sc.sid} crashed: {exc}[/red]")
            ok = False
        results.append(ok)

    console.rule()
    passed = sum(results)
    total = len(results)
    style = "bold green" if passed == total else "bold yellow"
    console.print(f"[{style}]Result: {passed}/{total} scenarios passed[/{style}]")
    return 0 if passed == total else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="CloudDash orchestrator smoke test.")
    parser.add_argument(
        "--scenario",
        type=int,
        choices=[s.sid for s in SCENARIOS],
        default=None,
        help="Run only one scenario.",
    )
    args = parser.parse_args()
    return asyncio.run(amain(args.scenario))


if __name__ == "__main__":
    sys.exit(main())
