"""Typer-based CLI for local demo and scripting.

Entry point: `clouddash` (see pyproject.toml [project.scripts]).
"""

from clouddash.cli.main import app

__all__ = ["app"]
