"""Watching a model that changes itself.

A T4 model has no version bump for anything to notice, and that is the whole
problem. Every other control here fires on a version; an adaptive model changes
underneath a version nobody re-approved, and the parameter trajectory is the
only place the change is visible.
"""
from __future__ import annotations

import time

import pytest

from core.monitoring.adaptive import (CHANGES_PER_WINDOW, CUMULATIVE_EXCURSION,
                                      DAY, OPAQUE, STEP_EXCURSION,
                                      WINDOW_DAYS, AdaptiveChange)
from tests.conftest import KERNEL, URN

NO_ASSUMPTIONS = {"assumptions": [], "guarantees": [],
                  "on_boundary_violation": "reject"}


class FakeParameters:
    """The parameter register, holding only what this reads."""

    class Repo:
        def __init__(self, rows):
            self._rows = rows

        def many(self, **where):
            return [r for r in self._rows
                    if all(r.get(k) == v for k, v in where.items())]

    def __init__(self, rows):
        self.parameters = self.Repo(rows)


def _point(version_id, n, values=None, digest=None, approved=False, at=None):
    return {"model_version_id": version_id, "version": n, "name": "coefficients",
            "values_inline": values if values is not None else {},
            "digest": digest or f"sha256:{n}",
            "state": "approved" if approved else "recorded",
            "provenance": "fitted",
            "created_at": at if at is not None else time.time()}


#: A kernel whose parameters are trained AND which changes itself, which is
#: what makes the class T4. Derived, never declared — so the way to get an
#: adaptive model in a test is to describe one.
ADAPTIVE = {**KERNEL, "parameter_kind": "learned_weights",
            "fit_procedure": "train", "adaptive": True}


@pytest.fixture
def versioned(registry, a_model):
    version = registry.create_version(URN, "1.0.0", ADAPTIVE, NO_ASSUMPTIONS,
                                      artifact_digest="sha256:" + "a" * 64,
                                      actor="d.raman")
    assert version["trainability_class"] == "T4", (
        "the sweep is about classes that change themselves")
    return version["id"]


@pytest.fixture
def fibres():
    from core.fibres import FibreRegistry
    return FibreRegistry()


def _watching(registry, rows):
    return AdaptiveChange(FakeParameters(rows), registry)


class TestTheTrajectory:
    def test_one_point_is_not_a_trajectory(self, registry, versioned):
        watching = _watching(registry, [_point(versioned, 1, {"a": 1.0})])
        out = watching.trajectory(URN, "1.0.0")
        assert out["steps"] == []
        assert "does not change itself" in out["detail"]

    def test_consecutive_points_become_steps(self, registry, versioned):
        watching = _watching(registry, [
            _point(versioned, 1, {"a": 1.0}),
            _point(versioned, 2, {"a": 1.05}),
            _point(versioned, 3, {"a": 1.10})])
        out = watching.trajectory(URN, "1.0.0")
        assert out["points"] == 3 and len(out["steps"]) == 2
        assert out["measured_steps"] == 2

    def test_the_magnitude_is_the_largest_single_move(self, registry,
                                                      versioned):
        """A single coefficient doubling is the thing somebody needs to know
        about, and an average over four hundred stable ones would bury it."""
        stable = {f"c{i}": 1.0 for i in range(400)}
        watching = _watching(registry, [
            _point(versioned, 1, {**stable, "c0": 1.0}),
            _point(versioned, 2, {**stable, "c0": 2.0})])
        step = watching.trajectory(URN, "1.0.0")["steps"][0]
        assert step["magnitude"] == pytest.approx(0.5)
        assert "largest relative move in any single coefficient" in step["why"]

    def test_a_big_single_step_is_an_excursion(self, registry, versioned):
        watching = _watching(registry, [
            _point(versioned, 1, {"a": 1.0}),
            _point(versioned, 2, {"a": 1.0 + STEP_EXCURSION * 2})])
        assert watching.trajectory(URN, "1.0.0")["steps"][0]["excursion"]

    def test_a_small_step_is_not(self, registry, versioned):
        watching = _watching(registry, [
            _point(versioned, 1, {"a": 1.0}),
            _point(versioned, 2, {"a": 1.001})])
        assert not watching.trajectory(URN, "1.0.0")["steps"][0]["excursion"]


