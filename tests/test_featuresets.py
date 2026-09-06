"""
MAYA — tests for derived features, featuresets and fitted parameters.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The worked example is a multiple linear regression predicting New Jersey home
prices — small enough to hold in your head, and it exercises every rule here:
a derived feature that reads the row's own clock, one that would leak the label,
a schema that a wider model cannot consume, and a roll-forward that leaves the
version somebody trained on exactly where it was.
"""
from __future__ import annotations

import datetime as dt

import pytest

from core.domain.schemas import Field, Schema
from core.features import FeatureError

ENTITY = "property_id"
SALE = dt.datetime(2024, 6, 1, tzinfo=dt.timezone.utc).timestamp()

PRIMITIVES = [
    ("living_area_sqft", "numeric"), ("lot_size_sqft", "numeric"),
    ("bedrooms", "integer"), ("bathrooms", "numeric"),
    ("year_built", "integer"), ("municipality_code", "categorical"),
    ("school_rating", "numeric"), ("sale_price", "numeric"),
]
CHARACTERISTICS = [n for n, _ in PRIMITIVES if n != "sale_price"]
DERIVED = ["log_living_area", "lot_to_living_ratio", "property_age"]


def _houses(n=6):
    return [{"entity_id": f"P{i}", "event_ts": SALE, "ingest_ts": SALE,
             "living_area_sqft": 1800.0 + i * 40, "lot_size_sqft": 7000.0 + i * 250,
             "bedrooms": 3, "bathrooms": 2.5, "year_built": 1962 + i,
             "municipality_code": "MONTCLAIR", "school_rating": 7.0 + i * 0.1}
            for i in range(n)]


@pytest.fixture
def nj(full_features):
    """The NJ estate: primitives defined, derived declared, views materialised."""
    f = full_features
    for name, dtype in PRIMITIVES:
        f.define(name, ENTITY, dtype, f"NJ {name}", "person/j.okafor")
    f.define_derived("log_living_area", "log(living_area_sqft)", "numeric",
                     "log of heated floor area", "person/d.raman")
    f.define_derived("lot_to_living_ratio", "lot_size_sqft / living_area_sqft",
                     "numeric", "parcel to floor area", "person/d.raman")
    f.define_derived("property_age", "year(event_ts) - year_built", "numeric",
                     "age at the observation date", "person/d.raman")

    rows = _houses()
    for name in DERIVED:
        rows = f.compute_derived(name, rows)
    columns = CHARACTERISTICS + DERIVED
    f.create_view("nj_characteristics", ENTITY, "person/j.okafor", columns)
    f.materialise("nj_characteristics", rows, columns)
    f.create_view("nj_transactions", ENTITY, "person/j.okafor", ["sale_price"])
    f.materialise("nj_transactions",
                  [{"entity_id": r["entity_id"], "event_ts": SALE,
                    "ingest_ts": SALE, "sale_price": 600000.0 + i * 15000}
                   for i, r in enumerate(rows)], ["sale_price"])
    return f


CORE_SLOTS = {"log_living_area": "numeric", "lot_to_living_ratio": "numeric",
              "bedrooms": "integer", "bathrooms": "numeric",
              "property_age": "numeric", "municipality_code": "categorical",
              "sale_price": "numeric"}
CORE_BINDINGS = {k: k for k in CORE_SLOTS}


@pytest.fixture
def core(nj):
    nj.define_featureset("nj_home_core", ENTITY, "person/j.okafor", CORE_SLOTS,
                         label_slot="sale_price")
    return nj.publish_featureset("nj_home_core", CORE_BINDINGS)


# ================================================================ expressions
class TestTheExpressionLanguageIsSmallOnPurpose:
    def test_it_computes_arithmetic_over_feature_values(self, nj):
        rows = nj.compute_derived("lot_to_living_ratio",
                                  [{"entity_id": "P", "event_ts": SALE, "ingest_ts": SALE,
                                    "lot_size_sqft": 8000.0, "living_area_sqft": 2000.0}])
        assert rows[0]["lot_to_living_ratio"] == 4.0

    def test_it_reads_the_row_s_own_clock_not_today(self, nj):
        """A house built in 1962 is 62 in a 2024 sale however long ago that was."""
        rows = nj.compute_derived("property_age",
                                  [{"entity_id": "P", "event_ts": SALE,
                                    "ingest_ts": SALE, "year_built": 1962}])
        assert rows[0]["property_age"] == 62

    def test_undefined_arithmetic_is_a_null_not_a_failure(self, nj):
        """One bad row must not fail a materialisation of a million."""
        rows = nj.compute_derived("lot_to_living_ratio",
                                  [{"entity_id": "P", "event_ts": SALE, "ingest_ts": SALE,
                                    "lot_size_sqft": 8000.0, "living_area_sqft": 0.0}])
        assert rows[0]["lot_to_living_ratio"] is None

    @pytest.mark.parametrize("hostile", [
        "__import__('os').system('ls')", "open('/etc/passwd').read()",
        "living_area_sqft.__class__", "[x for x in (1, 2)]",
        "(lambda: 1)()", "globals()",
    ])
    def test_it_admits_nothing_that_is_not_arithmetic(self, nj, hostile):
        with pytest.raises(FeatureError):
            nj.define_derived("hostile", hostile, "numeric", "no", "person/x")

    def test_a_constant_is_not_a_derived_feature(self, nj):
        with pytest.raises(FeatureError, match="constant"):
            nj.define_derived("always_four", "2 + 2", "numeric", "no", "person/x")

    def test_an_undefined_input_is_refused(self, nj):
        with pytest.raises(FeatureError, match="undefined inputs"):
            nj.define_derived("bogus", "acreage * 2", "numeric", "no", "person/x")


