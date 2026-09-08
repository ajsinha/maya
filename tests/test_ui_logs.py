"""
MAYA — the live log viewer.

The screen exists because reading MAYA's log meant being the person who started
the process. These tests hold the three things that make it worth having and
the two that stop it being a liability.

Worth having: it shows what the process actually wrote; it says when lines have
aged out rather than presenting a gap as continuity; and a filter narrows what
the SERVER sends rather than what the browser displays.

Not a liability: it needs a permission, and anything that names itself a
credential is blanked on the way into the buffer rather than on the way out.
"""
from __future__ import annotations

import logging

import pytest

from core.log import LIVE, Ring, configure, redact
from tests.api_helpers import login


@pytest.fixture
def ring():
    """A ring of our own, wired to a logger nothing else uses."""
    handler = Ring(capacity=5)
    handler.addFilter(__import__("core.log", fromlist=["ContextFilter"]).ContextFilter())
    logger = logging.getLogger("maya.test.ring")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger, handler


class TestTheRingIsBounded:
    def test_it_holds_the_newest_and_drops_the_oldest(self, ring):
        logger, handler = ring
        for i in range(12):
            logger.info("line %d", i)
        lines, cursor, _ = handler.since(0)
        assert len(lines) == 5, "the ring holds what it says it holds"
        assert [line["message"] for line in lines] == [f"line {i}" for i in range(7, 12)]
        assert cursor == 12, "the cursor counts everything written, not what survived"

    def test_a_reader_that_fell_behind_is_told_so(self, ring):
        """The honest field. A viewer given lines 8-12 after asking from 2, with
        no word that 3-7 are gone, is showing a continuous stream that is not
        one — and somebody reads that gap as 'nothing happened'."""
        logger, handler = ring
        for i in range(12):
            logger.info("line %d", i)
        _, _, missed = handler.since(2)
        assert missed == 5

    def test_nothing_is_missed_when_nothing_was(self, ring):
        logger, handler = ring
        logger.info("one")
        logger.info("two")
        lines, cursor, missed = handler.since(0)
        assert missed == 0 and len(lines) == 2
        assert handler.since(cursor)[0] == [], "asked again, nothing new"

    def test_a_resize_keeps_the_newest(self, ring):
        logger, handler = ring
        for i in range(5):
            logger.info("line %d", i)
        handler.resize(2)
        assert [line["message"] for line in handler.since(0)[0]] == ["line 3", "line 4"]
        assert handler.snapshot()["capacity"] == 2


class TestWhatIsCapturedIsData:
    def test_the_record_is_not_held(self, ring):
        """A LogRecord keeps every argument alive for as long as it is held. A
        ring of two thousand of those is a leak wearing a diagnostic's clothes."""
        logger, handler = ring
        big = {"rows": list(range(1000))}
        logger.info("processed %s", big)
        line = handler.since(0)[0][0]
        assert isinstance(line, dict)
        assert set(line) >= {"seq", "level", "logger", "message", "request_id",
                             "principal", "ts"}
        assert all(isinstance(v, (str, int, float)) for v in line.values())

    def test_the_request_and_principal_ride_along(self, ring):
        from core import log

        logger, handler = ring
        log.bind_request("req-42")
        log.bind_principal("a.mehta")
        logger.warning("refused")
        line = handler.since(0)[0][0]
        assert line["request_id"] == "req-42" and line["principal"] == "a.mehta"

    def test_a_traceback_is_kept_as_text(self, ring):
        logger, handler = ring
        try:
            int("no such featureset")
        except ValueError:
            logger.exception("could not resolve")
        line = handler.since(0)[0][0]
        assert "ValueError" in line["exception"]
        assert "no such featureset" in line["exception"]


