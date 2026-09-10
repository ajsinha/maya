"""What an artifact says about itself, read from the bytes rather than declared.

Everything the register held about an artifact's shape came from whoever
uploaded it. The digest was checked and the size measured; the input schema was
taken on trust, and the first thing that compared it against the file was the
execution engine, at invoke time, in production — by which point the version had
been approved, aliased and warranted.
"""
from __future__ import annotations

import importlib.util
import json
import struct

import pytest

from core.artifacts.introspect import disagreement, introspect


def _onnx_available() -> bool:
    return importlib.util.find_spec("onnx") is not None


@pytest.fixture
def graph(tmp_path):
    """A real ONNX graph with one input four wide, built here."""
    if not _onnx_available():
        pytest.skip("the `onnx` authoring library is not installed")
    from onnx import TensorProto, helper

    node = helper.make_node("MatMul", ["features", "w"], ["score"])
    weights = helper.make_tensor("w", TensorProto.FLOAT, [4, 1],
                                 [0.5, -0.25, 0.1, 0.0])
    g = helper.make_graph(
        [node], "scorer",
        [helper.make_tensor_value_info("features", TensorProto.FLOAT, [1, 4])],
        [helper.make_tensor_value_info("score", TensorProto.FLOAT, [1, 1])],
        initializer=[weights])
    model = helper.make_model(g, opset_imports=[helper.make_opsetid("", 18)])
    model.ir_version = 9
    path = tmp_path / "scorer.onnx"
    path.write_bytes(model.SerializeToString())
    return path


class TestReadingAGraph:
    def test_it_reads_the_shape_the_opset_and_the_parameters(self, graph):
        facts = introspect(graph, "onnx")
        assert facts["read"] is True
        assert facts["opset"]["ai.onnx"] == 18
        assert facts["inputs"][0]["shape"] == [1, 4]
        assert facts["parameters"] == 4, "counted from the initializers"
        assert facts["graph_name"] == "scorer"

    def test_it_records_which_library_read_it(self, graph):
        """`onnxruntime` is a MAYA dependency and `onnx` is not, so the answer
        says which effort it made rather than pretending they are the same."""
        assert introspect(graph, "onnx")["read_with"] in ("onnx", "onnxruntime")


class TestWhatItWillNotRead:
    @pytest.mark.parametrize("fmt", ["torchscript", "tar"])
    def test_code_formats_are_not_opened(self, tmp_path, fmt):
        """The platform's whole position is that loading an artifact is a
        decision, and an introspector that quietly imported one would be
        making it."""
        path = tmp_path / "thing"
        path.write_bytes(b"not really anything")
        facts = introspect(path, fmt)
        assert facts["read"] is False
        assert "would mean loading it" in facts["why"]

    def test_a_malformed_artifact_does_not_fail_the_upload(self, tmp_path):
        """The bytes are still the evidence of what somebody tried to register,
        and an introspection that could not run is a fact recorded as one."""
        path = tmp_path / "broken.onnx"
        path.write_bytes(b"this is not a protobuf")
        facts = introspect(path, "onnx")
        assert facts["read"] is False and facts["why"]


class TestSafetensorsNeedsNoDependency:
    def test_the_header_alone_gives_the_parameter_count(self, tmp_path):
        header = {"a": {"dtype": "F32", "shape": [2, 3], "data_offsets": [0, 24]},
                  "__metadata__": {"format": "pt"}}
        blob = json.dumps(header).encode()
        path = tmp_path / "w.safetensors"
        path.write_bytes(struct.pack("<Q", len(blob)) + blob + b"\x00" * 24)
        facts = introspect(path, "safetensors")
        assert facts["read"] and facts["tensors"] == 1
        assert facts["parameters"] == 6
        assert facts["metadata"]["format"] == "pt"


class TestCheckingADeclaration:
    """Arity and names, not types. MAYA's ONNX runtime builds one tensor from
    the declared schema in order, so a name-by-name comparison would refuse
    every model this platform actually runs."""

    def test_a_matching_arity_is_no_disagreement(self, graph):
        facts = introspect(graph, "onnx")
        declared = [{"name": n} for n in ("a", "b", "c", "d")]
        assert disagreement(declared, facts) is None

    def test_a_wrong_arity_is_caught_with_both_numbers(self, graph):
        facts = introspect(graph, "onnx")
        declared = [{"name": n} for n in ("a", "b", "c", "d", "e")]
        problem = disagreement(declared, facts)
        assert problem and "5 input(s)" in problem and "4 wide" in problem

    def test_an_unreadable_artifact_is_not_evidence_of_a_mismatch(self):
        """Refusing on one would make an optional dependency load-bearing."""
        assert disagreement([{"name": "a"}], {"read": False}) is None

    def test_a_version_declaring_no_inputs_is_not_checked(self, graph):
        assert disagreement([], introspect(graph, "onnx")) is None

    def test_a_dynamic_dimension_says_nothing_either_way(self):
        """A batch axis is a name rather than a number, and treating it as zero
        would make every exported model disagree with itself."""
        facts = {"read": True,
                 "inputs": [{"name": "x", "shape": ["batch", "features"]}]}
        assert disagreement([{"name": "a"}, {"name": "b"}], facts) is None
