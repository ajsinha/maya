"""Telling other systems what happened, from the record of what happened.

There is no event table. Every act that changes this register already appends to
the evidence chain — hash-linked, append-only, in a total order — so a
subscription is a cursor over the chain rather than a copy of it.
"""
from __future__ import annotations

import json

import pytest

from core.events import ENVELOPE_VERSION, EventError, EventStream, Subscriptions
from core.events.stream import MAX_LIMIT
from core.events.subscriptions import (BATCH, MAX_FAILURES, SEQUENCE_HEADER,
                                       SIGNATURE_HEADER)


@pytest.fixture
def stream(evidence):
    return EventStream(evidence)


@pytest.fixture
def sent():
    return []


@pytest.fixture
def subscriptions(db, stream, evidence, sent):
    from db import SubscriptionRepository

    def sender(url, body, headers):
        sent.append({"url": url, "body": body, "headers": headers})

    return Subscriptions(SubscriptionRepository(db), stream, evidence,
                         sender=sender)


def _acts(evidence, n=3, kind="model_registered"):
    for i in range(n):
        evidence.append(kind, "model", f"m-{i}", {"n": i},
                        actor="person/j.okafor")


class TestTheChainReadForwards:
    def test_an_empty_chain_yields_nothing(self, stream):
        out = stream.read()
        assert out["count"] == 0 and out["more"] is False

    def test_events_come_back_in_sequence(self, stream, evidence):
        _acts(evidence, 3)
        seqs = [e["seq"] for e in stream.read()["events"]]
        assert seqs == sorted(seqs)

    def test_the_cursor_resumes_exactly(self, stream, evidence):
        """A consumer that stores the last seq it processed resumes where it
        stopped — no window, no watermark, no duplicate heuristics."""
        _acts(evidence, 5)
        first = stream.read(limit=2)
        rest = stream.read(after=first["cursor"])
        assert first["count"] == 2 and rest["count"] == 3
        assert not (set(e["seq"] for e in first["events"])
                    & set(e["seq"] for e in rest["events"]))

    def test_it_says_whether_more_remain(self, stream, evidence):
        """A consumer that cannot tell catching-up from caught-up either polls
        too often or falls further behind."""
        _acts(evidence, 5)
        assert stream.read(limit=2)["more"] is True
        assert stream.read(limit=100)["more"] is False

    def test_an_absurd_page_size_is_refused(self, stream):
        with pytest.raises(EventError) as caught:
            stream.read(limit=MAX_LIMIT + 1)
        assert caught.value.code == "limit_out_of_range"

    def test_it_filters_by_kind(self, stream, evidence):
        _acts(evidence, 2, kind="model_registered")
        _acts(evidence, 3, kind="risk_assessed")
        out = stream.read(kinds=["risk_assessed"])
        assert out["count"] == 3

    def test_the_kinds_are_derived_and_not_declared(self, stream, evidence):
        """A hand-written list goes stale the first time somebody appends a new
        kind, and a subscriber filtering on one that no longer exists receives
        nothing and is told nothing."""
        _acts(evidence, 1, kind="model_registered")
        _acts(evidence, 1, kind="alias_moved")
        assert stream.kinds() == ["alias_moved", "model_registered"]

    def test_the_detail_says_it_is_not_a_second_log(self, stream, evidence):
        _acts(evidence, 1)
        assert "second thing to keep in step" in stream.read()["detail"]


class TestTheEnvelope:
    def test_it_carries_the_cursor_and_a_deduplication_key(self, stream,
                                                           evidence):
        """Telling somebody to make their handler idempotent without giving
        them a key is how at-least-once becomes at-least-twice."""
        _acts(evidence, 1)
        event = stream.read()["events"][0]
        assert event["seq"] and event["content_hash"]
        assert event["envelope"] == ENVELOPE_VERSION

    def test_it_carries_the_act_and_who_did_it(self, stream, evidence):
        _acts(evidence, 1)
        event = stream.read()["events"][0]
        assert event["kind"] == "model_registered"
        assert event["actor"] == "person/j.okafor"
        assert event["payload"] == {"n": 0}