class TestNothingThatNamesItselfACredentialIsShown:
    """Nothing logs a password deliberately. 'Deliberately' is the word doing
    the work: a live viewer renders every accidental one in a browser."""

    @pytest.mark.parametrize("written,gone", [
        ("password: hunter2", "hunter2"),
        ("api_key=sk-live-abcdef", "sk-live-abcdef"),
        ("Authorization: Bearer eyJhbGci", "eyJhbGci"),
    ])
    def test_it_is_blanked(self, written, gone):
        cleaned = redact(written)
        assert gone not in cleaned
        assert "[redacted]" in cleaned

    def test_it_is_blanked_on_the_way_in(self, ring):
        """On capture rather than on render, so no reader can skip it — the
        download, the stream and the JSON all get the same line."""
        logger, handler = ring
        logger.info("bound with password: hunter2")
        assert "hunter2" not in handler.since(0)[0][0]["message"]

    def test_an_ordinary_sentence_survives(self):
        assert redact("the warrant was refused") == "the warrant was refused"

    @pytest.mark.parametrize("prose", [
        # The line that made this a rule. An earlier pattern also matched
        # "<name> is <value>", so MAYA's own start-up warning was rendered as
        # "the session cookie is [redacted] with a PUBLISHED secret" — the verb
        # of a security warning blanked, and a reader left wondering what had
        # been hidden from them.
        "the session cookie is signed with a PUBLISHED secret",
        "Set auth.session_secret (or MAYA_SESSION_SECRET) before this instance",
        "warrants are being signed with a PUBLISHED default key",
        "the api key was revoked by s.iqbal",
    ])
    def test_prose_is_not_eaten(self, prose):
        """A redaction that eats prose costs more than the credential it might
        have caught: it teaches people to distrust the whole screen."""
        assert redact(prose) == prose


class TestTheScreenNeedsThePermission:
    def test_the_page_refuses_somebody_without_it(self, client, people):
        login(client, *people["d.raman"])
        assert client.get("/admin/logs").status_code == 403

    def test_the_api_refuses_them_too(self, client, people):
        """One rule, asked from two places. A screen that renders and then 403s
        to everything it does is worse than one that refuses."""
        assert client.get("/api/v1/logs", auth=people["d.raman"]).status_code == 403

    def test_an_administrator_is_shown_it(self, client):
        login(client)
        body = client.get("/admin/logs").text
        assert "Live log" in body
        assert "/static/js/admin-logs.js" in body

    def test_the_first_screenful_comes_from_the_server(self, client):
        """A page that is blank until a socket connects looks broken for the
        moment before it isn't — and it is opened by somebody who already
        thinks something is wrong. It also has to hold up where a proxy eats
        `text/event-stream`, which is the deployment nobody discovers until
        they need the log."""
        login(client)
        logging.getLogger("maya.test.render").warning("rendered without javascript")
        body = client.get("/admin/logs").text
        assert "rendered without javascript" in body
        assert "maya.test.render" in body

    def test_the_stream_resumes_where_the_render_stopped(self, client):
        """Starting the stream at zero would replay every rendered line
        underneath itself, which reads as the server having done it twice."""
        import re

        login(client)
        logging.getLogger("maya.test.render").warning("a line to anchor on")
        body = client.get("/admin/logs").text
        cursor = int(re.search(r'data-cursor="(\d+)"', body).group(1))
        assert cursor >= 1
        assert client.get(f"/api/v1/logs?after={cursor}").json()["lines"] == [] \
            or all(line["seq"] > cursor for line
                   in client.get(f"/api/v1/logs?after={cursor}").json()["lines"])

    def test_it_is_reachable_from_the_menu(self, client):
        login(client)
        assert 'href="/admin/logs"' in client.get("/dashboard").text

    def test_an_operator_may_read_it(self, client):
        """The role woken up to diagnose the platform is the one that needs it."""
        from core.authz.roles import ROLES

        assert "log:read" in ROLES["operator"]
        assert "log:read" not in ROLES["model_developer"]


