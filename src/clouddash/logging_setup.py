"""Structured logging configuration.

Per ADR-006: structlog with JSONRenderer to stdout AND a JSONL audit log.
Every log line carries trace_id / turn_id / span_id via contextvars so logs
across modules connect for one conversation. This is the audit trail that
satisfies §2.3's requirement to log every handover event.
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from pathlib import Path
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars
from structlog.types import EventDict, Processor

from clouddash.settings import get_settings

# Context variables propagate trace context across async boundaries
_trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
_turn_id_var: ContextVar[int | None] = ContextVar("turn_id", default=None)
_agent_var: ContextVar[str | None] = ContextVar("agent", default=None)

_configured = False


def _add_app_context(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    """Inject trace_id / turn_id / agent into every log line."""
    if (tid := _trace_id_var.get()) is not None:
        event_dict.setdefault("trace_id", tid)
    if (turn := _turn_id_var.get()) is not None:
        event_dict.setdefault("turn_id", turn)
    if (agent := _agent_var.get()) is not None:
        event_dict.setdefault("agent", agent)
    return event_dict


def _drop_color_message(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    """structlog adds 'color_message'; remove it for clean JSON."""
    event_dict.pop("color_message", None)
    return event_dict


def configure_logging(
    *,
    level: str | None = None,
    json_format: bool = True,
    audit_log_path: str | None = None,
) -> None:
    """Configure structlog + stdlib logging once at startup.

    Idempotent — safe to call multiple times.
    """
    global _configured
    if _configured:
        return

    settings = get_settings()
    log_level = (level or settings.log_level).upper()
    audit_path = Path(audit_log_path or settings.audit_log_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    # Shared structlog processors
    shared_processors: list[Processor] = [
        merge_contextvars,
        _add_app_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        _drop_color_message,
    ]

    if json_format:
        shared_processors.append(structlog.processors.format_exc_info)
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level)),
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Stdlib logging compatibility — captures uvicorn/httpx logs
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    # Quiet noisy libraries
    for noisy in ("httpx", "httpcore", "chromadb", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Audit log: append-only JSONL to disk
    audit_logger = logging.getLogger("clouddash.audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.propagate = False
    if not audit_logger.handlers:
        handler = logging.FileHandler(audit_path, mode="a", encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        audit_logger.addHandler(handler)

    _configured = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a configured structlog logger for the given module name."""
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)


# ---- Trace context API -------------------------------------------------------


def set_trace_context(
    *,
    trace_id: str | None = None,
    turn_id: int | None = None,
    agent: str | None = None,
) -> None:
    """Bind trace metadata into the current async context.

    Call at the start of a request / turn / agent invocation.
    """
    if trace_id is not None:
        _trace_id_var.set(trace_id)
        bind_contextvars(trace_id=trace_id)
    if turn_id is not None:
        _turn_id_var.set(turn_id)
        bind_contextvars(turn_id=turn_id)
    if agent is not None:
        _agent_var.set(agent)
        bind_contextvars(agent=agent)


def clear_trace_context() -> None:
    """Clear all trace metadata. Call at the end of a request."""
    _trace_id_var.set(None)
    _turn_id_var.set(None)
    _agent_var.set(None)
    clear_contextvars()


# ---- Audit log API -----------------------------------------------------------


def write_audit_event(event_type: str, **payload: Any) -> None:
    """Write a structured event to the JSONL audit log.

    This is the §2.3 audit log — every handover, every retrieval, every
    guardrail decision. Append-only. Replayable.
    """
    import json
    from datetime import datetime, timezone

    if not _configured:
        configure_logging()

    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "trace_id": _trace_id_var.get(),
        "turn_id": _turn_id_var.get(),
        "agent": _agent_var.get(),
        **payload,
    }
    audit_logger = logging.getLogger("clouddash.audit")
    audit_logger.info(json.dumps(record, default=str, ensure_ascii=False))
