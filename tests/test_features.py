"""
MAYA — feature platform tests.

The two guarantees under test are the ones adversarial review said would
otherwise fail silently: point-in-time correctness (a training set must never
contain a fact that was not yet known), and version-namespaced serving (a model
pinned to v7 must never be served v8 values — finding C-2).

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import pytest

from core.features import AssemblyRejected, FeatureError, detect_leakage, static_check
from core.features.pit import AssemblyRequest, verify_sampled


class TestFeatureDefinition:
    def test_define_returns_the_row(self, features):
        f = features.define("dscr", "customer", "float", "Coverage ratio", "person/a")
        assert f["name"] == "dscr" and f["certification"] == "experimental"

    def test_duplicate_name_is_refused(self, features):
        features.define("dscr", "customer", "float", "Coverage ratio", "person/a")
        with pytest.raises(FeatureError, match="already defined"):
            features.define("dscr", "customer", "float", "Other", "person/b")

    def test_pii_and_protected_basis_round_trip_as_booleans(self, features):
        features.define("age", "customer", "int", "Applicant age", "person/a",
                        pii=True, protected_basis=True)
        row = features.features.one(name="age")
        assert row["pii"] is True and row["protected_basis"] is True

    def test_proxy_risk_is_recorded(self, features):
        features.define("zip3", "customer", "string", "Postal prefix", "person/a",
                        proxy_risk="high")
        assert features.features.one(name="zip3")["proxy_risk"] == "high"

    def test_certification_lifecycle(self, features):
        features.define("dscr", "customer", "float", "Coverage ratio", "person/a")
        assert features.certify("dscr")["certification"] == "certified"
        assert features.certify("dscr", "deprecated")["certification"] == "deprecated"

    def test_unknown_certification_level_is_refused(self, features):
        features.define("dscr", "customer", "float", "x", "person/a")
        with pytest.raises(FeatureError, match="unknown certification"):
            features.certify("dscr", "blessed")

    def test_duplicate_detection_surfaces_near_matches(self, features):
        features.define("debt_service_coverage", "customer", "float",
                        "Debt service coverage ratio", "person/a")
        near = features.similar("dscr_ratio", "Debt service coverage ratio")
        assert [f["name"] for f in near] == ["debt_service_coverage"]

    def test_unrelated_feature_is_not_flagged_as_duplicate(self, features):
        features.define("debt_service_coverage", "customer", "float",
                        "Debt service coverage ratio", "person/a")
        assert features.similar("wildfire_hazard", "Geospatial wildfire hazard band") == []

    def test_listing_filters_by_entity(self, features):
        features.define("dscr", "customer", "float", "x", "p")
        features.define("notional", "facility", "float", "y", "p")
        assert len(features.features.many(entity="customer")) == 1
        assert len(features.features.many()) == 2


class TestViewsAndMaterialisation:
    def test_view_requires_defined_features(self, features):
        with pytest.raises(FeatureError, match="undefined features"):
            features.create_view("v", "customer", "p", ["nope"])

    def test_duplicate_view_is_refused(self, features):
        features.define("dscr", "customer", "float", "x", "p")
        features.create_view("v", "customer", "p", ["dscr"])
        with pytest.raises(FeatureError, match="already exists"):
            features.create_view("v", "customer", "p", ["dscr"])

    def test_materialise_creates_version_one(self, sb_view):
        versions = sb_view.view_versions.many(feature_view_id=sb_view.views.one(name="sb_financials")["id"])
        assert len(versions) == 1 and versions[0]["version"] == 1
        assert versions[0]["row_count"] == 4

    def test_each_materialisation_is_a_new_namespace(self, sb_view):
        sb_view.materialise("sb_financials", [
            {"entity_id": "C1", "event_ts": 300.0, "ingest_ts": 310.0, "dscr": 1.9, "revenue": 7.0}])
        assert sb_view.namespace("sb_financials", 1).endswith("/v1")
        assert sb_view.namespace("sb_financials", 2).endswith("/v2")

    def test_versions_are_separate_tables_not_a_shared_latest(self, sb_view):
        """Finding C-2: the version IS the serving namespace."""
        sb_view.materialise("sb_financials", [
            {"entity_id": "C1", "event_ts": 300.0, "ingest_ts": 310.0, "dscr": 9.9, "revenue": 1.0}])
        v1 = sb_view.delta.read(sb_view.namespace("sb_financials", 1))
        v2 = sb_view.delta.read(sb_view.namespace("sb_financials", 2))
        assert len(v1) == 4 and len(v2) == 1
        assert 9.9 not in list(v1["dscr"]), "v2 values must not appear in the v1 namespace"

    def test_rows_missing_a_clock_are_refused(self, features):
        features.define("dscr", "customer", "float", "x", "p")
        features.create_view("v", "customer", "p", ["dscr"])
        with pytest.raises(FeatureError, match="two clocks"):
            features.materialise("v", [{"entity_id": "C1", "dscr": 1.0}])

    def test_missing_ingest_time_is_refused(self, features):
        features.define("dscr", "customer", "float", "x", "p")
        features.create_view("v", "customer", "p", ["dscr"])
        with pytest.raises(FeatureError, match="ingest_ts"):
            features.materialise("v", [{"entity_id": "C1", "event_ts": 1.0, "dscr": 1.0}])

    def test_quality_report_is_computed(self, sb_view):
        v = sb_view.view_versions.many(feature_view_id=sb_view.views.one(name="sb_financials")["id"])[0]
        assert v["quality_report"]["dscr"]["null_rate"] == 0.0

    def test_namespace_for_unknown_version_is_refused(self, sb_view):
        with pytest.raises(FeatureError, match="no version 9"):
            sb_view.namespace("sb_financials", 9)


class TestBitemporalReads:
    """Two clocks. Same query, different answers depending on what was known."""

    def test_before_the_restatement_lands_the_original_figure_is_returned(self, sb_view):
        got = sb_view.delta.as_of(sb_view.namespace("sb_financials", 1), 500.0, 500.0)
        assert float(got[got.entity_id == "C1"]["dscr"].iloc[0]) == pytest.approx(1.20)

    def test_after_the_restatement_lands_the_revised_figure_is_returned(self, sb_view):
        got = sb_view.delta.as_of(sb_view.namespace("sb_financials", 1), 500.0, 999.0)
        assert float(got[got.entity_id == "C1"]["dscr"].iloc[0]) == pytest.approx(0.40)

    def test_a_fact_not_yet_true_is_excluded(self, sb_view):
        got = sb_view.delta.as_of(sb_view.namespace("sb_financials", 1), 50.0, 999.0)
        assert got.empty

    def test_delta_version_is_recorded(self, sb_view):
        assert sb_view.delta.version(sb_view.namespace("sb_financials", 1)) >= 0


class TestStaticGate:
    """Layer 1 is a proof, not a warning: a missing bound is a rejection."""

    def test_both_bounds_present_passes(self):
        assert static_check(AssemblyRequest([], [], 0.0, True, True)).passed

    @pytest.mark.parametrize("valid,txn,missing", [
        (False, True, "valid_time"), (True, False, "transaction_time"),
        (False, False, "valid_time")])
    def test_missing_bound_fails_and_names_it(self, valid, txn, missing):
        r = static_check(AssemblyRequest([], [], 0.0, valid, txn))
        assert not r.passed and missing in r.detail


class TestTrainingSetAssembly:
    SPINE = [{"entity_id": "C1", "label_ts": 500.0, "label": 0},
             {"entity_id": "C2", "label_ts": 500.0, "label": 0},
             {"entity_id": "C3", "label_ts": 500.0, "label": 1}]
    VIEWS = [{"view": "sb_financials", "version": 1}]

    def test_assembly_is_point_in_time_correct(self, sb_view):
        """The decision was taken at t=500. The August restatement did not exist
        then, so the training set must carry the ORIGINAL figure."""
        snap = sb_view.build_training_set("pd_train_v1", self.SPINE, self.VIEWS, as_of=500.0)
        rows = sb_view.delta.read(snap["delta_table"])
        c1 = rows[rows.entity_id == "C1"].iloc[0]
        assert float(c1["dscr"]) == pytest.approx(1.20), \
            "the restated figure was not knowable at label time"
        assert snap["pit_verified"] is True

    def test_a_later_assembly_sees_the_restatement(self, sb_view):
        snap = sb_view.build_training_set("pd_train_v2", self.SPINE, self.VIEWS, as_of=999.0)
        rows = sb_view.delta.read(snap["delta_table"])
        assert float(rows[rows.entity_id == "C1"].iloc[0]["dscr"]) == pytest.approx(0.40)

    def test_assembly_without_a_temporal_bound_is_rejected(self, sb_view):
        with pytest.raises(AssemblyRejected, match="transaction_time"):
            sb_view.build_training_set("bad", self.SPINE, self.VIEWS, as_of=500.0,
                                       transaction_time_bound=False)

    def test_rejection_explains_why(self, sb_view):
        with pytest.raises(AssemblyRejected, match="leakage cannot be excluded"):
            sb_view.build_training_set("bad", self.SPINE, self.VIEWS, as_of=500.0,
                                       valid_time_bound=False)

    def test_snapshot_is_recorded_with_its_report(self, sb_view):
        snap = sb_view.build_training_set("pd_train_v1", self.SPINE, self.VIEWS, as_of=500.0)
        stored = sb_view.snapshots.one(id=snap["id"])
        assert stored["row_count"] == 3 and stored["pit_report"]["layer"] == "sampled"

    def test_entities_with_no_admissible_fact_get_no_values(self, sb_view):
        spine = [{"entity_id": "UNKNOWN", "label_ts": 500.0, "label": 0}]
        snap = sb_view.build_training_set("sparse", spine, self.VIEWS, as_of=500.0)
        rows = sb_view.delta.read(snap["delta_table"])
        assert "dscr" not in rows.columns or rows["dscr"].isna().all()

    def test_assembly_emits_evidence(self, sb_view, evidence):
        snap = sb_view.build_training_set("pd_train_v1", self.SPINE, self.VIEWS, as_of=500.0)
        kinds = [n["kind"] for n in evidence.for_subject(snap["id"])]
        assert "dataset_snapshot_created" in kinds


class TestLeakageDetection:
    """Layer 3's target: a feature that predicts the label perfectly is the label."""

    def test_a_perfect_predictor_is_flagged(self):
        rows = [{"entity_id": f"C{i}", "label": i % 2, "leaky": i % 2, "ok": i}
                for i in range(20)]
        assert "leaky" in detect_leakage(rows)

    def test_an_innocent_feature_is_not_flagged(self):
        rows = [{"entity_id": f"C{i}", "label": i % 2, "noise": i % 7} for i in range(20)]
        assert "noise" not in detect_leakage(rows)

    def test_single_class_labels_yield_no_finding(self):
        rows = [{"entity_id": f"C{i}", "label": 1, "x": i} for i in range(20)]
        assert detect_leakage(rows) == []

    def test_too_few_rows_yields_no_finding(self):
        assert detect_leakage([{"entity_id": "C1", "label": 0, "x": 0}]) == []

    def test_injected_leakage_fails_the_assembly(self, sb_view, features):
        """Adversarial: the verifier must catch leakage it was not told about."""
        features.define("outcome_copy", "customer", "int", "Copy of the label", "p")
        features.create_view("leaky", "customer", "p", ["outcome_copy"])
        features.materialise("leaky", [
            {"entity_id": f"C{i}", "event_ts": 10.0, "ingest_ts": 20.0, "outcome_copy": i % 2}
            for i in range(1, 21)])
        spine = [{"entity_id": f"C{i}", "label_ts": 500.0, "label": i % 2} for i in range(1, 21)]
        snap = features.build_training_set("leaky_set", spine,
                                           [{"view": "leaky", "version": 1}], as_of=999.0)
        assert snap["pit_verified"] is False
        assert "outcome_copy" in snap["pit_report"]["leakage"]


