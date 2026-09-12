"""
MAYA — evidence engine tests.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import json

import pytest

from tests.conftest import without_append_only

from core.evidence import (BOOLEAN, COST, COUNTING, FRESHNESS, TRUST, WHY, Derivation)

CLAIM = {"authorised": Derivation("authorised",
                                  (("tests", "report", "committee"),
                                   ("tests", "report", "delegated")))}


def tamper(db, seq: int, **columns) -> None:
    """Change an evidence row behind the application's back.

    Raw SQL on purpose. `EvidenceRepository` refuses `set` and `remove` — it is
    append-only — so a test that tampered through it was really testing that the
    repository would let it, which is no longer true and was never the threat.

    The threat is somebody with the database, and this is what that looks like:
    an UPDATE the application never issued. Every test below that verifies
    tamper *evidence* has to get there this way, or it is checking the wrong
    door.

    **And it now has to drop the trigger to do it**, which is the point rather
    than an inconvenience. `db/schema/immutable.py` makes `evidence_node`
    append-only in the database, so this door is shut to anything connecting
    here. It is not shut to every path a mutated row can arrive by: a restore
    from a backup taken before the trigger existed, a replica fed by something
    that does not carry triggers, a database where the application's role could
    not create one — `Database._apply_enforcement` logs a warning and carries
    on precisely so that a deployment can be in that state and know it.

    So **detection is still the control and the trigger is defence in depth**,
    and dropping it here is how these tests keep saying so. A suite that
    deleted them because the trigger exists would be asserting that the only
    way into the table is the one MAYA owns.
    """
    sets = ", ".join(f"{c} = :{c}" for c in columns)
    values = {c: (json.dumps(v) if isinstance(v, (dict, list)) else v)
              for c, v in columns.items()}
    with without_append_only(db):
        db.execute(f"UPDATE evidence_node SET {sets} WHERE seq = :seq",
                   {**values, "seq": seq})


def remove_node(db, seq: int) -> None:
    """Delete a node the same way, and for the same reason as `tamper`."""
    with without_append_only(db):
        db.execute("DELETE FROM evidence_node WHERE seq = :seq", {"seq": seq})


def erase(db, seq: int) -> None:
    """Delete an evidence row behind the application's back. See `tamper`."""
    remove_node(db, seq)


