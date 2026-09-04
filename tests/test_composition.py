"""
MAYA — tests for dimensionality, composition, lifecycle and retrieval policy.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A feature is not always a number, is not always defined in one place, and does
not always outlive the request that made it. These are the tests for the parts
of that which can be got quietly wrong.
"""
from __future__ import annotations

import math

import pytest

from core.features import FeatureError
from core.features import shapes
from core.features.alignment import align
from core.features.composition import fold, merge, apply
from core.features.normalisation import normalise
from core.features.policy import combine, explain
from core.features.preparation import prepare, survey

TENORS = ["1m", "3m", "6m", "1y", "2y", "5y", "10y", "30y"]


@pytest.fixture
def cat(full_features):
    return full_features.catalogue


@pytest.fixture
def curve(cat):
    return cat.define("usd_curve", "book_id", "numeric", "USD zero curve",
                      "person/j.okafor", shape=[8], components=TENORS,
                      actor="person/j.okafor")


# ============================================================ dimensionality
class TestAFeatureNeedNotBeANumber:
    def test_a_vector_knows_its_own_shape(self, cat, curve):
        d = cat.resolved("usd_curve")["dimensionality"]
        assert d["kind"] == "vector" and d["cells"] == 8
        assert d["components"] == TENORS

    def test_component_order_is_the_axis_order(self, cat, curve):
        """A curve whose tenors came back alphabetically would be a different
        curve, and one nobody would notice was wrong."""
        assert cat.resolved("usd_curve")["components"] == TENORS
        assert cat.resolved("usd_curve")["components"] != sorted(TENORS)

    def test_a_matrix_and_a_tensor_are_described_as_such(self, cat):
        cat.define("corr", "book_id", "numeric", "correlations", "person/o",
                   shape="8,8")
        cat.define("grid", "book_id", "numeric", "scenarios", "person/o",
                   shape=[5, 8, 8])
        assert cat.resolved("corr")["dimensionality"]["kind"] == "matrix"
        assert cat.resolved("grid")["dimensionality"]["kind"] == "tensor"
        assert cat.resolved("grid")["dimensionality"]["cells"] == 320

    def test_naming_some_entries_and_not_others_is_refused(self, cat):
        with pytest.raises(FeatureError, match="identified only by"):
            cat.define("partial", "book_id", "numeric", "x", "person/o",
                       shape=[8], components=["1m", "3m"])

    def test_a_scalar_has_no_axis_to_name(self, cat):
        with pytest.raises(FeatureError, match="no axis to name"):
            cat.define("scalar", "book_id", "numeric", "x", "person/o",
                       components=["a"])

    def test_duplicate_component_names_are_refused(self, cat):
        with pytest.raises(FeatureError, match="appear twice"):
            cat.define("dup", "book_id", "numeric", "x", "person/o",
                       shape=[2], components=["a", "a"])

    def test_a_declared_shape_is_checked_against_the_values(self):
        rows = [{"curve": [1.0] * 8}, {"curve": [1.0] * 7}]
        with pytest.raises(FeatureError, match="expected 8, got 7"):
            shapes.check_rows(rows, "curve", (8,))

    def test_a_ragged_value_is_not_a_tensor(self):
        ok, why = shapes.conforms([[1, 2], [3]], (2, 2))
        assert not ok


# ================================================================ composition
class TestCompositionIsAMonoid:
    """Which is why 'a combination of features is a feature' is a statement
    rather than an aspiration."""

    def test_the_fold_is_associative(self):
        a, b, c = {"x": 1}, {"x": 2, "y": 2}, {"y": 3}
        assert merge(merge(a, b), c) == merge(a, merge(b, c))

    def test_the_empty_composition_is_the_identity(self):
        a = {"x": 1, "y": 2}
        assert merge({}, a) == a == merge(a, {})
        assert fold([a]) == a

    def test_the_rightmost_wins(self):
        assert fold([{"x": 1}, {"x": 2}, {"x": 3}])["x"] == 3