class TestContractsAndRetirement:
    def test_binding_pins_exact_versions(self, sb_view):
        c = sb_view.bind_contract("mv-1", [{"view": "sb_financials", "version": 1}])
        assert c["items"][0]["namespace"].endswith("/v1") and c["digest"].startswith("sha256:")

    def test_binding_an_unknown_version_is_refused(self, sb_view):
        with pytest.raises(FeatureError, match="no version 7"):
            sb_view.bind_contract("mv-1", [{"view": "sb_financials", "version": 7}])

    def test_serving_namespaces_come_from_the_contract(self, sb_view):
        sb_view.bind_contract("mv-1", [{"view": "sb_financials", "version": 1}])
        ns = sb_view.serving_namespaces("mv-1")
        assert ns["sb_financials"].endswith("/v1")

    def test_serving_still_points_at_v1_after_v2_is_published(self, sb_view):
        """Finding C-2 in one assertion: publishing a new version must not move
        what a pinned model is served."""
        sb_view.bind_contract("mv-1", [{"view": "sb_financials", "version": 1}])
        sb_view.materialise("sb_financials", [
            {"entity_id": "C1", "event_ts": 300.0, "ingest_ts": 310.0, "dscr": 9.9, "revenue": 1.0}])
        assert sb_view.serving_namespaces("mv-1")["sb_financials"].endswith("/v1")

    def test_missing_contract_is_an_error_not_a_default(self, sb_view):
        with pytest.raises(FeatureError, match="no feature contract"):
            sb_view.serving_namespaces("mv-unknown")

    def test_a_pinned_version_cannot_be_retired(self, sb_view):
        sb_view.bind_contract("mv-1", [{"view": "sb_financials", "version": 1}])
        ok, consumers = sb_view.can_retire("sb_financials", 1)
        assert ok is False and consumers == ["mv-1"]

    def test_an_unpinned_version_can_be_retired(self, sb_view):
        sb_view.materialise("sb_financials", [
            {"entity_id": "C1", "event_ts": 300.0, "ingest_ts": 310.0, "dscr": 1.0, "revenue": 1.0}])
        sb_view.bind_contract("mv-1", [{"view": "sb_financials", "version": 1}])
        assert sb_view.can_retire("sb_financials", 2)[0] is True
