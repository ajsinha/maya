"""The cheapest route, and the claim that two artifacts are the same model.

Two failure modes: a shortest-path solver that recommends the waiver, and an
equivalence report that passes by omitting the probes that did not.
"""
from __future__ import annotations

import pytest

from core.artifacts.common import ArtifactError
from core.artifacts.migration import (FAILED, PASSED, UNSUBSTANTIATED,
                                      FormatMigration)
from core.assist.probes import ProbeSets
from core.assist.remediation import (ACTS, DEFAULT_COSTS, DERIVATIONS, LEAVES,
                                     PRODUCES, REMOVES, RemediationPlanner)
from tests.conftest import URN


@pytest.fixture
def planner(registry, findings, validation, monitoring):
    return RemediationPlanner(registry, findings=findings, validation=validation,
                              monitoring=monitoring)


class TestThePlanIsComputed:
    def test_a_bare_model_gets_a_plan(self, planner, a_model):
        out = planner.plan(URN)
        assert out["steps"] and out["cost"] > 0

    def test_it_names_the_route_and_never_executes(self, planner, a_model):
        out = planner.plan(URN)
        assert all(s["route"].startswith(("GET", "POST")) for s in out["steps"])
        assert planner.describe()["executes"] is False
        assert "Nothing here is executed" in out["detail"]

    def test_what_is_already_done_costs_nothing(self, planner, registry,
                                               a_model, kernel_spec,
                                               contract_spec):
        before = planner.plan(URN)["cost"]
        registry.create_version(URN, "1.0.0", kernel_spec, contract_spec,
                                artifact_digest="sha256:" + "a" * 64)
        assert planner.plan(URN)["cost"] < before

    def test_approval_is_an_act_and_not_a_derived_fact(self, planner, a_model):
        """Collapsing the two made the signature invisible to the solver: it
        had a derivation, so it was never a leaf, so nothing costed it."""
        acts = {s["act"] for s in planner.plan(URN)["steps"]}
        assert "approve_version" in acts
        assert "signed_off" in LEAVES

    def test_the_derivation_is_published(self, planner):
        out = planner.describe()
        assert "in_force" in out["derivation"] and out["leaves"]

    def test_every_leaf_can_be_established_by_some_act(self):
        establishes = {a["establishes"] for a in ACTS.values()}
        assert set(LEAVES) <= establishes

    def test_every_act_names_a_cost(self):
        assert set(ACTS) <= set(DEFAULT_COSTS)

    def test_every_derived_fact_is_not_also_a_leaf(self):
        assert not (set(DERIVATIONS) & set(LEAVES))


class TestTheCheapestPathIsATrap:
    def test_a_waiver_is_excluded_from_the_plan(self, planner, a_model):
        """It is genuinely cheaper, and a solver with no opinion about kind
        would recommend it every time — correctly, and disastrously."""
        out = planner.plan(URN)
        assert "waive_validation" not in {s["act"] for s in out["steps"]}
        assert "waive_validation" in {h["act"] for h in
                                      out["cheaper_but_hollow"]}

    def test_the_cheap_route_is_shown_rather_than_hidden(self, planner,
                                                         a_model):
        out = planner.plan(URN)
        assert out["cheapest_of_any_kind"] < out["cost"]
        assert "rather than find it by accident" in out["detail"]

    def test_the_cheap_acts_are_priced_honestly(self):
        """Pricing them high would be lying about what they cost to make the
        arithmetic come out right, and the next reader would correct the lie."""
        assert DEFAULT_COSTS["waive_validation"] < \
            DEFAULT_COSTS["conclude_validation"]

    def test_exclusion_is_by_kind_and_not_by_price(self, planner):
        removes = {k for k, a in ACTS.items() if a["kind"] == REMOVES}
        assert removes and all(a["kind"] in (PRODUCES, REMOVES)
                               for a in ACTS.values())
        assert "by kind rather than by price" in planner.describe()["detail"]

    def test_every_hollow_act_says_why_it_is_excluded(self, planner, a_model):
        for hollow in planner.plan(URN)["cheaper_but_hollow"]:
            assert "without anything about the model changing" in \
                hollow["why_excluded"]