# ============================================== the external evaluator, reached
class TestAnExpressionMayaCannotRead:
    """`external` is documented as the evaluator for an expression that "needs a
    library, external data or a model". It was unreachable for exactly those
    expressions: `define` parsed before it looked at `evaluator`, so anything
    the tiny language could not parse was refused whatever you declared it as.

    The only route left was to register the result as a primitive — which loses
    the lineage and the leakage check that keeping the definition was *for*. A
    feature that reads the label then arrives in the catalogue with nothing to
    catch it.
    """

    OUT_OF_LANGUAGE = "vendor.pd_model.score(living_area_sqft, year_built)"

    def test_an_out_of_language_expression_can_be_declared_external(self, nj):
        row = nj.define_derived(
            "vendor_pd", self.OUT_OF_LANGUAGE, "numeric", "vendor score",
            "person/x", evaluator="external",
            inputs=["living_area_sqft", "year_built"])
        assert row["evaluator"] == "external"
        assert row["expression"] == self.OUT_OF_LANGUAGE
        assert set(row["inputs"]) == {"living_area_sqft", "year_built"}

    def test_it_still_carries_lineage_which_is_the_point(self, nj):
        nj.define_derived("vendor_pd", self.OUT_OF_LANGUAGE, "numeric", "v",
                          "person/x", evaluator="external",
                          inputs=["living_area_sqft", "year_built"])
        assert "living_area_sqft" in nj.lineage("vendor_pd")

    def test_maya_refuses_to_compute_it(self, nj):
        nj.define_derived("vendor_pd", self.OUT_OF_LANGUAGE, "numeric", "v",
                          "person/x", evaluator="external",
                          inputs=["living_area_sqft", "year_built"])
        with pytest.raises(FeatureError, match="external"):
            nj.compute_derived("vendor_pd", [{"living_area_sqft": 1200.0}])

    def test_an_opaque_expression_must_declare_its_inputs(self, nj):
        """Without them there is no lineage and no leakage check, so an
        unparseable expression with no declared inputs is refused rather than
        recorded as a feature resting on nothing."""
        with pytest.raises(FeatureError, match="declare the features it reads"):
            nj.define_derived("vendor_pd", self.OUT_OF_LANGUAGE, "numeric", "v",
                              "person/x", evaluator="external")

    def test_declared_inputs_are_refused_on_an_internal_definition(self, nj):
        """Two lists that can disagree, and the leakage check would run against
        whichever one the reader happened to open."""
        with pytest.raises(FeatureError, match="two lists that can disagree"):
            nj.define_derived("ratio2", "lot_size_sqft / living_area_sqft",
                              "numeric", "d", "person/x",
                              inputs=["lot_size_sqft"])

    def test_a_declared_list_that_contradicts_a_parseable_expression_is_refused(self, nj):
        with pytest.raises(FeatureError, match="the declared list says"):
            nj.define_derived("ratio3", "lot_size_sqft / living_area_sqft",
                              "numeric", "d", "person/x", evaluator="external",
                              inputs=["lot_size_sqft"])

    def test_an_external_feature_is_still_checked_for_leakage(self, nj):
        """The whole reason the definition is kept.

        Leakage is refused where it can be — at featureset definition, once
        there is a label slot to leak *from*; there is nothing to check at
        define time, because a feature is not yet in relation to any label.

        So the declared inputs are what makes the check work at all: without
        them this expression would have been registered as a primitive, and a
        slot computed from the label would have been bound alongside the label
        with nothing to catch it.
        """
        nj.define_derived("vendor_ppsf", "vendor.f(sale_price)", "numeric", "c",
                          "person/x", evaluator="external",
                          inputs=["sale_price"])
        nj.define_featureset("vendor_leaky", ENTITY, "person/j.okafor",
                             {"x": "numeric", "sale_price": "numeric"},
                             label_slot="sale_price")
        with pytest.raises(FeatureError, match="leaks the answer"):
            nj.publish_featureset("vendor_leaky", {"x": "vendor_ppsf",
                                                   "sale_price": "sale_price"})


# ================================================================ derived rules
class TestDerivedFeaturesCarryTheirLineage:
    def test_lineage_is_the_transitive_closure(self, nj):
        nj.define_derived("age_squared", "property_age * property_age", "numeric",
                          "convexity in age", "person/d.raman")
        assert set(nj.lineage("age_squared")) == {"property_age", "year_built"}

    def test_a_primitive_knows_what_rests_on_it(self, nj):
        assert set(nj.dependants_of("living_area_sqft")) == {
            "log_living_area", "lot_to_living_ratio"}

    def test_a_feature_cannot_depend_on_itself(self, nj):
        with pytest.raises(FeatureError, match="itself"):
            nj.define_derived("loop", "loop + 1", "numeric", "no", "person/x")

    def test_a_cycle_through_another_feature_is_refused(self, nj):
        """A correction is a new definition version, so a cycle is reachable by
        redefining an input in terms of what already reads it."""
        nj.define_derived("area_index", "log_living_area * 2", "numeric",
                          "an index over the log", "person/d.raman")
        with pytest.raises(FeatureError, match="itself"):
            nj.define_derived("log_living_area", "area_index / 2",
                              "numeric", "no", "person/x")

    def test_the_ingest_clock_is_inherited_as_a_maximum(self, nj):
        """You did not know Z before you knew both its inputs. Taking anything
        less would make the value appear knowable earlier than it was."""
        later = SALE + 86400
        rows = nj.compute_derived("lot_to_living_ratio", [{
            "entity_id": "P", "event_ts": SALE, "ingest_ts": SALE,
            "lot_size_sqft": 8000.0, "living_area_sqft": 2000.0,
            "lot_size_sqft__ingest_ts": later}])
        assert rows[0]["ingest_ts"] == later

    def test_an_external_definition_is_kept_but_not_computed(self, nj):
        nj.define_derived("neighbourhood_embedding", "log(school_rating)",
                          "numeric", "a stand-in for a model-derived value",
                          "person/d.raman", evaluator="external")
        with pytest.raises(FeatureError, match="external"):
            nj.compute_derived("neighbourhood_embedding", _houses(1))
        assert nj.lineage("neighbourhood_embedding") == ["school_rating"]

    def test_certification_is_the_meet_of_its_inputs(self, nj):
        assert nj.derived.certification_of(["living_area_sqft"]) == "experimental"


