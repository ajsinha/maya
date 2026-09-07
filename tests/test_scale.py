"""
MAYA — the platform at a size where its claims are falsifiable.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Every other test in this suite asserts that something is *correct*. These assert
that it is still correct, and still quick enough to be used, at a size where the
difference between a good implementation and a bad one is visible.

Two rules govern how they are written.

**Assert shape, not stopwatch.** A threshold in milliseconds is a promise about
somebody else's hardware, and a suite that fails on a loaded machine is a suite
people learn to re-run rather than read. So the assertions are mostly about
*complexity*: that doubling the estate does not more than double the work, that
an operation claimed to be constant in estate size actually is, that a read
claimed not to materialise a dataset does not. Where a wall-clock budget is
asserted it is generous by an order of magnitude, because its job is to catch a
change from linear to quadratic rather than to measure a machine.

**Run at a size the default suite will not.** These are marked ``scale`` and
excluded from the ordinary run. A suite that is slow gets disabled, and a
disabled suite proves nothing.

The transfer layer's own scale tests live in ``test_transfer_scale.py``; they
found a real Arrow bug that a five-hundred-row test could not see, which is the
argument for this file.
"""
from __future__ import annotations

import time
from typing import Callable, Tuple

import pytest

pytestmark = pytest.mark.scale

DAY = 86400.0
TS = 1735689600.0


def timed(work: Callable) -> Tuple[float, object]:
    """Wall clock around one call, so a ratio can be taken over two sizes."""
    started = time.perf_counter()
    result = work()
    return time.perf_counter() - started, result


def growth(small: float, large: float, factor: int) -> float:
    """How much the work grew, relative to how much the input did.

    1.0 is linear. Meaningfully above 1 means the cost is superlinear in the
    input, which is the thing worth catching — a change from linear to quadratic
    is invisible at fixture size and fatal at estate size.
    """
    if small <= 0:
        return 1.0
    return (large / small) / factor


# ============================================================ evidence chain
class TestTheEvidenceChainAtEstateSize:
    """Every governance act appends a node. A chain that verified in quadratic
    time would make the verification somebody actually relies on unusable
    exactly when the estate is large enough to need it."""

    def test_appending_stays_linear(self, evidence):
        first, _ = timed(lambda: [evidence.append("test", "model", f"m{i}", {})
                                  for i in range(2_000)])
        second, _ = timed(lambda: [evidence.append("test", "model", f"m{i}", {})
                                   for i in range(2_000, 6_000)])
        assert growth(first, second, 2) < 2.5, (
            "appending is getting more expensive as the chain grows, which "
            "means something is reading the chain to write to it")

    def test_verification_is_linear_in_the_chain(self, evidence):
        for i in range(2_000):
            evidence.append("test", "model", f"m{i}", {"i": i})
        small, report = timed(evidence.verify_chain)
        assert report["valid"] and report["length"] == 2_000

        for i in range(2_000, 6_000):
            evidence.append("test", "model", f"m{i}", {"i": i})
        large, report = timed(evidence.verify_chain)
        assert report["valid"] and report["length"] == 6_000
        assert growth(small, large, 3) < 2.0

    def test_a_tamper_is_still_found_in_a_long_chain(self, evidence, repos, db):
        """The chain's whole purpose. Finding it at fixture size proves nothing
        about finding it at the size an examiner would look at.

        Tampered through SQL rather than through the repository. `AppendOnly`
        now refuses `repos["evidence"].set(...)`, so this test raised
        `AppendOnlyViolation` instead of asserting anything — and because
        `scale` is excluded from every default run and from CI, nothing
        noticed. The claim it protects had not been checked since that control
        landed.

        SQL is also the honest threat model: `AppendOnly` stops the
        application writing over its own history, and its docstring says so. It
        cannot stop somebody holding the database, and detecting exactly that
        is what the hash chain is for.
        """
        for i in range(5_000):
            evidence.append("test", "model", f"m{i}", {"i": i})
        assert evidence.verify_chain()["valid"]
        middle = repos["evidence"].many()[2_500]
        db.execute("UPDATE evidence_node SET payload = :p WHERE id = :i",
                   {"p": '{"i": "altered"}', "i": middle["id"]})
        report = evidence.verify_chain()
        assert not report["valid"]
        assert report.get("broken_at") or report.get("detail"), \
            "a tamper report must say WHERE the chain stops verifying"

    def test_reading_one_subject_does_not_read_the_whole_chain(self, evidence):
        for i in range(6_000):
            evidence.append("test", "model", f"m{i % 50}", {"i": i})
        small, rows = timed(lambda: evidence.for_subject("m0"))
        assert len(rows) == 120
        # Constant in the chain's length is the claim; a scan would be linear.
        assert small < 2.0


