"""Comparing the runs, saying whether any could be repeated, and where they may
happen at all.

A parameter set under one version is an experiment. "Promote a run to a version"
is a category error and saying so is the answer. And "reproducible" is a property
of a claim, not of a wish.
"""
from __future__ import annotations

import pytest

from core.execution.errors import WarrantError
from core.execution.zones import DEFAULT_HANDLES, ComputeZones
from core.parameters.experiments import BUNDLE, Experiments
from tests.conftest import KERNEL, URN

NO_ASSUMPTIONS = {"assumptions": [], "guarantees": [],
                  "on_boundary_violation": "reject"}


class FakeParameters:
    class Repo:
        def __init__(self, rows):
            self._rows = rows

        def many(self, **where):
            return [r for r in self._rows
                    if all(r.get(k) == v for k, v in where.items())]

        def one(self, **where):
            found = self.many(**where)
            return found[0] if found else None

    def __init__(self, rows):
        self.parameters = self.Repo(rows)


def _run(version_id, n, *, diagnostics=None, snapshot="snap-1",
         featureset="fsv-1", warrant="w-1", window=(0.0, 1.0),
         state="recorded"):
    return {"id": f"ps-{n}", "model_version_id": version_id,
            "name": "coefficients", "version": n, "state": state,
            "provenance": "fitted", "cardinality": 12,
            "digest": f"sha256:{n}", "warrant_id": warrant,
            "snapshot_id": snapshot, "featureset_version_id": featureset,
            "window_from": window[0] if window else None,
            "window_to": window[1] if window else None,
            "diagnostics": diagnostics or {}, "created_at": float(n)}


@pytest.fixture
def versioned(registry, a_model):
    v = registry.create_version(URN, "1.0.0", KERNEL, NO_ASSUMPTIONS,
                                artifact_digest="sha256:" + "a" * 64,
                                actor="d.raman")
    return v["id"]


def _experiments(registry, rows):
    return Experiments(FakeParameters(rows), registry)


class TestComparingRuns:
    def test_a_version_nobody_fitted_says_so(self, registry, versioned):
        out = _experiments(registry, []).compare(URN, "1.0.0")
        assert out["count"] == 0
        assert "nobody has fitted" in out["detail"]

    def test_runs_are_put_side_by_side_on_shared_metrics(self, registry,
                                                         versioned):
        rows = [_run(versioned, 1, diagnostics={"gini": 0.60, "ks": 0.4}),
                _run(versioned, 2, diagnostics={"gini": 0.63, "ks": 0.5})]
        out = _experiments(registry, rows).compare(URN, "1.0.0")
        assert out["metrics"] == ["gini", "ks"]
        assert out["runs"][1]["metrics"]["gini"] == 0.63

    def test_no_numeric_diagnostic_is_a_fact_about_the_fitter(self, registry,
                                                              versioned):
        out = _experiments(registry, [_run(versioned, 1)]).compare(URN, "1.0.0")
        assert out["metrics"] == []
        assert "a fact about the fitter" in out["detail"]

    def test_runs_over_different_inputs_are_named_as_unlike(self, registry,
                                                            versioned):
        """Runs over the same inputs differ because of the procedure; runs over
        different inputs differ for reasons nobody has separated."""
        rows = [_run(versioned, 1, snapshot="snap-1"),
                _run(versioned, 2, snapshot="snap-2")]
        out = _experiments(registry, rows).compare(URN, "1.0.0")
        assert out["differ_only_in_parameters"] is False
        assert "a table of unlike things" in out["detail"]

    def test_runs_over_the_same_inputs_are_comparable(self, registry,
                                                      versioned):
        rows = [_run(versioned, 1), _run(versioned, 2)]
        out = _experiments(registry, rows).compare(URN, "1.0.0")
        assert out["differ_only_in_parameters"] is True