# ================================================================== featuresets
class TestAFeaturesetIsASchemaAVersionFills:
    def test_a_version_pins_the_exact_view_version(self, core, nj):
        binding = core["bindings"]["bedrooms"]
        assert binding["view_version"] == 1
        assert binding["namespace"].endswith("/v1")

    def test_the_plan_carries_everything_an_engine_needs(self, core, nj):
        plan = nj.featureset_plan("nj_home_core", 1)
        assert plan["entity"] == ENTITY
        assert plan["label"]["feature"] == "sale_price"
        # The rule itself is executed against the operator in
        # tests/test_laws.py::TestL10TheAsOfOperator — a substring check here
        # passed happily while the published rule was wrong.
        assert plan["pit_rule"] == ("event_ts <= label_ts AND "
                                    "ingest_ts <= min(label_ts, as_of)")
        assert len(plan["slots"]) == len(CORE_SLOTS)

    def test_a_slot_left_unfilled_is_refused(self, nj):
        nj.define_featureset("partial", ENTITY, "person/j.okafor", CORE_SLOTS,
                             label_slot="sale_price")
        with pytest.raises(FeatureError, match="unfilled"):
            nj.publish_featureset("partial", {"bedrooms": "bedrooms"})

    def test_a_binding_naming_no_slot_is_refused(self, nj):
        """Adding a slot changes X, which is a model change, not a data change."""
        nj.define_featureset("strict", ENTITY, "person/j.okafor", CORE_SLOTS,
                             label_slot="sale_price")
        with pytest.raises(FeatureError, match="no declared slot"):
            nj.publish_featureset("strict",
                                  {**CORE_BINDINGS, "school_rating": "school_rating"})

    def test_a_slot_filled_with_the_wrong_type_is_refused(self, nj):
        nj.define_featureset("mistyped", ENTITY, "person/j.okafor",
                             {"beds": "numeric"})
        with pytest.raises(FeatureError, match="integer"):
            nj.publish_featureset("mistyped", {"beds": "bedrooms"})

    def test_a_featureset_with_no_slots_is_not_one(self, nj):
        with pytest.raises(FeatureError, match="schema with nothing in it"):
            nj.define_featureset("empty", ENTITY, "person/j.okafor", {})

    def test_publishing_is_witnessed(self, core, repos):
        kinds = [e["kind"] for e in repos["evidence"].many()]
        assert "featureset_version_published" in kinds


class TestDifferentVersionsMayHoldDifferentFeatures:
    """The user's inflation case: same structure, different constituents."""

    def test_a_slot_can_be_refilled_with_another_feature(self, nj):
        nj.define_featureset("inflation", ENTITY, "person/j.okafor",
                             {"local_index": "numeric"})
        v1 = nj.publish_featureset("inflation", {"local_index": "school_rating"})
        v2 = nj.publish_featureset(
            "inflation", {"local_index": {"feature": "bathrooms",
                                          "view": "nj_characteristics",
                                          "view_version": 1}})
        assert v1["bindings"]["local_index"]["feature"] == "school_rating"
        assert v2["bindings"]["local_index"]["feature"] == "bathrooms"
        assert v1["digest"] != v2["digest"]

    def test_the_schema_is_unchanged_so_the_model_is_unchanged(self, nj):
        nj.define_featureset("inflation", ENTITY, "person/j.okafor",
                             {"local_index": "numeric"})
        nj.publish_featureset("inflation", {"local_index": "school_rating"})
        kernel = Schema((Field("local_index", "numeric"),))
        assert nj.featureset_satisfies("inflation", kernel)[0]


class TestTheSchemaIsCheckedAgainstTheKernel:
    def test_a_set_that_provides_what_the_kernel_reads_satisfies_it(self, core, nj):
        kernel = Schema(tuple(Field(n, t) for n, t in CORE_SLOTS.items()
                              if n != "sale_price"))
        assert nj.featureset_satisfies("nj_home_core", kernel) == (True, [])

    def test_a_wider_kernel_is_refused_and_says_what_is_missing(self, core, nj):
        """Adding a regressor is a model change, and the check says so by name."""
        kernel = Schema(tuple(Field(n, t) for n, t in CORE_SLOTS.items()
                              if n != "sale_price") + (Field("school_rating", "numeric"),))
        ok, missing = nj.featureset_satisfies("nj_home_core", kernel)
        assert not ok and missing == ["school_rating"]

    def test_the_label_is_not_offered_to_the_kernel(self, core, nj):
        assert "sale_price" not in [f.name for f in nj.sets.schema("nj_home_core").fields]


class TestLeakageIsRefusedNotDetected:
    def test_a_slot_computed_from_the_label_is_refused(self, nj):
        nj.define_derived("price_per_sqft", "sale_price / living_area_sqft",
                          "numeric", "price per square foot", "person/d.raman")
        nj.define_featureset("leaky", ENTITY, "person/j.okafor",
                             {"ppsf": "numeric", "sale_price": "numeric"},
                             label_slot="sale_price")
        with pytest.raises(FeatureError, match="leaks the answer"):
            nj.publish_featureset("leaky", {"ppsf": "price_per_sqft",
                                            "sale_price": "sale_price"})

    def test_it_is_refused_however_many_hops_away(self, nj):
        nj.define_derived("ppsf", "sale_price / living_area_sqft", "numeric",
                          "ppsf", "person/d.raman")
        nj.define_derived("log_ppsf", "log(ppsf)", "numeric", "log ppsf",
                          "person/d.raman")
        nj.define_featureset("sneaky", ENTITY, "person/j.okafor",
                             {"x": "numeric", "sale_price": "numeric"},
                             label_slot="sale_price")
        with pytest.raises(FeatureError, match="leaks the answer"):
            nj.publish_featureset("sneaky", {"x": "log_ppsf",
                                             "sale_price": "sale_price"})

    def test_it_bites_before_the_view_is_even_resolved(self, nj):
        """'you cannot train on the answer' beats 'no view supplies that'."""
        nj.define_derived("ppsf", "sale_price / living_area_sqft", "numeric",
                          "ppsf", "person/d.raman")
        nj.define_featureset("unmaterialised", ENTITY, "person/j.okafor",
                             {"x": "numeric", "sale_price": "numeric"},
                             label_slot="sale_price")
        with pytest.raises(FeatureError, match="leaks the answer"):
            nj.publish_featureset("unmaterialised",
                                  {"x": "ppsf", "sale_price": "sale_price"})


