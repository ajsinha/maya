"""The data upstream of the models, watched as carefully as the models.

Most "model failures" are data failures. The model was fine; the feed stopped,
or arrived a tenth of its usual size, or lost a column, or filled one with
nulls — and the model went on producing plausible numbers from it, because that
is what models do. Every other monitor in this platform points at a model's
scores, which is to say at the last place the problem shows up.
"""
from __future__ import annotations

import time


from core.features.pipeline import MIN_HISTORY, PipelineHealth

HOUR = 3600.0


class _Repo:
    @staticmethod
    def many():
        return [{"name": "book"}]


class _Views:
    """Stands in for the view manager: `views` is the repository behind it."""

    def __init__(self, versions):
        self._versions = versions
        self.views = _Repo()

    def versions_of(self, name):
        return list(self._versions)


def _version(n, *, at, rows=1000, features=("pd", "lgd"), nulls=None):
    return {"version": n, "materialised_at": at, "row_count": rows,
            "features": list(features),
            "quality_report": {f: {"null_rate": (nulls or {}).get(f, 0.0),
                                   "distinct": 10} for f in features}}


def _steady(count=6, *, now, gap=24 * HOUR, rows=1000, features=("pd", "lgd")):
    """A view that has behaved like itself for `count` loads."""
    return [_version(i + 1, at=now - (count - 1 - i) * gap, rows=rows,
                     features=features) for i in range(count)]


class TestItJudgesAViewAgainstItsOwnHistory:
    """A freshness SLA somebody sets at onboarding is one nobody revisits, and
    it either never fires or fires until somebody switches it off."""

    def test_a_steady_feed_is_healthy(self):
        now = time.time()
        health = PipelineHealth(_Views(_steady(now=now)))
        out = health.for_view("book", now=now)
        assert out["judged"] and out["healthy"]
        assert out["detail"] == "this feed is behaving like itself"

    def test_a_young_feed_is_not_judged_and_says_why(self):
        """A baseline built from one observation is a number with a false air
        of authority, and a monitor that cries wolf in its first week is one
        nobody trusts later."""
        now = time.time()
        health = PipelineHealth(_Views(_steady(count=MIN_HISTORY, now=now)))
        out = health.for_view("book", now=now)
        assert out["judged"] is False
        assert "false air of authority" in out["detail"]

    def test_a_view_never_materialised_says_so(self):
        out = PipelineHealth(_Views([])).for_view("book")
        assert out["judged"] is False and "never been materialised" in out["detail"]


class TestFreshness:
    def test_a_stopped_feed_is_reported_with_both_numbers(self):
        now = time.time()
        versions = _steady(now=now - 5 * 24 * HOUR)
        out = PipelineHealth(_Views(versions)).for_view("book", now=now)
        problem = next(p for p in out["problems"] if p["kind"] == "freshness")
        assert problem["usual_hours"] == 24.0
        assert problem["observed_hours"] > 100
        assert "a late batch and two is a stopped one" in problem["detail"]

    def test_one_late_load_is_not_reported(self):
        """One missed load is a late batch."""
        now = time.time()
        versions = _steady(now=now - 30 * HOUR)
        out = PipelineHealth(_Views(versions)).for_view("book", now=now)
        assert not [p for p in out["problems"] if p["kind"] == "freshness"]


class TestVolume:
    def test_a_load_at_half_its_size_is_reported(self):
        now = time.time()
        versions = _steady(now=now)
        versions[-1]["row_count"] = 300
        out = PipelineHealth(_Views(versions)).for_view("book", now=now)
        problem = next(p for p in out["problems"] if p["kind"] == "volume_drop")
        assert problem["observed"] == 300 and problem["usual"] == 1000
        assert "average of less" in problem["detail"]

    def test_a_spike_is_reported_more_gently_than_a_drop(self):
        now = time.time()
        versions = _steady(now=now)
        versions[-1]["row_count"] = 9000
        problem = next(p for p in
                       PipelineHealth(_Views(versions)).for_view("book", now=now)["problems"]
                       if p["kind"] == "volume_spike")
        assert "backfill" in problem["detail"]

    def test_ordinary_variation_is_not_reported(self):
        now = time.time()
        versions = _steady(now=now)
        versions[-1]["row_count"] = 1100
        assert not [p for p in
                    PipelineHealth(_Views(versions)).for_view("book", now=now)["problems"]
                    if p["kind"].startswith("volume")]


