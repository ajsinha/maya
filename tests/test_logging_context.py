"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Which request, and whose.

Every line already went through one logger with one format. What no line said
was which request produced it — so a refusal reported by a user was a refusal
somebody reproduced before they could read about it, and two people using the
platform at once produced one interleaved stream with nothing to separate them.

There is a second reason particular to this system. The evidence chain records
what was *decided*; the log records what happened around it. A `warrant_resolved`
node and the six lines preceding it join on the request id, or they do not join
at all — and "what else was this process doing when it refused me" is the first
question of any real incident.

The sharp edge is that an inbound id is untrusted input on its way to a log file.
"""
from __future__ import annotations

import json
import logging

import pytest

from core import log


@pytest.fixture(autouse=True)
def restore():
    """Each test binds context; none of them may leak it to the next."""
    yield
    log.bind_request(log.UNBOUND)
    log.bind_principal(None)


class TestAnInboundIdIsCheckedBeforeItIsLogged:
    """It reaches a log file, so it is untrusted input to whatever reads that."""

    @pytest.mark.parametrize("hostile", [
        "trace\nWARNING forged line",          # a whole forged entry
        "trace\r\nERROR everything is fine",
        "trace\tid",
        "a" * 65,                              # unbounded length
        "id with spaces",
        "id;rm -rf /",
        "",
    ])
    def test_an_unusable_id_is_replaced_rather_than_escaped(self, hostile):
        out = log.accept_request_id(hostile)
        assert out != hostile
        assert log.SAFE_ID.match(out)

    @pytest.mark.parametrize("fine", [
        "trace-42", "01HQ8Z.9F:AB", "a", "req_9", "A" * 64,
    ])
    def test_a_safe_id_is_honoured(self, fine):
        """Honouring it is what lets one trace span a gateway, a queue and this
        process; the check is what stops that being an injection."""
        assert log.accept_request_id(fine) == fine

    def test_a_missing_id_gets_a_fresh_one(self):
        assert log.SAFE_ID.match(log.accept_request_id(None))

    def test_two_fresh_ids_differ(self):
        assert log.new_request_id() != log.new_request_id()


class TestTheThreadpoolBoundary:
    """The constraint that decided the shape of this module.

    A sync route runs in a threadpool with a *copy* of the context, so a
    `ContextVar.set` inside it is invisible to the middleware that resumes
    afterwards — the access line would have said every request was anonymous
    however carefully the route identified the caller. It did, until this was
    asserted. A copied context still points at the same dict, so a write into
    the dict crosses the boundary while a rebind does not.
    """

    def test_a_write_from_another_thread_is_visible_here(self):
        import concurrent.futures
        import contextvars
        log.bind_request("trace-42")

        def in_worker():
            log.bind_principal("d.raman")
            return log.current_principal()

        ctx = contextvars.copy_context()
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            assert pool.submit(ctx.run, in_worker).result() == "d.raman"
        assert log.current_principal() == "d.raman", (
            "a write from the worker must be visible to whoever started the "
            "context, or the access line cannot say who caused the request")

    def test_a_rebind_from_another_thread_is_not(self):
        """Stated so the reason for the dict is not lost to a later tidy-up."""
        import concurrent.futures
        import contextvars
        log.bind_request("trace-42")

        def in_worker():
            log.bind_request("something-else")   # a rebind, not a write

        ctx = contextvars.copy_context()
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            pool.submit(ctx.run, in_worker).result()
        assert log.current_request_id() == "trace-42"


class TestTheContextReachesEveryRecord:
    def test_a_line_carries_the_bound_request_and_principal(self, caplog):
        # Deliberately not calling `configure` here: it installs the root
        # handler with force=True, which removes the one caplog added, and the
        # test would then assert on an empty list. The filter is what is under
        # test; where it is installed is the test below.
        log.bind_request("trace-42")
        log.bind_principal("a.mehta")
        with caplog.at_level(logging.INFO):
            log.get_logger("probe").info("something happened")
        record = caplog.records[-1]
        log.ContextFilter().filter(record)
        assert record.request_id == "trace-42"
        assert record.principal == "a.mehta"

    def test_nothing_bound_reads_as_a_dash_rather_than_a_blank(self):
        """So the columns still line up, and a search for lines with no request
        has something to match."""
        assert log.current_request_id() == log.UNBOUND
        assert log.current_principal() == log.UNBOUND

    def test_the_filter_is_installed_on_the_handler_not_the_logger(self):
        """A filter on a logger does not run for records propagating up from its
        children, and every logger here is a child of the root."""
        log.configure("INFO")
        handlers = logging.getLogger().handlers
        assert handlers
        assert any(isinstance(f, log.ContextFilter)
                   for h in handlers for f in h.filters)


class TestTheJsonFormat:
    def test_one_object_per_line_with_the_context_in_it(self):
        log.bind_request("trace-42")
        log.bind_principal("d.raman")
        record = logging.LogRecord("probe", logging.WARNING, __file__, 1,
                                   "refused (%s)", ("blocked",), None)
        log.ContextFilter().filter(record)
        out = json.loads(log.JsonFormatter().format(record))
        assert out["request_id"] == "trace-42" and out["principal"] == "d.raman"
        assert out["level"] == "WARNING" and out["message"] == "refused (blocked)"
        assert out["ts"].endswith("Z")

    def test_access_fields_appear_only_when_present(self):
        plain = logging.LogRecord("p", logging.INFO, __file__, 1, "hi", (), None)
        log.ContextFilter().filter(plain)
        assert "status" not in json.loads(log.JsonFormatter().format(plain))

        access = logging.LogRecord("p", logging.INFO, __file__, 1, "hi", (), None)
        access.method, access.path = "POST", "/api/v1/models"
        access.status, access.duration_ms = 201, 12.4
        log.ContextFilter().filter(access)
        out = json.loads(log.JsonFormatter().format(access))
        assert out["status"] == 201 and out["path"] == "/api/v1/models"

    def test_an_exception_is_carried_rather_than_lost(self):
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            record = logging.LogRecord("p", logging.ERROR, __file__, 1, "failed",
                                       (), sys.exc_info())
        log.ContextFilter().filter(record)
        out = json.loads(log.JsonFormatter().format(record))
        assert "ValueError: boom" in out["exception"]


class TestOverHttp:
    def test_the_id_comes_back_so_a_caller_can_quote_it(self, client):
        r = client.get("/api/v1/models")
        assert log.SAFE_ID.match(r.headers[log.REQUEST_HEADER])

    def test_a_supplied_id_is_echoed(self, client):
        r = client.get("/api/v1/models", headers={log.REQUEST_HEADER: "trace-42"})
        assert r.headers[log.REQUEST_HEADER] == "trace-42"

    def test_a_forged_id_is_replaced_and_the_caller_told_which(self, client):
        r = client.get("/api/v1/models",
                       headers={log.REQUEST_HEADER: "x" * 200})
        assert r.headers[log.REQUEST_HEADER] != "x" * 200
        assert log.SAFE_ID.match(r.headers[log.REQUEST_HEADER])

    def test_every_response_carries_one_including_a_refusal(self, client):
        r = client.get("/api/v1/models/does.not.exist")
        assert r.status_code == 404
        assert r.headers[log.REQUEST_HEADER]

    def test_two_requests_get_different_ids(self, client):
        first = client.get("/api/v1/models").headers[log.REQUEST_HEADER]
        second = client.get("/api/v1/models").headers[log.REQUEST_HEADER]
        assert first != second

    def _access_line(self, records, path):
        return next(r for r in reversed(records)
                    if getattr(r, "path", None) == path)

    def test_the_access_line_names_who_caused_it(self, client, caplog):
        with caplog.at_level(logging.INFO):
            client.get("/api/v1/models")
        line = self._access_line(caplog.records, "/api/v1/models")
        assert line.principal == "admin"
        assert line.status == 200 and line.method == "GET"

    def test_the_principal_does_not_leak_between_requests(self, client, caplog):
        """A worker is reused, and a principal left bound would attribute the
        next caller's lines to the last one. Asserted on the access line rather
        than on the context, because the context is gone by the time a test can
        look at it — which is how this test passed for the wrong reason first."""
        with caplog.at_level(logging.INFO):
            client.get("/api/v1/models")        # authenticates as admin
            client.get("/health")               # authenticates as nobody
        assert self._access_line(caplog.records, "/health").principal == log.UNBOUND

    def test_a_refused_request_is_logged_at_a_level_that_shows(self, client, caplog):
        with caplog.at_level(logging.WARNING):
            client.get("/api/v1/models/does.not.exist")
        assert any("/api/v1/models/does.not.exist" in r.getMessage()
                   for r in caplog.records), \
            "a refusal must produce a line naming the path that was refused"
