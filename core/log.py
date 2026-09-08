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
import threading
import time
from collections import deque
from contextvars import ContextVar
from typing import Any, Deque, Dict, List, Optional, Tuple, Union

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

# This module's own logger, for the one thing in here that can fail: capturing
# a line into the ring. Built directly rather than through `get_logger` because
# that function is defined below it, and a module cannot be a client of itself
# at import time.
logger = logging.getLogger(__name__)


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


# A value that must never reach a screen, whatever wrote it. Nothing in this
# platform logs a credential deliberately — but "deliberately" is the operative
# word, and a live log viewer turns every accidental one into something a
# browser renders. The pattern is applied on the way INTO the ring rather than
# on the way out, so a redaction cannot be skipped by a caller who forgets.
# The optional scheme in the middle is what makes `Authorization: Bearer eyJ…`
# work: without it the pattern matched "Bearer" as the value and left the
# actual token in the line, which is the failure mode a redaction must not
# have — it looks redacted.
#
# Only `name=value` and `name: value`. An earlier version also matched
# "<name> is <value>", and the first real line it met was the start-up warning
# "the session cookie is signed with a PUBLISHED secret" — which it rendered as
# "the session cookie is [redacted] with a PUBLISHED secret", blanking the verb
# of a security warning and leaving a reader to wonder what had been hidden
# from them. A redaction that eats prose costs more than the one credential it
# might have caught, because it teaches people to distrust the whole screen.
_SECRETISH = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|bearer|"
    r"cookie|session|private[_-]?key)\b"
    r"(\s*[=:]\s*)((?:bearer|basic|token)\s+)?(\S+)")


def redact(text: str) -> str:
    """Blank anything that names itself a credential. Belt, not braces."""
    return _SECRETISH.sub(
        lambda m: f"{m.group(1)}{m.group(2)}{m.group(3) or ''}[redacted]", text)


