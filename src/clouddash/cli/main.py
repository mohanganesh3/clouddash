"""CloudDash CLI — operate the multi-agent system from your terminal.

Commands:

    clouddash ingest                       — (re)build the KB vector store.
    clouddash agents                       — list registered agents.
    clouddash chat                         — interactive REPL.
    clouddash demo --scenario N            — run one of the 4 official scenarios.
    clouddash demo                         — run all 4 official scenarios.
    clouddash trace <conversation_id>      — print the audit-log replay.
    clouddash serve [--port 8000]          — start the FastAPI server.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional
from uuid import UUID, uuid4

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from clouddash.logging_setup import configure_logging
from clouddash.models import (
    AgentType,
    ConversationState,
    CustomerProfile,
    Plan,
)
from clouddash.orchestrator.graph import Orchestrator

app = typer.Typer(
    name="clouddash",
    help="CloudDash multi-agent customer support — CLI.",
    add_completion=False,
    no_args_is_help=True,
)

console = Console()


# ---- ingest -----------------------------------------------------------------


@app.command()
def ingest(
    rebuild: bool = typer.Option(False, "--rebuild", help="Wipe and rebuild the index."),
) -> None:
    """(Re)build the KB vector store from `knowledge_base/`."""
    from clouddash.scripts.ingest_kb import main as ingest_main

    sys.argv = ["ingest_kb"] + (["--rebuild"] if rebuild else [])
    raise typer.Exit(code=ingest_main())


# ---- agents -----------------------------------------------------------------


@app.command()
def agents() -> None:
    """List every agent registered in `config/agents.yaml`."""
    from clouddash.agents.registry import get_registry

    registry = get_registry()
    table = Table(title="Registered Agents", show_lines=True)
    table.add_column("agent", style="bold")
    table.add_column("model_tier")
    table.add_column("KB?")
    table.add_column("tools")
    table.add_column("description", overflow="fold")
    for atype in registry.list_agents():
        cfg = registry.get_config(atype)
        table.add_row(
            atype.value,
            cfg.model_tier,
            "yes" if cfg.requires_kb else "no",
            ", ".join(cfg.tools) or "—",
            cfg.description.strip().split("\n")[0],
        )
    console.print(table)


# ---- chat -------------------------------------------------------------------


def _render_response(state: ConversationState) -> None:
    final = None
    for m in reversed(state.messages):
        if m.role.value == "assistant":
            final = m
            break
    if final is None:
        console.print("[red]No assistant response produced.[/red]")
        return

    agent_label = final.agent.value if final.agent else "?"
    conf = final.metadata.get("confidence", "?")
    lat = final.metadata.get("latency_ms", "?")
    console.print(
        f"\n[bold green]Agent ({agent_label})[/bold green] "
        f"[dim](confidence={conf}, latency={lat}ms)[/dim]"
    )
    console.print(Panel(Markdown(final.content), border_style="green"))
    if final.citations:
        cites = ", ".join(c.render_inline() for c in final.citations[:8])
        console.print(f"[dim]Citations: {cites}[/dim]")
    if state.handover_history:
        console.print("[dim]Handover chain:[/dim]")
        for evt in state.handover_history[-6:]:
            console.print(
                f"  • {evt.from_agent.value} → {evt.to_agent.value} "
                f"[dim]({evt.reason.value}, {evt.status.value})[/dim]"
            )


@app.command()
def chat(
    customer_id: Optional[str] = typer.Option(None, "--customer-id"),
    org: Optional[str] = typer.Option(None, "--org"),
    plan: Optional[Plan] = typer.Option(None, "--plan"),
) -> None:
    """Interactive REPL. Type 'exit' or Ctrl-D to quit."""
    configure_logging(level="WARNING", json_format=False)
    console.rule("[bold cyan]CloudDash Chat")
    console.print(
        "[dim]Tip: this is a fresh conversation. State is in-memory; "
        "Ctrl-D / 'exit' to quit.[/dim]\n"
    )

    profile = CustomerProfile(customer_id=customer_id, org_name=org, plan=plan)
    state = ConversationState(trace_id=uuid4(), customer_profile=profile)
    orchestrator = Orchestrator()

    async def loop() -> None:
        nonlocal state
        while True:
            try:
                msg = console.input("[bold blue]You:[/bold blue] ").strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]bye[/dim]")
                return
            if not msg:
                continue
            if msg.lower() in {"exit", "quit", ":q"}:
                console.print("[dim]bye[/dim]")
                return
            try:
                state = await orchestrator.run_turn(state, msg)
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]Error: {type(exc).__name__}: {exc}[/red]")
                continue
            _render_response(state)

    asyncio.run(loop())


# ---- demo -------------------------------------------------------------------


@app.command()
def demo(
    scenario: Optional[int] = typer.Option(
        None,
        "--scenario",
        "-s",
        help="Scenario id 1..4. Omit to run all 4.",
    ),
) -> None:
    """Run one or all of the 4 official scenarios end-to-end."""
    from clouddash.scripts.smoke_orchestrator import main as smoke_main

    sys.argv = ["smoke_orchestrator"] + (
        ["--scenario", str(scenario)] if scenario is not None else []
    )
    raise typer.Exit(code=smoke_main())


# ---- trace ------------------------------------------------------------------


@app.command()
def trace(conversation_id: str) -> None:
    """Print every audit-log event recorded for the given conversation."""
    try:
        cid = UUID(conversation_id)
    except ValueError:
        console.print(f"[red]Invalid UUID: {conversation_id}[/red]")
        raise typer.Exit(code=1)
    from clouddash.handover.audit import read_trace_events

    events = read_trace_events(cid)
    if not events:
        console.print(f"[yellow]No events found for {cid}[/yellow]")
        return
    table = Table(title=f"Audit replay — {cid}", show_lines=False)
    table.add_column("ts", style="dim")
    table.add_column("event", style="bold cyan")
    table.add_column("agent")
    table.add_column("detail", overflow="fold")
    for e in events:
        detail_pairs = [
            f"{k}={v}"
            for k, v in e.items()
            if k not in {"event", "agent", "timestamp", "trace_id"}
        ]
        table.add_row(
            e.get("timestamp", "")[:19],
            e.get("event", ""),
            e.get("agent", "—"),
            ", ".join(detail_pairs)[:200],
        )
    console.print(table)


# ---- serve ------------------------------------------------------------------


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Start the FastAPI server (uvicorn)."""
    import uvicorn

    uvicorn.run(
        "clouddash.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# ---- health -----------------------------------------------------------------


@app.command()
def health() -> None:
    """Show current configuration and registered agents."""
    from clouddash.agents.registry import get_registry
    from clouddash.settings import get_settings

    settings = get_settings()
    registry = get_registry()
    table = Table(title="CloudDash Health", show_header=False)
    table.add_column("key", style="bold")
    table.add_column("value", overflow="fold")
    table.add_row("provider", settings.llm_provider)
    table.add_row("reasoning model", settings.llm_reasoning_model)
    table.add_row("fast model", settings.llm_fast_model)
    table.add_row("judge model", settings.llm_judge_model)
    table.add_row("agents", ", ".join(a.value for a in registry.list_agents()))
    table.add_row("chroma_persist_dir", settings.chroma_persist_dir)
    table.add_row("kb_root_dir", settings.kb_root_dir)
    table.add_row("audit_log_path", settings.audit_log_path)
    table.add_row("grounding_min_score", str(settings.grounding_min_score))
    console.print(table)


if __name__ == "__main__":
    app()
