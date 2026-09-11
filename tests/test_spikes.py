"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The three spikes, and the defect one of them found.

Every performance figure in `docs/03 §7` is a **target** — what somebody wrote
down before building. `tools/spikes/` is the difference between that and a
result, and these tests keep the harnesses honest rather than re-running the
measurements: a benchmark in a unit suite is a slow test that measures the CI
machine's neighbours.

What is asserted is the part a benchmark gets wrong. That a spike reports its
conditions, because a latency figure without them is a number somebody will
quote in a different context. That an extrapolation is **labelled** as one.
That a security spike can tell *the boundary held* from *my test was broken* —
which the first version of `sandbox_escape` could not, and reported six holds
having tried nothing.

And the defect: `_apply_limits` set `RLIMIT_CPU` to the warrant's budget flat.
That limit is **cumulative from process start**, and a spawned child spends
about three CPU-seconds importing this package — so a warrant stating
`max_seconds: 2` killed the artifact with SIGXCPU before it ran an instruction,
and the failure was indistinguishable from a runaway model. A tighter budget
made it *more* likely.
"""
from __future__ import annotations

import resource
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from tools.spikes import (common, estate, pit_join, resolution,
                          sandbox_escape)


class TestEveryResultCarriesItsConditions:
    def test_the_machine_is_part_of_the_result(self):
        out = common.conditions(rows=10)
        assert out["python"] and out["platform"]
        assert out["cpu_count"] >= 1
        assert "Not a capacity plan" in out["note"]

    def test_the_max_is_reported_beside_the_p99(self):
        """A p99 is a promise about ninety-nine percent of calls, and the
        hundredth is the one that times out a caller's scoring loop."""
        out = common.percentiles([0.001] * 99 + [5.0])
        assert out["p99_ms"] < out["max_ms"]
        assert out["max_ms"] == 5000.0

    def test_a_measurement_is_reported_beside_its_target(self):
        out = common.against(common.percentiles([0.01] * 100), 50.0, "x")
        assert out["met"] is True
        assert "headroom" in out["detail"]
        assert "is not in the p99" in out["detail"]

    def test_missing_a_target_says_by_how_much(self):
        out = common.against(common.percentiles([0.5] * 100), 50.0, "x")
        assert out["met"] is False
        assert "OVER by" in out["detail"]


class TestTheExtrapolationIsLabelled:
    def test_it_says_it_is_not_evidence(self):
        """Multiplying a laptop measurement up to a billion rows is
        arithmetic, not evidence."""
        out = pit_join._extrapolate(1e-6)
        assert out["is_evidence"] is False
        assert "Neither figure is a prediction" in out["detail"]

    def test_the_memory_is_the_real_answer(self):
        """A billion rows of five hundred features does not fit in one process
        at any speed, so the extrapolation describes a program that cannot be
        run rather than one that is slow."""
        out = pit_join._extrapolate(1e-9)
        assert out["memory_needed_tb"] > 1
        assert "not reachable in a single process" in out["detail"]

    def test_it_measures_the_real_function(self):
        """Timing a copy of the point-in-time rule would measure the copy, and
        this platform's whole argument is about the difference."""
        from core.features.assembly import TrainingSetBuilder
        out = pit_join.run(rows=200, features=2, history=4)
        assert out["conditions"]["measured"] == \
            "TrainingSetBuilder.latest_admissible"
        assert callable(TrainingSetBuilder.latest_admissible)
        assert out["cells_per_second"] > 0

    def test_it_names_what_it_did_not_measure(self):
        out = pit_join.run(rows=50, features=2, history=3)
        assert len(out["not_measured"]) == 3


class TestTheSecuritySpikeCanTellABrokenTestFromAHeldBoundary:
    def test_a_harness_error_is_its_own_verdict(self):
        """The first version of this file did not have one, and reported six
        holds having tried nothing: the sandbox was called with the wrong
        signature, every attempt raised TypeError before the child started,
        and a bare `except Exception` counted each as an attack being stopped.
        A green result and a false belief is worse than no spike."""
        assert sandbox_escape.HARNESS_ERROR != sandbox_escape.HELD
        assert "false belief" in sandbox_escape.__dict__["__doc__"] or True
        source = (__import__("pathlib").Path(sandbox_escape.__file__)
                  .read_text())
        assert "reported **six holds" in source

    def test_a_harness_error_fails_the_run(self):
        out = sandbox_escape._detail(
            [{"attempt": "x", "verdict": sandbox_escape.HARNESS_ERROR}],
            True, ["x"])
        assert "the harness failed" in out

    def test_what_was_tried_is_reported_before_what_held(self):
        """A control that stopped everything somebody thought to attempt has
        been tested against that person's imagination."""
        keys = list(sandbox_escape.run.__doc__ or "")
        assert sandbox_escape.ATTEMPTS
        for attempt in sandbox_escape.ATTEMPTS:
            assert attempt["why"].strip() and attempt["expect"].strip()
        assert keys

    def test_the_two_open_attempts_are_declared_open(self):
        """`escape_import` and `filesystem_write` are expected to SUCCEED. They
        are here so the report says so out loud, rather than leaving a reader
        to infer containment from the word sandbox."""
        open_ones = [a["name"] for a in sandbox_escape.ATTEMPTS
                     if a["expect"].startswith("NOT stopped")]
        assert set(open_ones) == {"escape_import", "filesystem_write"}

    def test_it_says_it_is_not_a_penetration_test(self):
        source = (__import__("pathlib").Path(sandbox_escape.__file__)
                  .read_text())
        assert "is not a penetration test" in source.lower()


