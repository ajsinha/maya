"""
MAYA — isolating artifact execution.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

The engine loads files whose contents it did not write. A governance platform
that runs an arbitrary artifact in its own process has made the artifact's bugs
into its own.

The tests that matter are the ones proving the boundary is where the docstring
says it is — and the one proving the engine is honest about what it does *not*
protect against. An engine that claims isolation it does not have is more
dangerous than one that claims none.
"""

import pytest

from core.execution import CaptiveEngine, WarrantService
from core.execution.errors import WarrantError
from core.execution.runtimes import digest_of
from core.execution.sandbox import (DEFAULT_MEMORY_MB, InProcessSandbox, Limits,
                                    SubprocessSandbox, describe)
from tests.conftest import URN

SCORECARD = """<?xml version="1.0"?>
<PMML xmlns="http://www.dmg.org/PMML-4_4" version="4.4">
  <Header/><DataDictionary/>
  <RegressionModel functionName="regression" normalizationMethod="softmax">
    <RegressionTable intercept="-1.5">
      <NumericPredictor name="dscr" coefficient="-0.8"/>
    </RegressionTable>
  </RegressionModel>
</PMML>
"""


@pytest.fixture
def artifact(tmp_path):
    path = tmp_path / "sb.pmml"
    path.write_text(SCORECARD)
    return path


def warrant_for(digest, seconds=30, memory_mb=512):
    return {
        "subject": {"version_id": "v-1", "model_urn": URN, "version": "1.0.0"},
        "realisation": {"runtime": "pmml", "entry": {},
                        "artifact": {"uri": "file://sb.pmml", "digest": digest}},
        "io_contract": {"input_schema": [{"name": "dscr"}],
                        "output_schema": [{"name": "pd_12m"}]},
        "constraints": {"resources": {"max_seconds": seconds,
                                      "max_memory_mb": memory_mb}},
    }


# ================================================================== the limits
class TestLimitsComeFromTheWarrant:
    """The grammar already carried constraints.resources; this is where that
    section stops being documentation."""

    def test_limits_are_read_from_the_warrant(self):
        limits = Limits.of(warrant_for("d", seconds=7, memory_mb=256))
        assert limits.seconds == 7.0 and limits.memory_mb == 256

    def test_a_warrant_with_no_resources_gets_defaults(self):
        limits = Limits.of({"constraints": {}})
        assert limits.memory_mb == DEFAULT_MEMORY_MB

    def test_a_warrant_with_no_constraints_at_all_gets_defaults(self):
        assert Limits.of({}).seconds > 0


# ================================================================ the boundary
class TestTheSandboxIsHonest:
    def test_it_says_what_it_protects_against(self):
        from core.execution.sandbox import RLIMITS

        report = describe(SubprocessSandbox())
        assert report["isolates"] is True
        assert "artifact crash" in report["protects_against"]
        # Platform-dependent, because the answer is. Claiming "protects
        # against unbounded memory" on a system with no `resource` module
        # would be this module's own stated failure, printed by the function
        # whose job is to prevent it.
        if RLIMITS:
            assert "runaway cpu" in report["protects_against"]
            assert report["resource_limits"] == "enforced"
        else:
            assert "runaway cpu" not in report["protects_against"]
            assert "UNAVAILABLE" in report["resource_limits"]

    def test_it_says_what_it_does_not(self):
        """An engine claiming isolation it does not have is worse than one
        claiming none."""
        report = describe(SubprocessSandbox())
        gaps = " ".join(report["does_not_protect_against"])
        assert "hostile artifact" in gaps
        assert "filesystem" in gaps and "network" in gaps
        assert "bound callables" in gaps

    def test_the_in_process_sandbox_admits_it_protects_nothing(self):
        report = describe(InProcessSandbox())
        assert report["isolates"] is False
        assert "no isolation" in " ".join(report["does_not_protect_against"])