class TestSubscribing:
    def test_a_subscription_starts_from_the_head_not_from_zero(
            self, subscriptions, evidence, stream):
        """A new subscriber does not want the entire history of the register
        delivered to it."""
        _acts(evidence, 5)
        before = stream.head()
        row = subscriptions.subscribe(name="risk hub",
                                      url="https://hub.example/events",
                                      kinds=["model_registered"],
                                      owner="person/j.okafor")
        # The head as it stood when the subscription was taken. Creating it is
        # itself a domain act and appends a node, so the head has since moved —
        # which is right: the five acts before it are history this subscriber
        # did not ask for, and anything after it is news.
        assert row["cursor"] == before
        assert subscriptions.deliver(row["reference"])["delivered"] == 0

    def test_the_secret_is_returned_once_and_never_again(self, subscriptions):
        """A secret a listing endpoint hands back is a secret held by everybody
        with read access."""
        row = subscriptions.subscribe(name="hub",
                                      url="https://hub.example/events",
                                      kinds=["model_registered"],
                                      owner="person/j.okafor")
        assert row["secret"]
        listed = subscriptions.across_the_estate()["subscriptions"][0]
        assert "secret" not in listed

    def test_a_subscription_with_no_kinds_is_refused(self, subscriptions):
        """A chain node's payload carries model inventory, findings and
        exposure figures."""
        with pytest.raises(EventError) as caught:
            subscriptions.subscribe(name="hub", url="https://h.example/e",
                                    kinds=[], owner="o")
        assert caught.value.code == "kinds_required"

    def test_a_wildcard_is_refused_by_name(self, subscriptions):
        """*We send you all our events* is not a data-sharing decision anybody
        made."""
        with pytest.raises(EventError) as caught:
            subscriptions.subscribe(name="hub", url="https://h.example/e",
                                    kinds=["*"], owner="o")
        assert caught.value.code == "wildcard_refused"
        assert "the decision being visible rather than avoided" in (
            caught.value.remediation)

    def test_a_subscription_with_no_owner_is_refused(self, subscriptions):
        with pytest.raises(EventError) as caught:
            subscriptions.subscribe(name="hub", url="https://h.example/e",
                                    kinds=["model_registered"], owner=" ")
        assert caught.value.code == "owner_required"

    def test_the_url_goes_through_the_outbound_guard(self, subscriptions):
        """A webhook is the first thing here that deliberately reaches
        outward."""
        with pytest.raises(EventError):
            subscriptions.subscribe(name="hub", url="http://h.example/e",
                                    kinds=["model_registered"], owner="o")

    def test_it_lands_on_the_evidence_chain(self, subscriptions, evidence):
        subscriptions.subscribe(name="hub", url="https://h.example/e",
                                kinds=["model_registered"],
                                owner="person/j.okafor")
        assert any(n["kind"] == "event_subscription_created"
                   for n in evidence.repo.many())