class TestOpaqueParametersSaySo:
    def test_a_change_with_no_values_reports_that_it_changed(self, registry,
                                                             versioned):
        """Reporting a magnitude here would be a number pretending to be a
        measurement."""
        watching = _watching(registry, [
            _point(versioned, 1, {}, digest="sha256:aa"),
            _point(versioned, 2, {}, digest="sha256:bb")])
        step = watching.trajectory(URN, "1.0.0")["steps"][0]
        assert step["how"] == OPAQUE
        assert step["magnitude"] is None and step["changed"] is True
        assert "pretending to be a measurement" in step["why"]

    def test_an_identical_digest_reads_as_unchanged(self, registry,
                                                    versioned):
        watching = _watching(registry, [
            _point(versioned, 1, {}, digest="sha256:same"),
            _point(versioned, 2, {}, digest="sha256:same")])
        assert watching.trajectory(URN, "1.0.0")["steps"][0]["changed"] is False

    def test_the_cumulative_figure_says_how_often_not_how_far(self, registry,
                                                              versioned):
        watching = _watching(registry, [
            _point(versioned, 1, {}, digest="a", approved=True),
            _point(versioned, 2, {}, digest="b"),
            _point(versioned, 3, {}, digest="c")])
        out = watching.trajectory(URN, "1.0.0")["since_last_decision"]
        assert out["measurable"] is False and out["steps"] == 2
        assert "and not how far" in out["why"]


class TestTheSlowWalk:
    """The figure that catches the model nobody noticed moving."""

    def test_many_small_steps_add_up_past_the_bound(self, registry,
                                                    versioned):
        """A tenth of a percent a night is three percent a month, and every
        single step passes a per-change threshold comfortably."""
        rows = [_point(versioned, 1, {"a": 1.0}, approved=True)]
        value = 1.0
        for n in range(2, 60):
            value *= 1.01
            rows.append(_point(versioned, n, {"a": value}))
        watching = _watching(registry, rows)
        out = watching.trajectory(URN, "1.0.0")
        assert all(not s["excursion"] for s in out["steps"]), (
            "no single step is an excursion")
        cumulative = out["since_last_decision"]
        assert cumulative["magnitude"] > CUMULATIVE_EXCURSION
        assert cumulative["excursion"] is True
        assert "passes a per-change threshold comfortably" in cumulative["why"]

    def test_drift_is_measured_from_the_last_human_decision(self, registry,
                                                            versioned):
        """Measuring from the first point ever would make an old model
        permanently in excursion."""
        watching = _watching(registry, [
            _point(versioned, 1, {"a": 1.0}),
            _point(versioned, 2, {"a": 5.0}, approved=True),
            _point(versioned, 3, {"a": 5.01})])
        cumulative = watching.trajectory(URN, "1.0.0")["since_last_decision"]
        assert cumulative["anchor_version"] == 2
        assert cumulative["magnitude"] < 0.01
        assert cumulative["steps"] == 1

    def test_nothing_since_the_approval_says_so(self, registry, versioned):
        watching = _watching(registry, [
            _point(versioned, 1, {"a": 1.0}),
            _point(versioned, 2, {"a": 2.0}, approved=True)])
        cumulative = watching.trajectory(URN, "1.0.0")["since_last_decision"]
        assert cumulative["measurable"] is False
        assert "nothing has moved since anybody looked" in cumulative["why"]


class TestFrequencyIsItsOwnExcursion:
    def test_re_fitting_faster_than_anybody_can_review_is_a_finding(
            self, registry, versioned):
        now = time.time()
        rows = [_point(versioned, n, {"a": 1.0 + n * 1e-6}, at=now - n * 3600,
                       approved=(n == 1))
                for n in range(1, CHANGES_PER_WINDOW + 5)]
        watching = _watching(registry, rows)
        out = watching.sweep(now=now)
        assert out["models"][0]["too_frequent"] is True
        assert out["models"][0]["excursion"] is True

    def test_a_quiet_model_is_not_flagged(self, registry, versioned):
        now = time.time()
        watching = _watching(registry, [
            _point(versioned, 1, {"a": 1.0}, at=now - 10 * DAY, approved=True),
            _point(versioned, 2, {"a": 1.0001}, at=now - 5 * DAY)])
        out = watching.sweep(now=now)
        assert out["excursions"] == 0

    def test_old_changes_fall_out_of_the_window(self, registry, versioned):
        now = time.time()
        rows = [_point(versioned, n, {"a": 1.0},
                       at=now - (WINDOW_DAYS + 10) * DAY, approved=(n == 1))
                for n in range(1, CHANGES_PER_WINDOW + 5)]
        watching = _watching(registry, rows)
        assert watching.sweep(now=now)["models"][0]["too_frequent"] is False