class TestRollingForwardIsDeliberate:
    def test_publishing_a_new_view_version_changes_nothing(self, core, nj):
        before = nj.featureset_plan("nj_home_core", 1)["namespaces"]
        nj.materialise("nj_characteristics", _houses(3),
                       CHARACTERISTICS + DERIVED)
        assert nj.featureset_plan("nj_home_core", 1)["namespaces"] == before

    def test_rolling_forward_mints_a_version_and_says_what_moved(self, core, nj):
        nj.materialise("nj_characteristics", _houses(3), CHARACTERISTICS + DERIVED)
        rolled = nj.roll_forward("nj_home_core")
        assert rolled["version"] == 2
        moved = {m["slot"] for m in rolled["moved"]}
        assert "bedrooms" in moved and "sale_price" not in moved

    def test_a_view_version_a_featureset_pins_cannot_be_retired(self, core, nj):
        assert nj.sets.can_retire("nj_characteristics", 1)[0] is False


# ================================================================== parameters
COEFFICIENTS = {
    "intercept": -142380.55, "log_living_area": 108422.31,
    "lot_to_living_ratio": 6218.04, "bedrooms": -4102.77,
    "bathrooms": 21845.90, "property_age": -1187.62,
    "municipality_code[MONTCLAIR]": 88214.03,
}
URN = "maya://model/credit.pd.smallbiz"


@pytest.fixture
def fit_warrant(warrants, approved_version):
    """A standing entitlement to fit. Parameters are accepted only against one."""
    return warrants.issue(URN, "lab", "svc/model-lab", "model_development",
                          actor="person/j.okafor")


class TestParametersComeBackUnderAWarrant:
    def test_a_fitted_set_is_recorded_against_the_version_and_the_featureset(
            self, parameters, approved_version, fit_warrant, core):
        row = parameters.record(
            URN, "3.2.1", "nj-core-2025q1", "estimated_coefficients",
            COEFFICIENTS, featureset="nj_home_core", featureset_version=1,
            warrant_id=fit_warrant["id"], as_of=SALE,
            diagnostics={"r_squared": 0.783, "n": 41208},
            actor="person/d.raman")
        assert row["state"] == "proposed" and row["provenance"] == "fitted"
        assert row["cardinality"] == len(COEFFICIENTS)
        assert row["values_inline"]["log_living_area"] == 108422.31
        assert row["featureset_version_id"] == core["id"]

    def test_a_fit_without_a_warrant_is_refused(self, parameters,
                                                approved_version, core):
        """Otherwise 'which data produced these numbers' has no answer."""
        with pytest.raises(Exception) as exc:
            parameters.record(URN, "3.2.1", "p", "estimated_coefficients",
                              COEFFICIENTS, featureset="nj_home_core",
                              featureset_version=1)
        assert exc.value.code == "warrant_required"

    def test_a_warrant_maya_did_not_issue_is_refused(self, parameters,
                                                     approved_version, core):
        with pytest.raises(Exception) as exc:
            parameters.record(URN, "3.2.1", "p", "estimated_coefficients",
                              COEFFICIENTS, featureset="nj_home_core",
                              featureset_version=1, warrant_id="not-ours")
        assert exc.value.code == "unknown_warrant"

    def test_a_revoked_warrant_is_refused(self, parameters, approved_version,
                                          fit_warrant, warrants, core):
        warrants.revoke(fit_warrant["id"], "the training data was wrong")
        with pytest.raises(Exception) as exc:
            parameters.record(URN, "3.2.1", "p", "estimated_coefficients",
                              COEFFICIENTS, featureset="nj_home_core",
                              featureset_version=1, warrant_id=fit_warrant["id"])
        assert exc.value.code == "warrant_revoked"

    def test_a_fit_must_name_the_featureset_that_produced_it(
            self, parameters, approved_version, fit_warrant):
        """Coefficients mean nothing without the columns they belong to."""
        with pytest.raises(Exception) as exc:
            parameters.record(URN, "3.2.1", "p", "estimated_coefficients",
                              COEFFICIENTS, warrant_id=fit_warrant["id"])
        assert exc.value.code == "featureset_required"

    def test_declared_parameters_need_neither(self, parameters, approved_version):
        """A closed form arrives with its parameters and never trains."""
        row = parameters.record(URN, "3.2.1", "black-scholes", "rule_set",
                                {"r": 0.04, "sigma": 0.22}, provenance="declared",
                                actor="person/j.okafor")
        assert row["provenance"] == "declared" and row["featureset_version_id"] is None

    def test_an_empty_parameter_set_is_refused(self, parameters, approved_version):
        with pytest.raises(Exception) as exc:
            parameters.record(URN, "3.2.1", "p", "rule_set", {},
                              provenance="declared")
        assert exc.value.code == "no_parameters"

    def test_recording_is_witnessed(self, parameters, approved_version,
                                    fit_warrant, core, repos):
        parameters.record(URN, "3.2.1", "p", "estimated_coefficients",
                          COEFFICIENTS, featureset="nj_home_core",
                          featureset_version=1, warrant_id=fit_warrant["id"])
        assert "parameter_set_recorded" in [e["kind"] for e in repos["evidence"].many()]


