"""
MAYA — the captive engine's runtimes.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

The grammar names eighteen runtimes. This engine implements five, and its
usefulness lies in being precise about which — so the refusals are tested as
carefully as the invocations.

TestDigestVerification is the one that matters most. A warrant that names a
digest and an engine that does not check it is a chain of custody with its last
link missing, and it is the only link that touches what actually executes.
"""
import hashlib
import json
import pathlib

import pytest

from core.execution.errors import WarrantError
from core.execution.runtimes import (CallableRuntime, Invocation, OnnxRuntime,
                                     PmmlRuntime, RuntimeRegistry, digest_of)

SCORECARD = """<?xml version="1.0"?>
<PMML xmlns="http://www.dmg.org/PMML-4_4" version="4.4">
  <Header/>
  <DataDictionary/>
  <RegressionModel functionName="regression" normalizationMethod="softmax">
    <RegressionTable intercept="-1.5">
      <NumericPredictor name="dscr" coefficient="-0.8"/>
      <NumericPredictor name="months_on_book" coefficient="-0.01"/>
      <CategoricalPredictor name="segment" value="hospitality" coefficient="0.6"/>
    </RegressionTable>
  </RegressionModel>
</PMML>
"""

POINTS = """<?xml version="1.0"?>
<PMML xmlns="http://www.dmg.org/PMML-4_4" version="4.4">
  <Header/>
  <DataDictionary/>
  <Scorecard functionName="regression" initialScore="500">
    <Characteristics>
      <Characteristic name="dscr">
        <Attribute partialScore="-80"><SimplePredicate field="dscr" operator="lessThan" value="1.0"/></Attribute>
        <Attribute partialScore="40"><SimplePredicate field="dscr" operator="greaterOrEqual" value="1.0"/></Attribute>
      </Characteristic>
      <Characteristic name="tenure">
        <Attribute partialScore="25"><SimplePredicate field="months_on_book" operator="greaterThan" value="24"/></Attribute>
      </Characteristic>
    </Characteristics>
  </Scorecard>
</PMML>
"""

TREE = """<?xml version="1.0"?>
<PMML xmlns="http://www.dmg.org/PMML-4_4" version="4.4">
  <Header/><DataDictionary/>
  <TreeModel functionName="classification"><Node id="1"/></TreeModel>
</PMML>
"""


def warrant_for(runtime, uri, digest, inputs_schema, outputs=("pd_12m",), entry=None):
    return {
        "subject": {"version_id": "v-1", "model_urn": "maya://model/x",
                    "version": "1.0.0"},
        "realisation": {"runtime": runtime, "entry": entry or {},
                        "artifact": {"uri": uri, "digest": digest}},
        "io_contract": {"input_schema": [{"name": n} for n in inputs_schema],
                        "output_schema": [{"name": n} for n in outputs]},
    }


@pytest.fixture
def artifacts(tmp_path):
    (tmp_path / "scorecard.pmml").write_text(SCORECARD)
    (tmp_path / "points.pmml").write_text(POINTS)
    (tmp_path / "tree.pmml").write_text(TREE)
    return tmp_path


# ============================================================ what it implements
class TestTheRegistry:
    def test_it_reports_what_it_can_run(self):
        registry = RuntimeRegistry([CallableRuntime(), OnnxRuntime(), PmmlRuntime()])
        described = {d["runtime"]: d for d in registry.describe()}
        assert {"python.callable", "onnx", "pmml"} <= set(described)
        assert described["pmml"]["usable"] is True

    def test_a_runtime_it_does_not_have_is_refused_by_name(self):
        registry = RuntimeRegistry([PmmlRuntime()])
        call = Invocation(warrant_for("quantlib", "x", "d", []), {})
        with pytest.raises(WarrantError) as exc:
            registry.invoke(call)
        assert exc.value.code == "no_runtime"
        assert "does not implement the 'quantlib' runtime" in exc.value.detail
        assert "pmml" in exc.value.remediation, "say what it does implement"

    def test_descriptor_only_dispatches_to_the_engine_supplied_model(self):
        """MAYA holds the governance; the engine holds the artifact."""
        callables = CallableRuntime()
        callables.bind("v-1", lambda i: {"pd_12m": 0.4})
        registry = RuntimeRegistry([callables])
        call = Invocation(warrant_for("descriptor_only", "", "", []), {})
        assert registry.invoke(call) == {"pd_12m": 0.4}

    def test_descriptor_only_with_nothing_bound_says_why(self):
        registry = RuntimeRegistry([CallableRuntime()])
        call = Invocation(warrant_for("descriptor_only", "", "", []), {})
        with pytest.raises(WarrantError) as exc:
            registry.invoke(call)
        assert "MAYA does not locate its artifact" in exc.value.detail
        assert "bind the vendor's model" in exc.value.remediation


