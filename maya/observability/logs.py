"""
Logging configuration (§20): text or structured JSON, one event per line,
to stdout and a rotating file. Switching format changes every line without
touching a call site — the same arrangement as DishtaYantra's log_config.

Two things beyond the format, both asked for by §20 and neither of them a call
site's business:

**Every line carries who and what.** §20 wants request id, trace id, actor and
object reference on every event. Trace and span id come from the trace context;
the other two have to be *bound* somewhere, because a logging call deep in a
service has no idea who the request belongs to. ``bind`` puts them on a
context variable and the formatter reads it: the HTTP middleware binds the
request id and the path, the job runner binds the job's owner and reference, and
the *unit of work* binds the actor — not the authentication dependency, because
FastAPI resolves a synchronous dependency in a worker thread whose context copy
is thrown away. The alternative — threading an actor through every signature
that might log — is the reason structured logging usually stays a plan.

**Levels change at runtime, per module.** Debugging a resolution problem on a
running instance means turning up ``maya.resolution`` without drowning in
``maya.persistence``, and without a restart that loses the state you are trying
to look at. ``set_level`` does that and ``levels`` says what is currently
overridden, so an override can be seen and undone rather than left behind.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import contextlib
import json
import logging
import logging.handlers
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterator

LEVELS = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG")
FIELDS = ("request_id", "actor", "object_ref", "channel")

_CONTEXT: ContextVar[dict[str, str]] = ContextVar("maya_log_context", default={})
_OVERRIDES: dict[str, str] = {}


def bind(**fields: Any) -> dict[str, str]:
    """Add fields to every log line from here on in this task. Returns what was replaced."""
    before = _CONTEXT.get()
    merged = {**before, **{k: str(v) for k, v in fields.items() if v is not None}}
    _CONTEXT.set(merged)
    return before


def restore(fields: dict[str, str]) -> None:
    """Put back what ``bind`` replaced. A plain set rather than a token reset, because the
    caller that binds and the caller that restores may be different frames."""
    _CONTEXT.set(dict(fields))


def context() -> dict[str, str]:
    return dict(_CONTEXT.get())


@contextlib.contextmanager
def bound(**fields: Any) -> Iterator[None]:
    """Bind for the duration of a block, restoring what was there before."""
    token = _CONTEXT.set({**_CONTEXT.get(), **{k: str(v) for k, v in fields.items() if v}})
    try:
        yield
    finally:
        _CONTEXT.reset(token)


def set_level(module: str, level: str) -> dict[str, str]:
    """Set one logger's level at runtime; ``level='inherit'`` removes the override.

    ``module`` is a dotted logger name (``maya.resolution``, ``maya.jobs.queue``) and
    applies to everything under it. Overrides are per process: with several web processes
    or a worker fleet, each one has its own, which is a limitation worth knowing before
    concluding that a module is quiet.
    """
    name = module.strip() or "maya"
    wanted = level.strip().upper()
    if wanted in ("INHERIT", "", "NONE", "UNSET"):
        _OVERRIDES.pop(name, None)
        logging.getLogger(name).setLevel(logging.NOTSET)
        return levels()
    if wanted not in LEVELS:
        from maya.core.errors import ValidationFailed

        raise ValidationFailed(
            f"'{level}' is not a log level; expected one of {', '.join(LEVELS)} or 'inherit'",
            level=level,
            allowed=list(LEVELS),
        )
    logging.getLogger(name).setLevel(wanted)
    _OVERRIDES[name] = wanted
    return levels()


def levels() -> dict[str, str]:
    """The root level and every module override in force in this process."""
    return {"": logging.getLevelName(logging.getLogger().getEffectiveLevel()), **_OVERRIDES}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        from maya.observability.tracing import current

        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        ctx = current()
        if ctx is not None:
            payload.update(trace_id=ctx.trace_id, span_id=ctx.span_id)
        payload.update({k: v for k, v in _CONTEXT.get().items() if k in FIELDS})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """The human format, with whatever of the bound context is set appended."""

    def __init__(self) -> None:
        super().__init__("%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        bits = [f"{k}={v}" for k, v in _CONTEXT.get().items() if k in FIELDS]
        return line + ("  [" + " ".join(bits) + "]" if bits else "")


def configure(level: str = "INFO", fmt: str = "text", logfile: str | None = None) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())
    _OVERRIDES.clear()
    formatter: logging.Formatter = JsonFormatter() if fmt == "json" else TextFormatter()
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
    if logfile:
        Path(logfile).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            logfile, maxBytes=20 * 2**20, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