class TestInheritingAFeature:
    @pytest.fixture
    def extended(self, cat, curve):
        return cat.define(
            "usd_curve_extended", "book_id", "numeric", "with a 50y point",
            "person/d.raman", shape=[8], composes=[{"name": "usd_curve"}],
            operations=[{"op": "add", "name": "50y", "value": {"dtype": "numeric"}},
                        {"op": "drop", "name": "1m"},
                        {"op": "override", "name": "3m",
                         "value": {"dtype": "numeric", "source": "OIS"}}])

    def test_add_drop_and_override_all_take_effect(self, cat, extended):
        components = cat.resolved("usd_curve_extended")["components"]
        assert "50y" in components and "1m" not in components
        assert len(components) == 8

    def test_the_shape_follows_the_components(self, cat, extended):
        """Composing a tenor onto a curve makes it longer; a shape that
        disagreed would be the stale half."""
        assert cat.resolved("usd_curve_extended")["shape"] == [8]

    def test_the_provenance_says_who_decided_each_component(self, cat, extended):
        provenance = cat.resolved("usd_curve_extended")["provenance"]
        assert provenance["3m"]["overrode"] == "usd_curve"
        assert "override" in provenance["3m"]["from"]

    def test_resolution_is_idempotent(self, cat, extended):
        """Storing the resolved set would apply the operations a second time."""
        first = cat.resolved("usd_curve_extended")["components"]
        assert cat.resolved("usd_curve_extended")["components"] == first

    def test_dropping_something_absent_is_refused(self, cat, curve):
        with pytest.raises(FeatureError, match="cannot drop"):
            cat.define("bad", "book_id", "numeric", "x", "person/o",
                       composes=[{"name": "usd_curve"}],
                       operations=[{"op": "drop", "name": "99y"}])

    def test_adding_something_present_is_refused(self, cat, curve):
        """Say override if replacing is meant; the two read differently."""
        with pytest.raises(FeatureError, match="say 'override'"):
            cat.define("bad", "book_id", "numeric", "x", "person/o",
                       composes=[{"name": "usd_curve"}],
                       operations=[{"op": "add", "name": "1m",
                                    "value": {"dtype": "numeric"}}])

    def test_overriding_something_absent_is_refused(self, cat, curve):
        with pytest.raises(FeatureError, match="say 'add'"):
            cat.define("bad", "book_id", "numeric", "x", "person/o",
                       composes=[{"name": "usd_curve"}],
                       operations=[{"op": "override", "name": "99y",
                                    "value": {"dtype": "numeric"}}])

    def test_a_cycle_has_no_fixed_point(self, cat, curve):
        cat.define("a", "book_id", "numeric", "x", "person/o",
                   composes=[{"name": "usd_curve"}])
        with pytest.raises(FeatureError, match="composes itself"):
            cat.amend("usd_curve", {"composes": [{"name": "a"}]})
            cat.resolved("usd_curve")


class TestCombiningFeatures:
    def test_later_parents_beat_earlier_ones(self, cat, curve):
        cat.define("gbp_curve", "book_id", "numeric", "GBP", "person/o",
                   shape=[3], components=["1y", "5y", "10y"])
        cat.define("blended", "book_id", "numeric", "USD then GBP",
                   "person/o", composes=[{"name": "usd_curve"},
                                         {"name": "gbp_curve"}])
        provenance = cat.resolved("blended")["provenance"]
        assert provenance["10y"]["from"] == "gbp_curve"
        assert provenance["10y"]["overrode"] == "usd_curve"

    def test_a_combination_of_featuresets_is_a_featureset(self, full_features,
                                                          cat, curve):
        f = full_features
        f.define_featureset("rates_core", "book_id", "person/o",
                            {"usd_curve": "numeric"})
        f.define_featureset("rates_plus", "book_id", "person/o", {},
                            composes=[{"name": "rates_core"}],
                            operations=[{"op": "add", "name": "extra",
                                         "value": {"dtype": "numeric"}}])
        resolved = f.sets.resolved("rates_plus")
        assert set(resolved["slots"]) == {"usd_curve", "extra"}
        # 'extra' came from this set's own operation, so it is its own; only
        # 'usd_curve' was inherited. Crediting the parent with both would credit
        # it with a decision it did not make.
        assert resolved["declared_slots"] == ["extra"]
        assert resolved["inherited_slots"] == ["usd_curve"]