class TestApprovalIsSegregated:
    @pytest.fixture
    def recorded(self, parameters, approved_version, fit_warrant, core):
        return parameters.record(
            URN, "3.2.1", "nj-core", "estimated_coefficients", COEFFICIENTS,
            featureset="nj_home_core", featureset_version=1,
            warrant_id=fit_warrant["id"], actor="person/d.raman")

    def test_whoever_fitted_them_cannot_approve_them(self, parameters, recorded):
        with pytest.raises(Exception) as exc:
            parameters.approve(recorded["id"], "person/d.raman")
        assert exc.value.code == "self_approval"

    def test_somebody_else_can(self, parameters, recorded):
        row = parameters.approve(recorded["id"], "person/a.mehta", "residuals ok")
        assert row["state"] == "approved" and row["approved_by"] == "person/a.mehta"

    def test_rejection_needs_a_reason(self, parameters, recorded):
        with pytest.raises(Exception) as exc:
            parameters.reject(recorded["id"], "person/a.mehta", "  ")
        assert exc.value.code == "reason_required"

    def test_an_approved_set_cannot_be_reviewed_again(self, parameters, recorded):
        parameters.approve(recorded["id"], "person/a.mehta")
        with pytest.raises(Exception) as exc:
            parameters.reject(recorded["id"], "person/s.iqbal", "changed my mind")
        assert exc.value.code == "already_reviewed"


class TestResolvingWhatAVersionRunsOn:
    @pytest.fixture
    def approved(self, parameters, approved_version, fit_warrant, core):
        row = parameters.record(
            URN, "3.2.1", "nj-core", "estimated_coefficients", COEFFICIENTS,
            featureset="nj_home_core", featureset_version=1,
            warrant_id=fit_warrant["id"], actor="person/d.raman")
        return parameters.approve(row["id"], "person/a.mehta")

    def test_it_returns_the_approved_set(self, parameters, approved):
        assert parameters.resolve(URN, "3.2.1")["id"] == approved["id"]

    def test_nothing_unapproved_may_run(self, parameters, approved_version,
                                        fit_warrant, core):
        parameters.record(URN, "3.2.1", "nj-core", "estimated_coefficients",
                          COEFFICIENTS, featureset="nj_home_core",
                          featureset_version=1, warrant_id=fit_warrant["id"])
        with pytest.raises(Exception) as exc:
            parameters.resolve(URN, "3.2.1")
        assert exc.value.code == "no_approved_parameters"

    def test_two_candidates_and_no_name_is_refused_not_guessed(
            self, parameters, approved, approved_version, fit_warrant, core):
        """Choosing for the caller is how a model quietly runs on last
        quarter's coefficients."""
        other = parameters.record(
            URN, "3.2.1", "nj-enriched", "estimated_coefficients", COEFFICIENTS,
            featureset="nj_home_core", featureset_version=1,
            warrant_id=fit_warrant["id"], actor="person/d.raman")
        parameters.approve(other["id"], "person/a.mehta")
        with pytest.raises(Exception) as exc:
            parameters.resolve(URN, "3.2.1")
        assert exc.value.code == "ambiguous_parameters"
        assert parameters.resolve(URN, "3.2.1", "nj-core")["id"] == approved["id"]

    def test_the_status_says_whether_the_kernel_is_ready(self, parameters,
                                                         approved):
        status = parameters.status(URN, "3.2.1")
        assert status["ready"] and status["approved"] == 1
        assert "running on 'nj-core'" in status["detail"]

    def test_a_version_with_no_parameters_is_not_ready(self, parameters,
                                                       approved_version):
        status = parameters.status(URN, "3.2.1")
        assert not status["ready"]
        assert "cannot be run until it has some" in status["detail"]


class TestAssemblingFromAFeatureset:
    def test_a_snapshot_names_the_featureset_version_that_built_it(self, core, nj):
        spine = [{"entity_id": "P0", "label_ts": SALE + 1},
                 {"entity_id": "P1", "label_ts": SALE + 1}]
        snapshot = nj.build_from_featureset("nj_home_core", 1, spine, SALE + 10)
        assert snapshot["featureset"] == "nj_home_core"
        assert snapshot["featureset_version"] == 1
        assert snapshot["featureset_digest"] == core["digest"]
        assert snapshot["row_count"] == 2

    def test_it_reads_the_pinned_namespaces_and_not_the_newest(self, core, nj):
        """v1 was assembled from view v1, and stays that way after a refresh."""
        nj.materialise("nj_characteristics", _houses(3), CHARACTERISTICS + DERIVED)
        spine = [{"entity_id": "P0", "label_ts": SALE + 1}]
        snapshot = nj.build_from_featureset("nj_home_core", 1, spine, SALE + 10)
        assert snapshot["pit_verified"]

    def test_it_is_refused_if_the_assembly_cannot_be_shown_correct(self, core, nj):
        """No label timestamp means no point-in-time bound to check against."""
        from core.features import AssemblyRejected
        with pytest.raises((AssemblyRejected, KeyError)):
            nj.build_from_featureset("nj_home_core", 1,
                                     [{"entity_id": "P0"}], SALE + 10)


class TestAComposedFeaturesetCanActuallyBeFitted:
    """`schema()` read the row's own `slots`; `publish()` fills what
    `resolver.resolve` produces.

    So a featureset composed from parents — which declares nothing of its own —
    reported an **empty** schema and satisfied no kernel at all. A fit warrant
    naming it was refused `schema_not_satisfied`, listing slots the set
    demonstrably had and had just been published with.

    Composition is the ordinary case for this object, not an exotic one, and it
    was the case that could never be fitted. Two readings of "what slots does
    this have" have to be one reading, and it has to be the one `publish` uses,
    because that is the one the data fills.
    """

    @pytest.fixture
    def composed(self, nj):
        nj.define_featureset("nj_parent", ENTITY, "person/j.okafor", CORE_SLOTS,
                             label_slot="sale_price")
        nj.define_featureset("nj_child", ENTITY, "person/j.okafor", {},
                             composes=["nj_parent"], label_slot="sale_price")
        return nj

    def test_the_child_resolves_its_parents_slots(self, composed):
        assert set(composed.sets.resolved("nj_child")["slots"]) == set(CORE_SLOTS)

    def test_the_schema_is_the_resolved_one_not_the_declared_one(self, composed):
        """The declared one is empty; the resolved one is what gets filled."""
        named = {f.name for f in composed.sets.schema("nj_child").fields}
        assert named == set(CORE_SLOTS) - {"sale_price"}

    def test_it_satisfies_a_kernel_over_the_slots_it_inherited(self, composed):
        from core.domain.schemas import Field, Schema
        kernel = Schema((Field("log_living_area", "numeric"),
                         Field("bedrooms", "integer")))
        ok, missing = composed.sets.satisfies("nj_child", kernel)
        assert ok and not missing

    def test_a_kernel_reading_something_nobody_supplies_is_still_refused(
            self, composed):
        """The fix must not make satisfaction vacuous."""
        from core.domain.schemas import Field, Schema
        ok, missing = composed.sets.satisfies(
            "nj_child", Schema((Field("nobody_has_this", "numeric"),)))
        assert not ok and "nobody_has_this" in missing

    def test_an_uncomposed_set_is_unchanged(self, composed):
        named = {f.name for f in composed.sets.schema("nj_parent").fields}
        assert named == set(CORE_SLOTS) - {"sale_price"}