class TestPromotionIsACategoryError:
    def test_it_is_refused_with_the_algebra(self):
        """Promoting a point of P to a kernel would mean the kernel changed
        because somebody re-fitted."""
        out = Experiments.promotion()
        assert out["supported"] is False
        assert "point in `P`" in out["why_not"]
        assert "committee meets every morning" in out["why_not"]

    def test_it_points_at_the_act_that_is_actually_meant(self):
        out = Experiments.promotion()
        assert "approve the parameter set" in out["what_to_do_instead"]
        assert "L-7" in out["if_the_kernel_really_changed"]

    def test_it_travels_with_the_comparison(self, registry, versioned):
        out = _experiments(registry, [_run(versioned, 1)]).compare(URN, "1.0.0")
        assert out["promotion"]["supported"] is False


class TestReproducibleIsAClaim:
    def test_everything_present_reads_as_reproducible(self, registry,
                                                      versioned):
        row = _run(versioned, 1, diagnostics={"seed": 42,
                                              "lockfile_digest": "sha256:l",
                                              "commit": "abc123"})
        out = _experiments(registry, [row]).bundle(row)
        assert out["reproducible"] is True and out["missing"] == []
        assert "only the fitter could supply" in out["detail"]

    def test_a_missing_snapshot_is_fatal_and_named_as_the_reason(
            self, registry, versioned):
        """Re-running on a different population is not a reproduction."""
        row = _run(versioned, 1, snapshot=None)
        out = _experiments(registry, [row]).bundle(row)
        assert out["reproducible"] is False
        assert "snapshot" in out["fatal"]
        assert "different experiment" in out["detail"]

    def test_a_missing_seed_does_not_make_it_irreproducible(self, registry,
                                                            versioned):
        """The register can guarantee which data was read; the seed is the
        fitter's, and its absence is stated rather than assumed away."""
        row = _run(versioned, 1)
        out = _experiments(registry, [row]).bundle(row)
        assert out["reproducible"] is True
        assert {m["fact"] for m in out["missing"]} == {"seed", "environment",
                                                       "commit"}
        assert "cannot reconstruct an environment it never had" in out["detail"]

    def test_the_bundle_ranks_by_threat_not_by_count(self):
        """*Seven fields missing* is not a finding."""
        assert BUNDLE["snapshot"]["threat"] == "fatal"
        assert BUNDLE["environment"]["threat"] == "moderate"
        assert all(v["why"] and v["from"] for v in BUNDLE.values())

    def test_the_seed_is_found_under_any_of_its_names(self, registry,
                                                      versioned):
        for key in ("seed", "random_seed", "rng_seed"):
            row = _run(versioned, 1, diagnostics={key: 7})
            out = _experiments(registry, [row]).bundle(row)
            assert "seed" in out["present"], key

    def test_the_estate_names_the_commonest_gap(self, registry, versioned):
        rows = [_run(versioned, n) for n in (1, 2, 3)]
        out = _experiments(registry, rows).across_the_estate()
        assert out["fitted_runs"] == 3
        assert out["missing_by_fact"]["seed"] == 3
        assert "a fact the fitter supplies" in out["detail"]