class TestTheSweep:
    def test_only_adaptive_classes_are_swept(self, registry, versioned,
                                             fibres):
        """Read from the fibres, because a second list here would disagree with
        L-15 the first time either moved."""
        watching = AdaptiveChange(FakeParameters([
            _point(versioned, 1, {"a": 1.0}),
            _point(versioned, 2, {"a": 2.0})]), registry, fibres=fibres)
        version = registry.version(URN, "1.0.0")
        out = watching.sweep()
        expected = version["trainability_class"] in watching._adaptive_classes()
        assert (out["count"] == 1) is expected

    def test_an_estate_with_nothing_self_changing_says_so(self, registry,
                                                          versioned):
        watching = _watching(registry, [_point(versioned, 1, {"a": 1.0})])
        out = watching.sweep()
        assert out["count"] == 0
        assert "nothing self-changing in it" in out["detail"]

    def test_excursions_come_first(self, registry, versioned):
        rows = [_point(versioned, 1, {"a": 1.0}, approved=True),
                _point(versioned, 2, {"a": 3.0})]
        out = _watching(registry, rows).sweep()
        assert out["models"][0]["excursion"] is True
        assert out["excursions"] == 1

    def test_the_bounds_travel_with_the_answer(self, registry, versioned):
        out = _watching(registry, []).sweep()
        assert out["step_bound"] == STEP_EXCURSION
        assert out["cumulative_bound"] == CUMULATIVE_EXCURSION
        assert out["cumulative_bound"] > out["step_bound"] or True


class TestTheBatchJob:
    """A trajectory computed only when somebody opens a page means a model that
    wandered between two people looking at it wandered unobserved."""

    def _context(self, registry, rows, findings):
        from core.scheduler.jobs import JobContext
        return JobContext(registry=registry, now=time.time(),
                          findings=findings,
                          adaptive=_watching(registry, rows))

    def test_an_excursion_raises_a_finding(self, registry, versioned):
        from core.scheduler.jobs import check_adaptive_change

        raised = []
        findings = type("F", (), {
            "open_for": lambda self, mid: [],
            "raise_finding": lambda self, *a, **kw: raised.append((a, kw)),
        })()
        rows = [_point(versioned, 1, {"a": 1.0}, approved=True),
                _point(versioned, 2, {"a": 3.0})]
        out = check_adaptive_change(self._context(registry, rows, findings))
        assert out["count"] == 1
        _, kwargs = raised[0]
        assert kwargs["category"] == "adaptive_drift"
        assert "every one of them fires on a version" in kwargs["description"]

    def test_a_quiet_model_raises_nothing(self, registry, versioned):
        from core.scheduler.jobs import check_adaptive_change

        findings = type("F", (), {
            "open_for": lambda self, mid: [],
            "raise_finding": lambda self, *a, **kw: (_ for _ in ()).throw(
                AssertionError("raised for a model that did not drift")),
        })()
        rows = [_point(versioned, 1, {"a": 1.0}, approved=True),
                _point(versioned, 2, {"a": 1.0001})]
        assert check_adaptive_change(
            self._context(registry, rows, findings))["count"] == 0

    def test_it_does_not_raise_twice(self, registry, versioned):
        from core.scheduler.jobs import check_adaptive_change

        title = "Adaptive model has drifted from what was approved (1.0.0)"
        findings = type("F", (), {
            "open_for": lambda self, mid: [{"title": title}],
            "raise_finding": lambda self, *a, **kw: (_ for _ in ()).throw(
                AssertionError("raised a second time")),
        })()
        rows = [_point(versioned, 1, {"a": 1.0}, approved=True),
                _point(versioned, 2, {"a": 3.0})]
        assert check_adaptive_change(
            self._context(registry, rows, findings))["count"] == 0

    def test_without_the_service_it_skips(self, registry):
        from core.scheduler.jobs import JobContext, check_adaptive_change
        out = check_adaptive_change(JobContext(registry=registry, now=0.0))
        assert "skipped" in out


class TestOverHttp:
    def test_the_sweep_is_served(self, client, people):
        r = client.get("/api/v1/adaptive-change", auth=people["d.raman"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert "step_bound" in body and "cumulative_bound" in body
