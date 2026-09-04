"""
MAYA — domain algebra tests.

Includes the executable laws from docs/00-mathematical-foundations.md §12.
A failing law fails the build; that is the whole point of stating them.

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.domain import (Bound, Contract, Field, FitProcedure, OutputKind, ParameterKind,
                         ParameterObject, ParametricKernel, Probe, Schema, pi_equivalent,
                         substitutable)


def kernel(kind, fit=FitProcedure.NONE, adaptive=False, **kw):
    return ParametricKernel(ParameterObject(kind), Schema(), Schema(),
                            fit=fit, adaptive=adaptive, **kw)


# ============================================================ trainability
class TestTrainabilityClassification:
    """The class is DERIVED from how P is inhabited. It is never declared."""

    @pytest.mark.parametrize("kind,fit,adaptive,expected", [
        (ParameterKind.NONE,                   FitProcedure.NONE,      False, "T0"),
        (ParameterKind.CALIBRATION_SET,        FitProcedure.CALIBRATE, False, "T1"),
        (ParameterKind.ESTIMATED_COEFFICIENTS, FitProcedure.ESTIMATE,  False, "T2"),
        (ParameterKind.LEARNED_WEIGHTS,        FitProcedure.TRAIN,     False, "T3"),
        (ParameterKind.LEARNED_WEIGHTS,        FitProcedure.TRAIN,     True,  "T4"),
        (ParameterKind.LLM_CONFIGURATION,      FitProcedure.CONFIGURE, False, "T5"),
        (ParameterKind.OPAQUE,                 FitProcedure.NONE,      False, "T6"),
        (ParameterKind.ELICITED_WEIGHTS,       FitProcedure.ELICIT,    False, "T7"),
        (ParameterKind.RULE_SET,               FitProcedure.AUTHOR,    False, "T8"),
    ])
    def test_all_nine_classes(self, kind, fit, adaptive, expected):
        assert kernel(kind, fit, adaptive).trainability_class == expected

    def test_terminal_parameter_object_is_the_t0_case(self):
        assert ParameterObject(ParameterKind.NONE).is_terminal

    def test_opaque_parameters_are_inaccessible_but_exist(self):
        p = ParameterObject(ParameterKind.OPAQUE)
        assert not p.is_accessible
        assert not p.is_terminal, "a vendor model HAS parameters; you just cannot see them"

    def test_opaque_wins_over_fit_procedure(self):
        """A vendor model stays T6 whatever fitting procedure is claimed for it."""
        assert kernel(ParameterKind.OPAQUE, FitProcedure.TRAIN).trainability_class == "T6"

    @pytest.mark.parametrize("kind,fit", [(ParameterKind.NONE, FitProcedure.NONE),
                                          (ParameterKind.OPAQUE, FitProcedure.NONE)])
    def test_t0_and_t6_require_no_fitting_evidence(self, kind, fit):
        """Asking a closed-form pricer for a training set is a type error."""
        assert kernel(kind, fit).requires_fitting_evidence is False

    @pytest.mark.parametrize("kind,fit", [
        (ParameterKind.CALIBRATION_SET, FitProcedure.CALIBRATE),
        (ParameterKind.ESTIMATED_COEFFICIENTS, FitProcedure.ESTIMATE),
        (ParameterKind.LEARNED_WEIGHTS, FitProcedure.TRAIN),
    ])
    def test_fitted_classes_require_evidence(self, kind, fit):
        assert kernel(kind, fit).requires_fitting_evidence is True


# ============================================================ law L-12
class TestSchemaVariance:
    """Law L-12: contravariant in inputs, covariant in outputs."""

    def test_identical_schemas_are_substitutable(self):
        s = Schema((Field("a", "float"),))
        assert substitutable(s, s, s, s).ok

    def test_accepting_more_inputs_is_allowed(self):
        old_in = Schema((Field("a", "float", minimum=0, maximum=10),))
        new_in = Schema((Field("a", "float", minimum=-5, maximum=20),))
        assert substitutable(new_in, Schema(), old_in, Schema()).ok

    def test_narrowing_an_input_range_regresses(self):
        old_in = Schema((Field("a", "float", minimum=0, maximum=10),))
        new_in = Schema((Field("a", "float", minimum=2, maximum=8),))
        r = substitutable(new_in, Schema(), old_in, Schema())
        assert not r.ok and "a" in r.input_regressions

    def test_dropping_an_input_regresses(self):
        r = substitutable(Schema(), Schema(), Schema((Field("a", "float"),)), Schema())
        assert not r.ok and "a" in r.input_regressions

    def test_dropping_an_output_regresses(self):
        r = substitutable(Schema(), Schema(), Schema(), Schema((Field("y", "float"),)))
        assert not r.ok and "y" in r.output_regressions

    def test_adding_an_output_is_allowed(self):
        new_out = Schema((Field("y", "float"), Field("extra", "float")))
        assert substitutable(Schema(), new_out, Schema(), Schema((Field("y", "float"),))).ok

    def test_changing_an_output_dtype_regresses(self):
        r = substitutable(Schema(), Schema((Field("y", "string"),)),
                          Schema(), Schema((Field("y", "float"),)))
        assert not r.ok

    def test_refusing_nulls_the_old_version_accepted_regresses(self):
        old_in = Schema((Field("a", "float", nullable=True),))
        new_in = Schema((Field("a", "float", nullable=False),))
        assert not substitutable(new_in, Schema(), old_in, Schema()).ok

    def test_reason_names_the_offending_field(self):
        r = substitutable(Schema(), Schema(), Schema((Field("dscr", "float"),)), Schema())
        assert "dscr" in r.reason()


# ============================================================ law L-7
class TestContractRefinement:
    """Law L-7: a replacement must weaken assumptions and strengthen guarantees."""

    @staticmethod
    def c(a=(), g=()):
        return Contract(assumptions=tuple(a), guarantees=tuple(g))

    def test_identical_contracts_refine_each_other(self):
        k = self.c([Bound("x", 0, 10)], [Bound("gini", 0.4)])
        assert k.refines(k).holds

    def test_weaker_assumption_and_stronger_guarantee_refines(self):
        old = self.c([Bound("x", 0, 10)], [Bound("gini", minimum=0.40)])
        new = self.c([Bound("x", -5, 20)], [Bound("gini", minimum=0.45)])
        assert new.refines(old).holds

    def test_narrower_assumption_does_not_refine(self):
        old = self.c([Bound("x", 0, 10)], [])
        new = self.c([Bound("x", 2, 8)], [])
        r = new.refines(old)
        assert not r.holds and "x" in r.assumption_failures

    def test_weaker_guarantee_does_not_refine(self):
        old = self.c([], [Bound("gini", minimum=0.45)])
        new = self.c([], [Bound("gini", minimum=0.40)])
        r = new.refines(old)
        assert not r.holds and "gini" in r.guarantee_failures

    def test_dropping_a_guarantee_does_not_refine(self):
        r = self.c().refines(self.c([], [Bound("gini", minimum=0.4)]))
        assert not r.holds

    def test_dropping_an_assumption_is_a_weakening_and_refines(self):
        """Promising to work everywhere is stronger than promising a narrow band."""
        assert self.c().refines(self.c([Bound("x", 0, 10)])).holds

    def test_reason_explains_the_failure(self):
        r = self.c([Bound("x", 2, 8)]).refines(self.c([Bound("x", 0, 10)]))
        assert "assumptions not weakened" in r.reason()

    def test_categorical_assumption_widening(self):
        old = self.c([Bound("region", allowed=("US",))])
        new = self.c([Bound("region", allowed=("US", "CA"))])
        assert new.refines(old).holds
        assert not old.refines(new).holds


class TestContractBoundaryChecks:
    def test_input_inside_the_boundary_passes(self):
        c = Contract(assumptions=(Bound("dscr", 0.0, 20.0),))
        assert c.check_inputs({"dscr": 1.2}) == []

    @pytest.mark.parametrize("value", [-1.0, 25.0])
    def test_input_outside_the_boundary_is_named(self, value):
        c = Contract(assumptions=(Bound("dscr", 0.0, 20.0),))
        assert c.check_inputs({"dscr": value}) == ["dscr"]

    def test_unmentioned_keys_are_not_constrained(self):
        c = Contract(assumptions=(Bound("dscr", 0.0, 20.0),))
        assert c.check_inputs({"other": 999}) == []

    def test_non_numeric_value_against_a_numeric_bound_fails(self):
        c = Contract(assumptions=(Bound("dscr", 0.0, 20.0),))
        assert c.check_inputs({"dscr": "not a number"}) == ["dscr"]

    def test_categorical_membership(self):
        c = Contract(assumptions=(Bound("region", allowed=("US", "CA")),))
        assert c.check_inputs({"region": "US"}) == []
        assert c.check_inputs({"region": "GB"}) == ["region"]


class TestContractAlgebra:
    def test_composition_carries_both_sets(self):
        a = Contract(assumptions=(Bound("x", 0, 1),), guarantees=(Bound("p", minimum=0.5),))
        b = Contract(assumptions=(Bound("y", 0, 1),), guarantees=(Bound("q", minimum=0.5),))
        composed = a.compose(b)
        assert {bd.key for bd in composed.assumptions} == {"x", "y"}
        assert {bd.key for bd in composed.guarantees} == {"p", "q"}

    def test_conjunction_merges_viewpoints(self):
        perf = Contract(guarantees=(Bound("gini", minimum=0.4),))
        fair = Contract(guarantees=(Bound("air", minimum=0.8),))
        assert {b.key for b in perf.conjoin(fair).guarantees} == {"gini", "air"}

    def test_quotient_yields_the_missing_specification(self):
        target = Contract(guarantees=(Bound("gini", minimum=0.4), Bound("air", minimum=0.8)))
        have = Contract(guarantees=(Bound("gini", minimum=0.4),))
        assert {b.key for b in target.quotient(have).guarantees} == {"air"}

    def test_quotient_of_everything_is_empty(self):
        c = Contract(guarantees=(Bound("gini", minimum=0.4),))
        assert c.quotient(c).guarantees == ()


# ============================================================ probe equivalence
class TestProbeRelativeEquivalence:
    """Equivalence is only ever as strong as the probe set is rich."""

    def test_identical_outputs_are_equivalent(self):
        probes = [Probe("p1", {"a": 1}), Probe("p2", {"b": 2})]
        r = pi_equivalent({"p1": 1.0, "p2": 2.0}, {"p1": 1.0, "p2": 2.0}, probes, declared_inputs=2)
        assert r.equivalent and r.probe_count == 2

    def test_divergence_is_named(self):
        probes = [Probe("p1", {"a": 1})]
        r = pi_equivalent({"p1": 1.0}, {"p1": 2.0}, probes)
        assert not r.equivalent and r.divergences == ("p1",)

    def test_tolerance_admits_small_differences(self):
        probes = [Probe("p1", {"a": 1})]
        assert pi_equivalent({"p1": 1.0}, {"p1": 1.0005}, probes, tolerance=0.001).equivalent

    def test_tolerance_does_not_admit_large_differences(self):
        probes = [Probe("p1", {"a": 1})]
        assert not pi_equivalent({"p1": 1.0}, {"p1": 1.5}, probes, tolerance=0.001).equivalent

    def test_non_numeric_outputs_compare_by_equality(self):
        probes = [Probe("p1", {"a": 1})]
        assert pi_equivalent({"p1": "APPROVE"}, {"p1": "APPROVE"}, probes).equivalent
        assert not pi_equivalent({"p1": "APPROVE"}, {"p1": "DECLINE"}, probes).equivalent

    def test_coverage_is_reported_with_the_claim(self):
        """A thin probe set must be visible, not silently assumed adequate."""
        probes = [Probe("p1", {"a": 1})]
        r = pi_equivalent({"p1": 1}, {"p1": 1}, probes, declared_inputs=10)
        assert r.equivalent and r.coverage == 0.1

    def test_empty_probe_set_claims_equivalence_with_zero_coverage(self):
        """The honest failure mode: it 'passes' but the coverage says nothing was tested."""
        r = pi_equivalent({}, {}, [], declared_inputs=5)
        assert r.equivalent and r.coverage == 0.0


# ============================================================ property-based
class TestLawsUnderGeneratedInput:
    @settings(max_examples=200, deadline=None)
    @given(lo=st.floats(-1e3, 1e3), hi=st.floats(-1e3, 1e3))
    def test_refinement_is_reflexive(self, lo, hi):
        c = Contract(assumptions=(Bound("x", min(lo, hi), max(lo, hi)),))
        assert c.refines(c).holds

    @settings(max_examples=200, deadline=None)
    @given(a=st.floats(-100, 100), b=st.floats(-100, 100), c=st.floats(-100, 100))
    def test_refinement_is_transitive(self, a, b, c):
        """Widening bounds must compose: if C3 <= C2 and C2 <= C1 then C3 <= C1."""
        w1, w2, w3 = sorted([abs(a), abs(b), abs(c)])
        k1 = Contract(assumptions=(Bound("x", -w1, w1),))
        k2 = Contract(assumptions=(Bound("x", -w2, w2),))
        k3 = Contract(assumptions=(Bound("x", -w3, w3),))
        if k3.refines(k2).holds and k2.refines(k1).holds:
            assert k3.refines(k1).holds

    @settings(max_examples=200, deadline=None)
    @given(st.lists(st.tuples(st.text(min_size=1, max_size=6), st.sampled_from(["float", "int"])),
                    min_size=0, max_size=6, unique_by=lambda t: t[0]))
    def test_substitutability_is_reflexive(self, spec):
        s = Schema(tuple(Field(n, d) for n, d in spec))
        assert substitutable(s, s, s, s).ok

    @settings(max_examples=200, deadline=None)
    @given(st.integers(0, 8))
    def test_trainability_is_a_total_function(self, i):
        """Every combination yields exactly one class in T0..T8. No gaps, no crashes."""
        kinds, fits = list(ParameterKind), list(FitProcedure)
        k = kernel(kinds[i % len(kinds)], fits[i % len(fits)])
        assert k.trainability_class in {f"T{n}" for n in range(9)}
