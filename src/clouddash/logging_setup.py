from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

# context vars so every log line knows where it is without passing context around
_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_turn_id: ContextVar[int] = ContextVar("turn_id", default=0)
_agent: ContextVar[str] = ContextVar("agent", default="")

_audit_path: str | None = None


def setup_logging(log_level: str = "INFO", audit_log_path: str | None = None) -> None:
    global _audit_path
    _audit_path = audit_log_path

    if audit_log_path:
        Path(audit_log_path).parent.mkdir(parents=True, exist_ok=True)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _inject_trace_context,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    )


def _inject_trace_context(logger: Any, method: str, event_dict: dict) -> dict:
    if tid := _trace_id.get():
        event_dict["trace_id"] = tid
    if turn := _turn_id.get():
        event_dict["turn_id"] = turn
    if ag := _agent.get():
        event_dict["agent"] = ag
    return event_dict


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)


def set_trace_context(trace_id: str = "", turn_id: int = 0, agent: str = "") -> None:
    _trace_id.set(trace_id)
    _turn_id.set(turn_id)
    _agent.set(agent)


def clear_trace_context() -> None:
    _trace_id.set("")
    _turn_id.set(0)
    _agent.set("")


def write_audit_event(event_type: str, **payload: Any) -> None:
    """Append a structured event to the JSONL audit log."""
    if not _audit_path:
        return
    record = {
        "ts": datetime.now(tz=timezone.utc).isoformat(),
        "event": event_type,
        "trace_id": _trace_id.get(),
        "turn_id": _turn_id.get(),
        "agent": _agent.get(),
        **payload,
    }
    try:
        with open(_audit_path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:  # yeah I know, fix later
        pass


def read_trace_events(trace_id: str) -> list[dict]:
    if not _audit_path or not Path(_audit_path).exists():
        return []
    events = []
    with open(_audit_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("trace_id") == trace_id:
                    events.append(rec)
            except json.JSONDecodeError:
                pass
    return events