# =================================================================== sealing
class TestSealing:
    def test_a_sealed_feature_refuses_amendment(self, cat, curve):
        cat.seal("usd_curve", "person/s.iqbal", "signed off")
        with pytest.raises(FeatureError, match="cannot be amended"):
            cat.amend("usd_curve", {"description": "changed"})

    def test_a_sealed_feature_can_still_be_composed_from(self, cat, curve):
        """Which is the point: a parent that cannot move is worth building on."""
        cat.seal("usd_curve", "person/s.iqbal")
        child = cat.define("child", "book_id", "numeric", "x", "person/o",
                           composes=[{"name": "usd_curve"}])
        assert len(cat.resolved("child")["components"]) == 8

    def test_sealing_twice_is_refused(self, cat, curve):
        cat.seal("usd_curve", "person/s.iqbal")
        with pytest.raises(FeatureError, match="already sealed"):
            cat.seal("usd_curve", "person/other")

    def test_breaking_a_seal_requires_a_reason(self, cat, curve):
        cat.seal("usd_curve", "person/s.iqbal")
        with pytest.raises(FeatureError, match="requires a reason"):
            cat.break_seal("usd_curve", "admin", "  ")

    def test_a_broken_seal_leaves_its_own_trace(self, cat, curve, repos):
        cat.seal("usd_curve", "person/s.iqbal")
        cat.break_seal("usd_curve", "admin", "sealed the wrong one")
        kinds = [e["kind"] for e in repos["evidence"].many()]
        assert "feature_sealed" in kinds and "feature_seal_broken" in kinds
        assert cat.resolved("usd_curve")["sealed"] is False

    def test_a_sealed_featureset_refuses_another_version(self, full_features, cat,
                                                         curve):
        f = full_features
        f.define_featureset("s", "book_id", "person/o", {"usd_curve": "numeric"})
        f.sets.seal("s", "person/s.iqbal")
        with pytest.raises(FeatureError, match="cannot take another version"):
            f.publish_featureset("s", {"usd_curve": "usd_curve"})


# ================================================================= ephemeral
class TestEphemeral:
    def test_it_reports_what_is_left(self, cat):
        cat.define("scratch", "book_id", "numeric", "one-off", "person/o",
                   ephemeral=True, ttl_days=0.5)
        left = cat.resolved("scratch")["lifetime"]
        assert left["ephemeral"] and 11 < left["seconds_left"] / 3600 <= 12

    def test_composing_from_one_is_refused(self, cat):
        """A child that resolves today and dangles tomorrow."""
        cat.define("scratch", "book_id", "numeric", "x", "person/o",
                   ephemeral=True)
        with pytest.raises(FeatureError, match="which is ephemeral"):
            cat.define("built_on_sand", "book_id", "numeric", "x", "person/o",
                       composes=[{"name": "scratch"}])

    def test_sealing_one_is_refused(self, cat):
        cat.define("scratch", "book_id", "numeric", "x", "person/o",
                   ephemeral=True)
        with pytest.raises(FeatureError, match="one of them is wrong"):
            cat.seal("scratch", "person/s.iqbal")

    def test_a_lifetime_longer_than_the_limit_is_refused(self, cat):
        with pytest.raises(FeatureError, match="is not ephemeral"):
            cat.define("long", "book_id", "numeric", "x", "person/o",
                       ephemeral=True, ttl_days=90)

    def test_destroying_a_durable_feature_is_refused(self, cat, curve):
        with pytest.raises(FeatureError, match="not ephemeral"):
            cat.destroy("usd_curve")

    def test_destruction_keeps_the_record(self, cat, repos):
        cat.define("scratch", "book_id", "numeric", "x", "person/o",
                   ephemeral=True)
        cat.destroy("scratch", "the client finished with it")
        assert cat.get("scratch") is None
        node = [e for e in repos["evidence"].many()
                if e["kind"] == "feature_destroyed"]
        assert node and node[0]["payload"]["name"] == "scratch"

    def test_the_expired_are_findable(self, cat):
        import time
        cat.define("scratch", "book_id", "numeric", "x", "person/o",
                   ephemeral=True, ttl_days=1)
        assert cat.expired() == []
        assert [r["name"] for r in cat.expired(now=time.time() + 2 * 86400)] \
            == ["scratch"]