class TestTheApiIsAWindowWithACursor:
    def test_it_returns_lines_and_the_next_cursor(self, client):
        logging.getLogger("maya.test.api").warning("a distinctive line")
        first = client.get("/api/v1/logs").json()
        assert first["cursor"] >= 1
        assert any("a distinctive line" in line["message"] for line in first["lines"])
        again = client.get(f"/api/v1/logs?after={first['cursor']}").json()
        assert all(line["seq"] > first["cursor"] for line in again["lines"])

    def test_a_level_filter_is_at_least_not_exactly(self, client):
        """'At least WARNING' has to include ERROR, or the filter hides the one
        thing somebody set it to find."""
        logging.getLogger("maya.test.api").error("an error line")
        logging.getLogger("maya.test.api").warning("a warning line")
        levels = {line["level"] for line
                  in client.get("/api/v1/logs?level=WARNING").json()["lines"]}
        assert "ERROR" in levels

    def test_an_unspellable_level_filters_nothing(self, client):
        """A filter nobody can spell is one that silently hides everything."""
        logging.getLogger("maya.test.api").warning("still visible")
        body = client.get("/api/v1/logs?level=LOUD").json()
        assert any("still visible" in line["message"] for line in body["lines"])

    def test_a_request_filter_narrows_to_one_call(self, client):
        from core import log

        log.bind_request("only-this-one")
        logging.getLogger("maya.test.api").warning("mine")
        log.bind_request("some-other")
        logging.getLogger("maya.test.api").warning("theirs")
        lines = client.get("/api/v1/logs?request_id=only-this-one").json()["lines"]
        assert [line["message"] for line in lines if line["message"] in ("mine", "theirs")] \
            == ["mine"]

    def test_a_substring_filter_reads_the_module_too(self, client):
        logging.getLogger("maya.test.needle").warning("nothing special")
        lines = client.get("/api/v1/logs?contains=test.needle").json()["lines"]
        assert any(line["logger"] == "maya.test.needle" for line in lines)


class TestTheAssetNoiseIsHiddenAndSaysSo:
    """One page load is thirty font, stylesheet and script lines. Thirty of
    those bury the one line somebody came to read — but a viewer that drops
    lines without telling you is one you cannot trust to be complete, so the
    switch is on the screen and the filter is off with one click."""

    @staticmethod
    def _an_asset_request():
        """An access line shaped exactly as the middleware writes one.

        Written directly rather than by fetching an asset, because the suite
        runs at WARNING and the real access lines are INFO — so a test that
        fetched a stylesheet would observe nothing and pass whatever the
        filter did."""
        logging.getLogger("maya").warning(
            "GET /static/js/admin-logs.js -> 200 in 0.9ms",
            extra={"method": "GET", "path": "/static/js/admin-logs.js",
                   "status": 200, "duration_ms": 0.9})

    def test_static_requests_are_hidden_by_default(self, client):
        self._an_asset_request()
        paths = [line.get("path") for line
                 in client.get("/api/v1/logs").json()["lines"]]
        assert not any((p or "").startswith("/static/") for p in paths)

    def test_they_are_one_switch_away(self, client):
        self._an_asset_request()
        paths = [line.get("path") for line
                 in client.get("/api/v1/logs?quiet=false").json()["lines"]]
        assert any((p or "").startswith("/static/") for p in paths)

    def test_the_download_hides_them_too(self, client):
        """The same filter on every reader. A download that disagreed with the
        screen it was taken from is worse than one that shows everything."""
        self._an_asset_request()
        assert "/static/js/admin-logs.js" not in \
            client.get("/api/v1/logs/download").text
        assert "/static/js/admin-logs.js" in \
            client.get("/api/v1/logs/download?quiet=false").text

    def test_the_switch_is_on_the_screen(self, client):
        login(client)
        body = client.get("/admin/logs").text
        assert 'id="quiet"' in body
        assert "Hide static assets" in body

    def test_a_warning_about_a_static_path_is_still_shown(self, client):
        """The filter is on the ACCESS line's path, not on the message. A
        module that logs a problem while serving an asset is not noise."""
        logging.getLogger("maya.test.asset").warning("could not read /static/x")
        lines = client.get("/api/v1/logs?level=WARNING").json()["lines"]
        assert any("could not read /static/x" in line["message"] for line in lines)