class TestComputeZones:
    class Classified:
        def __init__(self, level):
            self.level = level

        def of_model(self, urn):
            return {"classification": self.level}

    def test_no_zones_configured_refuses_sensitive_work(self):
        """Allowing it by omission is what a zone policy exists to prevent."""
        zones = ComputeZones(classification=self.Classified("restricted"))
        with pytest.raises(WarrantError) as caught:
            zones.check(URN, "anywhere")
        assert caught.value.code == "zone_may_not_hold_this_data"
        assert "treated as the weakest rather than trusted" in (
            caught.value.detail)

    def test_an_internal_fit_runs_anywhere(self):
        zones = ComputeZones(classification=self.Classified("internal"))
        assert zones.check(URN, "anywhere")["permitted"] is True

    def test_a_cleared_zone_permits_restricted_work(self):
        zones = ComputeZones(
            zones=[{"name": "eu-secure", "residency": "EU",
                    "handles": "restricted", "purposes": ["credit"]}],
            classification=self.Classified("restricted"))
        assert zones.check(URN, "eu-secure", "credit")["permitted"] is True

    def test_purpose_limitation_is_separate_from_residency(self):
        """Purpose limitation is not about where the data is, it is about what
        it was gathered to do."""
        zones = ComputeZones(
            zones=[{"name": "eu-secure", "residency": "EU",
                    "handles": "restricted", "purposes": ["credit"]}],
            classification=self.Classified("restricted"))
        with pytest.raises(WarrantError) as caught:
            zones.check(URN, "eu-secure", "marketing")
        assert caught.value.code == "purpose_not_permitted_in_zone"

    def test_without_a_classification_it_assumes_the_strictest(self):
        """Guessing `internal` would let a restricted fit through on an
        instance where nobody wired the lattice in."""
        zones = ComputeZones(zones=[{"name": "z", "handles": "confidential"}])
        with pytest.raises(WarrantError):
            zones.check(URN, "z")

    def test_the_default_is_the_weakest(self):
        assert DEFAULT_HANDLES == "internal"
        assert "allowing it by omission is what a zone policy exists to\n            prevent".replace("\n            ", " ") in (
            ComputeZones().describe()["detail"])

    def test_enforcement_is_at_issue_and_says_so(self):
        assert ComputeZones().describe()["enforced_at"] == "warrant issue"


class TestWhereItRanIsAnAttestation:
    def test_a_matching_attestation_is_recorded(self, evidence):
        zones = ComputeZones(evidence=evidence)
        out = zones.attest("w-1", ran_in="eu-secure", authorised="eu-secure")
        assert out["matched"] is True and out["kind"] == "attestation"
        assert "MAYA did not run the training" in out["detail"]

    def test_a_mismatch_is_a_finding_and_not_a_refusal(self, evidence):
        """By the time it is known the run has happened, and refusing would be
        theatre."""
        zones = ComputeZones(evidence=evidence)
        out = zones.attest("w-1", ran_in="us-east", authorised="eu-secure")
        assert out["matched"] is False
        assert "refusing here would be theatre" in out["detail"]

    def test_it_lands_on_the_evidence_chain(self, evidence):
        ComputeZones(evidence=evidence).attest("w-1", ran_in="a",
                                               authorised="a")
        assert any(n["kind"] == "compute_zone_attested"
                   for n in evidence.repo.many())


class TestOverHttp:
    def test_the_estate_reproducibility_is_served(self, registered, people):
        r = registered.get("/api/v1/experiments", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        assert "bundle" in r.json()

    def test_a_versions_runs_are_served_with_the_promotion_answer(
            self, registered, people):
        from tests.conftest import URN as U
        r = registered.get("/api/v1/experiments", auth=people["d.raman"],
                           params={"urn": U, "semver": "3.2.1"})
        assert r.status_code == 200, r.text
        assert r.json()["promotion"]["supported"] is False

    def test_an_unknown_parameter_set_is_refused(self, registered, people):
        r = registered.get("/api/v1/reproducibility", auth=people["d.raman"],
                           params={"parameter_set_id": "nope"})
        assert r.status_code == 404, r.text

    def test_the_zones_are_served(self, client, people):
        r = client.get("/api/v1/compute-zones", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        assert r.json()["enforced_at"] == "warrant issue"

    def test_the_page_says_why_there_is_no_promote_button(self, registered,
                                                          people):
        from tests.conftest import NAME
        registered.post("/login", data={"username": "admin",
                                        "password": "maya-admin-dev",
                                        "next": "/dashboard"})
        body = registered.get(f"/model-algebra/version/{NAME}").text
        assert "is the answer rather than an omission" in body
        assert "property of a claim, not of a" in body