class TestAppendChain:
    def test_first_node_links_to_genesis(self, evidence):
        n = evidence.append("test_result", "version", "v1", {"gini": 0.47})
        assert n["seq"] == 1 and n["prev_hash"].endswith("0" * 64)

    def test_sequence_increments(self, evidence):
        for i in range(1, 6):
            assert evidence.append("k", "version", "v1")["seq"] == i

    def test_chain_verifies_when_intact(self, evidence):
        for _ in range(10):
            evidence.append("k", "version", "v1", {"n": _})
        assert evidence.verify_chain()["valid"] is True

    def test_empty_chain_is_valid(self, evidence):
        assert evidence.verify_chain() == {"valid": True, "scope": "full",
                                           "length": 0,
                                           "head": evidence.head()[1]}

    def test_deleting_a_node_breaks_the_chain(self, evidence, repos):
        for _ in range(5):
            evidence.append("k", "version", "v1", {"n": _})
        erase(repos["evidence"].db, 3)
        result = evidence.verify_chain()
        assert result["valid"] is False and result["broken_at"] == 4

    def test_tampering_with_a_payload_breaks_the_chain(self, evidence, repos):
        """What the name says: the PAYLOAD is altered and nothing else.

        This test previously altered the stored content_hash instead, which is a
        different act with a different detection path — and the payload case it
        was named for went undetected for as long as it existed, because
        verification re-linked the stored hash rather than re-deriving it.
        """
        for n in range(3):
            evidence.append("k", "version", "v1", {"n": n})
        tamper(repos["evidence"].db, 2, payload={"n": "altered"})
        result = evidence.verify_chain()
        assert result["valid"] is False
        assert result["reason"].startswith("content_hash mismatch")
        assert result["broken_at"] == 2

    def test_tampering_with_the_subject_breaks_it_too(self, evidence, repos):
        """The content hash covers the kind and the subject, not only the
        payload: moving a node to another model would otherwise be invisible."""
        for n in range(3):
            evidence.append("k", "version", "v1", {"n": n})
        tamper(repos["evidence"].db, 2, subject_id="v2")
        assert evidence.verify_chain()["valid"] is False

    def test_altering_the_stored_hash_breaks_it_as_well(self, evidence, repos):
        """The other direction: the links no longer agree with the node."""
        for n in range(3):
            evidence.append("k", "version", "v1", {"n": n})
        tamper(repos["evidence"].db, 2, content_hash="sha256:" + "f" * 64)
        result = evidence.verify_chain()
        assert result["valid"] is False

    def test_personal_data_is_never_stored_inline(self, evidence):
        """Law L-18: reconciles append-only evidence with the right to erasure."""
        n = evidence.append("subject_record", "version", "v1",
                            {"name": "A Borrower"}, personal_data=True)
        assert n["payload"] == {} and n["contains_personal_data"] is True

    def test_no_personal_payload_survives_anywhere_on_the_node(self, evidence):
        """The law is about the DATA not being there, and the assertion above is
        about one field being empty.

        A payload discarded from `payload` and echoed into a digest, a detail
        string or a summary would satisfy that assertion and break the law —
        and the whole point of L-18 is that erasure is possible, which it is not
        if the value survives somewhere else on the row. So the check is
        against the serialised node, not against one key.
        """
        import json

        # A distinctive value, so finding it anywhere is unambiguous.
        borrower_name = "Wilhelmina Ashcombe-Trevelyan"
        node = evidence.append("subject_record", "version", "v1",
                               {"name": borrower_name,
                                "nested": {"also": borrower_name}},
                               personal_data=True)
        assert borrower_name not in json.dumps(node, default=str), \
            "the value survives somewhere on the node, so it cannot be erased"

        # And not in the stored row either, which is what an examiner reads.
        stored = evidence.repo.one(id=node["id"])
        assert borrower_name not in json.dumps(stored, default=str)

    def test_a_flagged_node_still_verifies_against_itself(self, evidence):
        """The payload is discarded and the node hashes WHAT IT STORED, so the
        chain does not break at the row that carries nothing. A node that
        hashed the payload it threw away would fail verification forever."""
        evidence.append("subject_record", "version", "v1",
                        {"name": "A Borrower"}, personal_data=True)
        evidence.append("test_result", "version", "v1", {"gini": 0.47})
        report = evidence.verify_chain()
        assert report["valid"] is True, report

    def test_the_flag_is_what_decides_it_and_not_the_shape(self, evidence):
        """An identical payload without the flag is retained. The law is about
        what somebody DECLARED, because MAYA cannot detect personal data and
        pretending otherwise would be a control that fails silently."""
        flagged = evidence.append("subject_record", "version", "v1",
                                  {"name": "A Borrower"}, personal_data=True)
        plain = evidence.append("subject_record", "version", "v2",
                                {"name": "A Borrower"})
        assert flagged["payload"] == {}
        assert plain["payload"] == {"name": "A Borrower"}

    def test_ordinary_payloads_are_retained(self, evidence):
        n = evidence.append("test_result", "version", "v1", {"gini": 0.47})
        assert n["payload"] == {"gini": 0.47}

    def test_content_hash_is_stable_for_equal_content(self, evidence):
        a = evidence.append("k", "version", "v1", {"x": 1, "y": 2})
        b = evidence.append("k", "version", "v2", {"y": 2, "x": 1})
        assert a["content_hash"] != b["content_hash"], "subject is part of the identity"

    def test_for_subject_filters(self, evidence):
        evidence.append("a", "version", "v1")
        evidence.append("b", "version", "v2")
        assert [n["kind"] for n in evidence.for_subject("v1")] == ["a"]