# ================================================================= ownership
class TestOwnership:
    def test_the_creator_is_history_and_the_owner_is_a_responsibility(self, cat,
                                                                      curve):
        cat.transfer("usd_curve", "person/a.mehta", "person/j.okafor", "team move")
        own = cat.resolved("usd_curve")["ownership"]
        assert own["created_by"] == "person/j.okafor"
        assert own["owner"] == "person/a.mehta" and own["transferred"]

    def test_transferring_to_nobody_is_refused(self, cat, curve):
        with pytest.raises(FeatureError, match="nobody answers for"):
            cat.transfer("usd_curve", "  ", "person/j.okafor")

    def test_a_sealed_feature_does_not_change_hands(self, cat, curve):
        cat.seal("usd_curve", "person/s.iqbal")
        with pytest.raises(FeatureError, match="cannot change owner"):
            cat.transfer("usd_curve", "person/a.mehta", "person/j.okafor")

    def test_the_transfer_is_witnessed(self, cat, curve, repos):
        cat.transfer("usd_curve", "person/a.mehta", "person/j.okafor", "why")
        assert "feature_ownership_transferred" in [e["kind"]
                                                   for e in repos["evidence"].many()]


# ==================================================================== policy
class TestRetrievalPolicy:
    def test_precedence_is_the_composition_rule_again(self):
        parent = {"fill": {"a": "zero", "b": "median"}}
        own = {"fill": {"b": "mean"}}
        request = {"normalise": {"c": "minmax"}}
        out = combine([parent, own, request])
        assert out["fill"] == {"a": "zero", "b": "mean"}
        assert out["normalise"] == {"c": "minmax"}

    def test_sections_merge_column_by_column_not_wholesale(self):
        """A parent filling three columns and a child normalising one should end
        up doing both; replacing the section would silently drop the parent's."""
        out = combine([{"fill": {"a": "zero", "b": "zero", "c": "zero"}},
                       {"normalise": {"a": "zscore"}}])
        assert len(out["fill"]) == 3 and out["normalise"] == {"a": "zscore"}

    def test_it_says_which_layer_decided_each_column(self):
        who = explain({"name": "child", "defaults": {"fill": {"b": "mean"}}},
                      [{"name": "base", "defaults": {"fill": {"a": "zero"}}}],
                      {"fill": {"c": "zero"}})["decided_by"]
        assert who["fill"] == {"a": "base", "b": "child", "c": "the request"}

    def test_a_policy_naming_something_else_is_refused(self, cat):
        with pytest.raises(FeatureError, match="and nothing else"):
            cat.define("x", "book_id", "numeric", "x", "person/o",
                       defaults={"vibes": {}})

    def test_a_policy_is_validated_when_written_not_when_used(self, cat):
        with pytest.raises(FeatureError, match="is not a strategy"):
            cat.define("x", "book_id", "numeric", "x", "person/o",
                       defaults={"fill": {"a": "guess"}})

    def test_a_featureset_carries_its_policy_to_its_children(self, full_features,
                                                             cat, curve):
        f = full_features
        f.define_featureset("core", "book_id", "person/o", {"usd_curve": "numeric"},
                            defaults={"normalise": {"usd_curve": "zscore"}})
        f.define_featureset("plus", "book_id", "person/o", {},
                            composes=[{"name": "core"}])
        resolved = f.sets.resolved("plus")
        assert resolved["policy"]["policy"]["normalise"] == {"usd_curve": "zscore"}
        assert resolved["policy"]["decided_by"]["normalise"]["usd_curve"] == "core"


# ================================================== point-in-time normalisation
TS = 1735689600.0
DAY = 86400.0


def _series(n=120, missing=()):
    return [{"entity_id": f"B{i % 4}", "event_ts": TS + i * DAY,
             "ingest_ts": TS + i * DAY,
             "x": (None if i in missing else float(i))} for i in range(n)]


