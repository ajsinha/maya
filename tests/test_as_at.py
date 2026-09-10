"""The register as it stood on a date that has passed.

This is the question every examination opens with — *what did your inventory say
about this model in March* — and the one a register built out of mutable rows
cannot answer, because the rows have since been updated.
"""
from __future__ import annotations

import time

import pytest

from core.registry.asat import NOT_PROJECTED, AsAtProjection
from tests.conftest import CONTRACT, KERNEL, URN


@pytest.fixture
def projection(registry, evidence):
    return AsAtProjection(evidence, registry)


@pytest.fixture
def history(registry, evidence):
    """A model registered, versioned, tiered and taken through its lifecycle,
    with a timestamp captured at each step."""
    marks = {}

    def mark(name):
        marks[name] = time.time()
        return marks[name]

    mark("before_anything")
    registry.register(URN, "SB PD", "credit.pd", "credit", "person/j.okafor",
                      "LE-US-01", "12-month PD")
    mark("registered")
    registry.create_version(URN, "1.0.0", dict(KERNEL), dict(CONTRACT))
    mark("versioned")
    model = registry.require(URN)
    registry.set_tier(model["id"], 2)
    evidence.append("tier_assigned", "model", model["id"], {"tier": 2})
    mark("tiered")
    evidence.append("model_submit", "model", model["id"],
                    {"from": "draft", "to": "submitted"})
    evidence.append("model_approve", "model", model["id"],
                    {"from": "submitted", "to": "approved"})
    mark("approved")
    evidence.append("model_attest", "model", model["id"],
                    {"from": "approved", "to": "attested"})
    mark("attested")
    return marks


class TestFoldingTheChain:
    def test_before_anything_the_register_was_empty(self, projection, history):
        out = projection.register(history["before_anything"])
        assert out["count"] == 0
        assert "did not exist yet" in out["detail"]

    def test_at_registration_the_model_exists_and_is_a_draft(self, projection,
                                                             history):
        out = projection.model(URN, history["registered"])
        assert out["existed"] is True
        assert out["status"] == "draft" and out["tier"] is None

    def test_the_status_at_each_moment_is_what_it_was_then(self, projection,
                                                           history):
        """Not what it is now. That is the whole requirement."""
        assert projection.model(URN, history["registered"])["status"] == "draft"
        assert projection.model(URN, history["approved"])["status"] == "approved"
        assert projection.model(URN, history["attested"])["status"] == "attested"

    def test_the_tier_at_a_moment_before_it_was_assigned_is_none(
            self, projection, history):
        assert projection.model(URN, history["versioned"])["tier"] is None
        assert projection.model(URN, history["tiered"])["tier"] == 2

    def test_a_version_appears_when_it_was_created(self, projection, history):
        assert projection.model(URN, history["registered"])["versions"] == {}
        later = projection.model(URN, history["versioned"])
        assert "1.0.0" in later["versions"]
        assert later["versions"]["1.0.0"]["trainability_class"] == "T2"

    def test_a_model_that_did_not_exist_yet_says_which_of_two_things(
            self, projection, history):
        out = projection.model(URN, history["before_anything"])
        assert out["existed"] is False
        assert "did not exist yet, or it was registered and deleted" in \
            out["detail"]


class TestItIsEvidenceRatherThanAnAssertion:
    """A projection somebody could have rewritten is not evidence. The whole
    reason to fold the chain instead of keeping an audit table is that the
    chain cannot be rewritten without every hash after the edit disagreeing."""

    def test_the_answer_carries_the_chain_position_and_hash(self, projection,
                                                            history):
        out = projection.register(history["attested"])
        assert out["chain_seq"] is not None
        assert str(out["chain_hash"]).startswith("sha256:")
        assert "cannot be rewritten" in out["detail"]

    def test_an_earlier_moment_answers_at_an_earlier_sequence(self, projection,
                                                              history):
        early = projection.register(history["registered"])
        late = projection.register(history["attested"])
        assert early["chain_seq"] < late["chain_seq"]
        assert early["chain_hash"] != late["chain_hash"]


class TestWhatItWillNotInvent:
    """*We do not know what the purpose field said in March* is an answer. A
    confidently wrong purpose is not."""

    def test_the_unprojectable_fields_are_named_in_the_answer(self, projection,
                                                              history):
        out = projection.model(URN, history["attested"])
        assert "purpose" in out["not_projected"]
        assert "domain" in out["not_projected"]

    def test_it_does_not_report_a_field_it_cannot_project(self, projection,
                                                          history):
        out = projection.model(URN, history["attested"])
        for field in NOT_PROJECTED:
            assert field not in out or out[field] is None, \
                f"{field} is named as not projected and is being reported"


class TestAPureFold:
    def test_a_version_node_carries_its_models_urn(self, registry, evidence,
                                                   history):
        """So the fold needs no lookup: a fold cannot look anything up, and
        asking the register would mean a model deleted since silently lost its
        versions from its own history."""
        nodes = [n for n in evidence.repo.many()
                 if n["kind"] == "version_created"]
        assert nodes and nodes[-1]["payload"].get("urn") == URN

    def test_the_fold_works_without_a_register_at_all(self, evidence, history):
        unwired = AsAtProjection(evidence, registry=None)
        out = unwired.model(URN, history["attested"])
        assert out["existed"] is True
        assert "1.0.0" in out["versions"], "the urn on the payload is enough"