class TestGuessedWeightsAreReported:
    def test_an_undeclared_cost_counts_as_defaulted(self, registry, a_model):
        out = RemediationPlanner(registry).plan(URN)
        assert out["defaulted_share"] == 1.0
        assert "confidence is the dangerous part" in out["detail"]

    def test_a_declared_cost_changes_the_plan_and_the_share(self, registry,
                                                            a_model):
        planner = RemediationPlanner(registry,
                                     costs={"conclude_validation": 60.0})
        out = planner.plan(URN)
        assert out["defaulted_share"] < 1.0
        assert next(s for s in out["steps"]
                    if s["act"] == "conclude_validation")["cost_is_declared"]

    def test_steps_are_ordered_cheapest_first(self, planner, a_model):
        costs = [s["cost"] for s in planner.plan(URN)["steps"]]
        assert costs == sorted(costs)


# ------------------------------------------------------------- migration
@pytest.fixture
def migration(registry, a_model, kernel_spec, contract_spec, evidence):
    registry.create_version(URN, "1.0.0", kernel_spec, contract_spec,
                            artifact_digest="sha256:" + "a" * 64)
    return FormatMigration(registry, ProbeSets(registry), evidence)


@pytest.fixture
def probe_set(registry, migration):
    return ProbeSets(registry).propose(URN, "1.0.0")["probes"]


def _agreeing(probes, offset=0.0):
    return [{"probe": i, "from": 0.5, "to": 0.5 + offset}
            for i in range(len(probes))]


class TestMayaHoldsTheClaimAndConvertsNothing:
    def test_it_says_it_converts_nothing(self):
        out = FormatMigration.describe()
        assert out["converts"] is False and out["runs_probes"] is False
        assert "only witness to its own work" in out["detail"]

    def test_there_is_no_parameter_for_a_converted_artifact(self):
        import inspect
        params = set(inspect.signature(FormatMigration.verify).parameters)
        assert not (params & {"artifact", "bytes", "file", "convert"})

    def test_a_full_agreeing_run_passes(self, migration, probe_set):
        out = migration.verify(URN, "1.0.0", from_digest="sha256:" + "a" * 64,
                               to_digest="sha256:" + "b" * 64,
                               to_format="onnx", probes=probe_set,
                               results=_agreeing(probe_set), tolerance=1e-6,
                               ran_by="platform-team")
        assert out["outcome"] == PASSED and out["converted_by_maya"] is False

    def test_a_divergence_beyond_tolerance_fails(self, migration, probe_set):
        results = _agreeing(probe_set)
        results[0]["to"] = 0.9
        out = migration.verify(URN, "1.0.0", from_digest="sha256:" + "a" * 64,
                               to_digest="sha256:" + "b" * 64,
                               to_format="onnx", probes=probe_set,
                               results=results, tolerance=1e-6,
                               ran_by="platform-team")
        assert out["outcome"] == FAILED and out["divergences"]

    def test_a_missing_result_fails_rather_than_being_skipped(self, migration,
                                                              probe_set):
        """A report over 40 of 50 probes looks exactly like a report over 50 at
        the bottom of the page."""
        out = migration.verify(URN, "1.0.0", from_digest="sha256:" + "a" * 64,
                               to_digest="sha256:" + "b" * 64,
                               to_format="onnx", probes=probe_set,
                               results=_agreeing(probe_set)[:-1],
                               tolerance=1e-6, ran_by="platform-team")
        assert out["outcome"] == FAILED and out["missing_results"]
        assert "quietly omitting the probes that did not" in out["detail"]

    def test_both_refusing_is_agreement(self, migration, probe_set):
        results = [{"probe": i, "from": None, "to": None}
                   for i in range(len(probe_set))]
        out = migration.verify(URN, "1.0.0", from_digest="sha256:" + "a" * 64,
                               to_digest="sha256:" + "b" * 64,
                               to_format="onnx", probes=probe_set,
                               results=results, tolerance=1e-6,
                               ran_by="platform-team")
        assert out["outcome"] == PASSED

    def test_one_answering_and_one_refusing_is_a_divergence(self, migration,
                                                            probe_set):
        results = _agreeing(probe_set)
        results[0]["to"] = None
        out = migration.verify(URN, "1.0.0", from_digest="sha256:" + "a" * 64,
                               to_digest="sha256:" + "b" * 64,
                               to_format="onnx", probes=probe_set,
                               results=results, tolerance=1e6,
                               ran_by="platform-team")
        assert out["outcome"] == FAILED
        assert "no tolerance covers" in out["divergences"][0]["why"]

    def test_two_categories_are_never_nearly_the_same(self, migration,
                                                      probe_set):
        """A NaN gap compares as agreement, because every comparison with NaN
        is false and `nan > tolerance` reads as 'within tolerance'."""
        results = [{"probe": i, "from": "retail", "to": "manufacturing"}
                   for i in range(len(probe_set))]
        out = migration.verify(URN, "1.0.0", from_digest="sha256:" + "a" * 64,
                               to_digest="sha256:" + "b" * 64,
                               to_format="onnx", probes=probe_set,
                               results=results, tolerance=1e6,
                               ran_by="platform-team")
        assert out["outcome"] == FAILED