class TestNormalisationIsFittedAtAMoment:
    def test_it_fits_only_on_what_was_knowable(self, ):
        """A statistic fitted over the whole column encodes what the mean turned
        out to be, including the part that had not happened yet."""
        rows = _series()
        _, stats = normalise(rows, {"x": "zscore"}, as_of=TS + 59 * DAY)
        assert stats["x"]["fitted_on"] == 60
        assert stats["x"]["parameters"]["mean"] == pytest.approx(29.5)

    def test_without_an_as_of_it_is_refused(self):
        with pytest.raises(FeatureError, match="which is leakage"):
            normalise(_series(), {"x": "zscore"}, as_of=None)

    def test_the_fitted_statistics_come_back_with_the_data(self):
        """Whoever scores one row tomorrow has to apply the same transform."""
        _, stats = normalise(_series(), {"x": "minmax"}, as_of=TS + 119 * DAY)
        assert set(stats["x"]["parameters"]) == {"min", "max"}
        assert stats["x"]["as_of"] == TS + 119 * DAY

    def test_too_few_observations_is_a_guess_with_a_decimal_point(self):
        with pytest.raises(FeatureError, match="guess with a decimal point"):
            normalise(_series(10), {"x": "zscore"}, as_of=TS + 9 * DAY)

    def test_a_vector_normalises_elementwise(self):
        rows = [{"event_ts": TS + i, "ingest_ts": TS + i,
                 "curve": [float(i), float(i) * 2]} for i in range(60)]
        out, stats = normalise(rows, {"curve": "minmax"}, as_of=TS + 100)
        assert len(out[0]["curve"]) == 2
        assert stats["curve"]["fitted_on"] == 120

    def test_a_constant_column_says_so_rather_than_dividing_by_zero(self):
        rows = [{"event_ts": TS + i, "ingest_ts": TS + i, "x": 5.0}
                for i in range(60)]
        out, stats = normalise(rows, {"x": "zscore"}, as_of=TS + 100)
        assert out[0]["x"] == 0.0
        assert "constant over the fitting window" in stats["x"]["note"]


class TestFillingGaps:
    def test_null_nan_and_infinity_are_all_missing(self):
        rows = [{"x": None}, {"x": float("nan")}, {"x": float("inf")}, {"x": 1.0}]
        assert survey(rows, ["x"])["x"]["missing"] == 3

    def test_a_loud_fill_rate_is_reported_as_loud(self):
        """Filling forty per cent of a column with zeros produces a model that
        trains without complaint and means nothing."""
        rows = _series(100, missing=range(40))
        out = prepare(rows, fill={"x": "zero"})
        assert out["filled"]["x"]["loud"]
        assert "mostly invention" in out["filled"]["x"]["detail"]

    def test_a_fitted_fill_needs_a_moment_to_fit_at(self):
        with pytest.raises(FeatureError, match="puts the future into the past"):
            prepare(_series(), fill={"x": "median"})

    def test_a_constant_fill_needs_its_constant(self):
        with pytest.raises(FeatureError, match="needs the constant"):
            prepare(_series(), fill={"x": {"strategy": "constant"}})

    def test_statistics_are_fitted_before_anything_is_filled(self):
        """Fitting afterwards would shrink the spread by exactly the amount that
        was invented, because every filled cell sits at the centre."""
        rows = _series(100, missing=range(50))
        out = prepare(rows, fill={"x": "zero"},
                      normalise_spec={"x": "zscore"}, as_of=TS + 99 * DAY)
        assert out["normalised"]["x"]["fitted_on"] == 50
        assert "fitted on observed" in out["order"]

    def test_a_nan_is_not_folded_into_the_mean(self):
        rows = [{"event_ts": TS + i, "ingest_ts": TS + i,
                 "x": float("nan") if i % 3 == 0 else float(i)}
                for i in range(90)]
        out = prepare(rows, normalise_spec={"x": "zscore"}, as_of=TS + 89 * DAY)
        assert not math.isnan(out["normalised"]["x"]["parameters"]["mean"])