class TestSemiringEvaluation:
    @pytest.fixture
    def supported(self, evidence):
        for kind in ("tests", "report", "committee"):
            evidence.append(kind, "version", "v1")
        return evidence

    def test_boolean_true_when_a_route_is_complete(self, supported):
        r = supported.evaluate("authorised", CLAIM, BOOLEAN, supported.presence_valuation("v1"))
        assert r.value is True

    def test_boolean_false_when_no_route_is_complete(self, evidence):
        evidence.append("tests", "version", "v1")
        r = evidence.evaluate("authorised", CLAIM, BOOLEAN, evidence.presence_valuation("v1"))
        assert r.value is False

    def test_why_returns_every_minimal_support_set(self, evidence):
        r = evidence.evaluate("authorised", CLAIM, WHY, evidence.why_valuation())
        sets = {frozenset(s) for s in r.value}
        assert sets == {frozenset({"tests", "report", "committee"}),
                        frozenset({"tests", "report", "delegated"})}

    def test_why_absorbs_non_minimal_sets(self, evidence):
        """a OR ab == a. A superset of a sufficient set is not itself minimal."""
        d = {"c": Derivation("c", (("x",), ("x", "y")))}
        r = evidence.evaluate("c", d, WHY, evidence.why_valuation())
        assert {frozenset(s) for s in r.value} == {frozenset({"x"})}

    def test_counting_counts_alternative_derivations(self, evidence):
        r = evidence.evaluate("authorised", CLAIM, COUNTING, lambda k: 1)
        assert r.value == 2

    def test_trust_takes_the_best_route_and_multiplies_within_it(self, evidence):
        for kind, t in (("tests", 0.9), ("report", 1.0), ("committee", 1.0)):
            evidence.append(kind, "version", "v1", trust=t)
        r = evidence.evaluate("authorised", CLAIM, TRUST, evidence.trust_valuation("v1"))
        assert r.value == pytest.approx(0.9)

    def test_cost_finds_the_cheapest_route(self, evidence):
        costs = {"tests": 5.0, "report": 3.0, "committee": 10.0, "delegated": 1.0}
        r = evidence.evaluate("authorised", CLAIM, COST, lambda k: costs.get(k, float("inf")))
        assert r.value == 9.0, "tests+report+delegated is cheaper than the committee route"

    def test_freshness_reports_the_newest_supporting_item(self, evidence):
        stamps = {"tests": 100.0, "report": 250.0, "committee": 180.0, "delegated": 0.0}
        r = evidence.evaluate("authorised", CLAIM, FRESHNESS, lambda k: stamps.get(k, 0.0))
        assert r.value == 250.0

    def test_leaf_claim_uses_the_valuation_directly(self, evidence):
        r = evidence.evaluate("solo", {}, BOOLEAN, lambda k: True)
        assert r.value is True

    def test_cycles_terminate_and_contribute_nothing(self, evidence):
        d = {"a": Derivation("a", (("b",),)), "b": Derivation("b", (("a",),))}
        assert evidence.evaluate("a", d, BOOLEAN, lambda k: True).value is False

    def test_same_traversal_answers_different_questions(self, supported):
        """The point of the construction: one derivation, many semirings."""
        val = supported.presence_valuation("v1")
        assert supported.evaluate("authorised", CLAIM, BOOLEAN, val).value is True
        assert supported.evaluate("authorised", CLAIM, COUNTING, lambda k: 1).value == 2
        assert len(supported.evaluate("authorised", CLAIM, WHY,
                                      supported.why_valuation()).value) == 2


class TestCitationVerification:
    """Grounding verification reduces to a Boolean evaluation (paper, Prop. 11.3)."""

    def test_a_complete_citation_supports_the_claim(self, evidence):
        cited = {"tests", "report", "committee"}
        r = evidence.evaluate("authorised", CLAIM, BOOLEAN, evidence.cited_valuation(cited))
        assert r.value is True

    def test_an_incomplete_citation_is_rejected(self, evidence):
        """The worked example: citing only the report and the approval is not enough."""
        cited = {"report", "committee"}
        r = evidence.evaluate("authorised", CLAIM, BOOLEAN, evidence.cited_valuation(cited))
        assert r.value is False

    def test_an_unrelated_citation_is_rejected(self, evidence):
        r = evidence.evaluate("authorised", CLAIM, BOOLEAN,
                              evidence.cited_valuation({"something_else"}))
        assert r.value is False

    def test_a_superset_citation_still_supports(self, evidence):
        cited = {"tests", "report", "committee", "extra"}
        assert evidence.evaluate("authorised", CLAIM, BOOLEAN,
                                 evidence.cited_valuation(cited)).value is True