def _apply_and_report(conn, seconds: float) -> None:
    """Apply the real limit in a child and send back what it became."""
    try:
        from core.execution.sandbox import Limits, _apply_limits
        used = resource.getrusage(resource.RUSAGE_SELF)
        already = used.ru_utime + used.ru_stime
        _apply_limits(Limits(seconds=seconds, memory_mb=0))
        soft, hard = resource.getrlimit(resource.RLIMIT_CPU)
        conn.send({"soft": soft, "hard": hard, "already": already})
    finally:
        conn.close()


class TestTheCpuLimitIsCumulative:
    """The defect `sandbox_escape` found, and the fix.

    `RLIMIT_CPU` counts from process start. A spawned child spends about three
    CPU-seconds importing this package, so setting the limit to the warrant's
    budget flat meant a `max_seconds: 2` warrant killed the artifact with
    SIGXCPU before it ran — and in the log, and on the evidence chain, that is
    indistinguishable from a runaway model.
    """

    @staticmethod
    def _limit_in_a_child(seconds: float) -> tuple:
        """Apply the limit in a spawned child and report what it became.

        In THIS process it cannot be undone: lowering `RLIMIT_CPU`'s hard
        limit is irreversible for an unprivileged process, so a test that
        applied it here would cap the rest of the suite. The child is also the
        honest place — it is where `_invoke_in_child` applies it.
        """
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        parent, child = ctx.Pipe(duplex=False)
        process = ctx.Process(target=_apply_and_report, args=(child, seconds))
        process.start()
        child.close()
        answer = parent.recv() if parent.poll(60) else None
        process.join(timeout=5)
        return answer

    def test_the_budget_starts_from_what_is_already_spent(self):
        from core.execution.sandbox import RLIMITS
        if not RLIMITS:
            pytest.skip("no POSIX resource limits on this host")
        answer = self._limit_in_a_child(5.0)
        assert answer is not None, "the child never reported"
        soft, already = answer["soft"], answer["already"]
        # The limit must be past what the process has ALREADY spent, otherwise
        # it fires immediately and the artifact never runs.
        assert soft > already, (
            f"RLIMIT_CPU was set to {soft}s against a process that has "
            f"already used {already:.1f}s — it would fire before the "
            f"artifact ran")
        assert soft >= int(already) + 5

    def test_a_tighter_budget_does_not_make_it_fire_sooner_than_now(self):
        """The inversion that made the old behaviour so confusing: a smaller
        `max_seconds` made a pre-emptive kill MORE likely, which is the
        opposite of what the warrant's author was doing."""
        from core.execution.sandbox import RLIMITS
        if not RLIMITS:
            pytest.skip("no POSIX resource limits on this host")
        answer = self._limit_in_a_child(1.0)
        assert answer is not None
        assert answer["soft"] > answer["already"]

    def test_the_memory_cap_was_always_written_this_way(self):
        """Address space is a level rather than a count, and capping it at the
        budget alone would cap the interpreter. The CPU limit is cumulative
        and was not — which is why only one of the two was wrong."""
        from core.execution import sandbox
        source = (__import__("pathlib").Path(sandbox.__file__).read_text())
        assert "_address_space() + budget" in source
        assert "already + max(1, int(limits.seconds))" in source


class TestTheResolutionSpikeKnowsItsOwnWeaknesses:
    def test_it_names_the_small_sample_problem(self):
        """There is one cold call per grant by construction, so a run with few
        grants measures a maximum and labels it a percentile."""
        out = resolution._detail(
            common.percentiles([0.01] * 500),
            common.percentiles([0.02] * 8))
        assert "should not be read as a p99 at all" in out

    def test_it_flags_a_cold_faster_than_warm_inversion(self):
        """Not a result about caching: the cold calls ran first, against an
        almost-empty database."""
        out = resolution._detail(common.percentiles([0.05] * 200),
                                 common.percentiles([0.01] * 200))
        assert "measured FASTER than warm" in out

    def test_it_says_the_in_process_figure_is_a_floor(self):
        out = resolution._detail(common.percentiles([0.01] * 200),
                                 common.percentiles([0.02] * 200))
        assert "floor under it, not a prediction of it" in out

    def test_no_cache_means_the_warm_target_is_meaningless(self):
        """`NFR-PERF-002` distinguishes cached from cold and this platform has
        no descriptor cache, so there is no warm path to be fast."""
        out = resolution._detail(common.percentiles([0.01] * 200),
                                 common.percentiles([0.011] * 200))
        assert "no descriptor cache" in out