class TestCertificationIsAMeetAndStaysOne:
    """`certification_of` states "as certified as the least-certified input,
    never more". It was written onto the derived feature's row once, at
    definition, and never recomputed — so the invariant held at the moment of
    definition and was false from the first demotion onwards.

    Two certified inputs, a derivation, then deprecate one: the derivation went
    on reporting itself `certified`. That is the pattern this platform keeps
    finding — a value derived, then stored, then allowed to disagree with what
    it was derived from.
    """

    @pytest.fixture
    def derivation(self, nj):
        nj.certify("living_area_sqft", "certified")
        nj.certify("lot_size_sqft", "certified")
        return nj

    def test_the_meet_is_the_weakest_input(self, derivation):
        assert derivation.derived.certification_now("lot_to_living_ratio") == "certified"

    def test_demoting_an_input_demotes_the_derivation(self, derivation):
        derivation.certify("living_area_sqft", "deprecated")
        assert derivation.derived.certification_now("lot_to_living_ratio") == "deprecated"

    def test_restoring_it_restores_the_derivation(self, derivation):
        derivation.certify("living_area_sqft", "deprecated")
        derivation.certify("living_area_sqft", "certified")
        assert derivation.derived.certification_now("lot_to_living_ratio") == "certified"

    def test_deprecated_ranks_below_experimental_not_equal_to_it(self):
        """`deprecated` was outside the order the meet ranked over, so it fell
        to the fallback rank of 0 — the same rank as `experimental`. A feature
        built on a deprecated input was reported exactly as well-certified as
        one built on a merely experimental input, which is the opposite of what
        deprecating something is for."""
        from core.features.derived import CERTIFICATION_ORDER
        assert CERTIFICATION_ORDER.index("deprecated") < \
            CERTIFICATION_ORDER.index("experimental")

    def test_every_settable_level_can_be_ranked(self):
        """The order used to be a different vocabulary from the one `certify`
        accepts: `reviewed` and `gold` could never be set, and `deprecated`
        could never be ranked."""
        from core.features.catalogue import LEVELS
        from core.features.derived import CERTIFICATION_ORDER
        assert set(LEVELS) == set(CERTIFICATION_ORDER)

    def test_a_featureset_version_reports_the_current_meet(self, derivation, core):
        """The last place a stale certification should survive: a featureset
        version is exactly where somebody checks what they are training on."""
        derivation.certify("living_area_sqft", "deprecated")
        plan = derivation.featureset_plan("nj_home_core", 1)
        ratio = [s for s in plan["slots"] if s["slot"] == "lot_to_living_ratio"]
        assert ratio and ratio[0]["certification"] == "deprecated"