# ========================================================= digest verification
class TestDigestVerification:
    """The only link in the chain that touches what actually executes."""

    def test_a_matching_digest_runs(self, artifacts):
        path = artifacts / "scorecard.pmml"
        runtime = PmmlRuntime(artifacts)
        call = Invocation(
            warrant_for("pmml", "file://scorecard.pmml", digest_of(path),
                        ["dscr", "months_on_book"]),
            {"dscr": 1.5, "months_on_book": 30})
        assert "pd_12m" in runtime.invoke(call)

    def test_a_changed_artifact_is_refused(self, artifacts):
        path = artifacts / "scorecard.pmml"
        stale = digest_of(path)
        path.write_text(SCORECARD.replace("-0.8", "-0.9"))    # somebody edited it
        runtime = PmmlRuntime(artifacts)
        call = Invocation(
            warrant_for("pmml", "file://scorecard.pmml", stale, ["dscr"]),
            {"dscr": 1.5, "months_on_book": 30})
        with pytest.raises(WarrantError) as exc:
            runtime.invoke(call)
        assert exc.value.code == "artifact_mismatch"
        assert "raise a security incident" in exc.value.remediation

    def test_an_artifact_with_no_digest_is_refused(self, artifacts):
        runtime = PmmlRuntime(artifacts)
        call = Invocation(
            warrant_for("pmml", "file://scorecard.pmml", None, ["dscr"]),
            {"dscr": 1.5})
        with pytest.raises(WarrantError) as exc:
            runtime.invoke(call)
        assert exc.value.code == "artifact_unverifiable"
        assert "cannot be checked against what was approved" in exc.value.detail

    def test_a_path_outside_the_artifact_directory_is_refused(self, artifacts):
        """A warrant is a document from elsewhere; a path inside it is not trusted."""
        runtime = PmmlRuntime(artifacts)
        call = Invocation(
            warrant_for("pmml", "file://../../etc/passwd", "sha256:x", ["dscr"]),
            {"dscr": 1.0})
        with pytest.raises(WarrantError) as exc:
            runtime.invoke(call)
        assert exc.value.code == "artifact_outside_root"

    def test_a_missing_artifact_is_refused_clearly(self, artifacts):
        runtime = PmmlRuntime(artifacts)
        call = Invocation(
            warrant_for("pmml", "file://absent.pmml", "sha256:x", ["dscr"]),
            {"dscr": 1.0})
        with pytest.raises(WarrantError, match="no artifact at"):
            runtime.invoke(call)


# ======================================================================= PMML
class TestPmmlWithoutAJvm:
    def test_a_logistic_regression_evaluates(self, artifacts):
        path = artifacts / "scorecard.pmml"
        runtime = PmmlRuntime(artifacts)
        call = Invocation(
            warrant_for("pmml", "file://scorecard.pmml", digest_of(path),
                        ["dscr", "months_on_book", "segment"]),
            {"dscr": 2.0, "months_on_book": 36, "segment": "retail"})
        result = runtime.invoke(call)
        # -1.5 + (-0.8 x 2.0) + (-0.01 x 36) = -3.46 -> sigmoid
        assert result["pd_12m"] == pytest.approx(1 / (1 + pow(2.718281828, 3.46)),
                                                 rel=1e-3)

    def test_a_categorical_predictor_applies_on_a_match(self, artifacts):
        path = artifacts / "scorecard.pmml"
        runtime = PmmlRuntime(artifacts)

        def score(segment):
            call = Invocation(
                warrant_for("pmml", "file://scorecard.pmml", digest_of(path),
                            ["dscr", "months_on_book", "segment"]),
                {"dscr": 2.0, "months_on_book": 36, "segment": segment})
            return runtime.invoke(call)["pd_12m"]

        assert score("hospitality") > score("retail"), "the +0.6 coefficient applied"

    def test_a_points_scorecard_evaluates_band_by_band(self, artifacts):
        path = artifacts / "points.pmml"
        runtime = PmmlRuntime(artifacts)
        call = Invocation(
            warrant_for("pmml", "file://points.pmml", digest_of(path),
                        ["dscr", "months_on_book"], outputs=("score",)),
            {"dscr": 1.4, "months_on_book": 36})
        assert runtime.invoke(call)["score"] == 500 + 40 + 25

    def test_the_first_matching_band_wins(self, artifacts):
        path = artifacts / "points.pmml"
        runtime = PmmlRuntime(artifacts)
        call = Invocation(
            warrant_for("pmml", "file://points.pmml", digest_of(path),
                        ["dscr", "months_on_book"], outputs=("score",)),
            {"dscr": 0.5, "months_on_book": 12})
        assert runtime.invoke(call)["score"] == 500 - 80

    def test_a_missing_input_is_named(self, artifacts):
        path = artifacts / "scorecard.pmml"
        runtime = PmmlRuntime(artifacts)
        call = Invocation(
            warrant_for("pmml", "file://scorecard.pmml", digest_of(path), ["dscr"]),
            {"dscr": 1.0})
        with pytest.raises(WarrantError) as exc:
            runtime.invoke(call)
        assert "months_on_book" in exc.value.detail

    def test_an_unsupported_model_type_is_refused_by_name(self, artifacts):
        """A partial implementation that silently mis-evaluates a tree ensemble
        would be far worse than one that says it only does regressions."""
        path = artifacts / "tree.pmml"
        runtime = PmmlRuntime(artifacts)
        call = Invocation(
            warrant_for("pmml", "file://tree.pmml", digest_of(path), ["dscr"]),
            {"dscr": 1.0})
        with pytest.raises(WarrantError) as exc:
            runtime.invoke(call)
        assert exc.value.code == "pmml_unsupported"
        assert "TreeModel" in exc.value.detail
        assert "export it as ONNX" in exc.value.remediation

    def test_a_parsed_document_is_cached_by_digest(self, artifacts):
        path = artifacts / "points.pmml"
        runtime = PmmlRuntime(artifacts)
        call = Invocation(
            warrant_for("pmml", "file://points.pmml", digest_of(path),
                        ["dscr", "months_on_book"], outputs=("score",)),
            {"dscr": 1.4, "months_on_book": 36})
        runtime.invoke(call)
        assert len(runtime._parsed) == 1
        runtime.invoke(call)
        assert len(runtime._parsed) == 1, "parsed once, not per call"


