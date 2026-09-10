"""Two versions of one model, side by side.

`L-7` and `L-12` already decide whether an alias *may* move. That is a yes with
a reason, and it is the right thing to gate a promotion on — but *is this legal*
and *what changed* are different questions, and a boolean cannot be turned back
into the second one.
"""
from __future__ import annotations

import pytest

from core.registry.common import RegistryError
from core.registry.comparison import SHAPES, VersionComparison
from tests.conftest import KERNEL, URN

CONTRACT = {"assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
            "guarantees": [{"key": "gini", "minimum": 0.42}],
            "on_boundary_violation": "reject"}


@pytest.fixture
def compare(registry):
    return VersionComparison(registry)


def _version(registry, semver, *, kernel=None, contract=None, digest="a"):
    return registry.create_version(
        URN, semver, kernel or KERNEL, contract or CONTRACT,
        artifact_digest="sha256:" + digest * 64, actor="d.raman")


class TestTheShapeOfTheChange:
    def test_only_the_digest_moving_is_a_rebuild(self, compare, registry,
                                                 a_model):
        """The same specification compiled again, which needs a different
        question asked of it than a re-fit does."""
        _version(registry, "1.0.0", digest="a")
        _version(registry, "1.0.1", digest="b")
        out = compare.compare(URN, "1.0.0", "1.0.1")
        assert out["shape"] == "rebuild"
        assert "why did the bytes change" in out["shape_means"]

    def test_nothing_moving_at_all_is_reported_as_identical(self, compare,
                                                            registry, a_model):
        _version(registry, "1.0.0", digest="a")
        _version(registry, "1.0.1", digest="a")
        out = compare.compare(URN, "1.0.0", "1.0.1")
        assert out["shape"] == "identical"
        assert "registered twice" in out["shape_means"]

    def test_a_moved_contract_is_a_respecification(self, compare, registry,
                                                   a_model):
        _version(registry, "1.0.0")
        _version(registry, "2.0.0", contract={
            **CONTRACT, "guarantees": [{"key": "gini", "minimum": 0.50}]})
        out = compare.compare(URN, "1.0.0", "2.0.0")
        assert out["shape"] == "respecification"

    def test_a_changed_class_outranks_everything_else(self, compare, registry,
                                                      a_model):
        """The reviewer's question is set by the largest thing that moved: a
        re-specification that also re-fitted is a re-specification."""
        _version(registry, "1.0.0")
        _version(registry, "2.0.0",
                 kernel={**KERNEL, "parameter_kind": "learned_weights",
                         "fit_procedure": "train"},
                 digest="b")
        out = compare.compare(URN, "1.0.0", "2.0.0")
        assert out["shape"] == "reclassification"
        assert out["kernel"]["reclassified"] is True
        assert "every obligation derived from the class moves with it" in (
            out["shape_means"])

    def test_every_shape_says_what_it_asks_of_a_reviewer(self):
        assert set(SHAPES) == {"identical", "rebuild", "refit",
                               "respecification", "reclassification"}
        assert all(v for v in SHAPES.values())

    def test_a_version_compared_with_itself_is_refused(self, compare, registry,
                                                       a_model):
        _version(registry, "1.0.0")
        with pytest.raises(RegistryError) as caught:
            compare.compare(URN, "1.0.0", "1.0.0")
        assert "is not a comparison" in str(caught.value)


class TestDirectionOnTheContract:
    """A tightened assumption and a loosened one are both *changed*, and they
    are opposite governance facts."""

    def test_an_unchanged_contract_says_so(self, compare, registry, a_model):
        _version(registry, "1.0.0", digest="a")
        _version(registry, "1.0.1", digest="b")
        out = compare.compare(URN, "1.0.0", "1.0.1")
        assert out["contract"]["direction"] == "unchanged"
        assert out["contract"]["same"] is True

    def test_a_stronger_guarantee_narrows(self, compare, registry, a_model):
        """The newer version promises more, so it substitutes for the older."""
        _version(registry, "1.0.0")
        _version(registry, "2.0.0", contract={
            **CONTRACT, "guarantees": [{"key": "gini", "minimum": 0.50}]})
        out = compare.compare(URN, "1.0.0", "2.0.0")
        assert out["contract"]["direction"] == "narrowed"
        assert out["contract"]["refines"] is True
        assert "safe substitute" in out["contract"]["detail"]

    def test_a_weaker_guarantee_widens_and_L7_refuses_it(self, compare,
                                                         registry, a_model):
        _version(registry, "1.0.0")
        _version(registry, "2.0.0", contract={
            **CONTRACT, "guarantees": [{"key": "gini", "minimum": 0.30}]})
        out = compare.compare(URN, "1.0.0", "2.0.0")
        assert out["contract"]["direction"] == "widened"
        assert out["contract"]["refines"] is False
        assert "L-7 refuses the alias move" in out["contract"]["detail"]

    def test_added_and_removed_clauses_are_named(self, compare, registry,
                                                 a_model):
        wider = {**KERNEL, "input_schema": list(KERNEL["input_schema"]) + [
            {"name": "turnover", "dtype": "float"}]}
        _version(registry, "1.0.0", kernel=wider)
        _version(registry, "2.0.0", kernel=wider, contract={
            "assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20},
                            {"key": "turnover", "minimum": 0}],
            "guarantees": [{"key": "gini", "minimum": 0.42}],
            "on_boundary_violation": "reject"})
        out = compare.compare(URN, "1.0.0", "2.0.0")
        assert out["contract"]["assumptions_added"] == ["turnover"]
        assert out["contract"]["assumptions_removed"] == []