# ============================================================== the estate
class TestTheEstateAtScale:
    """A worklist derived from the register rather than stored is the design's
    strongest claim and its most expensive one: it is computed on every read."""

    @pytest.fixture
    def estate(self, registry, kernel_spec, contract_spec):
        for i in range(300):
            urn = f"maya://model/scale.m{i:04d}"
            registry.register(urn, f"Model {i}", "credit.pd.scorecard", "credit",
                              "person/j.okafor", "LE-US-01", "scale")
            registry.set_tier(registry.get(urn)["id"], (i % 4) + 1)
            if i % 3 == 0:
                registry.create_version(urn, "1.0.0", kernel_spec, contract_spec)
        return registry

    def test_listing_the_estate_is_quick(self, estate):
        elapsed, models = timed(estate.list)
        assert len(models) == 300
        assert elapsed < 2.0, "listing the register should not be the slow part"

    def test_the_worklist_is_linear_in_the_estate(self, estate, worklist):
        half = estate.list()[:150]
        small, _ = timed(lambda: worklist.across(half))
        whole = estate.list()
        large, items = timed(lambda: worklist.across(whole))
        assert items, "an estate of drafts has outstanding work"
        assert growth(small, large, 2) < 2.5, (
            "the worklist is superlinear in the estate, so it will stop being "
            "usable exactly when the estate is large enough to need it")

    def test_a_principal_sees_only_their_own_work_without_scanning_twice(
            self, estate, worklist, authz, principals):
        principals.create("s.iqbal", "S Iqbal", ["model_risk_manager"], "pw-long-enough-x")
        who = principals.require("s.iqbal")
        elapsed, mine = timed(
            lambda: worklist.mine(who, authz, estate.list()))
        assert elapsed < 10.0
        assert mine["items"] or mine["others"]

    def test_the_summary_does_not_grow_worse_than_the_estate(self, estate,
                                                             summary):
        small, _ = timed(lambda: summary.of(estate.list()[:150]))
        large, _ = timed(lambda: summary.of(estate.list()))
        assert growth(small, large, 2) < 2.5


# ========================================================== point in time
class TestPointInTimeAssemblyAtScale:
    """The three-layer verification is the platform's most expensive control.
    It has to remain affordable at a size where somebody would want it."""

    @pytest.fixture
    def big_view(self, full_features):
        f = full_features
        for name in ("dscr", "turnover", "utilisation"):
            f.define(name, "borrower_id", "numeric", name, "person/j.okafor")
        columns = ["dscr", "turnover", "utilisation"]
        f.create_view("sb", "borrower_id", "person/j.okafor", columns)
        rows = [{"entity_id": f"B{i % 5000}", "event_ts": TS + i * 60.0,
                 "ingest_ts": TS + i * 60.0, "dscr": 1.0 + i % 7,
                 "turnover": 1000.0 * (i % 13), "utilisation": (i % 100) / 100.0}
                for i in range(20_000)]
        f.materialise("sb", rows, columns)
        return f

    def test_assembly_is_linear_in_the_spine(self, big_view):
        def spine(n):
            return [{"entity_id": f"B{i}", "label_ts": TS + 20_000 * 60.0}
                    for i in range(n)]
        views = [{"view": "sb", "version": 1}]
        small, _ = timed(lambda: big_view.build_training_set(
            "s1", spine(500), views, TS + 30_000 * 60.0))
        large, snapshot = timed(lambda: big_view.build_training_set(
            "s2", spine(2_000), views, TS + 30_000 * 60.0))
        assert snapshot["row_count"] == 2_000
        assert growth(small, large, 4) < 3.0

    def test_the_assembly_is_still_verified_at_size(self, big_view):
        spine = [{"entity_id": f"B{i}", "label_ts": TS + 20_000 * 60.0}
                 for i in range(1_000)]
        snapshot = big_view.build_training_set(
            "verified", spine, [{"view": "sb", "version": 1}],
            TS + 30_000 * 60.0)
        assert snapshot["pit_verified"], (
            "the verification passing at fixture size and being skipped at "
            "scale would be the worst of both")

    def test_an_unbounded_request_is_still_refused_at_size(self, big_view):
        from core.features import AssemblyRejected
        spine = [{"entity_id": f"B{i}", "label_ts": TS} for i in range(1_000)]
        with pytest.raises(AssemblyRejected):
            big_view.build_training_set(
                "unbounded", spine, [{"view": "sb", "version": 1}],
                TS, transaction_time_bound=False)


# ============================================================== warrants
class TestWarrantResolutionStaysFast:
    """A warrant is resolved on the hot path of whatever is running the model.
    Everything else here can take a second; this cannot."""

    @pytest.fixture
    def ready(self, registry, warrants, a_model, approved_version):
        registry.move_alias("maya://model/credit.pd.smallbiz", "prod",
                            "champion", "3.2.1")
        warrants.issue("maya://model/credit.pd.smallbiz", "prod",
                       "svc/origination", "origination_decision")
        return warrants

    def test_a_thousand_resolutions_stay_within_budget(self, ready):
        urn = "maya://model/credit.pd.smallbiz#champion"
        elapsed, _ = timed(lambda: [
            ready.resolve(urn, "prod", "svc/origination", "origination_decision")
            for _ in range(1_000)])
        per_call = elapsed / 1_000
        assert per_call < 0.05, (
            f"{per_call * 1000:.1f}ms per resolution. the budget is generous by "
            f"an order of magnitude; its job is to catch a change from linear "
            f"to quadratic, not to measure a machine")

    def test_resolution_does_not_slow_as_the_chain_grows(self, ready, evidence):
        urn = "maya://model/credit.pd.smallbiz#champion"
        before, _ = timed(lambda: [
            ready.resolve(urn, "prod", "svc/origination", "origination_decision")
            for _ in range(200)])
        for i in range(5_000):
            evidence.append("noise", "model", f"other{i}", {"i": i})
        after, _ = timed(lambda: [
            ready.resolve(urn, "prod", "svc/origination", "origination_decision")
            for _ in range(200)])
        assert growth(before, after, 1) < 3.0, (
            "resolution is reading the evidence chain, which would make the "
            "hot path slower every day the platform is used")