class TestAThinProbeSetIsNotAPass:
    def test_an_interior_only_set_is_unsubstantiated(self, migration):
        probes = [{"field": "dscr", "kind": "interior", "value": 3.0}]
        out = migration.verify(URN, "1.0.0", from_digest="sha256:" + "a" * 64,
                               to_digest="sha256:" + "b" * 64,
                               to_format="onnx", probes=probes,
                               results=[{"probe": 0, "from": 0.5, "to": 0.5}],
                               tolerance=1e-6, ran_by="platform-team")
        assert out["outcome"] == UNSUBSTANTIATED
        assert "This is not a pass" in out["detail"]

    def test_it_is_not_recorded_as_a_failure_either(self, migration):
        probes = [{"field": "dscr", "kind": "interior", "value": 3.0}]
        out = migration.verify(URN, "1.0.0", from_digest="sha256:" + "a" * 64,
                               to_digest="sha256:" + "b" * 64,
                               to_format="onnx", probes=probes,
                               results=[{"probe": 0, "from": 0.5, "to": 0.5}],
                               tolerance=1e-6, ran_by="platform-team")
        assert out["outcome"] != FAILED and not out["divergences"]


class TestTheRefusals:
    def test_a_tolerance_must_be_declared_with_the_claim(self, migration,
                                                         probe_set):
        with pytest.raises(ArtifactError) as e:
            migration.verify(URN, "1.0.0", from_digest="a", to_digest="b",
                             to_format="onnx", probes=probe_set, results=[],
                             ran_by="team")
        assert e.value.code == "tolerance_required"
        assert "exactly wide enough" in e.value.detail

    def test_whoever_ran_the_probes_must_be_named(self, migration, probe_set):
        with pytest.raises(ArtifactError) as e:
            migration.verify(URN, "1.0.0", from_digest="a", to_digest="b",
                             to_format="onnx", probes=probe_set, results=[],
                             tolerance=1e-6, ran_by="  ")
        assert e.value.code == "ran_by_required"

    def test_the_same_artifact_twice_is_refused(self, migration, probe_set):
        with pytest.raises(ArtifactError) as e:
            migration.verify(URN, "1.0.0", from_digest="a", to_digest="a",
                             to_format="onnx", probes=probe_set, results=[],
                             tolerance=1e-6, ran_by="team")
        assert e.value.code == "same_artifact"

    def test_the_claim_reaches_the_evidence_chain(self, migration, probe_set,
                                                  evidence):
        migration.verify(URN, "1.0.0", from_digest="sha256:" + "a" * 64,
                         to_digest="sha256:" + "b" * 64, to_format="onnx",
                         probes=probe_set, results=_agreeing(probe_set),
                         tolerance=1e-6, ran_by="platform-team")
        kinds = {n["kind"] for n in evidence.for_subject(
            migration.registry.version(URN, "1.0.0")["id"])}
        assert "migration_equivalence_claimed" in kinds
