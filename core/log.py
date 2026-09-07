"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The standardised logger.

Every module logs through ``get_logger(__name__)`` so that names form the package
hierarchy and a single level change reaches all of them.

The rule this exists to serve: **no exception is ignored or swallowed**. A
handler may decide to continue — returning a default, skipping a row — but it may
never do so silently. Something that went wrong and left no trace is the failure
that costs a week to diagnose, and in a governance system it is worse than that:
a value that quietly fell back to a default is a governance claim resting on a
fact nobody checked.

``tests/test_logging_discipline.py`` enforces this by inspecting the AST of every
source file, so the rule cannot rot.

**Every line carries who and which request.** A refusal you cannot trace back to
a request is a refusal you diagnose twice, and in a governance system there is a
second reason: the evidence chain records what was decided, and the log records
what happened around it — a `warrant_resolved` node and the six lines that
preceded it join on the request id or they do not join at all. The identifiers
ride on context variables rather than being threaded through every call, because
a parameter forty functions have to pass is a parameter that will be dropped.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import time
from contextvars import ContextVar
from typing import Any, Dict, Optional, Union

FORMAT = "%(asctime)s %(levelname)-7s %(name)s [%(request_id)s %(principal)s] | %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"

# What a line says when nothing is bound: a scheduler run, a startup message, a
# test. A dash rather than an empty field, so the columns still line up and a
# grep for "no request" has something to match.
UNBOUND = "-"

# One MUTABLE dict per request rather than a variable per field, and the reason
# is a real constraint rather than tidiness. A sync route runs in a threadpool
# with a *copy* of the context, so a `ContextVar.set` inside it is invisible to
# the middleware that resumes afterwards — the access line would say the request
# was anonymous however carefully the route had identified the caller. A copied
# context still points at the same dict object, so a write into the dict crosses
# that boundary while a rebind does not.
_STATE: ContextVar[Dict[str, str]] = ContextVar("maya_log_state")

# An inbound request id is written into every log line this request produces, so
# it is untrusted input reaching a log file. A newline in it forges a whole line;
# a control character corrupts the file for whatever reads it next. So an id that
# is not plainly alphanumeric is REPLACED rather than escaped -- a caller who
# sends one we cannot use gets a fresh one and the header tells them which.
SAFE_ID = re.compile(r"\A[A-Za-z0-9._:-]{1,64}\Z")

REQUEST_HEADER = "x-request-id"


def new_request_id() -> str:
    return secrets.token_hex(8)


def accept_request_id(supplied: Optional[str]) -> str:
    """The caller's correlation id if it is safe to log, otherwise a fresh one.

    Honouring an inbound id is what lets one trace span a gateway, a queue and
    this process. Honouring it *unchecked* is log injection: the value lands in
    a log line, and a newline in it writes a line of somebody else's choosing.
    """
    if supplied and SAFE_ID.match(supplied):
        return supplied
    return new_request_id()


def bind_request(request_id: str) -> Dict[str, str]:
    """Start a new context. Returns the dict, which the caller may keep."""
    state = {"request_id": request_id, "principal": UNBOUND}
    _STATE.set(state)
    return state


def bind_principal(username: Optional[str]) -> None:
    """Name who is acting, into the dict this request already owns.

    A write rather than a rebind, so it is visible to the caller that started
    the context even when this runs in a worker thread.
    """
    state = _STATE.get(None)
    if state is None:
        # Nothing started a context — a scheduler job, a script, a test. Start
        # one rather than dropping the name on the floor.
        state = bind_request(UNBOUND)
    state["principal"] = username or UNBOUND


def _field(name: str) -> str:
    state = _STATE.get(None)
    return (state or {}).get(name, UNBOUND)


def current_request_id() -> str:
    return _field("request_id")


def current_principal() -> str:
    return _field("principal")


class ContextFilter(logging.Filter):
    """Puts the bound request and principal on every record.

    A filter rather than an adapter, because the fields have to reach records
    emitted by code that knows nothing about this — a library warning inside a
    request is exactly the line you want the id on.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        state = _STATE.get(None) or {}
        # `extra` on the call site wins: the access line carries the principal
        # by value because by the time anything inspects that record, the
        # context it was written in is gone.
        if not hasattr(record, "request_id"):
            record.request_id = state.get("request_id", UNBOUND)
        if not hasattr(record, "principal"):
            record.principal = state.get("principal", UNBOUND)
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for anything that ships logs.

    Offered rather than imposed: a human reading a terminal is served worse by
    JSON, and an instance nobody ships logs from should not pay for a format
    only a machine reads.
    """

    def format(self, record: logging.LogRecord) -> str:
        out: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", UNBOUND),
            "principal": getattr(record, "principal", UNBOUND),
            "message": record.getMessage(),
        }
        for field in ("method", "path", "status", "duration_ms"):
            if (value := getattr(record, field, None)) is not None:
                out[field] = value
        if record.exc_info:
            out["exception"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def configure(level: str = "INFO", fmt: str = FORMAT, json_lines: bool = False) -> None:
    """Install the standard format and the context filter. Idempotent.

    The filter goes on the HANDLER rather than on a logger, because a filter on
    a logger does not run for records that propagate up from its children — and
    every logger here is a child of the root. That distinction cost an afternoon
    the first time somebody met it.
    """
    logging.basicConfig(level=str(level).upper(), format=fmt, datefmt=DATEFMT,
                        force=True)
    context = ContextFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(context)
        if json_lines:
            handler.setFormatter(JsonFormatter())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def swallowed(logger: logging.Logger, exc: BaseException, action: str,
              detail: Optional[Any] = None,
              level: Union[int, str] = logging.WARNING) -> None:
    """Record a handled exception that the caller has chosen to recover from.

    Use this at every ``except`` that returns a default or skips a value. It is
    deliberately noisy at WARNING: recovering from an error is a decision, and a
    decision that never appears in a log is indistinguishable from a bug.

    `level` accepts the name as well as the number, because two callers assumed
    it did and the assumption was invisible. `core/execution/sandbox.py` passed
    `"warning"` and `"error"` into the terminal handlers of the sandboxed child
    — so `level >= logging.ERROR` raised TypeError, the child died with that
    instead of a log line, and the ONE line explaining why a governed model
    execution was killed was never written. An operator investigating found a
    TypeError inside the logging helper. A helper whose contract is "record
    what you recovered from" must not itself be a way to lose the record.
    """
    if isinstance(level, str):
        level = logging.getLevelName(level.upper())
        if not isinstance(level, int):
            level = logging.WARNING
    logger.log(level, "%s — recovered from %s: %s%s", action, type(exc).__name__, exc,
               f" ({detail})" if detail is not None else "", exc_info=level >= logging.ERROR)
