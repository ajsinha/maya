"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

How this API pages, narrows and retires.

`ETag`/`If-Match` and `Idempotency-Key` were built first, because they are about
correctness under retry and concurrency. These three are about something slower
and just as damaging: what happens to a governance API over the years somebody
depends on it.

Each of them has a failure mode that produces a **plausible answer**, which is
why they are worth tests at all:

- an offset walk over a list being written to skips a row and reports a
  complete-looking queue with a hole in it, and the hole is a model nobody
  triaged;
- a projection that removed the field saying *this answer is partial* produces
  a response that reads as complete;
- a deprecation announced only in a release note reaches nobody, and the
  integration that breaks is a control.
"""
from __future__ import annotations

import time

import pytest

from core.http import conventions
from core.http.conventions import (ALWAYS_KEPT, CURSOR_TTL, CursorError, Sunsetting, page, project)


def _rows(count, start=0):
    return [{"id": i, "name": f"n{i}", "detail": "this answer is partial"}
            for i in range(start, start + count)]


class TestACursorNamesTheLastRowNotAPosition:
    def test_a_walk_reaches_every_row(self):
        rows, seen, cursor = _rows(250), [], None
        while True:
            out = page(rows, order="id", limit=100, cursor=cursor)
            seen += [r["id"] for r in out["rows"]]
            if not out["has_more"]:
                break
            cursor = out["next_cursor"]
        assert seen == list(range(250))

    def test_an_insert_above_the_cursor_does_not_make_you_skip_one(self):
        """The whole reason this exists. Under LIMIT/OFFSET the insert shifts
        everything down, page 2 starts one past where page 1 ended, and the
        caller receives a complete-looking list with a hole in it."""
        rows = _rows(150, start=100)
        first = page(rows, order="id", limit=100)
        # A scanner posts a candidate that sorts ABOVE everything seen so far.
        rows = _rows(1, start=0) + rows
        second = page(rows, order="id", limit=100,
                      cursor=first["next_cursor"])
        walked = [r["id"] for r in first["rows"]] + \
            [r["id"] for r in second["rows"]]
        # Nothing between the two pages was skipped.
        assert walked == sorted(walked)
        assert len(set(walked)) == len(walked)
        assert 200 in walked, "the row after the page boundary was skipped"

    def test_it_pages_descending_too(self):
        rows = _rows(120)
        first = page(rows, order="id", desc=True, limit=50)
        assert first["rows"][0]["id"] == 119
        second = page(rows, order="id", desc=True, limit=50,
                      cursor=first["next_cursor"])
        assert second["rows"][0]["id"] == 69

    def test_the_last_page_says_it_is_the_last(self):
        out = page(_rows(10), order="id", limit=100)
        assert out["has_more"] is False
        assert out["next_cursor"] is None
        assert "the end of the listing" in out["detail"]


class TestACursorCarriesItsOrdering:
    def test_resuming_under_a_different_sort_is_refused(self):
        """Replaying a cursor under a different ordering is a different query
        producing a plausible answer, and nothing in the result would show
        it."""
        first = page(_rows(200), order="id", limit=100)
        with pytest.raises(CursorError) as e:
            page(_rows(200), order="name", limit=100,
                 cursor=first["next_cursor"])
        assert e.value.code == "cursor_ordering_changed"
        assert "nothing in the result would show it" in e.value.remediation

    def test_reversing_the_direction_is_refused_too(self):
        first = page(_rows(200), order="id", limit=100)
        with pytest.raises(CursorError):
            page(_rows(200), order="id", desc=True, limit=100,
                 cursor=first["next_cursor"])

    def test_a_hand_built_cursor_is_refused(self):
        """A client that constructs one is depending on an internal ordering,
        which is then an ordering that can never change."""
        with pytest.raises(CursorError) as e:
            page(_rows(10), order="id", cursor="id:42")
        assert e.value.code == "cursor_malformed"
        assert "is not meant to be constructed" in e.value.remediation

    def test_an_old_cursor_is_refused_rather_than_honoured(self):
        first = page(_rows(200), order="id", limit=100)
        with pytest.raises(CursorError) as e:
            page(_rows(200), order="id", limit=100,
                 cursor=first["next_cursor"],
                 now=time.time() + CURSOR_TTL + 60)
        assert e.value.code == "cursor_expired"
        assert "has moved underneath it" in e.value.remediation

    def test_a_page_is_capped(self):
        out = page(_rows(3000), order="id", limit=99_999)
        assert out["count"] == conventions.MAX_PAGE


class TestProjectionNeverHidesARefusal:
    def test_it_narrows_to_the_named_fields(self):
        out = project({"id": 1, "name": "x", "secret": "y"}, "id,name")
        assert out == {"id": 1, "name": "x"}

    def test_the_fields_that_say_partial_always_survive(self):
        """A response that looked complete because somebody projected away the
        sentence saying it was not is the failure this codebase spends most of
        its effort avoiding."""
        out = project({"id": 1, "detail": "three sources were unreachable",
                       "gaps": ["outcomes analysis"]}, "id")
        assert out["detail"] and out["gaps"]

    def test_every_kept_field_is_a_way_of_saying_incomplete(self):
        assert {"detail", "gaps", "not_projected", "remediation",
                "cannot_check"} <= ALWAYS_KEPT

    def test_it_narrows_the_rows_of_a_page(self):
        out = project(page(_rows(5), order="id"), "id")
        assert out["rows"][0] == {"id": 0, "detail": "this answer is partial"}
        assert out["projected_to"] == ["id"]
        # And the page's own answer about itself survives.
        assert out["has_more"] is False

    def test_no_fields_means_no_change(self):
        payload = {"id": 1, "name": "x"}
        assert project(payload, None) == payload
        assert project(payload, "") == payload

    def test_a_scalar_is_returned_whole(self):
        assert project("a string", "id") == "a string"


class TestSunsetReachesTheMachineThatIsCalling:
    def test_it_carries_the_date_and_the_successor(self):
        entry = Sunsetting("/api/v1/old", time.time() + 90 * 86400,
                           successor="/api/v1/new", why="replaced")
        headers = entry.headers()
        assert "Sunset" in headers and headers["Deprecation"] == "true"
        assert 'rel="successor-version"' in headers["Link"]
        assert "day(s)" in headers["X-Sunset-Detail"]

    def test_a_passed_date_says_so_rather_than_counting_backwards(self):
        entry = Sunsetting("/api/v1/old", time.time() - 86400)
        assert "passed its sunset date" in entry.headers()["X-Sunset-Detail"]

    def test_nothing_is_deprecated_and_that_is_the_correct_state(self):
        """The mechanism ships before the first retirement on purpose: adding
        it when something is being retired means the first endpoint to go is
        the one nobody was warned about."""
        assert conventions.SUNSET == {}
        assert conventions.deprecations() == []

    def test_an_endpoint_not_being_retired_gets_no_headers(self):
        assert conventions.sunset_headers("/api/v1/models") == {}


class TestThroughTheApi:
    def test_the_conventions_are_published(self, client):
        out = client.get("/api/v1/conventions").json()
        assert out["paging"]["parameter"] == "cursor"
        assert "complete-looking list with a hole in it" in \
            out["paging"]["why_not_offset"]
        assert set(out["projection"]["always_kept"]) == set(ALWAYS_KEPT)

    def test_the_deprecations_endpoint_answers_empty_and_explains(self, client):
        out = client.get("/api/v1/deprecations").json()
        assert out["count"] == 0
        assert "the one nobody was warned about" in out["detail"]

    def test_fields_narrows_a_response_over_the_wire(self, client):
        whole = client.get("/api/v1/conventions").json()
        narrowed = client.get("/api/v1/conventions",
                              params={"fields": "paging"}).json()
        assert "paging" in narrowed and "retry" not in narrowed
        assert "retry" in whole

    def test_the_etag_is_of_what_was_actually_served(self, client):
        """Tagging the full body and then narrowing it would hand the caller an
        ETag for a representation they were never sent, and their next
        If-None-Match would be answered 304 against a body that differs from
        the one they hold."""
        whole = client.get("/api/v1/conventions")
        narrowed = client.get("/api/v1/conventions",
                              params={"fields": "paging"})
        assert whole.headers.get("etag")
        assert narrowed.headers.get("etag")
        assert whole.headers["etag"] != narrowed.headers["etag"]

    def test_the_discovery_queue_pages_by_cursor(self, client):
        out = client.get("/api/v1/discovery/candidates")
        assert out.status_code == 200
        body = out.json()
        assert body["ordered_by"] == "found_at"
        assert body["descending"] is True

    def test_a_bad_cursor_is_refused_by_name_over_the_wire(self, client):
        out = client.get("/api/v1/discovery/candidates",
                         params={"cursor": "not-a-cursor"})
        assert out.status_code == 422
        assert "cursor_malformed" in out.text
