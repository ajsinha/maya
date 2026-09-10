"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What an artifact says about itself, read from the bytes rather than declared.

Everything the register held about an artifact's shape came from the person who
uploaded it. The digest was checked, the size was measured, the format was
named — and then the input schema, the framework, the version of the library
that produced it were all taken on trust, and the first thing that compared them
against the file was the execution engine, at invoke time, in production.

That is the wrong place for the check twice over. It is late: a version whose
declared schema disagrees with its graph has already been approved, aliased and
warranted before anything notices. And it is narrow: the engine checks the one
thing it needs to make the call, so a graph produced by a library nobody
recorded, at an opset nothing supports, passes until the day it is run.

**What this reads and what it will not.** It reads structure — how many inputs a
graph takes, what they are called, what shape they are, which opset it needs,
which library produced it, how many parameters it carries. It does not execute
anything, and it does not read a format that would have to execute to be read:
a `torchscript` bundle and a `tar` are code, and introspecting them by loading
them would put the thing this platform refuses to do in the middle of an upload.
Those return what is knowable without opening them, and say so.

**Best-effort, and honest about which effort it made.** `onnxruntime` is a MAYA
dependency and `onnx` is not, so a graph is read through the runtime where the
authoring library is absent and the answer records `read_with` either way. A
field that could not be read is missing rather than guessed.
"""
from __future__ import annotations

import json
import logging
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.log import get_logger, swallowed

logger = get_logger(__name__)

#: Formats that would have to be executed, or as good as, to be read. Named
#: rather than attempted: the platform's whole position on artifacts is that
#: loading one is a decision, and an introspector that quietly imported a
#: torchscript bundle would be making it.
NOT_READ_WITHOUT_EXECUTING = ("torchscript", "tar")


def introspect(path: Path, fmt: str) -> Dict[str, Any]:
    """Everything the bytes will say about themselves, for this format."""
    try:
        if fmt == "onnx":
            return _onnx(path)
        if fmt == "safetensors":
            return _safetensors(path)
        if fmt in ("json", "pfa"):
            return _json(path)
        if fmt in NOT_READ_WITHOUT_EXECUTING:
            return {"read": False,
                    "why": f"a '{fmt}' artifact is code, and reading it would "
                           f"mean loading it. Nothing about an upload is worth "
                           f"executing an artifact for"}
    except Exception as exc:
        # A malformed artifact must not fail the upload. The bytes are still
        # worth storing — they are the evidence of what somebody tried to
        # register — and an introspection that could not run is a fact about
        # the artifact, recorded as one.
        swallowed(logger, exc, "could not introspect an artifact",
                  detail=f"format {fmt}; storing it anyway",
                  level=logging.WARNING)
        return {"read": False, "why": f"could not be read as {fmt}: {exc}"}
    return {"read": False, "why": f"nothing is extracted from '{fmt}' yet"}


# ------------------------------------------------------------------- ONNX
def _onnx(path: Path) -> Dict[str, Any]:
    """Opset, producer, and the graph's actual inputs and outputs.

    Tried with the authoring library first because it says more — the producer
    and the opset live in the model proto and not in the session — and through
    `onnxruntime` otherwise, which is a MAYA dependency and can still answer
    the question that matters most: how many inputs does this graph really
    take, and what are they called.
    """
    try:
        import onnx

        model = onnx.load(str(path), load_external_data=False)
        opsets = {(o.domain or "ai.onnx"): o.version
                  for o in model.opset_import}
        graph = model.graph
        parameters = sum(_numel(t.dims) for t in graph.initializer)
        return {
            "read": True, "read_with": "onnx",
            "graph_name": graph.name or None,
            "ir_version": model.ir_version,
            "opset": opsets,
            "producer": (f"{model.producer_name} {model.producer_version}".strip()
                         or None),
            "domain": model.domain or None,
            "inputs": [_value_info(v) for v in graph.input],
            "outputs": [_value_info(v) for v in graph.output],
            "nodes": len(graph.node),
            "initializers": len(graph.initializer),
            "parameters": parameters,
            # Where an exporter usually leaves hyperparameters, if anywhere.
            "metadata": {p.key: p.value for p in model.metadata_props} or None,
        }
    except ImportError as exc:
        swallowed(logger, exc, "read an ONNX graph through the runtime",
                  detail="the `onnx` authoring library is not installed, so "
                         "the opset and producer cannot be read; the runtime "
                         "still answers the shape",
                  level=logging.DEBUG)

    import onnxruntime

    session = onnxruntime.InferenceSession(
        str(path), providers=["CPUExecutionProvider"])
    meta = session.get_modelmeta()
    return {
        "read": True, "read_with": "onnxruntime",
        "graph_name": meta.graph_name or None,
        "producer": meta.producer_name or None,
        "domain": meta.domain or None,
        "inputs": [{"name": i.name, "dtype": i.type, "shape": list(i.shape)}
                   for i in session.get_inputs()],
        "outputs": [{"name": o.name, "dtype": o.type, "shape": list(o.shape)}
                    for o in session.get_outputs()],
        "metadata": dict(meta.custom_metadata_map) or None,
        # Said rather than omitted: a reader should know the difference between
        # "this graph declares no opset" and "nothing here could read one".
        "not_read": ["opset", "ir_version", "parameters"],
        "why_not_read": "the opset and the parameter count live in the model "
                        "proto rather than in a session; install the `onnx` "
                        "authoring library to have them",
    }


def _value_info(value) -> Dict[str, Any]:
    tensor = value.type.tensor_type
    shape = []
    for dim in tensor.shape.dim:
        # A dynamic dimension is a name, not a number, and reporting it as 0
        # would make a batch axis look like an empty one.
        shape.append(dim.dim_value if dim.HasField("dim_value")
                     else (dim.dim_param or None))
    return {"name": value.name, "elem_type": tensor.elem_type, "shape": shape}


def _numel(dims) -> int:
    total = 1
    for dim in dims:
        total *= int(dim)
    return total if dims else 0


# ----------------------------------------------------------- safetensors
def _safetensors(path: Path) -> Dict[str, Any]:
    """Tensor names, dtypes and shapes, from the header alone.

    A safetensors file begins with an 8-byte little-endian length and then that
    many bytes of JSON. No dependency and no load: the whole point of the format
    is that its shape is readable without touching the weights, and a parameter
    count from the header is exact.
    """
    with path.open("rb") as handle:
        (length,) = struct.unpack("<Q", handle.read(8))
        header = json.loads(handle.read(length).decode("utf-8"))
    tensors = {k: v for k, v in header.items() if k != "__metadata__"}
    parameters = 0
    for spec in tensors.values():
        count = 1
        for dim in spec.get("shape", []):
            count *= int(dim)
        parameters += count if spec.get("shape") else 0
    return {"read": True, "read_with": "safetensors header",
            "tensors": len(tensors), "parameters": parameters,
            "dtypes": sorted({str(v.get("dtype")) for v in tensors.values()}),
            "metadata": header.get("__metadata__") or None}


def _json(path: Path) -> Dict[str, Any]:
    with path.open("rb") as handle:
        parsed = json.loads(handle.read().decode("utf-8"))
    return {"read": True, "read_with": "json",
            "top_level_keys": sorted(parsed)[:24] if isinstance(parsed, dict)
                              else None,
            "kind": type(parsed).__name__}


# ------------------------------------------------- checking a declaration
def disagreement(declared_inputs: List[Dict[str, Any]],
                 facts: Dict[str, Any]) -> Optional[str]:
    """Whether a version's declared input schema can be true of this artifact.

    Deliberately a check on ARITY and names rather than on types. MAYA's ONNX
    runtime builds one input tensor from the declared schema in order, so a
    four-feature model is a graph with one input of width four — and a
    name-by-name comparison would refuse every model this platform actually
    runs. What can be checked without knowing the convention in use is the
    count, and the count is what catches the error that matters: a schema that
    declares five features for a graph that takes four.

    Returns the disagreement, or None. None is also the answer when the
    artifact could not be read — an unreadable artifact is not evidence of a
    mismatch, and refusing on it would make an optional dependency load-bearing.
    """
    if not facts.get("read") or not declared_inputs:
        return None
    graph_inputs = facts.get("inputs")
    if not graph_inputs:
        return None

    declared = len(declared_inputs)
    if len(graph_inputs) == 1:
        shape = graph_inputs[0].get("shape") or []
        # The single-tensor convention: the last dimension is the width, and a
        # dynamic one (a name rather than a number) says nothing either way.
        width = shape[-1] if shape else None
        if isinstance(width, int) and width > 0 and width != declared:
            return (f"the version declares {declared} input(s) and the graph's "
                    f"single input '{graph_inputs[0].get('name')}' is "
                    f"{width} wide. MAYA's ONNX runtime fills one tensor from "
                    f"the declared schema in order, so those two numbers are "
                    f"the same fact and disagreeing means one of them is wrong")
        return None

    names = {str(i.get("name")) for i in graph_inputs}
    declared_names = {str(i.get("name")) for i in declared_inputs}
    missing = sorted(declared_names - names)
    if missing:
        return (f"the version declares input(s) {', '.join(missing)} that the "
                f"graph does not have; it takes {', '.join(sorted(names))}")
    return None
