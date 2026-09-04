"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The loop from a featureset to an approved point of P.

Every piece of this existed and none of it had ever been run together, because
nothing in the platform could produce a parameter set: the implementation plan
said so in as many words -- parameters were stored, not computed. These tests
walk the whole path, so a control that only works when somebody hands it a
hand-written dictionary is a control that fails here.
"""
from __future__ import annotations

import math

import pytest

from core.execution.errors import WarrantError
from core.parameters.common import PROPOSED, ParameterError
from tests.conftest import URN

AS_OF = 1736899200.0
WINDOW = {"from": 1546300800.0, "to": 1735603200.0}
EVENT = 1717200000.0


@pytest.fixture
def warrants_with_features(repos, registry, evidence, full_features):
    """A warrant service that can check a featureset against a kernel.

    resolve_fit refuses without one, and rightly: whether a set provides what a
    particular kernel reads is only answerable once both are named.
    """
    from core.execution import WarrantService
    return WarrantService(repos["warrants"], registry, evidence, jitter_pct=0,
                          featuresets=full_features.sets)


@pytest.fixture
def fitting(engine_for_fit, warrants_with_features, parameters, full_features,
            db, delta, evidence):
    from core.parameters import FittingService
    from db import SnapshotRepository
    return FittingService(engine_for_fit, warrants_with_features, parameters,
                          full_features, SnapshotRepository(db), delta, evidence)


@pytest.fixture
def engine_for_fit(warrants_with_features):
    from core.execution.engine import CaptiveEngine
    return CaptiveEngine(warrants_with_features)


@pytest.fixture
def fittable(registry, a_model, contract_spec):
    """A version whose kernel says it is fitted by ordinary least squares."""
    kernel = {"parameter_kind": "estimated_coefficients",
              "fit_procedure": "estimate",
              "runtime": "estimator",
              "entry": {"family": "ols", "target": "spend",
                        "regressors": ["dscr", "turnover"]},
              "input_schema": [{"name": "dscr", "dtype": "numeric"},
                               {"name": "turnover", "dtype": "numeric"}],
              "output_schema": [{"name": "spend", "dtype": "numeric"}]}
    registry.create_version(URN, "3.2.1", kernel, contract_spec)
    approved = registry.approve_version(URN, "3.2.1")
    registry.move_alias(URN, "prod", "champion", "3.2.1")
    return approved


@pytest.fixture
def snapshot(full_features):
    """A training set assembled from a published featureset version.

    The rows follow spend = 5 + 2*dscr - 0.5*turnover exactly, so a fit that
    does not recover those three numbers has not fitted anything.
    """
    f = full_features
    for name in ("dscr", "turnover", "spend"):
        f.define(name, "borrower_id", "numeric", f"the {name}", "person/d.raman")
    columns = ["dscr", "turnover", "spend"]
    f.create_view("sb_credit", "borrower_id", "person/j.okafor", columns)
    rows = []
    for i in range(60):
        dscr, turnover = 1.0 + i * 0.05, 100.0 + (i % 7) * 3.0
        rows.append({"entity_id": f"B{i}", "event_ts": EVENT, "ingest_ts": EVENT,
                     "dscr": dscr, "turnover": turnover,
                     "spend": 5.0 + 2.0 * dscr - 0.5 * turnover})
    f.materialise("sb_credit", rows, columns)
    f.define_featureset("sb_set", "borrower_id", "person/j.okafor",
                        {"dscr": "numeric", "turnover": "numeric",
                         "spend": "numeric"})
    f.publish_featureset("sb_set", {"dscr": "dscr", "turnover": "turnover",
                                    "spend": "spend"})
    spine = [{"entity_id": f"B{i}", "label_ts": AS_OF} for i in range(60)]
    return f.build_from_featureset("sb_set", 1, spine, AS_OF)


@pytest.fixture
def entitled(warrants_with_features, a_model):
    return warrants_with_features.issue(URN, "prod", "svc/model-lab", "model_development",
                          actor="person/j.okafor")


class TestTheFitLoopCloses:
    def test_a_fit_recovers_the_relationship_in_the_data(
            self, fitting, fittable, snapshot, entitled):
        """The whole point. If this passes, the path from a featureset version
        to a point of P runs, and every control on it has been exercised against
        a real fit rather than a hand-written dictionary."""
        out = fitting.fit(URN, snapshot["id"], "prod", "svc/model-lab",
                          "model_development", WINDOW, name="ols_v1",
                          actor="person/d.raman")
        values = out["values_inline"]
        assert values["intercept"] == pytest.approx(5.0, abs=1e-6)
        assert values["dscr"] == pytest.approx(2.0, abs=1e-6)
        assert values["turnover"] == pytest.approx(-0.5, abs=1e-6)

    def test_the_fit_lands_proposed_and_not_approved(
            self, fitting, fittable, snapshot, entitled):
        """A fit that approved its own output would have removed the one control
        the parameter object exists to carry."""
        out = fitting.fit(URN, snapshot["id"], "prod", "svc/model-lab",
                          "model_development", WINDOW, actor="person/d.raman")
        assert out["state"] == PROPOSED

    def test_the_parameter_set_names_what_produced_it(
            self, fitting, fittable, snapshot, entitled):
        out = fitting.fit(URN, snapshot["id"], "prod", "svc/model-lab",
                          "model_development", WINDOW, actor="person/d.raman")
        assert out["snapshot_id"] == snapshot["id"]
        # The grant, not the descriptor: a resolved warrant is minted per call
        # and never stored, so the grant is the only thing the register can
        # check when it asks "did this come from us".
        assert out["warrant_id"] == entitled["id"]
        assert out["descriptor_id"] != entitled["id"]
        assert out["fitted_from"]["featureset"] == "sb_set"
        assert out["fitted_from"]["featureset_version"] == 1
        assert out["fitted_from"]["rows"] == 60

    def test_the_diagnostics_a_validator_asks_for_travel_with_it(
            self, fitting, fittable, snapshot, entitled):
        """The platform does not decide whether a fit is any good. It puts the
        numbers in front of somebody who can."""
        d = fitting.fit(URN, snapshot["id"], "prod", "svc/model-lab",
                        "model_development", WINDOW, actor="person/d.raman")["diagnostics"]
        assert d["family"] == "ols"
        assert d["r_squared"] == pytest.approx(1.0)
        assert set(d["standard_errors"]) == {"intercept", "dscr", "turnover"}
        assert d["condition_number"] is not None
        assert d["rows"] == 60 and d["pit_verified"] is True

    def test_the_fit_reads_the_pinned_delta_version_not_the_head(
            self, fitting, fittable, snapshot, entitled, delta):
        """A fit run twice on one snapshot must see the same bytes, even when
        the table has been written to since. Otherwise 'reproduce this fit' has
        no meaning and neither does replaying the validation that used it."""
        first = fitting.fit(URN, snapshot["id"], "prod", "svc/model-lab",
                            "model_development", WINDOW, actor="person/d.raman")
        delta.write(snapshot["delta_table"],
                    [{"entity_id": "X", "dscr": 99.0, "turnover": 1.0,
                      "spend": 0.0, "label_ts": AS_OF}], mode="append")
        second = fitting.fit(URN, snapshot["id"], "prod", "svc/model-lab",
                             "model_development", WINDOW, actor="person/d.raman")
        assert second["values_inline"] == first["values_inline"]
        assert second["diagnostics"]["rows"] == 60


class TestWhatTheLoopRefuses:
    def test_a_fit_without_an_entitlement_is_refused_before_anything_is_read(
            self, fitting, fittable, snapshot):
        """Authority first. A read performed under an authority that turns out
        not to exist has already happened."""
        with pytest.raises(WarrantError) as exc:
            fitting.fit(URN, snapshot["id"], "prod", "svc/nobody",
                        "model_development", WINDOW, actor="person/d.raman")
        assert exc.value.code == "no_entitlement"

    def test_a_snapshot_that_names_no_featureset_is_refused(
            self, fitting, fittable, entitled, full_features):
        """A snapshot assembled from bare views satisfies no declared schema, so
        'which slots are these columns' has no answer."""
        f = full_features
        f.define("dscr", "borrower_id", "numeric", "d", "person/d.raman")
        f.create_view("bare", "borrower_id", "person/j.okafor", ["dscr"])
        f.materialise("bare", [{"entity_id": "B1", "event_ts": EVENT,
                                "ingest_ts": EVENT, "dscr": 1.0}], ["dscr"])
        loose = f.assembly.build("loose", [{"entity_id": "B1", "label_ts": AS_OF}],
                                 [{"view": "bare", "version": 1}], AS_OF)
        with pytest.raises(ParameterError) as exc:
            fitting.fit(URN, loose["id"], "prod", "svc/model-lab",
                        "model_development", WINDOW, actor="person/d.raman")
        assert exc.value.code == "snapshot_not_from_a_featureset"

    def test_an_unknown_snapshot_is_refused_by_name(self, fitting, fittable,
                                                    entitled):
        with pytest.raises(ParameterError) as exc:
            fitting.fit(URN, "no-such-snapshot", "prod", "svc/model-lab",
                        "model_development", WINDOW, actor="person/d.raman")
        assert exc.value.code == "no_snapshot"


class TestTheEstimatorRefusesRatherThanGuesses:
    """A fit that cannot be defended is worse than no fit: it produces numbers
    of exactly the same shape as a good one, and nothing downstream can tell."""

    def _fit(self, rows, entry):
        from core.execution.runtimes import EstimatorRuntime, Invocation
        warrant = {"operation": {"verb": "fit"},
                   "realisation": {"runtime": "estimator", "entry": entry}}
        return EstimatorRuntime().invoke(Invocation(warrant, {"rows": rows}))

    def _linear(self, n=60, **extra):
        return [{"a": i * 0.5, "b": math.sin(i / 3.0),
                 "y": 2 + 3 * (i * 0.5) - 1.5 * math.sin(i / 3.0), **extra}
                for i in range(n)]

    def test_it_recovers_coefficients_exactly_on_a_noiseless_relationship(self):
        out = self._fit(self._linear(),
                        {"family": "ols", "target": "y", "regressors": ["a", "b"]})
        assert out["values"]["a"] == pytest.approx(3.0, abs=1e-9)
        assert out["values"]["b"] == pytest.approx(-1.5, abs=1e-9)

    def test_an_exactly_collinear_regressor_is_refused_not_arbitrated(self):
        """lstsq would happily return one of infinitely many answers, and the
        coefficient a validator reads would be an artefact of the solver."""
        rows = [{**r, "double_a": r["a"] * 2} for r in self._linear()]
        with pytest.raises(WarrantError) as exc:
            self._fit(rows, {"family": "ols", "target": "y",
                             "regressors": ["a", "double_a"]})
        assert exc.value.code == "collinear_regressors"

    def test_fitting_the_target_on_itself_is_refused(self):
        with pytest.raises(WarrantError) as exc:
            self._fit(self._linear(), {"family": "ols", "target": "y",
                                       "regressors": ["a", "y"]})
        assert exc.value.code == "target_is_a_regressor"

    def test_a_missing_value_is_refused_rather_than_dropped_or_zeroed(self):
        """Dropping changes the population the fit speaks for without saying so.
        The featureset's fill policy is where that decision belongs, because
        there it is on the record and somebody chose it."""
        rows = self._linear()
        rows[7]["a"] = None
        with pytest.raises(WarrantError) as exc:
            self._fit(rows, {"family": "ols", "target": "y",
                             "regressors": ["a", "b"]})
        assert exc.value.code == "value_not_numeric"

    def test_too_few_rows_is_refused_rather_than_reported_with_a_perfect_fit(self):
        with pytest.raises(WarrantError) as exc:
            self._fit(self._linear(n=10), {"family": "ols", "target": "y",
                                           "regressors": ["a", "b"]})
        assert exc.value.code == "too_few_rows"

    def test_a_runtime_that_scores_is_not_one_that_fits(self):
        from core.execution.runtimes import EstimatorRuntime, Invocation
        warrant = {"operation": {"verb": "score"},
                   "realisation": {"entry": {"family": "ols"}}}
        with pytest.raises(WarrantError) as exc:
            EstimatorRuntime().invoke(Invocation(warrant, {"rows": []}))
        assert exc.value.code == "wrong_verb"


class TestGarch:
    """The non-linear family, which is here because it exercises the part a
    closed-form fit leaves untested: an iterative fit can fail to converge, and
    three numbers from a search that stopped early look exactly like three
    numbers from one that finished."""

    @staticmethod
    def _series(n=3000, omega=0.02, alpha=0.10, beta=0.85):
        """A GARCH path driven by a fixed sequence, so the test is reproducible
        without depending on anyone's random number generator."""
        state, draws = 12345, []
        for _ in range(n):
            state = (1103515245 * state + 12345) % (2 ** 31)
            u1 = (state + 1) / (2 ** 31 + 1)
            state = (1103515245 * state + 12345) % (2 ** 31)
            u2 = (state + 1) / (2 ** 31 + 1)
            draws.append(math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2))
        h, prev, rows = omega / (1 - alpha - beta), 0.0, []
        for z in draws:
            h = omega + alpha * prev ** 2 + beta * h
            prev = math.sqrt(h) * z
            rows.append({"r": prev})
        return rows

    def _fit(self, rows):
        from core.execution.runtimes import EstimatorRuntime, Invocation
        warrant = {"operation": {"verb": "fit"},
                   "realisation": {"runtime": "estimator",
                                   "entry": {"family": "garch11", "series": "r"}}}
        return EstimatorRuntime().invoke(Invocation(warrant, {"rows": rows}))

    def test_it_recovers_the_parameters_that_generated_the_series(self):
        out = self._fit(self._series())
        assert out["values"]["alpha"] == pytest.approx(0.10, abs=0.05)
        assert out["values"]["beta"] == pytest.approx(0.85, abs=0.06)
        assert out["diagnostics"]["converged"] is True

    def test_the_same_rows_give_the_same_digits(self):
        """A fit nobody can reproduce is a number in the register with no
        provenance, so there is no randomness anywhere in the optimiser."""
        rows = self._series(n=500)
        assert self._fit(rows)["values"] == self._fit(rows)["values"]

    def test_the_fit_is_constrained_to_be_stationary(self):
        """alpha + beta >= 1 has no unconditional variance, so the model would
        forecast an exploding one and the long-run figure beside it would be
        meaningless or negative."""
        out = self._fit(self._series())
        assert out["diagnostics"]["persistence"] < 1.0
        assert out["diagnostics"]["long_run_variance"] > 0

    def test_a_series_that_does_not_move_has_no_volatility_to_model(self):
        with pytest.raises(WarrantError) as exc:
            self._fit([{"r": 1.0} for _ in range(60)])
        assert exc.value.code == "series_is_constant"