# =================================================================== alignment
class TestAligningOntoAnAxis:
    ROWS = [{"entity_id": "B1", "event_ts": 0.0, "ingest_ts": 0.0, "bal": 100.0},
            {"entity_id": "B1", "event_ts": 3.0, "ingest_ts": 3.0, "bal": 400.0}]
    GRID = [0.0, 1.0, 2.0, 3.0]

    def test_flat_forward_uses_only_what_had_happened(self):
        out = align(self.ROWS, ["bal"], rule="flat_forward", grid=self.GRID)
        assert out["point_in_time_safe"]
        assert [r["bal"] for r in out["rows"]] == [100.0, 100.0, 100.0, 400.0]

    def test_a_back_filled_value_carries_the_clock_it_became_knowable_at(self):
        """The leakage is not caught by a check; it is made impossible to hide."""
        out = align(self.ROWS, ["bal"], rule="flat_backward", grid=self.GRID)
        assert not out["point_in_time_safe"]
        at_one = next(r for r in out["rows"] if r["event_ts"] == 1.0)
        assert at_one["bal"] == 400.0
        assert at_one["ingest_ts"] == 3.0, "the fill came from an observation at 3"

    def test_a_point_in_time_read_therefore_excludes_it_by_the_ordinary_rule(self):
        out = align(self.ROWS, ["bal"], rule="linear", grid=self.GRID)
        knowable_at_one = [r for r in out["rows"]
                           if r["event_ts"] <= 1.0 and r["ingest_ts"] <= 1.0]
        assert [r["event_ts"] for r in knowable_at_one] == [0.0]

    def test_linear_interpolates_between_the_neighbours(self):
        out = align(self.ROWS, ["bal"], rule="linear", grid=self.GRID)
        assert [r["bal"] for r in out["rows"]] == [100.0, 200.0, 300.0, 400.0]

    def test_it_will_not_extrapolate_under_the_name_of_interpolating(self):
        out = align(self.ROWS, ["bal"], rule="linear", grid=[-1.0, 1.0, 5.0])
        assert [r["bal"] for r in out["rows"]] == [None, 200.0, None]

    def test_a_carry_limit_stops_a_stale_value_becoming_a_fabricated_one(self):
        out = align(self.ROWS, ["bal"], rule="flat_forward", grid=self.GRID,
                    limit=1.0)
        assert out["carried_beyond_limit"] == 1
        assert [r["bal"] for r in out["rows"]] == [100.0, 100.0, None, 400.0]

    def test_a_regular_grid_is_built_from_a_step(self):
        from core.features.alignment import grid_for
        assert grid_for(self.ROWS, "event_ts", "regular", step=1.5) == [0.0, 1.5, 3.0]

    def test_a_grid_finer_than_the_data_is_refused(self):
        from core.features.alignment import grid_for
        with pytest.raises(FeatureError, match="adds rows"):
            grid_for(self.ROWS, "event_ts", "regular", step=0.00001)

    def test_vectors_interpolate_elementwise_and_refuse_a_length_change(self):
        rows = [{"entity_id": "B1", "event_ts": 0.0, "ingest_ts": 0.0,
                 "curve": [0.0, 0.0]},
                {"entity_id": "B1", "event_ts": 2.0, "ingest_ts": 2.0,
                 "curve": [10.0, 20.0]}]
        out = align(rows, ["curve"], rule="linear", grid=[0.0, 1.0, 2.0])
        assert out["rows"][1]["curve"] == [5.0, 10.0]

        ragged = [rows[0], {**rows[1], "curve": [1.0, 2.0, 3.0]}]
        with pytest.raises(FeatureError, match="invent a correspondence"):
            align(ragged, ["curve"], rule="linear", grid=[1.0])


class TestAParentThatMovesIsReported:
    """A composition records which DEFINITION of a parent it resolved against.
    Without that, amending a parent silently changes every child — a stable
    identifier over moving contents, which is finding C-2 in a third costume."""

    def test_the_parent_version_is_stamped_at_compose_time(self, cat, curve):
        child = cat.define("child", "book_id", "numeric", "x", "person/o",
                           composes=[{"name": "usd_curve"}])
        assert child["composes"][0]["definition_version"] == 1

    def test_nothing_has_drifted_when_nothing_has_moved(self, cat, curve):
        cat.define("child", "book_id", "numeric", "x", "person/o",
                   composes=[{"name": "usd_curve"}])
        assert cat.resolved("child")["drift"] == []

    def test_amending_a_parent_is_reported_as_drift(self, cat, curve):
        cat.define("child", "book_id", "numeric", "x", "person/o",
                   composes=[{"name": "usd_curve"}])
        cat.amend("usd_curve", {"description": "revised"})
        drift = cat.resolved("child")["drift"]
        assert drift and drift[0]["parent"] == "usd_curve"
        assert drift[0]["composed_against"] == 1 and drift[0]["now_at"] == 2

    def test_a_sealed_parent_cannot_drift_because_it_cannot_move(self, cat,
                                                                 curve):
        """Which is what sealing is for, stated as a property rather than a
        promise: an amendment is refused, so the version cannot advance."""
        cat.seal("usd_curve", "person/s.iqbal")
        cat.define("child", "book_id", "numeric", "x", "person/o",
                   composes=[{"name": "usd_curve"}])
        with pytest.raises(FeatureError):
            cat.amend("usd_curve", {"description": "revised"})
        assert cat.resolved("child")["drift"] == []

    def test_composing_from_something_that_does_not_exist_is_refused_now(
            self, cat):
        with pytest.raises(FeatureError, match="no such feature"):
            cat.define("orphan", "book_id", "numeric", "x", "person/o",
                       composes=[{"name": "never_defined"}])