class TestTheAssemblerHonoursTheBindings:
    """The frame must be built from the columns the featureset names.

    A model developer published a featureset version pinning one slot to a view
    of constant values, fitted it, and got coefficients byte-identical to the
    unpinned fit. Swapping two regressor bindings produced the same numbers a
    third time. The bindings — published, digested and signed into the fit
    warrant — were reduced to a set of `(view, version)` pairs one call before
    they were used, and the assembler then name-joined every column of every
    view with last-write-wins.
    """

    @pytest.fixture
    def rival(self, nj):
        """A second view carrying a column of the SAME NAME, different values.

        This is the whole test. Two views supplying `school_rating`: the real
        one, and one where every house scores 1.0.
        """
        nj.create_view("nj_alt_ratings", ENTITY, "person/j.okafor", ["school_rating"])
        nj.materialise("nj_alt_ratings",
                       [{"entity_id": f"P{i}", "event_ts": SALE, "ingest_ts": SALE,
                         "school_rating": 1.0} for i in range(6)],
                       ["school_rating"])
        return nj

    def test_a_slot_pinned_to_one_view_reads_that_view(self, rival):
        """`school_rating` is bound to the rival view, so it must be 1.0.

        Under the old join it was whichever view was processed last — which was
        stable, invisible, and wrong.
        """
        # `bedrooms` drags `nj_characteristics` into the plan as well, so BOTH
        # views supply a `school_rating` column and the collision is live. That
        # is the reviewer's case: with only one view in the plan the old
        # name-join happened to pick the right value, and the test would pass
        # against the bug.
        slots = {"school_rating": "numeric", "bedrooms": "integer",
                 "sale_price": "numeric"}
        rival.define_featureset("pinned", ENTITY, "person/j.okafor", slots,
                                label_slot="sale_price")
        rival.publish_featureset("pinned", {
            "school_rating": {"feature": "school_rating", "view": "nj_alt_ratings",
                              "view_version": 1},
            "bedrooms": {"feature": "bedrooms", "view": "nj_characteristics",
                         "view_version": 1},
            "sale_price": "sale_price"})
        snapshot = rival.build_from_featureset(
            "pinned", 1, [{"entity_id": "P3", "label_ts": SALE + 1}], SALE + 10)
        rows = rival.assembly.delta.read(snapshot["delta_table"],
                                         snapshot["delta_version"])
        assert rows.to_dict("records")[0]["school_rating"] == 1.0

    def test_the_same_set_bound_to_the_other_view_reads_the_other_view(self, rival):
        """The counterpart, and the one that makes the first mean something.

        Two featureset versions differing ONLY in a binding must produce
        different frames. They produced identical ones.
        """
        slots = {"school_rating": "numeric", "bedrooms": "integer",
                 "sale_price": "numeric"}
        rival.define_featureset("either", ENTITY, "person/j.okafor", slots,
                                label_slot="sale_price")
        rival.publish_featureset("either", {
            "school_rating": {"feature": "school_rating",
                              "view": "nj_characteristics", "view_version": 1},
            # Present so the rival view is in the plan too, exactly as above.
            "bedrooms": {"feature": "bedrooms", "view": "nj_characteristics",
                         "view_version": 1},
            "sale_price": "sale_price"})
        snapshot = rival.build_from_featureset(
            "either", 1, [{"entity_id": "P3", "label_ts": SALE + 1}], SALE + 10)
        rows = rival.assembly.delta.read(snapshot["delta_table"],
                                         snapshot["delta_version"])
        # P3's real rating is 7.0 + 3 * 0.1, and emphatically not the rival's 1.0.
        assert rows.to_dict("records")[0]["school_rating"] == pytest.approx(7.3)

    def test_a_slot_may_be_named_differently_from_the_feature_filling_it(self, nj):
        """Slot and feature are different words for a reason.

        A set composed from parents routinely names a slot for the role it plays
        rather than for the feature that happens to fill it. The assembler
        copied the FEATURE's name into the frame, so such a set produced a frame
        whose columns were not the slots it declared.
        """
        nj.define_featureset("renamed", ENTITY, "person/j.okafor",
                             {"size": "numeric", "sale_price": "numeric"},
                             label_slot="sale_price")
        nj.publish_featureset("renamed", {
            "size": {"feature": "log_living_area", "view": "nj_characteristics",
                     "view_version": 1},
            "sale_price": "sale_price"})
        snapshot = nj.build_from_featureset(
            "renamed", 1, [{"entity_id": "P1", "label_ts": SALE + 1}], SALE + 10)
        row = nj.assembly.delta.read(snapshot["delta_table"],
                                     snapshot["delta_version"]).to_dict("records")[0]
        assert "size" in row and row["size"] is not None
        assert "log_living_area" not in row

    def test_only_the_bound_columns_arrive(self, core, nj):
        """A view holding ten features contributes the ones bound to a slot.

        Everything else it carries is somebody else's data, and a training frame
        that quietly includes it is a leakage surface nobody declared.
        """
        snapshot = nj.build_from_featureset(
            "nj_home_core", 1, [{"entity_id": "P0", "label_ts": SALE + 1}], SALE + 10)
        row = nj.assembly.delta.read(snapshot["delta_table"],
                                     snapshot["delta_version"]).to_dict("records")[0]
        arrived = set(row) - {"entity_id", "label_ts", "event_ts", "ingest_ts"}
        assert arrived == set(CORE_SLOTS), arrived
        # `living_area_sqft` is in the view and is bound to no slot.
        assert "living_area_sqft" not in row


class TestTheVerifierCanActuallyFail:
    """`pit_verified` has to be capable of being false.

    A developer bound the LABEL slot of one entity's featureset to a feature in
    an unrelated view and got 60 rows, `passed: true`, `violations: []` and
    "60 of 60 rows independently recomputed" — because the verifier walked the
    same view list the same way and made the same mistake.
    """

    def test_the_recomputation_resolves_each_column_from_its_own_binding(self, nj):
        """The structural property, asserted directly.

        `_join` groups columns by source and reads each view once; `_recompute`
        reads one view per column. If both grouped, a mis-grouping would be
        reproduced rather than caught.
        """
        import inspect

        from core.features.assembly import TrainingSetBuilder
        source = inspect.getsource(TrainingSetBuilder._recompute)
        assert "for column in columns" in source
        assert "by_source" not in source, (
            "the verifier groups by source like the join does, so a grouping "
            "mistake would be reproduced rather than caught")

    def test_it_reports_a_mismatch_when_the_frame_disagrees_with_the_bindings(
            self, core, nj):
        """Corrupt one assembled value; the verifier must notice.

        Done by recomputing against a frame somebody has tampered with, which is
        the only way to exercise the comparison without reintroducing the bug it
        exists to catch.
        """
        from core.features.assembly import Column
        from core.features.pit import verify_sampled

        plan = nj.sets.plan("nj_home_core", 1)
        columns = [Column(b["slot"], b["feature"], b["view"], b["view_version"])
                   for b in plan["slots"]]
        spine = [{"entity_id": "P0", "label_ts": SALE + 1}]
        rows = nj.assembly._join(spine, columns, SALE + 10)
        honest = verify_sampled(
            rows, lambda r: nj.assembly._recompute(r, columns, SALE + 10))
        assert honest.passed

        rows[0]["bedrooms"] = 999
        tampered = verify_sampled(
            rows, lambda r: nj.assembly._recompute(r, columns, SALE + 10))
        assert not tampered.passed, "the verifier accepted a value nothing produced"


class TestTwoSourcesForOneColumnIsRefused:
    def test_it_is_refused_rather_than_resolved_by_iteration_order(self, nj):
        """A frame whose contents depend on which view was read last is not
        reproducible, which is the one property this module exists to give."""
        from core.features import AssemblyRejected
        from core.features.assembly import Column

        columns = [Column("school_rating", "school_rating", "nj_characteristics", 1),
                   Column("school_rating", "school_rating", "nj_transactions", 1)]
        with pytest.raises(AssemblyRejected, match="same column"):
            nj.assembly._refuse_ambiguous(columns)