class TestTheChainCoversWhoDidIt:
    """Segregation of duties is decided by reading `recorded_by` off these
    nodes. The content hash did not cover it, so one UPDATE reassigning
    authorship turned the control off for that subject -- and `verify_chain`
    went on reporting the chain intact, because it was, over the fields it
    happened to hash."""

    def test_reassigning_authorship_breaks_the_chain(self, evidence, db):
        evidence.append("version_created", "version", "v1", {"semver": "1.0.0"},
                        actor="d.raman")
        assert evidence.verify_chain()["valid"] is True
        tamper(db, 1, recorded_by="somebody.else")
        report = evidence.verify_chain()
        assert report["valid"] is False
        assert "content_hash" in report["reason"]

    def test_reweighting_trust_breaks_the_chain(self, evidence, db):
        """Trust weights the TRUST semiring, so a silently re-weighted node is a
        conclusion nobody can check."""
        evidence.append("test_result_recorded", "version", "v1", {"gini": 0.5},
                        actor="a.mehta", trust=0.5)
        tamper(db, 1, trust=1.0)
        assert evidence.verify_chain()["valid"] is False

    def test_the_duties_check_cannot_be_cleared_by_an_update(self, evidence,
                                                             segregation, db):
        """The end-to-end statement, which is the one that matters."""
        evidence.append("version_created", "version", "v1", {}, actor="d.raman")
        assert segregation.conflict("d.raman", "version:approve", "v1") is not None
        tamper(db, 1, recorded_by="someone.harmless")
        # The conflict is gone -- and now the chain says so out loud.
        assert segregation.conflict("d.raman", "version:approve", "v1") is None
        assert evidence.verify_chain()["valid"] is False


class TestReadinessAsksTheCheapQuestion:
    """Verifying the whole chain on every readiness probe was O(chain).

    Measured: 2.9 seconds and 83 MB at forty thousand nodes, and the same call
    sat on the dashboard. A busy instance reaches a million nodes in half an
    hour, at which point an orchestrator takes the node out of service for being
    slow to answer whether it is healthy.

    So readiness now asks a narrower question — has anything broken SINCE the
    chain was last verified in full — and the full walk runs on the schedule,
    where its cost is somebody's decision rather than a side effect.
    """

    @pytest.fixture
    def checkpointed(self, db):
        from core.evidence import EvidenceEngine
        from db import EvidenceCheckpointRepository, EvidenceRepository
        return EvidenceEngine(EvidenceRepository(db),
                              EvidenceCheckpointRepository(db))

    def test_the_first_call_falls_back_to_the_full_walk(self, checkpointed):
        """With nothing recorded, there is no shortcut to take and pretending
        otherwise would be verifying nothing."""
        checkpointed.append("model_registered", "model", "m", {}, actor="p")
        report = checkpointed.verify_since_checkpoint()
        assert report["valid"] is True and report["scope"] == "full"

    def test_afterwards_it_checks_only_what_arrived(self, checkpointed):
        for i in range(5):
            checkpointed.append("model_registered", "model", f"m{i}", {}, actor="p")
        checkpointed.verify_since_checkpoint()
        checkpointed.append("tier_assigned", "model", "m0", {"tier": 1}, actor="p")
        report = checkpointed.verify_since_checkpoint()
        assert report["scope"] == "incremental"
        assert report["checked"] == 1, "one node arrived; one node is checked"

    def test_a_break_after_the_checkpoint_is_still_caught(self, checkpointed, db):
        for i in range(3):
            checkpointed.append("model_registered", "model", f"m{i}", {}, actor="p")
        checkpointed.verify_since_checkpoint()
        node = checkpointed.append("risk_assessed", "model", "m0", {"tier": 3},
                                   actor="p")
        tamper(db, node["seq"], payload={"tier": 1})
        assert checkpointed.verify_since_checkpoint()["valid"] is False

    def test_a_broken_chain_does_not_advance_the_checkpoint(self, checkpointed, db):
        """Otherwise the mark moves past the damage and every subsequent cheap
        check starts after it and reports health."""
        checkpointed.append("model_registered", "model", "m", {}, actor="p")
        checkpointed.verify_since_checkpoint()
        before = checkpointed.checkpoint()["seq"]
        node = checkpointed.append("risk_assessed", "model", "m", {"tier": 3},
                                   actor="p")
        tamper(db, node["seq"], payload={"tier": 1})
        checkpointed.verify_since_checkpoint()
        assert checkpointed.checkpoint()["seq"] == before

    def test_the_full_walk_is_still_available_and_still_the_real_control(
            self, checkpointed, db):
        """The cheap question trusts the checkpoint. Only this one answers
        whether the whole chain is intact, which is why it runs on a schedule."""
        for i in range(4):
            checkpointed.append("model_registered", "model", f"m{i}", {}, actor="p")
        checkpointed.verify_since_checkpoint()
        tamper(db, 1, payload={"tampered": 1})
        assert checkpointed.verify_since_checkpoint()["valid"] is True, \
            "the cheap check starts after the checkpoint, by construction"
        assert checkpointed.verify_chain()["valid"] is False, \
            "the full walk sees it, which is the whole reason it stays"

    def test_the_probe_does_not_get_slower_as_the_chain_grows(self, checkpointed):
        """The property that matters operationally: cost tracks what arrived,
        not what is stored."""
        for i in range(400):
            checkpointed.append("model_registered", "model", f"m{i}", {}, actor="p")
        checkpointed.verify_since_checkpoint()
        checkpointed.append("tier_assigned", "model", "m0", {}, actor="p")
        assert checkpointed.verify_since_checkpoint()["checked"] == 1


