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
        report = describe(SubprocessSandbox())
        assert report["isolates"] is True
        assert "runaway cpu" in report["protects_against"]

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