class TestTheSnapshotDigestIdentifiesTheData:
    """The value a fit warrant pins to say *this model was trained on this data*.

    It was a hash of the snapshot's name, its `as_of` and its row count. A
    developer reproduced the digest published in the shipped tutorial on
    completely different data, then produced a second, different 60-row set and
    got the same digest a third time. Reproducibility, replay and the training
    record all rest on this value, and it identified nothing.
    """

    def test_different_data_digests_differently(self, nj):
        from core.features.assembly import TrainingSetBuilder
        one = [{"entity_id": "P1", "x": 1.0}, {"entity_id": "P2", "x": 2.0}]
        two = [{"entity_id": "P1", "x": 1.0}, {"entity_id": "P2", "x": 9.9}]
        assert (TrainingSetBuilder.content_digest(one)
                != TrainingSetBuilder.content_digest(two))

    def test_the_same_facts_in_a_different_order_digest_alike(self, nj):
        """Or a replay that legitimately reorders would report tampering."""
        from core.features.assembly import TrainingSetBuilder
        rows = [{"entity_id": "P1", "x": 1.0}, {"entity_id": "P2", "x": 2.0}]
        assert (TrainingSetBuilder.content_digest(rows)
                == TrainingSetBuilder.content_digest(list(reversed(rows))))

    def test_row_count_and_name_alone_no_longer_decide_it(self, core, nj):
        """Two assemblies of the same name and shape, over different spines.

        Same snapshot name, same `as_of`, same row count — and different rows.
        Under the old digest these were indistinguishable.
        """
        first = nj.build_from_featureset(
            "nj_home_core", 1, [{"entity_id": "P0", "label_ts": SALE + 1}],
            SALE + 10, snapshot_name="same-name")
        second = nj.build_from_featureset(
            "nj_home_core", 1, [{"entity_id": "P3", "label_ts": SALE + 1}],
            SALE + 10, snapshot_name="same-name")
        assert first["row_count"] == second["row_count"] == 1
        assert first["as_of"] == second["as_of"]
        assert first["digest"] != second["digest"]

    def test_reassembling_the_same_thing_reproduces_the_digest(self, core, nj):
        """The property the digest exists to have, and the reason it cannot
        simply be made unique per call."""
        spine = [{"entity_id": "P0", "label_ts": SALE + 1}]
        again = [{"entity_id": "P0", "label_ts": SALE + 1}]
        assert (nj.build_from_featureset("nj_home_core", 1, spine, SALE + 10,
                                         snapshot_name="repeat")["digest"]
                == nj.build_from_featureset("nj_home_core", 1, again, SALE + 10,
                                            snapshot_name="repeat")["digest"])


class TestTheLeakageScreenRunsOnTheFeaturesetPath:
    """`detect_leakage(rows)` looks for a column named `label`.

    A featureset-assembled frame does not have one: the label sits under
    whatever slot the author named it — `defaulted` here, `charged_off` in
    somebody else's set. So the screen returned `[]` on its first line, every
    time, on the path the platform recommends. Every snapshot came back with no
    suspected leakage, which reads exactly like a clean one.
    """

    @pytest.fixture
    def credit(self, full_features):
        """Ten borrowers, a binary label, and one column that IS the label.

        `recovered` is `1 - defaulted`: the label wearing a different hat, which
        is what a leak looks like in practice. `region` is unrelated and must
        not be flagged, or the screen would be noise rather than a control.
        """
        f = full_features
        for name, dtype in (("recovered", "integer"), ("region", "categorical"),
                            ("defaulted", "integer")):
            f.define(name, "borrower_id", dtype, name, "person/j.okafor")
        rows = [{"entity_id": f"B{i}", "event_ts": SALE, "ingest_ts": SALE,
                 "recovered": 1 - (i % 2), "region": ["N", "S", "E"][i % 3]}
                for i in range(10)]
        f.create_view("credit_features", "borrower_id", "person/j.okafor",
                      ["recovered", "region"])
        f.materialise("credit_features", rows, ["recovered", "region"])
        f.create_view("credit_labels", "borrower_id", "person/j.okafor",
                      ["defaulted"])
        f.materialise("credit_labels",
                      [{"entity_id": f"B{i}", "event_ts": SALE, "ingest_ts": SALE,
                        "defaulted": i % 2} for i in range(10)], ["defaulted"])
        return f

    @staticmethod
    def _spine(n=10):
        return [{"entity_id": f"B{i}", "label_ts": SALE + 1} for i in range(n)]

    @staticmethod
    def _publish(f, name):
        f.define_featureset(name, "borrower_id", "person/j.okafor",
                            {"recovered": "integer", "region": "categorical",
                             "defaulted": "integer"},
                            label_slot="defaulted")
        f.publish_featureset(name, {
            "recovered": {"feature": "recovered", "view": "credit_features",
                          "view_version": 1},
            "region": {"feature": "region", "view": "credit_features",
                       "view_version": 1},
            "defaulted": {"feature": "defaulted", "view": "credit_labels",
                          "view_version": 1}})

    def test_the_label_under_its_own_slot_name_is_screened(self, credit):
        self._publish(credit, "leaky")
        snapshot = credit.build_from_featureset("leaky", 1, self._spine(),
                                                SALE + 10)
        report = snapshot["pit_report"]
        assert report["leakage_screened"], "the screen must have run"
        assert report["label_column"] == "defaulted"
        assert "recovered" in report["leakage"], \
            "a column that is the label under another name is the whole point"
        assert "region" not in report["leakage"], \
            "and an unrelated column must not be flagged, or this is noise"
        assert not snapshot["pit_verified"], \
            "a leaking snapshot must not be point-in-time verified"

    def test_a_frame_with_no_label_says_the_screen_did_not_run(self, credit):
        """Silence and a clean bill of health must not look the same.

        A views-only assembly has no declared label, so there is nothing to
        screen against — and reporting an empty list of suspects would claim a
        check that never happened.
        """
        snapshot = credit.build_training_set(
            "no-label", self._spine(),
            [{"view": "credit_features", "version": 1}], SALE + 10)
        report = snapshot["pit_report"]
        assert not report["leakage_screened"]
        assert report["leakage"] == []
        assert "no 'label' column" in report["detail"]

    def test_a_continuous_label_is_reported_as_unscreened(self, nj):
        """The subtler silence. The only screen for a continuous column is a
        threshold split, and that means nothing unless the label is binary — so
        a regression training set was coming back clean having been compared
        against nothing."""
        from core.features.pit import screen_leakage
        rows = [{"x": float(i), "sale_price": 600000.0 + i * 15000}
                for i in range(10)]
        suspects, why_not = screen_leakage(rows, "sale_price")
        assert suspects == []
        assert why_not and "continuous" in why_not