class TestDelivery:
    def _subscribed(self, subscriptions, kinds=("model_registered",)):
        return subscriptions.subscribe(
            name="hub", url="https://hub.example/events", kinds=list(kinds),
            owner="person/j.okafor")

    def test_nothing_new_delivers_nothing(self, subscriptions, evidence):
        row = self._subscribed(subscriptions)
        out = subscriptions.deliver(row["reference"])
        assert out["delivered"] == 0
        assert "nothing new" in out["detail"]

    def test_a_backlog_is_pushed_and_the_cursor_advances(self, subscriptions,
                                                         evidence, sent):
        row = self._subscribed(subscriptions)
        _acts(evidence, 3)
        out = subscriptions.deliver(row["reference"])
        assert out["delivered"] == 3
        assert len(sent) == 1
        assert subscriptions.deliver(row["reference"])["delivered"] == 0

    def test_only_the_subscribed_kinds_are_sent(self, subscriptions, evidence,
                                                sent):
        row = self._subscribed(subscriptions, kinds=("alias_moved",))
        _acts(evidence, 3, kind="model_registered")
        assert subscriptions.deliver(row["reference"])["delivered"] == 0
        _acts(evidence, 2, kind="alias_moved")
        assert subscriptions.deliver(row["reference"])["delivered"] == 2

    def test_every_delivery_is_signed_over_the_exact_body(self, subscriptions,
                                                          evidence, sent):
        """A signature covering anything less than what was sent leaves the
        rest unsigned."""
        row = self._subscribed(subscriptions)
        _acts(evidence, 2)
        subscriptions.deliver(row["reference"])
        posted = sent[0]
        expected = Subscriptions.sign(row["secret"], posted["body"])
        assert posted["headers"][SIGNATURE_HEADER] == expected
        assert posted["headers"][SEQUENCE_HEADER]

    def test_the_body_carries_the_envelope_version(self, subscriptions,
                                                   evidence, sent):
        row = self._subscribed(subscriptions)
        _acts(evidence, 1)
        subscriptions.deliver(row["reference"])
        assert json.loads(sent[0]["body"])["envelope"] == ENVELOPE_VERSION

    def test_a_batch_is_bounded(self, subscriptions, evidence, sent):
        row = self._subscribed(subscriptions)
        _acts(evidence, BATCH + 10)
        out = subscriptions.deliver(row["reference"])
        assert out["delivered"] == BATCH and out["more"] is True

    def test_without_a_sender_nothing_leaves_and_it_says_so(self, db, stream,
                                                            evidence):
        from db import SubscriptionRepository
        subs = Subscriptions(SubscriptionRepository(db), stream, evidence)
        row = subs.subscribe(name="hub", url="https://h.example/e",
                             kinds=["model_registered"], owner="o")
        _acts(evidence, 2)
        out = subs.deliver(row["reference"])
        assert out["delivered"] == 0 and out["would_deliver"] == 2
        assert "rather than silently dropped" in out["detail"]


class TestFailure:
    def _failing(self, db, stream, evidence):
        from db import SubscriptionRepository

        def sender(url, body, headers):
            raise RuntimeError("connection refused")

        return Subscriptions(SubscriptionRepository(db), stream, evidence,
                             sender=sender)

    def test_a_failure_is_counted_and_the_cursor_does_not_move(self, db,
                                                               stream,
                                                               evidence):
        subs = self._failing(db, stream, evidence)
        row = subs.subscribe(name="hub", url="https://h.example/e",
                             kinds=["model_registered"], owner="o")
        _acts(evidence, 2)
        out = subs.deliver(row["reference"])
        assert out["failures"] == 1 and out["delivered"] == 0
        assert subs.require(row["reference"])["cursor"] == row["cursor"]

    def test_repeated_failure_suspends_rather_than_deletes(self, db, stream,
                                                           evidence):
        """Deleting would lose the cursor, and a receiver that came back would
        either miss everything in between or be resent the whole chain."""
        subs = self._failing(db, stream, evidence)
        row = subs.subscribe(name="hub", url="https://h.example/e",
                             kinds=["model_registered"], owner="o")
        _acts(evidence, 2)
        for _ in range(MAX_FAILURES):
            out = subs.deliver(row["reference"])
        assert out["state"] == "suspended"
        assert subs.require(row["reference"]) is not None
        assert "lose the cursor" in out["detail"]

    def test_a_suspended_one_resumes_from_where_it_stopped(self, db, stream,
                                                           evidence):
        subs = self._failing(db, stream, evidence)
        row = subs.subscribe(name="hub", url="https://h.example/e",
                             kinds=["model_registered"], owner="o")
        _acts(evidence, 2)
        for _ in range(MAX_FAILURES):
            subs.deliver(row["reference"])
        resumed = subs.resume(row["reference"], actor="admin")
        assert resumed["state"] == "active"
        assert resumed["cursor"] == row["cursor"]

    def test_one_failing_receiver_does_not_hold_up_the_others(self, db, stream,
                                                              evidence, sent):
        """A receiver that is failing falls behind on its own."""
        from db import SubscriptionRepository
        calls = []

        def sender(url, body, headers):
            calls.append(url)
            if "broken" in url:
                raise RuntimeError("nope")

        subs = Subscriptions(SubscriptionRepository(db), stream, evidence,
                             sender=sender)
        subs.subscribe(name="broken", url="https://broken.example/e",
                       kinds=["model_registered"], owner="o")
        subs.subscribe(name="good", url="https://good.example/e",
                       kinds=["model_registered"], owner="o")
        _acts(evidence, 2)
        out = subs.deliver_all()
        assert out["delivered"] == 2 and out["failed"] == 1