class Ring(logging.Handler):
    """The last N log lines, in memory, for the live viewer to read.

    A handler rather than a file tail, and the reason is operational rather
    than aesthetic. This platform is run in places where the process writes to
    stdout and something else owns the file — a container, a supervisor, a
    journal — so "read the log file" is a thing the server frequently cannot
    do, and a viewer built on it shows an empty page on exactly the deployments
    that most need one. A handler sees every record the moment it is emitted,
    whatever the process does with it afterwards.

    Bounded, and bounded by construction: a `deque(maxlen=)` drops the oldest
    line rather than growing, so a process that logs steadily for a month uses
    the same memory as one that started a minute ago. The viewer says which
    lines it can no longer show rather than pretending the buffer is the
    history — a log viewer that silently loses the beginning is one that
    answers "when did this start" wrongly.

    Each line is rendered to plain data AT CAPTURE. Holding the LogRecord would
    keep every argument object alive — a whole result set, a database row, an
    exception's frames — for as long as the line stays in the ring, which turns
    a diagnostic aid into a leak.
    """

    def __init__(self, capacity: int = 2000) -> None:
        super().__init__()
        self.capacity = max(1, int(capacity))
        self._lines: Deque[Dict[str, Any]] = deque(maxlen=self.capacity)
        self._lock = threading.Lock()
        # Whether THIS thread is already inside emit. Recording a failed
        # capture is a log call, and this handler sits on the root logger, so
        # without the guard the report of the failure would re-enter the
        # handler that just failed — once per frame, until the stack ended.
        self._inside = threading.local()
        self._seq = 0
        self.dropped = 0

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(self._inside, "flag", False):
            # Re-entered while reporting an earlier failure. Counted rather
            # than kept: the report still reaches every other handler, and the
            # count is what tells a reader this window is incomplete.
            with self._lock:
                self.dropped += 1
            return
        try:
            line = {
                "level": record.levelname,
                "logger": record.name,
                "request_id": getattr(record, "request_id", UNBOUND),
                "principal": getattr(record, "principal", UNBOUND),
                "message": redact(record.getMessage()),
                "created": record.created,
                "ts": time.strftime(DATEFMT, time.localtime(record.created)),
            }
            for field in ("method", "path", "status", "duration_ms"):
                if (value := getattr(record, field, None)) is not None:
                    line[field] = value
            if record.exc_info:
                line["exception"] = redact(self.format_exception(record))
        except Exception as exc:
            # A handler that raises is a handler that can take the process down
            # through logging's own error path, so this recovers. It does not
            # do so silently: the platform rule is that a handler may decide to
            # carry on but may never make the decision invisible, and a viewer
            # quietly missing lines is exactly the kind of incompleteness that
            # rule exists to prevent.
            #
            # `handleError` is logging's own answer here and is not used,
            # because it writes to stderr — the one place a deployment that
            # needs this screen may not have. The re-entrancy guard is what
            # makes the ordinary call safe.
            with self._lock:
                self.dropped += 1
            self._inside.flag = True
            try:
                swallowed(logger, exc, f"captured a log line from {record.name}",
                          detail="the line is counted as dropped and is not in "
                                 "the window; every other handler still has it")
            finally:
                self._inside.flag = False
            return
        with self._lock:
            self._seq += 1
            line["seq"] = self._seq
            if len(self._lines) == self.capacity:
                self.dropped += 1
            self._lines.append(line)

    def format_exception(self, record: logging.LogRecord) -> str:
        if record.exc_info is None:
            return ""
        return logging.Formatter().formatException(record.exc_info)

    def since(self, cursor: int = 0, limit: int = 500) -> Tuple[List[Dict[str, Any]], int, int]:
        """Lines after `cursor`, the new cursor, and how many were missed.

        The third value is the honest part. A caller that asks again after the
        ring has turned over more than `capacity` times cannot be given what it
        missed, and saying so lets the screen show a gap rather than a
        continuous stream that silently isn't one.
        """
        with self._lock:
            lines = list(self._lines)
            latest, oldest = self._seq, (lines[0]["seq"] if lines else self._seq + 1)
        missed = max(0, oldest - cursor - 1) if cursor else 0
        fresh = [line for line in lines if line["seq"] > cursor]
        if len(fresh) > limit:
            missed += len(fresh) - limit
            fresh = fresh[-limit:]
        return fresh, latest, missed

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {"held": len(self._lines), "capacity": self.capacity,
                    "latest": self._seq, "dropped": self.dropped}

    def resize(self, capacity: int) -> None:
        """Change how many lines are held, keeping the newest.

        Configuration is read after this module is imported — start-up itself
        logs — so the ring exists at the default and is resized once the
        deployment's number is known. Rebuilding the deque rather than mutating
        `maxlen`, which is read-only, and keeping the tail rather than the head
        because a shrink should drop the oldest lines, exactly as an overflow
        does.
        """
        capacity = max(1, int(capacity))
        with self._lock:
            self.capacity = capacity
            kept = deque(self._lines, maxlen=capacity)
            self.dropped += max(0, len(self._lines) - len(kept))
            self._lines = kept

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()


#: The one ring the viewer reads. Created here rather than in the app so that a
#: line logged during start-up — before any route exists — is already in it.
LIVE = Ring()


def configure(level: str = "INFO", fmt: str = FORMAT, json_lines: bool = False,
              ring: Optional[Ring] = None) -> None:
    """Install the standard format and the context filter. Idempotent.

    The filter goes on the HANDLER rather than on a logger, because a filter on
    a logger does not run for records that propagate up from its children — and
    every logger here is a child of the root. That distinction cost an afternoon
    the first time somebody met it.
    """
    logging.basicConfig(level=str(level).upper(), format=fmt, datefmt=DATEFMT,
                        force=True)
    context = ContextFilter()
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(context)
        if json_lines:
            handler.setFormatter(JsonFormatter())
    # The ring goes on last and keeps the filter too, because it reads
    # `request_id` off the record and `basicConfig(force=True)` has just
    # removed every handler including this one.
    live = LIVE if ring is None else ring
    live.addFilter(context)
    if live not in root.handlers:
        root.addHandler(live)


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