class TestItRunsWhereThereAreNoResourceLimits:
    """`resource` is POSIX-only. Importing it at module scope meant MAYA could
    not START on Windows — the traceback ended at `import resource`, which is a
    portability bug rather than a sandbox one.

    What survives without it is process isolation and the wall-clock deadline;
    what is lost is the CPU and address-space caps. The rule these hold is that
    the platform stops CLAIMING the two it cannot deliver.
    """

    def test_the_import_is_guarded(self):
        """Asserted on the SOURCE, because the failure was an ImportError at
        module scope: by the time a test runs, the import has already either
        worked or taken the process down.

        Not by reloading the module — that rebinds its classes, so
        `SubprocessSandbox` imported at the top of this file stops being the
        one the module now holds, and five unrelated tests fail on identity.
        """
        import inspect

        from core.execution import sandbox

        source = inspect.getsource(sandbox)
        assert "try:\n    import resource\nexcept ImportError" in source, \
            "`resource` is POSIX-only and must not be imported unguarded"
        assert isinstance(sandbox.RLIMITS, bool)

    def test_a_warrant_that_states_a_memory_cap_is_REFUSED(self, monkeypatch):
        """Not run unbounded with a warning. Running would put an execution on
        the evidence chain under a warrant declaring a cap that was never
        imposed — the platform asserting compliance with a control it did not
        exercise."""
        from core.execution import sandbox as module

        monkeypatch.setattr(module, "RLIMITS", False)
        limits = Limits.of(warrant_for("d", seconds=7, memory_mb=256))
        assert limits.unenforceable() == ("max_memory_mb",)
        with pytest.raises(WarrantError) as raised:
            SubprocessSandbox().run({}, {}, None, limits)
        assert raised.value.code == "limit_not_enforceable"
        assert "has not been run" in raised.value.detail

    def test_a_warrant_that_states_nothing_still_runs(self, monkeypatch):
        """A default is MAYA's own conservative choice; nobody was promised it.
        Refusing every execution on a platform without rlimits would make the
        engine unusable there for no governance gain."""
        from core.execution import sandbox as module

        monkeypatch.setattr(module, "RLIMITS", False)
        assert Limits.of({}).unenforceable() == ()
        assert Limits.of({"constraints": {}}).unenforceable() == ()

    def test_a_stated_TIMEOUT_is_still_enforceable(self, monkeypatch):
        """The parent reclaims a child that does not return, whatever the
        platform — so a warrant asking for thirty seconds gets thirty seconds.
        Calling that unenforced would be the opposite error."""
        from core.execution import sandbox as module

        monkeypatch.setattr(module, "RLIMITS", False)
        limits = Limits.of({"constraints": {"resources": {"max_seconds": 5}}})
        assert limits.unenforceable() == ()

    def test_the_limits_say_which_the_warrant_stated(self):
        """The distinction the refusal turns on.

        Built inline rather than with `warrant_for`, which fills BOTH from its
        own defaults — so asking it for a memory-only warrant gives a warrant
        stating two limits, and the test would have been asserting the
        helper's shape rather than the rule.
        """
        def constraining(**resources):
            return {"constraints": {"resources": resources}}

        assert Limits.of({}).declared == ()
        assert Limits.of(constraining()).declared == ()
        assert Limits.of(constraining(max_memory_mb=256)).declared == \
            ("max_memory_mb",)
        assert Limits.of(constraining(max_seconds=7)).declared == \
            ("max_seconds",)
        assert Limits.of(constraining(max_seconds=7, max_memory_mb=256)
                         ).declared == ("max_memory_mb", "max_seconds")

    def test_applying_them_reports_what_it_applied(self, monkeypatch):
        """"The artifact ran under a 512 MB cap" has to be something the
        platform OBSERVED rather than intended; on a system without rlimits
        those are different statements and only one is evidence."""
        from core.execution import sandbox as module

        monkeypatch.setattr(module, "RLIMITS", False)
        assert module._apply_limits(Limits()) == ()

    def test_the_description_names_the_platform(self, monkeypatch):
        from core.execution import sandbox as module

        monkeypatch.setattr(module, "RLIMITS", False)
        report = describe(SubprocessSandbox())
        gaps = " ".join(report["does_not_protect_against"])
        assert "unbounded memory" in gaps
        assert "resource limits are unavailable" in gaps
        assert report["platform"]


