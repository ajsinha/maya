"""
MAYA — evidence engine tests.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import pytest

from core.evidence import (BOOLEAN, COST, COUNTING, FRESHNESS, TRUST, WHY, Derivation,
                           EvidenceEngine)

CLAIM = {"authorised": Derivation("authorised",
                                  (("tests", "report", "committee"),
                                   ("tests", "report", "delegated")))}


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
        assert evidence.verify_chain() == {"valid": True, "length": 0,
                                           "head": evidence.head()[1]}

    def test_deleting_a_node_breaks_the_chain(self, evidence, repos):
        for _ in range(5):
            evidence.append("k", "version", "v1", {"n": _})
        repos["evidence"].remove(seq=3)
        result = evidence.verify_chain()
        assert result["valid"] is False and result["broken_at"] == 4

    def test_tampering_with_a_payload_breaks_the_chain(self, evidence, repos):
        for _ in range(3):
            evidence.append("k", "version", "v1", {"n": _})
        repos["evidence"].set({"content_hash": "sha256:" + "f" * 64}, seq=2)
        result = evidence.verify_chain()
        assert result["valid"] is False and result["reason"] == "chain_hash mismatch"

    def test_personal_data_is_never_stored_inline(self, evidence):
        """Law L-18: reconciles append-only evidence with the right to erasure."""
        n = evidence.append("subject_record", "version", "v1",
                            {"name": "A Borrower"}, personal_data=True)
        assert n["payload"] == {} and n["contains_personal_data"] is True

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