class TestTheEstate:
    def test_an_empty_estate_says_that_is_the_resting_state(self, db, stream,
                                                            evidence):
        from db import SubscriptionRepository
        subs = Subscriptions(SubscriptionRepository(db), stream, evidence)
        out = subs.across_the_estate()
        assert out["count"] == 0
        assert "deployable air-gapped" in out["detail"]

    def test_it_reports_how_far_behind_each_has_fallen(self, subscriptions,
                                                       evidence):
        """What a broken integration looks like before anybody notices."""
        subscriptions.subscribe(name="hub", url="https://h.example/e",
                                kinds=["model_registered"], owner="o")
        _acts(evidence, 4)
        out = subscriptions.across_the_estate()
        assert out["subscriptions"][0]["behind"] > 0
        assert "before anybody notices" in out["detail"]


class TestOverHttp:
    def test_the_stream_is_served_with_a_cursor(self, registered, people):
        r = registered.get("/api/v1/events", auth=people["a.mehta"],
                           params={"limit": 5})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["envelope_version"] == ENVELOPE_VERSION
        assert "second thing to keep in step" in body["detail"]
        assert all(e["seq"] and e["content_hash"] for e in body["events"])

    def test_the_cursor_advances(self, registered, people):
        first = registered.get("/api/v1/events", auth=people["a.mehta"],
                               params={"limit": 2}).json()
        again = registered.get("/api/v1/events", auth=people["a.mehta"],
                               params={"after": first["cursor"],
                                       "limit": 2}).json()
        assert not (set(e["seq"] for e in first["events"])
                    & set(e["seq"] for e in again["events"]))

    def test_the_kinds_are_served(self, registered, people):
        r = registered.get("/api/v1/events/kinds", auth=people["a.mehta"])
        assert r.status_code == 200, r.text
        assert "model_registered" in r.json()["kinds"]

    def test_a_subscription_returns_its_secret_once(self, client, people):
        made = client.post("/api/v1/subscriptions", auth=("admin",
                                                          "maya-admin-dev"),
                           json={"name": "risk hub",
                                 "url": "https://hub.example/events",
                                 "kinds": ["model_registered"],
                                 "owner": "person/j.okafor"})
        assert made.status_code == 201, made.text
        assert made.json()["secret"]
        listed = client.get("/api/v1/subscriptions",
                            auth=("admin", "maya-admin-dev")).json()
        assert all("secret" not in s for s in listed["subscriptions"])

    def test_a_wildcard_subscription_is_refused(self, client, people):
        r = client.post("/api/v1/subscriptions",
                        auth=("admin", "maya-admin-dev"),
                        json={"name": "everything",
                              "url": "https://hub.example/events",
                              "kinds": ["*"], "owner": "person/j.okafor"})
        assert r.status_code == 422, r.text
        assert r.json()["error"] == "wildcard_refused"