class TestTheDownloadIsForSendingToSomebody:
    def test_it_is_the_ordinary_line_format(self, client):
        logging.getLogger("maya.test.dl").warning("something to send on")
        body = client.get("/api/v1/logs/download")
        assert body.status_code == 200
        assert "something to send on" in body.text
        assert "maya.test.dl" in body.text

    def test_it_says_it_is_not_the_evidence_chain(self, client):
        """A rolling window quoted in a governance pack is a claim resting on
        something that ages out. The file says so in its own first lines."""
        body = client.get("/api/v1/logs/download").text
        assert "not the evidence chain" in body
        assert "aged out" in body

    def test_it_downloads_rather_than_renders(self, client):
        headers = client.get("/api/v1/logs/download").headers
        assert "attachment" in headers["content-disposition"]


class TestTheViewerCannotChangeWhatItShows:
    """A screen that can quieten the log is a screen that can hide what it is
    showing you. Every route here is a GET."""

    def test_there_is_no_way_to_clear_or_set_the_level(self, client):
        paths = [route.path for route in client.app.routes
                 if getattr(route, "path", "").startswith("/api/v1/logs")]
        assert paths, "the log API is registered"
        for route in client.app.routes:
            if getattr(route, "path", "").startswith("/api/v1/logs"):
                assert set(route.methods) <= {"GET", "HEAD"}, route.path


class TestTheRingSurvivesAHandlerFailure:
    def test_a_line_that_cannot_be_rendered_is_counted_not_raised(self, ring):
        """logging routes a raising handler through its own error path, which
        can take the process with it. A diagnostic aid must not be the outage."""
        class Awkward:
            def __str__(self):
                raise RuntimeError("cannot be rendered")

        logger, handler = ring
        # Handed to the handler directly. Routing it through the logger would
        # reach pytest's capture handler first, which raises on the same value
        # — so the test would be measuring pytest rather than the ring.
        record = logging.LogRecord("maya.test.ring", logging.INFO, __file__, 1,
                                   "%s", (Awkward(),), None)
        handler.emit(record)
        assert handler.snapshot()["dropped"] == 1
        logger.info("and the next line still lands")
        assert handler.since(0)[0][-1]["message"] == "and the next line still lands"

    def test_the_failure_is_recorded_rather_than_swallowed(self, ring, caplog):
        """The platform rule is that a handler may decide to carry on but may
        never make the decision invisible — and a viewer quietly missing lines
        is exactly the incompleteness that rule exists to prevent."""
        class Awkward:
            def __str__(self):
                raise RuntimeError("cannot be rendered")

        _, handler = ring
        with caplog.at_level(logging.WARNING, logger="core.log"):
            handler.emit(logging.LogRecord("maya.test.ring", logging.INFO,
                                           __file__, 1, "%s", (Awkward(),), None))
        assert any("captured a log line" in r.getMessage() for r in caplog.records)

    def test_reporting_a_failure_does_not_re_enter_the_handler(self, ring):
        """The ring sits on the ROOT logger, so recording a failed capture is
        itself a log call that reaches this handler. Without the guard the
        report of the failure re-enters the handler that just failed, once per
        frame, until the stack ends."""
        class Awkward:
            def __str__(self):
                raise RuntimeError("cannot be rendered")

        _, handler = ring
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            handler.emit(logging.LogRecord("maya.test.ring", logging.INFO,
                                           __file__, 1, "%s", (Awkward(),), None))
        finally:
            root.removeHandler(handler)
        assert handler.snapshot()["dropped"] >= 1


class TestConfigureAttachesTheRing:
    def test_the_live_ring_is_on_the_root_logger(self):
        configure("INFO")
        assert LIVE in logging.getLogger().handlers

    def test_calling_it_twice_does_not_attach_it_twice(self):
        """`basicConfig(force=True)` removes every handler including this one,
        so `configure` must put it back — exactly once."""
        configure("INFO")
        configure("INFO")
        assert sum(1 for h in logging.getLogger().handlers if h is LIVE) == 1
