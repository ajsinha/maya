"""
Fitted parameters read out of the files training tools actually write (§9.3): a NumPy
`.npz`, a pickle, an ONNX graph. MAYA accepted JSON only, so the values had to be retyped,
which is where transcription errors come from. A pickle is a program, so it is scanned
before it is loaded and refused if it would import or construct anything.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import io
import json
import pickle

import numpy as np
import pytest

from maya.core import parameters
from maya.core.backends import has_module
from maya.core.errors import CapabilityRefused, ValidationFailed


def test_json_npz_and_a_data_only_pickle_all_give_the_same_values():
    expected = {"a": 2.0, "b": [1.0, 2.0, 3.0]}
    as_json = json.dumps(expected).encode()
    buf = io.BytesIO()
    np.savez(buf, a=np.float64(2.0), b=np.array([1.0, 2.0, 3.0]))
    as_pickle = pickle.dumps(expected, protocol=5)
    assert parameters.read(as_json, "json") == expected
    assert parameters.read(buf.getvalue(), "npz") == expected
    assert parameters.read(as_pickle, "pickle") == expected


def test_a_pickle_that_would_run_code_is_refused_and_names_the_opcode():
    class Evil:
        def __reduce__(self):
            import os

            return (os.system, ("echo pwned",))

    hostile = pickle.dumps({"a": Evil()})
    with pytest.raises(ValidationFailed) as exc:
        parameters.read(hostile, "pickle")
    assert "would run code" in exc.value.message
    assert exc.value.context["opcode"] in parameters.FORBIDDEN_OPCODES
    # a pickle of a numpy array also imports, so it is refused with the same message
    with pytest.raises(ValidationFailed, match="would run code"):
        parameters.read(pickle.dumps({"a": np.array([1.0])}), "pickle")


def test_malformed_files_are_refused_by_name():
    for data, fmt, message in [
        (b"not json", "json", "Not readable JSON"),
        (b"PK\x03\x04 junk", "npz", "Not a readable .npz"),
        (b"\x80\x05 truncated", "pickle", "Not a readable pickle"),
    ]:
        with pytest.raises(ValidationFailed, match=message):
            parameters.read(data, fmt)
    with pytest.raises(ValidationFailed, match="format must be one of"):
        parameters.read(b"{}", "h5")


def test_a_file_that_is_not_named_values_or_is_too_big_is_refused():
    with pytest.raises(ValidationFailed, match="Parameters are named values"):
        parameters.read(json.dumps([1, 2, 3]).encode(), "json")
    buf = io.BytesIO()
    np.savez(buf, huge=np.zeros(parameters.MAX_ELEMENTS + 1))
    with pytest.raises(ValidationFailed, match="that is a dataset"):
        parameters.read(buf.getvalue(), "npz")


def test_onnx_is_read_when_the_package_is_there_and_refused_by_name_when_not():
    if not has_module("onnx"):
        with pytest.raises(CapabilityRefused, match="needs the onnx package"):
            parameters.read(b"anything", "onnx")
        return
    import onnx
    from onnx import helper, numpy_helper

    tensor = numpy_helper.from_array(np.array([[1.0, 2.0]], dtype="float32"), name="W")
    graph = helper.make_graph([], "fit", [], [], initializer=[tensor])
    model = helper.make_model(graph)
    assert parameters.read(model.SerializeToString(), "onnx") == {"W": [[1.0, 2.0]]}
    empty = helper.make_model(helper.make_graph([], "empty", [], []))
    with pytest.raises(ValidationFailed, match="no initializers"):
        parameters.read(empty.SerializeToString(), "onnx")
    del onnx


def test_the_cli_picks_the_format_from_the_file_name():
    from maya.cli.__main__ import _format_of
    from maya.core.errors import MayaError

    assert _format_of("fit.npz") == "npz"
    assert _format_of("fit.pkl") == "pickle" and _format_of("fit.pickle") == "pickle"
    assert _format_of("graph.onnx") == "onnx" and _format_of("v.json") == "json"
    with pytest.raises(MayaError, match="Cannot tell the parameter format"):
        _format_of("fit.h5")