class TestSchemas:
    def test_an_added_input_is_named(self, compare, registry, a_model):
        _version(registry, "1.0.0")
        _version(registry, "2.0.0", kernel={
            **KERNEL, "input_schema": list(KERNEL["input_schema"]) + [
                {"name": "sector", "dtype": "string"}]}, contract=CONTRACT)
        out = compare.compare(URN, "1.0.0", "2.0.0")
        assert out["schemas"]["input_schema"]["added"] == ["sector"]

    def test_the_variance_verdict_is_read_off_the_law(self, compare, registry,
                                                      a_model):
        """Read off `L-12` rather than re-derived: two implementations of one
        order eventually disagree, in the direction of permitting more."""
        _version(registry, "1.0.0", digest="a")
        _version(registry, "1.0.1", digest="b")
        out = compare.compare(URN, "1.0.0", "1.0.1")
        assert out["schemas"]["variance"]["holds"] is True
        assert "substitutes for it" in out["schemas"]["variance"]["detail"]


class TestWhatWasMeasured:
    def test_without_a_validation_service_nothing_is_claimed(self, compare,
                                                             registry,
                                                             a_model):
        _version(registry, "1.0.0", digest="a")
        _version(registry, "1.0.1", digest="b")
        out = compare.compare(URN, "1.0.0", "1.0.1")
        assert out["measurements"]["available"] is False

    def test_two_versions_sharing_no_test_is_a_finding_not_an_empty_section(
            self, registry, validation, a_model):
        """Printing a delta across different test sets would be worse than
        printing nothing, because it looks like an answer."""
        _version(registry, "1.0.0", digest="a")
        _version(registry, "1.0.1", digest="b")
        out = VersionComparison(registry, validation=validation).compare(
            URN, "1.0.0", "1.0.1")
        assert out["measurements"]["shared"] == []
        assert "cannot be compared" in out["measurements"]["detail"]

    def test_a_shared_test_reports_the_delta_and_its_direction(
            self, registry, validation, a_model, scored):
        _version(registry, "1.0.0", digest="a")
        _version(registry, "1.0.1", digest="b")
        labels, scores = scored
        # The newer version separates slightly better on the same test. Both
        # measurements are ones MAYA was GIVEN — it runs neither version.
        better = [min(1.0, s * 1.05) for s in scores]
        for semver, right in (("1.0.0", scores), ("1.0.1", better)):
            episode = validation.open(URN, semver, "initial", "a.mehta")
            validation.record(episode["id"], "discrimination.gini",
                              labels, right, {"min": 0.42},
                              actor="a.mehta")
        out = VersionComparison(registry, validation=validation).compare(
            URN, "1.0.0", "1.0.1")
        row = out["measurements"]["shared"][0]
        assert row["test_key"] == "discrimination.gini"
        assert row["delta"] is not None
        assert row["direction"] in ("up", "down", "same")


class TestTheSeries:
    def test_one_version_has_nothing_to_compare(self, compare, registry,
                                                a_model):
        _version(registry, "1.0.0")
        out = compare.history(URN)
        assert out["count"] == 0
        assert "fewer than two versions" in out["detail"]

    def test_the_shape_of_the_series_is_counted(self, compare, registry,
                                                a_model):
        """A model whose last six versions were all rebuilds is telling a
        different story from one with six re-specifications, and neither is
        visible from a list of semvers."""
        _version(registry, "1.0.0", digest="a")
        _version(registry, "1.0.1", digest="b")
        _version(registry, "1.0.2", digest="c")
        out = compare.history(URN)
        assert out["count"] == 2
        assert out["by_shape"] == {"rebuild": 2}
        assert [s["shape"] for s in out["steps"]] == ["rebuild", "rebuild"]


class TestOverHttp:
    def _two_versions(self, client, people):
        from tests.conftest import NAME
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "12-month PD"})
        for semver, digest in (("1.0.0", "a"), ("1.0.1", "b")):
            r = client.post(f"/api/v1/models/{NAME}/versions",
                            auth=people["d.raman"],
                            json={"semver": semver, "kernel": KERNEL,
                                  "contract": CONTRACT,
                                  "artifact_digest": "sha256:" + digest * 64})
            assert r.status_code == 201, r.text

    def test_a_comparison_is_served_with_its_shape(self, client, people):
        self._two_versions(client, people)
        r = client.get("/api/v1/version-comparison", auth=people["d.raman"],
                       params={"urn": URN, "left": "1.0.0", "right": "1.0.1"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["shape"] == "rebuild"
        assert body["shape_means"]
        assert body["contract"]["direction"] == "unchanged"

    def test_the_series_is_served(self, client, people):
        self._two_versions(client, people)
        r = client.get("/api/v1/version-history", auth=people["d.raman"],
                       params={"urn": URN})
        assert r.status_code == 200, r.text
        assert r.json()["by_shape"] == {"rebuild": 1}

    def test_comparing_a_version_with_itself_is_refused(self, client, people):
        self._two_versions(client, people)
        r = client.get("/api/v1/version-comparison", auth=people["d.raman"],
                       params={"urn": URN, "left": "1.0.0", "right": "1.0.0"})
        assert r.status_code == 409, r.text

    def test_the_page_shows_the_shape_of_the_series(self, client, people):
        from tests.conftest import NAME
        self._two_versions(client, people)
        client.post("/login", data={"username": "admin",
                                    "password": "maya-admin-dev",
                                    "next": "/dashboard"})
        body = client.get(f"/model-algebra/version/{NAME}").text
        assert "What changed, step by step" in body
        assert "a plain diff loses it" in body