class TestSchema:
    def test_losing_a_column_is_reported_as_its_own_thing(self):
        """Gaining one is usually somebody's work; losing one breaks the
        featureset pinned to this view."""
        now = time.time()
        versions = _steady(now=now)
        versions[-1] = _version(6, at=now, features=("pd",))
        out = PipelineHealth(_Views(versions)).for_view("book", now=now)
        lost = next(p for p in out["problems"] if p["kind"] == "schema_lost")
        assert lost["features"] == ["lgd"]
        assert "can no longer be filled" in lost["detail"]

    def test_gaining_a_column_is_reported_separately(self):
        now = time.time()
        versions = _steady(now=now)
        versions[-1] = _version(6, at=now, features=("pd", "lgd", "ead"))
        out = PipelineHealth(_Views(versions)).for_view("book", now=now)
        gained = next(p for p in out["problems"] if p["kind"] == "schema_gained")
        assert gained["features"] == ["ead"]


class TestNullSpikes:
    """The one an assertion cannot reach: an assertion catches a rate crossing
    a line somebody drew in advance, and this catches one that tripled while
    staying inside it."""

    def test_a_tripling_above_the_floor_is_reported(self):
        now = time.time()
        versions = _steady(now=now)
        versions[-1] = _version(6, at=now, nulls={"pd": 0.30})
        out = PipelineHealth(_Views(versions)).for_view("book", now=now)
        spike = next(p for p in out["problems"] if p["kind"] == "null_spike")
        assert spike["feature"] == "pd" and spike["observed"] == 0.30

    def test_a_tiny_rate_multiplying_is_not_news(self):
        """0.1% to 0.4% is a quadrupling, and a monitor that says so is one
        people learn to skim."""
        now = time.time()
        versions = [_version(i + 1, at=now - (5 - i) * 24 * HOUR,
                             nulls={"pd": 0.001}) for i in range(5)]
        versions.append(_version(6, at=now, nulls={"pd": 0.004}))
        out = PipelineHealth(_Views(versions)).for_view("book", now=now)
        assert not [p for p in out["problems"] if p["kind"] == "null_spike"]


class TestTheSweep:
    """Only the two that break a model raise. Raising all four would make this
    the loudest thing in the estate and therefore the first thing muted."""

    def _health(self, versions, findings):
        return PipelineHealth(
            _Views(versions), findings=findings,
            registry=object(),
            models_using=lambda name: [{"id": "m-1", "owner": "person/o"}])

    def test_a_lost_column_raises(self, findings):
        now = time.time()
        versions = _steady(now=now)
        versions[-1] = _version(6, at=now, features=("pd",))
        out = self._health(versions, findings).sweep(now=now)
        assert out["count"] == 1
        raised = [f for f in findings.open_for("m-1")
                  if f["category"] == "data_pipeline"]
        assert raised and raised[0]["severity"] == "High"
        assert "upstream of the model rather than in it" in raised[0]["description"]

    def test_a_volume_drop_does_not_raise(self, findings):
        now = time.time()
        versions = _steady(now=now)
        versions[-1]["row_count"] = 10
        assert self._health(versions, findings).sweep(now=now)["count"] == 0

    def test_it_does_not_raise_the_same_finding_twice(self, findings):
        now = time.time()
        versions = _steady(now=now)
        versions[-1] = _version(6, at=now, features=("pd",))
        health = self._health(versions, findings)
        assert health.sweep(now=now)["count"] == 1
        assert health.sweep(now=now)["count"] == 0

    def test_a_healthy_estate_says_so(self, findings):
        now = time.time()
        out = self._health(_steady(now=now), findings).sweep(now=now)
        assert "behaving like itself" in out["detail"]
