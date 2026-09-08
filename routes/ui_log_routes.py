"""
MAYA — the live log.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What the process is doing, right now, on a screen.

Until this existed, the only way to see MAYA's log was to be the person who
started the process — a terminal, a `docker logs`, a `journalctl`. That is
fine for a developer and useless for everybody else: the operator who is asked
why a warrant resolution refused, the tester who wants to know what the server
made of the call they just sent, the administrator watching the nightly batch.
All three ended up asking a developer to read a terminal to them.

Three things this deliberately is NOT.

It is **not the evidence chain**. Evidence records what was decided and is
immutable, hash-linked and exportable; this is a rolling window of what
happened around those decisions, and it ages out. Nobody should ever cite it
as a governance record, so the screen says so.

It is **not a control**. The viewer reads. It cannot change the level, clear
the buffer or write a line. A screen that can quieten the log is a screen that
can hide what it is showing you.

It is **not a file tail**. The ring lives in the process, so it works
identically whether the deployment writes to a file, to stdout, to a journal or
to nothing at all — which is the case that matters, because the deployments
that most need a log viewer are exactly the ones where the file belongs to
somebody else.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List

from fastapi import Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse

from core.log import LIVE, get_logger
from routes.base import Routes

logger = get_logger(__name__)

#: Ordered loudest-last, so "at least WARNING" is a slice rather than a set.
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

#: How long a stream waits between looks at the ring. Short enough that a line
#: appears while you are still looking at the thing that produced it; long
#: enough that ten open tabs are not ten busy loops.
POLL_SECONDS = 0.7

#: A stream is closed at this age even if the browser is still holding it. An
#: EventSource reconnects by itself and resumes from its cursor, so the only
#: thing a person notices is nothing — and the server stops accumulating
#: connections from tabs somebody left open on a laptop lid three days ago.
MAX_STREAM_SECONDS = 30 * 60


def _at_least(level: str) -> List[str]:
    """The level and everything louder. An unknown name means no filter — a
    filter nobody can spell is one that silently hides lines."""
    upper = (level or "").upper()
    if upper not in LEVELS:
        return list(LEVELS)
    return list(LEVELS[LEVELS.index(upper):])


#: Paths whose access lines are noise on this screen. The server logs every
#: request, which is right — but one page load is thirty font, stylesheet and
#: script lines, and thirty of those bury the one line somebody came to read.
#: Hidden by DEFAULT and by a switch that says so, never silently: a log viewer
#: that drops lines without telling you is one you cannot trust to be complete.
STATIC = ("/static/", "/favicon", "/api/v1/logs/stream")


def _is_noise(line: Dict[str, Any]) -> bool:
    path = line.get("path") or ""
    return any(path.startswith(prefix) for prefix in STATIC)


def _matches(line: Dict[str, Any], levels: List[str], logger_name: str,
             request_id: str, principal: str, contains: str,
             quiet: bool = False) -> bool:
    if quiet and _is_noise(line):
        return False
    if line["level"] not in levels:
        return False
    if logger_name and not line["logger"].startswith(logger_name):
        return False
    if request_id and line["request_id"] != request_id:
        return False
    if principal and line["principal"] != principal:
        return False
    if contains:
        haystack = f"{line['logger']} {line['message']} {line.get('exception', '')}"
        if contains.lower() not in haystack.lower():
            return False
    return True


class LogRoutes(Routes):
    def register(self) -> None:
        api = self.api

        def _page(after: int, level: str, logger_name: str, request_id: str,
                  principal: str, contains: str, limit: int, quiet: bool):
            lines, cursor, missed = LIVE.since(after, limit=max(1, min(limit, 2000)))
            levels = _at_least(level)
            kept = [line for line in lines
                    if _matches(line, levels, logger_name, request_id,
                                principal, contains, quiet)]
            return {"lines": kept, "cursor": cursor, "missed": missed,
                    "considered": len(lines), **LIVE.snapshot()}

        # ------------------------------------------------------------ screen
        @self.app.get("/admin/logs", response_class=HTMLResponse, tags=["ui"])
        def logs_page(request: Request):
            """The live log. Follows by default; filters without reloading."""
            if (refusal := self.page_gate(request, "log:read")) is not None:
                return refusal
            state = LIVE.snapshot()
            # The first screenful is rendered by the SERVER, and the stream
            # picks up from its last sequence number. Two reasons, both real.
            # A page that is empty until a socket connects looks broken for the
            # half-second before it isn't, and this one is opened by somebody
            # who already suspects something is wrong. And where a proxy eats
            # `text/event-stream` — which is exactly the deployment nobody
            # discovers until they need the log — the screen still shows the
            # window rather than nothing at all.
            window, cursor, _ = LIVE.since(0, limit=LIVE.capacity)
            recent = [line for line in window if not _is_noise(line)][-200:]
            return self.page(
                request, "admin_logs.html",
                levels=list(LEVELS), ring=state,
                initial=recent, cursor=cursor,
                # The loggers actually present, so the filter offers what this
                # instance has rather than a list somebody maintains by hand.
                loggers=sorted({line["logger"].split(".")[0]
                                for line in LIVE.since(0, limit=LIVE.capacity)[0]}),
                # `may` is not passed: the brand context already carries the
                # permissions this principal holds, and `page()` refuses a
                # collision rather than letting one reader silently win.
                here="/admin/logs")

        # --------------------------------------------------------------- API
        @self.app.get(f"{api}/logs", tags=["logs"])
        def recent(request: Request, after: int = 0, level: str = "",
                   logger_name: str = "", request_id: str = "",
                   principal: str = "", contains: str = "", limit: int = 500,
                   quiet: bool = True):
            """Lines after `after`. The reply's `cursor` is the next `after`.

            `missed` is the honest field: if the ring turned over more than it
            holds since the last call, the lines in between are gone, and a
            viewer that did not say so would be showing a continuous stream
            that is not one.
            """
            self.authorise(request, "log:read")
            return _page(after, level, logger_name, request_id,
                         principal, contains, limit, quiet)

        @self.app.get(f"{api}/logs/stream", tags=["logs"])
        async def stream(request: Request, after: int = 0, level: str = "",
                         logger_name: str = "", request_id: str = "",
                         principal: str = "", contains: str = "",
                         quiet: bool = True):
            """Server-sent events, one per log line, until the client goes away.

            `async` rather than a sync route in a worker thread, and that is
            load-bearing: a sync streaming route holds one of the threadpool's
            threads for as long as the tab is open, so four people watching the
            log would starve the server that is producing it. Here a waiting
            stream holds nothing but a sleeping coroutine.
            """
            who = self.authorise(request, "log:read")
            levels = _at_least(level)
            # An EventSource resuming after a drop sends its last id; honour it
            # over the query string, because the query string is what the tab
            # was opened with and the header is where it actually got to.
            resume = request.headers.get("last-event-id") or ""
            cursor = int(resume) if resume.isdigit() else after
            logger.info("log stream opened by %s from cursor %d",
                        (who or {}).get("username"), cursor)

            async def events():
                nonlocal cursor
                waited = 0.0
                while True:
                    if await request.is_disconnected():
                        return
                    lines, cursor, missed = LIVE.since(cursor, limit=500)
                    if missed:
                        yield ("event: gap\ndata: "
                               + json.dumps({"missed": missed}) + "\n\n")
                    for line in lines:
                        if not _matches(line, levels, logger_name,
                                        request_id, principal, contains, quiet):
                            continue
                        yield f"id: {line['seq']}\ndata: " + json.dumps(line) + "\n\n"
                    if waited >= MAX_STREAM_SECONDS:
                        yield ("event: closing\ndata: "
                               + json.dumps({"why": "stream age limit; "
                                                    "reconnecting"}) + "\n\n")
                        return
                    # A comment line is a heartbeat: it keeps a proxy that
                    # times out an idle connection from cutting a stream that
                    # is merely quiet, which on a well-behaved server is most
                    # of the time. The client is disconnected mid-sleep in the
                    # ordinary case; the CancelledError that follows belongs to
                    # the server, which is why it is not caught here.
                    yield ": keep-alive\n\n"
                    await asyncio.sleep(POLL_SECONDS)
                    waited += POLL_SECONDS

            return StreamingResponse(
                events(), media_type="text/event-stream",
                headers={"Cache-Control": "no-store",
                         # Nginx buffers a proxied response by default, which
                         # turns a live stream into one long silence followed
                         # by everything at once.
                         "X-Accel-Buffering": "no"})

        @self.app.get(f"{api}/logs/download", response_class=PlainTextResponse,
                      tags=["logs"])
        def download(request: Request, level: str = "", logger_name: str = "",
                     request_id: str = "", principal: str = "",
                     contains: str = "", quiet: bool = True):
            """Everything the ring holds that matches, as plain text.

            The thing an operator actually does with a log they are looking at
            is send it to somebody. Offered in the standard line format rather
            than JSON, because the person receiving it will read it.
            """
            self.authorise(request, "log:read")
            levels = _at_least(level)
            lines, _, _ = LIVE.since(0, limit=LIVE.capacity)
            body = "\n".join(
                f"{line['ts']} {line['level']:<7} {line['logger']} "
                f"[{line['request_id']} {line['principal']}] | {line['message']}"
                + (f"\n{line['exception']}" if line.get("exception") else "")
                for line in lines
                if _matches(line, levels, logger_name, request_id, principal,
                            contains, quiet))
            state = LIVE.snapshot()
            header = (f"# MAYA log — {state['held']} line(s) held of "
                      f"{state['capacity']}, {state['dropped']} aged out.\n"
                      f"# This is a rolling window, not the evidence chain.\n")
            return PlainTextResponse(
                header + body + "\n",
                headers={"Content-Disposition":
                         'attachment; filename="maya-log.txt"'})


__all__ = ["LEVELS", "LogRoutes"]
