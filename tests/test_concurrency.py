"""Sending the same request twice, and two people changing one thing at once.

A client whose connection dropped mid-POST does not know whether the act
happened. Its choices are to retry — and risk two attestations, two waivers, two
break-glass grants — or not to, and risk none.

The lost update an ETag prevents is the quietest failure in any register: two
people open a record, both edit, both save, and the second write silently
discards the first. Nothing is refused and the only trace is a field nobody
typed.
"""
from __future__ import annotations

import time

import pytest

from core.concurrency import (HEADER, IdempotencyError, IdempotencyStore,
                              etag_of, matches)
from core.concurrency.idempotency import MAX_KEY, RETENTION_HOURS, STALE_MINUTES
from tests.conftest import NAME, URN


@pytest.fixture
def store(db):
    from db import IdempotencyRepository
    return IdempotencyStore(IdempotencyRepository(db))


class TestClaimingAKey:
    def test_a_fresh_key_says_go_and_do_the_work(self, store):
        assert store.claim("k1", "caller", "POST", "/models", b'{"a":1}') is None

    def test_a_completed_key_replays_the_answer(self, store):
        store.claim("k1", "caller", "POST", "/models", b'{"a":1}')
        store.complete("k1", "caller", 201, b'{"urn":"x"}')
        replay = store.claim("k1", "caller", "POST", "/models", b'{"a":1}')
        assert replay == {"status": 201, "body": '{"urn":"x"}'}

    def test_the_same_key_with_a_different_body_is_a_conflict(self, store):
        """An implementation that replays the first response to any second
        request tells a client that retried with a CORRECTED payload that the
        correction succeeded — when what it returned was the answer to the
        mistake."""
        store.claim("k1", "caller", "POST", "/models", b'{"a":1}')
        store.complete("k1", "caller", 201, b"{}")
        with pytest.raises(IdempotencyError) as caught:
            store.claim("k1", "caller", "POST", "/models", b'{"a":2}')
        assert caught.value.code == "idempotency_key_reused"
        assert "you have since corrected" in caught.value.detail

    def test_the_same_key_on_a_different_path_is_a_conflict(self, store):
        store.claim("k1", "caller", "POST", "/models", b"{}")
        store.complete("k1", "caller", 201, b"{}")
        with pytest.raises(IdempotencyError) as caught:
            store.claim("k1", "caller", "POST", "/features", b"{}")
        assert caught.value.code == "idempotency_key_reused"

    def test_keys_are_scoped_to_the_caller(self, store):
        """A key is chosen by the caller, and a well-chosen UUID does not
        protect you from somebody else's badly chosen one."""
        store.claim("k1", "alice", "POST", "/models", b'{"a":1}')
        store.complete("k1", "alice", 201, b'{"mine":true}')
        assert store.claim("k1", "bob", "POST", "/models", b'{"a":9}') is None

    def test_an_absurd_key_is_refused(self, store):
        with pytest.raises(IdempotencyError) as caught:
            store.claim("x" * (MAX_KEY + 1), "caller", "POST", "/m", b"{}")
        assert caught.value.code == "idempotency_key_too_long"


class TestTheConcurrentCase:
    """A retry usually races the original rather than following it politely."""

    def test_a_second_identical_request_in_flight_is_refused_not_replayed(
            self, store):
        store.claim("k1", "caller", "POST", "/models", b"{}")
        with pytest.raises(IdempotencyError) as caught:
            store.claim("k1", "caller", "POST", "/models", b"{}")
        assert caught.value.code == "idempotency_in_flight"
        assert "saying either would be a guess" in caught.value.detail

    def test_a_key_left_in_flight_by_a_dead_process_is_released(self, store,
                                                               db):
        """Without this a crash turns into a permanent inability to retry the
        very act that crashed."""
        store.claim("k1", "caller", "POST", "/models", b"{}")
        row = store.repo.one(idempotency_key="k1")
        store.repo.set({"started_at": time.time() - (STALE_MINUTES + 1) * 60},
                       id=row["id"])
        assert store.claim("k1", "caller", "POST", "/models", b"{}") is None


class TestAFailureReleasesTheKey:
    def test_releasing_lets_a_retry_actually_retry(self, store):
        """A recorded failure makes the retry replay that failure forever, and
        the key becomes a tombstone for an act that never happened."""
        store.claim("k1", "caller", "POST", "/models", b"{}")
        store.release("k1", "caller")
        assert store.claim("k1", "caller", "POST", "/models", b"{}") is None

    def test_releasing_a_key_that_was_never_claimed_is_quiet(self, store):
        store.release("nope", "caller")


class TestTheSweep:
    def test_old_records_are_dropped(self, store):
        store.claim("k1", "caller", "POST", "/models", b"{}")
        store.complete("k1", "caller", 201, b"{}")
        out = store.sweep(now=time.time() + (RETENTION_HOURS + 1) * 3600)
        assert out["dropped"] == 1

    def test_recent_records_are_kept(self, store):
        store.claim("k1", "caller", "POST", "/models", b"{}")
        assert store.sweep()["dropped"] == 0


