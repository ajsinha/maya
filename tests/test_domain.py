"""
MAYA — domain algebra tests.

Includes the executable laws from docs/00-mathematical-foundations.md §12.
A failing law fails the build; that is the whole point of stating them.

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.domain import (Bound, Contract, ContractError, Field, FitProcedure,
                         ParameterKind,
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

    @pytest.mark.parametrize("kind", [ParameterKind.CALIBRATION_SET,
                                      ParameterKind.ESTIMATED_COEFFICIENTS,
                                      ParameterKind.LEARNED_WEIGHTS,
                                      ParameterKind.LLM_CONFIGURATION,
                                      ParameterKind.ELICITED_WEIGHTS,
                                      ParameterKind.RULE_SET])
    def test_inhabited_p_with_no_fit_procedure_still_reads_t0_here(self, kind):
        """Recorded as it is, not as it should be.

        `trainability_class` ends `_FIT_TO_CLASS.get(self.fit, "T0")`, and the
        one key missing from that map is `NONE`. So a kernel with real,
        inspectable parameters and no declared fit procedure comes back **T0** —
        the class meaning `P` is *terminal*, no parameters at all — and
        `requires_fitting_evidence` then exempts it from fitting evidence on the
        grounds that it has none to have fitted.

        The derivation is not wrong to be total; it has nothing else to return,
        and raising from a property would put a refusal somewhere nobody can
        act on it. The state is instead made **unreachable** one layer up, at
        version creation — see
        `test_registry.py::TestParametersMustBeExplained`. This test pins the
        fallback so that if the refusal is ever removed, the silent T0 shows up
        here as a documented consequence rather than as a surprise.
        """
        assert kernel(kind, FitProcedure.NONE).trainability_class == "T0"
        assert not kernel(kind, FitProcedure.NONE).requires_fitting_evidence

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


class TestBoundLattice:
    """`meet` and `join`, and the cases where neither exists.

    Both are partial, and both must say so rather than approximating. Widening
    two disjoint bands to the interval that spans them is the single failure
    this file exists to prevent: it claims a contract holds in the gap, where
    neither of the contracts it came from says anything at all.
    """

    def test_meet_is_the_overlap(self):
        assert Bound("x", 0, 1).meet(Bound("x", 0.5, 2)) == Bound("x", 0.5, 1)

    def test_meet_of_disjoint_bands_does_not_exist(self):
        assert Bound("x", 0, 1).meet(Bound("x", 5, 6)) is None

    def test_join_is_the_union_where_the_union_is_a_band(self):
        assert Bound("x", 0, 1).join(Bound("x", 0.5, 2)) == Bound("x", 0, 2)

    def test_join_of_disjoint_bands_does_not_exist(self):
        """`[0,1] ∪ [5,6]` is not a band, and `[0,6]` is not it."""
        assert Bound("x", 0, 1).join(Bound("x", 5, 6)) is None

    def test_an_absent_endpoint_means_unbounded_and_cuts_both_ways(self):
        """For a meet the other endpoint stands; for a join it swallows it.

        Getting this backwards is silent, and it inverts the operation.
        """
        assert Bound("g", minimum=0.4).meet(Bound("g", minimum=0.6)).minimum == 0.6
        assert Bound("g", minimum=0.4).join(Bound("g", minimum=0.6)).minimum == 0.4
        assert Bound("g", 0, 1).join(Bound("g", minimum=0)).maximum is None

    def test_categories_meet_by_intersection_and_join_by_union(self):
        us_ca, ca_gb = Bound("r", allowed=("US", "CA")), Bound("r", allowed=("CA", "GB"))
        assert us_ca.meet(ca_gb).allowed == ("CA",)
        assert set(us_ca.join(ca_gb).allowed) == {"US", "CA", "GB"}

    def test_a_category_and_a_band_have_neither(self):
        """Not a disagreement about width. A disagreement about kind."""
        assert Bound("r", allowed=("US",)).meet(Bound("r", minimum=1)) is None
        assert Bound("r", allowed=("US",)).join(Bound("r", minimum=1)) is None


class TestContractAlgebra:
    """Three operations that answer three questions.

    They were one line of code each, and it was the same line: concatenate both
    tuples. `⊗`, `∧` and `/` returned identical contracts for identical inputs,
    which made the algebra decorative — and worse than decorative in `/`, which
    discharged a requirement whenever the partner merely mentioned the key.
    """

    def test_composition_discharges_what_the_upstream_guarantees(self):
        """The whole difference between `⊗` and `∧`.

        Downstream assumes a score in [0,1]; upstream guarantees exactly that.
        Nobody outside the pair has to supply it.
        """
        upstream = Contract(assumptions=(Bound("turnover", 0, 1e9),),
                            guarantees=(Bound("score", 0, 1),))
        downstream = Contract(assumptions=(Bound("score", 0, 1),
                                           Bound("region", allowed=("US",))),
                              guarantees=(Bound("pd", 0, 1),))
        result = upstream.composed_with(downstream)
        assert result.discharged == ("score",)
        assert [b.key for b in result.contract.assumptions] == ["turnover", "region"]
        assert {b.key for b in result.contract.guarantees} == {"score", "pd"}

    def test_an_upstream_that_speaks_to_a_key_without_settling_it_is_reported(self):
        """The finding somebody wiring two models together needs.

        Upstream promises a score in [0,5]; downstream assumes [0,1]. The
        boundary looks covered and is not, and the assumption stays on the
        caller rather than quietly disappearing.
        """
        upstream = Contract(guarantees=(Bound("score", 0, 5),))
        downstream = Contract(assumptions=(Bound("score", 0, 1),))
        result = upstream.composed_with(downstream)
        assert result.unmet == ("score",) and result.discharged == ()
        assert [b.key for b in result.contract.assumptions] == ["score"]

    def test_composition_refuses_guarantees_that_cannot_both_hold(self):
        a = Contract(guarantees=(Bound("latency_ms", maximum=50),))
        b = Contract(guarantees=(Bound("latency_ms", minimum=200),))
        with pytest.raises(ContractError) as exc:
            a.compose(b)
        assert exc.value.code == "no_guarantee_meet"

    def test_conjunction_takes_the_stronger_guarantee(self):
        perf = Contract(guarantees=(Bound("gini", minimum=0.4),))
        fair = Contract(guarantees=(Bound("gini", minimum=0.6), Bound("air", minimum=0.8)))
        joined = perf.conjoin(fair)
        assert {b.key: b.minimum for b in joined.guarantees} == {"gini": 0.6, "air": 0.8}

    def test_conjunction_widens_the_assumptions_rather_than_narrowing_them(self):
        """A contract promises nothing outside its assumptions, so holding two
        entitles the model to the union of the regions they cover. Intersecting
        here would narrow where a model may be used every time somebody added a
        viewpoint, which is the opposite of what adding one means."""
        perf = Contract(assumptions=(Bound("x", 0, 10),))
        fair = Contract(assumptions=(Bound("x", 5, 20),))
        assert perf.conjoin(fair).assumptions == (Bound("x", 0, 20),)

    def test_an_assumption_only_one_viewpoint_makes_constrains_nothing(self):
        perf = Contract(assumptions=(Bound("x", 0, 10), Bound("y", 0, 1)))
        fair = Contract(assumptions=(Bound("x", 5, 20),))
        assert [b.key for b in perf.conjoin(fair).assumptions] == ["x"]

    def test_conjunction_refuses_viewpoints_with_a_gap_between_them(self):
        perf = Contract(assumptions=(Bound("x", 0, 1),))
        fair = Contract(assumptions=(Bound("x", 5, 6),))
        with pytest.raises(ContractError) as exc:
            perf.conjoin(fair)
        assert exc.value.code == "no_assumption_join"

    def test_quotient_yields_the_missing_specification(self):
        target = Contract(guarantees=(Bound("gini", minimum=0.4), Bound("air", minimum=0.8)))
        have = Contract(guarantees=(Bound("gini", minimum=0.4),))
        assert {b.key for b in target.quotient(have).guarantees} == {"air"}

    def test_a_partner_that_promises_too_little_discharges_nothing(self):
        """The defect this rewrite exists for.

        A challenger promising `gini ≥ 0.2` used to satisfy a target of
        `gini ≥ 0.4`, because the old implementation asked only whether the key
        appeared. The residual came back empty, and an empty residual reads as
        *nothing more is needed*.
        """
        target = Contract(guarantees=(Bound("gini", minimum=0.4),))
        weak = Contract(guarantees=(Bound("gini", minimum=0.2),))
        residual = target.quotient(weak)
        assert [b.key for b in residual.guarantees] == ["gini"]
        assert residual.guarantees[0].minimum == 0.4

    def test_the_residual_may_rely_on_what_the_partner_guarantees(self):
        target = Contract(assumptions=(Bound("x", 0, 10),),
                          guarantees=(Bound("air", minimum=0.8),))
        have = Contract(guarantees=(Bound("score", 0, 1),))
        assert {b.key for b in target.quotient(have).assumptions} == {"x", "score"}

    def test_quotient_of_everything_is_empty(self):
        c = Contract(guarantees=(Bound("gini", minimum=0.4),))
        assert c.quotient(c).guarantees == ()

    def test_the_three_operations_are_not_the_same_operation(self):
        """They were. Byte for byte, all three concatenated both tuples.

        Held as a test rather than as a note, because the way this regresses is
        somebody simplifying three implementations that look similar back into
        one.
        """
        a = Contract(assumptions=(Bound("x", 0, 10),), guarantees=(Bound("s", 0, 1),))
        b = Contract(assumptions=(Bound("x", 5, 20), Bound("s", 0, 1)),
                     guarantees=(Bound("p", 0, 1),))
        results = {"compose": a.compose(b), "conjoin": a.conjoin(b),
                   "quotient": a.quotient(b)}
        shapes = {name: (tuple(sorted(c.assumptions, key=lambda bd: bd.key)),
                         tuple(sorted(c.guarantees, key=lambda bd: bd.key)))
                  for name, c in results.items()}
        assert len(set(shapes.values())) == 3, shapes
        # And the difference is not only in which keys survive. Composition
        # MEETS the shared assumption because both must hold of one wired
        # system; conjunction JOINS it because two viewpoints on one model
        # cover the union of what each covers.
        assert a.compose(b).assumptions == (Bound("x", 5, 10),)
        assert a.conjoin(b).assumptions == (Bound("x", 0, 20),)


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
        """Every combination yields exactly one class in T0..T8. No gaps, no crashes.

        Worth being clear about what this does *not* say, because it is a good
        example of a green test that guards less than its name suggests: it
        asserts the function is **total**, and totality stays true when the
        answer is wrong. It passed happily over the combination — inhabited,
        accessible `P` with `fit_procedure: none` — that returned T0 and thereby
        exempted a model with parameters from fitting evidence.

        Totality was never the property at risk. Correctness on each combination
        is, and that is the parametrised table above, one row at a time.
        """
        kinds, fits = list(ParameterKind), list(FitProcedure)
        k = kernel(kinds[i % len(kinds)], fits[i % len(fits)])
        assert k.trainability_class in {f"T{n}" for n in range(9)}


class TestTheUnitIsPartOfTheType:
    """`Field.unit`'s own docstring says a replacement declaring `bp` where the
    incumbent declared `ratio` is a hundred-fold error that every type check
    passes. Three places let exactly that through.

    The comparison existed, on `Schema.provides_superset_of`, and that method
    had no callers at all — `substitutable` asks `lattice.provides`, which
    compared name and dtype only. A rule written twice is a rule enforced in
    whichever copy nobody calls.
    """

    def test_a_version_changing_ratio_to_basis_points_is_not_a_substitute(self):
        from core.domain.lattice import provides
        from core.domain.schemas import Field, Schema

        ratio = Schema((Field("ltv", "numeric", unit="ratio"),))
        basis_points = Schema((Field("ltv", "numeric", unit="bp"),))
        assert provides(basis_points, ratio) == ("ltv",), \
            "a hundred-fold change of scale is not a compatible output"
        assert provides(ratio, ratio) == ()

    def test_an_incumbent_that_declared_no_unit_still_accepts_one(self):
        """The asymmetry is deliberate: callers of a field that never declared
        a unit cannot have been relying on one."""
        from core.domain.lattice import provides
        from core.domain.schemas import Field, Schema

        silent = Schema((Field("ltv", "numeric"),))
        stated = Schema((Field("ltv", "numeric", unit="ratio"),))
        assert provides(stated, silent) == ()

    def test_the_two_implementations_agree_because_there_is_one(self):
        from core.domain.lattice import provides
        from core.domain.schemas import Field, Schema

        a = Schema((Field("x", "numeric", unit="GBP"),))
        b = Schema((Field("x", "numeric", unit="USD"),))
        assert a.provides_superset_of(b) == list(provides(a, b)) == ["x"]

    def test_a_meet_carries_the_unit_rather_than_erasing_it(self):
        """`meet` rebuilt every Field without `symbol` or `unit`, so anything
        checked against a computed meet — "can one featureset serve both these
        models" — had its unit constraint silently dropped."""
        from core.domain.lattice import join, meet
        from core.domain.schemas import Field, Schema

        a = Schema((Field("ltv", "numeric", unit="ratio", symbol=r"\lambda"),))
        b = Schema((Field("ltv", "numeric", unit="ratio"),))
        assert meet(a, b).fields[0].unit == "ratio"
        assert meet(a, b).fields[0].symbol == r"\lambda"
        assert join(a, b).fields[0].unit == "ratio"

    def test_two_schemas_measuring_in_different_units_have_no_meet(self):
        from core.domain.lattice import NoMeet, meet
        from core.domain.schemas import Field, Schema

        ratio = Schema((Field("ltv", "numeric", unit="ratio"),))
        basis_points = Schema((Field("ltv", "numeric", unit="bp"),))
        with pytest.raises(NoMeet) as refusal:
            meet(ratio, basis_points)
        assert "ratio" in str(refusal.value) and "bp" in str(refusal.value)