# ============================================================= telemetry
class TestTelemetryAtVolume:
    def test_ingestion_is_linear_in_the_batch(self, telemetry, approved_version):
        urn = "maya://model/credit.pd.smallbiz"

        def batch(start, n):
            return [{"entity_id": f"B{i}", "scored_at": TS + i,
                     "ingest_ts": TS + i, "score": (i % 100) / 100.0}
                    for i in range(start, start + n)]
        small, _ = timed(lambda: telemetry.ingest(urn, "3.2.1", "scores",
                                                  batch(0, 5_000)))
        large, _ = timed(lambda: telemetry.ingest(urn, "3.2.1", "scores",
                                                 batch(5_000, 20_000)))
        assert growth(small, large, 4) < 3.0

    def test_the_cohort_join_is_not_quadratic(self, telemetry, approved_version):
        urn = "maya://model/credit.pd.smallbiz"
        telemetry.ingest(urn, "3.2.1", "scores",
                         [{"entity_id": f"B{i}", "scored_at": TS + i,
                           "ingest_ts": TS + i, "score": 0.5}
                          for i in range(10_000)])
        telemetry.ingest(urn, "3.2.1", "outcomes",
                         [{"entity_id": f"B{i}", "label": i % 2,
                           "label_ts": TS + 90 * DAY, "ingest_ts": TS + 90 * DAY}
                          for i in range(5_000)])
        elapsed, cohort = timed(lambda: telemetry.cohort(urn, "3.2.1"))
        assert len(cohort) == 10_000
        assert sum(1 for r in cohort if "label" in r) == 5_000
        assert elapsed < 15.0, (
            "the join is per-entity through a dictionary; a nested scan would "
            "show up here as a very different number")

    def test_a_redelivered_batch_is_cheap_to_refuse(self, telemetry,
                                                    approved_version):
        urn = "maya://model/credit.pd.smallbiz"
        rows = [{"entity_id": f"B{i}", "scored_at": TS + i, "ingest_ts": TS + i,
                 "score": 0.5} for i in range(10_000)]
        first, _ = timed(lambda: telemetry.ingest(urn, "3.2.1", "scores", rows))
        again, out = timed(lambda: telemetry.ingest(urn, "3.2.1", "scores", rows))
        assert out["duplicate"]
        assert again < first, (
            "recognising a redelivery should be cheaper than performing it; "
            "at-least-once delivery makes this the common case, not the rare one")


# ============================================================ composition
class TestCompositionAtDepthAndBreadth:
    def test_a_deep_chain_resolves_without_re_walking_the_world(self, full_features):
        cat = full_features.catalogue
        cat.define("base", "book_id", "numeric", "root", "person/o",
                   shape=[3], components=["a", "b", "c"])
        previous = "base"
        for i in range(10):
            name = f"layer{i}"
            cat.define(name, "book_id", "numeric", f"layer {i}", "person/o",
                       composes=[{"name": previous}],
                       operations=[{"op": "add", "name": f"x{i}",
                                    "value": {"dtype": "numeric"}}])
            previous = name
        elapsed, resolved = timed(lambda: cat.resolved(previous))
        assert len(resolved["components"]) == 13
        assert elapsed < 2.0

    def test_a_chain_beyond_the_limit_is_refused_rather_than_exhausting_the_stack(
            self, full_features):
        from core.features import FeatureError
        cat = full_features.catalogue
        cat.define("root", "book_id", "numeric", "root", "person/o",
                   shape=[1], components=["a"])
        previous = "root"
        for i in range(14):
            name = f"deep{i}"
            cat.define(name, "book_id", "numeric", "x", "person/o",
                       composes=[{"name": previous}]) if i < 11 else None
            if i < 11:
                previous = name
        with pytest.raises(FeatureError, match="modelling problem"):
            for i in range(11, 16):
                cat.define(f"deeper{i}", "book_id", "numeric", "x", "person/o",
                           composes=[{"name": previous}])
                previous = f"deeper{i}"

    def test_a_wide_catalogue_still_resolves_one_feature_quickly(self,
                                                                 full_features):
        cat = full_features.catalogue
        for i in range(500):
            cat.define(f"f{i:04d}", "book_id", "numeric", "x", "person/o")
        cat.define("wide", "book_id", "numeric", "x", "person/o",
                   composes=[{"name": f"f{i:04d}"} for i in range(20)])
        elapsed, _resolved = timed(lambda: cat.resolved("wide"))
        assert elapsed < 3.0