class TestTheChainRefusesToBeEdited:
    """The schema comment above `evidence_node` reads *"Append-only and
    hash-chained. The application role gets INSERT and SELECT."* That role does
    not exist — there are no grants, no triggers and no `CHECK` constraints in
    either dialect — and `EvidenceRepository` inherited a generic `set()` and
    `remove()` from `Repository`. Append-only was a property of nobody having
    called them.
    """

    def test_updating_the_chain_is_refused(self, repos):
        from db.repositories import AppendOnlyViolation
        with pytest.raises(AppendOnlyViolation, match="append-only"):
            repos["evidence"].set({"trust": 0.1}, seq=1)

    def test_deleting_from_the_chain_is_refused(self, repos):
        from db.repositories import AppendOnlyViolation
        with pytest.raises(AppendOnlyViolation, match="append-only"):
            repos["evidence"].remove(seq=1)

    def test_the_refusal_says_what_to_do_instead(self, repos):
        """Deletion is the wrong repair even where it looks like the right one:
        a node recorded in error is corrected by appending the correction, so
        the record carries the mistake *and* the correction."""
        from db.repositories import AppendOnlyViolation
        with pytest.raises(AppendOnlyViolation) as exc:
            repos["evidence"].remove(seq=1)
        assert "correcting entry" in exc.value.remediation
        assert exc.value.code == "append_only"

    def test_the_database_now_refuses_it_too(self, repos, evidence):
        """The limit has moved. This used to be the honest statement that
        anything holding the connection could still issue an UPDATE; since
        `db/schema/immutable.py` it cannot, and the repository's refusal is no
        longer the only thing standing there."""
        evidence.append("model_registered", "model", "m1", {"a": 1})
        with pytest.raises(Exception, match="append-only"):
            repos["evidence"].db.execute(
                "UPDATE evidence_node SET trust = 0.1 WHERE seq = 1")

    def test_detection_is_still_the_control(self, repos, evidence):
        """Because the trigger is not the only way a mutated row arrives — a
        restore, a replica, or a database whose role could not create one. A
        suite that stopped checking detection because a trigger exists would be
        asserting that the only door is the one MAYA owns."""
        evidence.append("model_registered", "model", "m1", {"a": 1})
        tamper(repos["evidence"].db, 1, trust=0.1)
        assert repos["evidence"].one(seq=1)["trust"] == 0.1
        assert not evidence.verify_chain()["valid"], (
            "the chain did not notice an edit made around the repository")

    def test_appending_still_works(self, evidence):
        """A refusal that refuses everything is not a control."""
        node = evidence.append("model_registered", "model", "m2", {"a": 2})
        assert node["seq"] >= 1