# ================================================================== execution
class TestArtifactsRunIsolated:
    def test_a_pmml_artifact_scores_through_the_subprocess(self, artifact):
        sandbox = SubprocessSandbox()
        result = sandbox.run(warrant_for(digest_of(artifact)), {"dscr": 2.0},
                             artifact.parent, Limits.of(warrant_for("d")))
        assert 0.0 < result["pd_12m"] < 1.0

    def test_a_refusal_crosses_the_process_boundary_intact(self, artifact):
        """A refusal computed in the child must arrive as the same refusal."""
        sandbox = SubprocessSandbox()
        with pytest.raises(WarrantError) as exc:
            sandbox.run(warrant_for("sha256:wrong"), {"dscr": 2.0},
                        artifact.parent, Limits.of(warrant_for("d")))
        assert exc.value.code == "artifact_mismatch"
        assert "raise a security incident" in exc.value.remediation

    def test_a_missing_input_refusal_also_crosses(self, artifact):
        sandbox = SubprocessSandbox()
        with pytest.raises(WarrantError) as exc:
            sandbox.run(warrant_for(digest_of(artifact)), {},
                        artifact.parent, Limits.of(warrant_for("d")))
        assert exc.value.code == "missing_inputs"

    def test_the_same_answer_in_process_and_sandboxed(self, artifact):
        """Isolation must not change the number."""
        warrant = warrant_for(digest_of(artifact))
        limits = Limits.of(warrant)
        direct = InProcessSandbox().run(warrant, {"dscr": 2.0}, artifact.parent,
                                        limits)
        isolated = SubprocessSandbox().run(warrant, {"dscr": 2.0}, artifact.parent,
                                           limits)
        assert direct == isolated


# ================================================================ the engine
class TestTheEngineChoosesCorrectly:
    def test_artifact_runtimes_are_sandboxed(self, repos, registry, evidence,
                                             a_model, approved_version):
        engine = CaptiveEngine(WarrantService(repos["warrants"], registry, evidence))
        assert engine._sandboxed({"realisation": {"runtime": "pmml"},
                                  "subject": {"version_id": "v-1"}}) is True
        assert engine._sandboxed({"realisation": {"runtime": "onnx"},
                                  "subject": {"version_id": "v-1"}}) is True

    def test_a_bound_callable_is_not_and_cannot_be(self, repos, registry, evidence,
                                                   a_model, approved_version):
        """You cannot isolate a function handed to you in your own address space."""
        engine = CaptiveEngine(WarrantService(repos["warrants"], registry, evidence))
        engine.register_runtime("v-1", lambda i: 1.0)
        assert engine._sandboxed({"realisation": {"runtime": "descriptor_only"},
                                  "subject": {"version_id": "v-1"}}) is False

    def test_the_engine_reports_its_isolation(self, repos, registry, evidence):
        engine = CaptiveEngine(WarrantService(repos["warrants"], registry, evidence))
        assert engine.isolation()["sandbox"] == "subprocess"
        assert engine.isolation()["does_not_protect_against"]

    def test_it_can_be_switched_to_no_isolation_deliberately(self, repos, registry,
                                                             evidence):
        engine = CaptiveEngine(WarrantService(repos["warrants"], registry, evidence),
                               sandbox=InProcessSandbox())
        assert engine.isolation()["isolates"] is False


# ================================================================== survival
class TestThePlatformSurvivesTheArtifact:
    def test_a_child_that_crashes_does_not_take_the_engine_with_it(self, tmp_path):
        """A segfault in a native runtime kills the child, not the platform."""
        bad = tmp_path / "sb.pmml"
        bad.write_text("<PMML>not valid xml at all")
        sandbox = SubprocessSandbox()
        with pytest.raises(WarrantError) as exc:
            sandbox.run(warrant_for(digest_of(bad)), {"dscr": 1.0}, tmp_path,
                        Limits.of(warrant_for("d")))
        assert exc.value.code in ("execution_failed", "pmml_unsupported")
        # the parent is still here, and still works
        good = tmp_path / "sb.pmml"
        good.write_text(SCORECARD)
        assert sandbox.run(warrant_for(digest_of(good)), {"dscr": 2.0}, tmp_path,
                           Limits.of(warrant_for("d")))["pd_12m"] > 0

    def test_the_failure_is_attributed_to_the_artifact(self, tmp_path):
        bad = tmp_path / "sb.pmml"
        bad.write_text("<PMML>broken")
        with pytest.raises(WarrantError) as exc:
            SubprocessSandbox().run(warrant_for(digest_of(bad)), {"dscr": 1.0},
                                    tmp_path, Limits.of(warrant_for("d")))
        if exc.value.code == "execution_failed":
            assert "the engine survived it" in exc.value.remediation