# ======================================================================= ONNX
class TestOnnx:
    def test_it_reports_whether_it_is_usable(self):
        assert OnnxRuntime().available() in (None,) or \
            "onnxruntime" in OnnxRuntime().available()

    @pytest.mark.skipif(OnnxRuntime().available() is not None,
                        reason="onnxruntime is not installed")
    def test_a_graph_scores(self, tmp_path):
        """A real ONNX graph, built here so the test does not need a fixture file."""
        import numpy as np
        import onnx
        from onnx import TensorProto, helper

        node = helper.make_node("MatMul", ["features", "weights"], ["score"])
        weights = helper.make_tensor("weights", TensorProto.FLOAT, [2, 1],
                                     [0.5, -0.25])
        graph = helper.make_graph(
            [node], "linear",
            [helper.make_tensor_value_info("features", TensorProto.FLOAT, [1, 2])],
            [helper.make_tensor_value_info("score", TensorProto.FLOAT, [1, 1])],
            initializer=[weights])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 18)])
        model.ir_version = 9
        path = tmp_path / "linear.onnx"
        path.write_bytes(model.SerializeToString())

        runtime = OnnxRuntime(tmp_path)
        call = Invocation(
            warrant_for("onnx", "file://linear.onnx", digest_of(path),
                        ["a", "b"], outputs=("score",),
                        entry={"input_names": ["features"]}),
            {"a": 4.0, "b": 8.0})
        # 4.0 x 0.5 + 8.0 x -0.25 = 0.0
        assert runtime.invoke(call)["score"] == pytest.approx(0.0, abs=1e-5)

    @pytest.mark.skipif(OnnxRuntime().available() is not None,
                        reason="onnxruntime is not installed")
    def test_an_input_the_graph_does_not_have_is_refused(self, tmp_path):
        import onnx
        from onnx import TensorProto, helper
        node = helper.make_node("Identity", ["features"], ["score"])
        graph = helper.make_graph(
            [node], "id",
            [helper.make_tensor_value_info("features", TensorProto.FLOAT, [1, 1])],
            [helper.make_tensor_value_info("score", TensorProto.FLOAT, [1, 1])])
        model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 18)])
        model.ir_version = 9
        path = tmp_path / "id.onnx"
        path.write_bytes(model.SerializeToString())

        runtime = OnnxRuntime(tmp_path)
        call = Invocation(
            warrant_for("onnx", "file://id.onnx", digest_of(path), ["a"],
                        outputs=("score",), entry={"input_names": ["wrong_name"]}),
            {"a": 1.0})
        with pytest.raises(WarrantError) as exc:
            runtime.invoke(call)
        assert exc.value.code == "input_not_in_graph"
        assert "does not match its artifact" in exc.value.remediation