class TestEntityTags:
    def test_the_same_content_gives_the_same_tag(self):
        assert etag_of({"a": 1, "b": [2, 3]}) == etag_of({"b": [2, 3], "a": 1})

    def test_different_content_gives_a_different_tag(self):
        assert etag_of({"a": 1}) != etag_of({"a": 2})

    def test_a_changed_narration_does_not_change_the_tag(self):
        """A tag that changes when nothing did makes every conditional request
        a full one and teaches clients to stop sending the header."""
        assert etag_of({"a": 1, "detail": "one way of saying it"}) == etag_of(
            {"a": 1, "detail": "another"})

    def test_the_tag_is_weak_and_says_so(self):
        """A digest of the semantic content with rendering noise removed is not
        a claim about the octets, and claiming octet equality would answer a
        question this does not check."""
        assert etag_of({"a": 1}).startswith('W/"')

    def test_a_star_precondition_matches_anything_that_exists(self):
        assert matches("*", etag_of({"a": 1}))

    def test_a_list_is_matched_member_wise(self):
        tag = etag_of({"a": 1})
        assert matches(f'W/"nope", {tag}', tag)

    def test_no_header_never_matches(self):
        assert not matches(None, etag_of({"a": 1}))
        assert not matches("", etag_of({"a": 1}))


class TestOverHttp:
    def _payload(self, urn=URN):
        return {"urn": urn, "name": "SB PD",
                "model_class": "credit.pd.scorecard", "domain": "credit",
                "owner": "person/j.okafor", "legal_entity": "LE-US-01",
                "purpose": "12-month PD"}

    def test_a_retried_post_does_not_register_twice(self, client, people):
        headers = {HEADER: "abc-123"}
        first = client.post("/api/v1/models", auth=people["j.okafor"],
                            json=self._payload(), headers=headers)
        assert first.status_code == 201, first.text
        second = client.post("/api/v1/models", auth=people["j.okafor"],
                             json=self._payload(), headers=headers)
        assert second.status_code == 201, second.text
        assert second.headers.get("idempotency-replayed") == "true"
        assert second.json() == first.json()
        listed = client.get("/api/v1/models", auth=people["j.okafor"]).json()
        assert len(listed["models"]) == 1, "the act happened once"

    def test_without_a_key_the_second_post_is_refused_by_the_register(
            self, client, people):
        """The key is what makes the retry safe; without one the ordinary
        uniqueness refusal is what a caller meets, which is correct and is a
        different answer."""
        client.post("/api/v1/models", auth=people["j.okafor"],
                    json=self._payload())
        again = client.post("/api/v1/models", auth=people["j.okafor"],
                            json=self._payload())
        assert again.status_code >= 400

    def test_a_reused_key_with_a_different_body_is_refused(self, client,
                                                           people):
        headers = {HEADER: "abc-123"}
        client.post("/api/v1/models", auth=people["j.okafor"],
                    json=self._payload(), headers=headers)
        other = client.post("/api/v1/models", auth=people["j.okafor"],
                            json=self._payload("maya://model/other"),
                            headers=headers)
        assert other.status_code == 409, other.text
        assert other.json()["error"] == "idempotency_key_reused"

    def test_a_failed_request_releases_the_key(self, client, people):
        headers = {HEADER: "abc-123"}
        bad = client.post("/api/v1/models", auth=people["j.okafor"],
                          json={"urn": URN}, headers=headers)
        assert bad.status_code >= 400
        good = client.post("/api/v1/models", auth=people["j.okafor"],
                           json=self._payload(), headers=headers)
        assert good.status_code == 201, good.text
        assert "idempotency-replayed" not in good.headers

    def test_a_get_carries_an_etag(self, client, people):
        r = client.get("/api/v1/models", auth=people["j.okafor"])
        assert r.status_code == 200
        assert r.headers.get("etag", "").startswith('W/"')

    def test_if_none_match_gets_a_304(self, client, people):
        first = client.get("/api/v1/models", auth=people["j.okafor"])
        again = client.get("/api/v1/models", auth=people["j.okafor"],
                           headers={"If-None-Match": first.headers["etag"]})
        assert again.status_code == 304, again.text

    def test_a_changed_resource_changes_the_tag(self, client, people):
        before = client.get("/api/v1/models", auth=people["j.okafor"])
        client.post("/api/v1/models", auth=people["j.okafor"],
                    json=self._payload())
        after = client.get("/api/v1/models", auth=people["j.okafor"])
        assert before.headers["etag"] != after.headers["etag"]

    def test_a_stale_if_match_is_refused_with_412(self, client, people):
        client.post("/api/v1/models", auth=people["j.okafor"],
                    json=self._payload())
        r = client.patch(f"/api/v1/models/{NAME}", auth=people["j.okafor"],
                         json={"fields": {"purpose": "changed"}},
                         headers={"If-Match": 'W/"not-the-current-tag"'})
        assert r.status_code == 412, r.text
        assert r.json()["error"] == "precondition_failed"
        assert "no longer true" in r.json()["detail"]

    def test_a_current_if_match_goes_through(self, client, people):
        client.post("/api/v1/models", auth=people["j.okafor"],
                    json=self._payload())
        read = client.get(f"/api/v1/models/{NAME}", auth=people["j.okafor"])
        r = client.patch(f"/api/v1/models/{NAME}", auth=people["j.okafor"],
                         json={"fields": {"purpose": "changed"}},
                         headers={"If-Match": read.headers["etag"]})
        assert r.status_code == 200, r.text

    def test_a_precondition_nobody_can_evaluate_is_refused_not_ignored(
            self, client, people):
        """Silently dropping If-Match is strictly worse than not supporting
        preconditions: the client believes it has optimistic concurrency, has
        none, and has stopped checking for itself."""
        client.post("/api/v1/models", auth=people["j.okafor"],
                    json=self._payload())
        r = client.post(f"/api/v1/models/{NAME}/submit",
                        auth=people["j.okafor"], json={"note": "x"},
                        headers={"If-Match": 'W/"anything"'})
        assert r.status_code == 428, r.text
        assert r.json()["error"] == "precondition_unevaluable"
        assert "optimistic concurrency you do not have" in r.json()["detail"]