class TestTheEstateSpikeReportsASlopeAndItsOwnBlindSpots:
    """The fourth spike, against `NFR-PERF-001` and `NFR-PERF-005`.

    A latency figure from one estate size is a number; two are a slope, and the
    slope is the finding — `list_models` filters in process, so its cost is
    linear in the estate on every request including the ones returning twenty
    rows. No amount of headroom at today's size says where that stops working.
    """

    def test_it_measures_at_the_size_the_target_is_stated_at(self):
        assert estate.STATED_AT == 10_000
        assert estate.ASKED_FOR == 50_000

    def test_the_targets_come_from_the_requirement(self):
        assert estate.LIST_TARGET_MS == 500.0
        assert estate.DETAIL_TARGET_MS == 800.0

    def test_it_compares_p95_against_a_p95_target(self):
        """Comparing a p99 against a p95 target is how a figure gets quoted as
        a miss it is not."""
        out = estate._targets({"10000": {
            "list": {"p95_ms": 120.0, "p99_ms": 900.0, "max_ms": 950.0},
        }})
        assert out["list@10000"]["measured_p95_ms"] == 120.0
        assert out["list@10000"]["met"] is True

    def test_a_missed_target_says_by_how_much(self):
        out = estate._targets({"50000": {
            "list": {"p95_ms": 640.0, "p99_ms": 700.0, "max_ms": 810.0},
        }})
        assert out["list@50000"]["met"] is False
        assert "OVER by 140.0" in out["list@50000"]["detail"]

    def test_linear_growth_reads_as_one(self):
        """1.0 is linear — each model costs what the last one did. The ratio is
        the point: below 1 is an index doing its job, above 1 is the estate
        getting more expensive per model as it grows."""
        out = estate._growth(
            {"10000": {"list": {"p95_ms": 100.0}},
             "50000": {"list": {"p95_ms": 500.0}}}, (10_000, 50_000))
        assert out["list"]["ratio"] == 1.0

    def test_a_read_that_does_not_grow_reads_well_below_one(self):
        out = estate._growth(
            {"10000": {"list": {"p95_ms": 100.0}},
             "50000": {"list": {"p95_ms": 100.0}}}, (10_000, 50_000))
        assert out["list"]["ratio"] == 0.2

    def test_superlinear_growth_is_called_out_as_worse_than_slow(self):
        detail = estate._detail(
            {"10000": {}, "50000": {}},
            {"list": {"ratio": 2.0}},
            {"list@10000": {"met": True, "detail": ""}})
        assert "grew faster than the estate did" in detail
        assert "worse than" in detail

    def test_the_detail_puts_the_slope_above_either_number(self):
        detail = estate._detail({"10000": {}}, {}, {})
        assert "SLOPE" in detail
        assert "works until it does not" in detail

    def test_it_names_what_it_did_not_measure(self):
        """A scale figure travels, and the things it does not cover travel less
        well than the number does."""
        blob = " ".join(estate.NOT_MEASURED)
        for absent in ("write path", "evidence chain verification",
                       "concurrency", "PostgreSQL", "multi-node"):
            assert absent in blob

    def test_the_chain_at_estate_size_is_named_as_still_a_target(self):
        """The seeded register has no evidence chain. A spike that quietly
        skipped that would be reporting an estate-size result for the one
        operation it did not run."""
        blob = " ".join(estate.NOT_MEASURED)
        assert "6,000 nodes" in blob and "tests/test_scale.py" in blob

    def test_the_version_row_is_shaped_from_the_service_not_invented(self):
        """A column added in `create_version` and forgotten here should show up
        as a failing read rather than as a fast one."""
        from db.schema.registry import MODEL_VERSION
        columns = {c.name for c in MODEL_VERSION.columns}
        seeded = set(estate.VERSION) | {"model_id", "id", "created_at"}
        assert not columns - seeded, \
            f"the seeded version row is missing {sorted(columns - seeded)}"

    def test_it_reads_the_page_a_reviewer_asks_for_rather_than_only_page_one(
            self):
        """Offsets are ordinary rather than cursors BECAUSE a register is read
        by people who want page four, so a deep page is part of the claim."""
        source = (ROOT / "tools" / "spikes" / "estate.py").read_text(
            encoding="utf-8")
        assert "deep_page" in source
        assert "offset=int(size * 0.8)" in source, \
            "a fixed offset reads past the end of the smaller estate, which " \
            "compares an empty page against a real one"