class TestThroughTheWholeChain:
    """A PMML scorecard scored through a resolved warrant, end to end."""

    def test_a_registered_pmml_model_scores_through_a_warrant(
            self, tmp_path, repos, registry, evidence, a_model, kernel_spec,
            contract_spec):
        from core.execution import CaptiveEngine, WarrantService
        from tests.conftest import URN

        path = tmp_path / "sb.pmml"
        path.write_text(SCORECARD)
        digest = digest_of(path)

        kernel_spec["runtime"] = "pmml"
        kernel_spec["entry"] = {"document": "sb.pmml", "model_name": "SB",
                                "pmml_version": "4.4"}
        kernel_spec["input_schema"] = [
            {"name": "dscr", "dtype": "float", "minimum": -5, "maximum": 20},
            {"name": "months_on_book", "dtype": "float"},
            {"name": "segment", "dtype": "string"}]
        registry.create_version(URN, "4.0.0", kernel_spec, contract_spec,
                                artifact_digest=digest,
                                artifact_uri="file://sb.pmml")
        registry.approve_version(URN, "4.0.0")
        registry.move_alias(URN, "prod", "champion", "4.0.0")

        warrants = WarrantService(repos["warrants"], registry, evidence, jitter_pct=0)
        warrants.issue(URN, "prod", "svc/pricing", "origination_decision")
        engine = CaptiveEngine(warrants, artifact_dir=tmp_path)

        assert {d["runtime"] for d in engine.implements()} >= {"pmml", "onnx"}
        result = engine.execute(URN, "prod", "svc/pricing", "origination_decision",
                                {"dscr": 2.0, "months_on_book": 36,
                                 "segment": "retail"})
        assert 0.0 < result.prediction["pd_12m"] < 1.0
        assert result.boundary_ok and result.model_urn == URN

    def test_the_boundary_is_checked_before_the_artifact_is_touched(
            self, tmp_path, repos, registry, evidence, a_model, kernel_spec,
            contract_spec):
        """No artifact should load on an authorisation that was never valid."""
        from core.execution import CaptiveEngine, WarrantService
        from tests.conftest import URN

        kernel_spec["runtime"] = "pmml"
        kernel_spec["entry"] = {"document": "absent.pmml", "model_name": "X",
                                "pmml_version": "4.4"}
        registry.create_version(URN, "5.0.0", kernel_spec, contract_spec,
                                artifact_digest="sha256:whatever")
        registry.approve_version(URN, "5.0.0")
        registry.move_alias(URN, "prod", "champion", "5.0.0")
        warrants = WarrantService(repos["warrants"], registry, evidence, jitter_pct=0)
        warrants.issue(URN, "prod", "svc/pricing", "origination_decision")
        engine = CaptiveEngine(warrants, artifact_dir=tmp_path)

        with pytest.raises(WarrantError) as exc:
            engine.execute(URN, "prod", "svc/pricing", "origination_decision",
                           {"dscr": 99.0})
        assert exc.value.code == "boundary_violation", \
            "refused on the boundary, not on the missing artifact"


class TestTheArtifactRootIsADirectoryNotAPrefix:
    """A warrant is a document from elsewhere, and a path inside it is the least
    trustworthy thing in it."""

    def _call(self, uri):
        return Invocation({"realisation": {"artifact": {"uri": uri}}}, {})

    def test_a_sibling_whose_name_extends_the_root_is_refused(self, tmp_path):
        """'/x/artifacts-backup' begins with '/x/artifacts' and is not inside it.
        A string prefix admitted it; is_relative_to does not."""
        from core.execution.runtimes.base import resolve_path
        root = tmp_path / "artifacts"
        root.mkdir()
        sibling = tmp_path / "artifacts-backup"
        sibling.mkdir()
        (sibling / "model.onnx").write_bytes(b"not ours")
        with pytest.raises(WarrantError) as exc:
            resolve_path(self._call("file://../artifacts-backup/model.onnx"), root)
        assert exc.value.code == "artifact_outside_root"

    def test_a_traversal_out_of_the_root_is_refused(self, tmp_path):
        from core.execution.runtimes.base import resolve_path
        root = tmp_path / "artifacts"
        root.mkdir()
        (tmp_path / "secret.onnx").write_bytes(b"not ours")
        with pytest.raises(WarrantError) as exc:
            resolve_path(self._call("file://../secret.onnx"), root)
        assert exc.value.code == "artifact_outside_root"

    def test_an_artifact_inside_the_root_is_located(self, tmp_path):
        from core.execution.runtimes.base import resolve_path
        root = tmp_path / "artifacts"
        (root / "credit").mkdir(parents=True)
        target = root / "credit" / "pd.onnx"
        target.write_bytes(b"ours")
        assert resolve_path(self._call("file://credit/pd.onnx"), root) == target
