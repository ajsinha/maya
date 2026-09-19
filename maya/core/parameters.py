"""
Reading fitted parameters out of the files people actually train with (§9.3).

MAYA's parameter sets are JSON: names to numbers, which is what a warrant can hash,
diff and show a reviewer. But a fit ends in whatever the training tool wrote — a NumPy
`.npz`, a pickle, an ONNX graph — and retyping those by hand is where transcription errors
come from. This module turns each into the same JSON, refusing what it cannot read safely:

* **npz** — read with `allow_pickle=False`, so an archive cannot execute anything.
* **pickle** — **scanned before it is loaded**, and refused if it would import or construct
  anything. A pickle is a program; the only ones accepted here are the ones that build
  plain data. A refusal names the opcode that caused it.
* **onnx** — the graph's initializers (its fitted tensors), when the `onnx` package is
  installed. Without it, MAYA says so rather than guessing.

Arrays become nested lists, scalars become numbers, and anything else is refused by name.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import io
import json
import pickletools
from typing import Any

from maya.core.errors import CapabilityRefused, ValidationFailed

FORMATS = ("json", "npz", "pickle", "onnx")

# A pickle that only builds data needs none of these. Each either imports a name or calls
# something, which is the whole of how a hostile pickle works.
FORBIDDEN_OPCODES = {
    "GLOBAL",
    "STACK_GLOBAL",
    "REDUCE",
    "BUILD",
    "INST",
    "OBJ",
    "NEWOBJ",
    "NEWOBJ_EX",
    "EXT1",
    "EXT2",
    "EXT4",
    "PERSID",
    "BINPERSID",
}
MAX_ELEMENTS = 1_000_000  # a parameter set is fitted values, not a dataset


def read(data: bytes, fmt: str) -> dict[str, Any]:
    """Fitted parameters from ``data``, as the JSON a parameter set stores."""
    if fmt not in FORMATS:
        raise ValidationFailed(f"Parameter format must be one of {', '.join(FORMATS)}", format=fmt)
    values = {"json": _json, "npz": _npz, "pickle": _pickle, "onnx": _onnx}[fmt](data)
    return _plain(values)


def _json(data: bytes) -> Any:
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationFailed(f"Not readable JSON parameters: {exc}") from exc


def _npz(data: bytes) -> dict[str, Any]:
    import numpy as np

    try:
        with np.load(io.BytesIO(data), allow_pickle=False) as archive:
            return {name: archive[name] for name in archive.files}
    except Exception as exc:  # noqa: BLE001 - numpy raises several types for a bad archive
        raise ValidationFailed(f"Not a readable .npz archive: {exc}") from exc


def _pickle(data: bytes) -> Any:
    """A pickle, scanned first. Anything that would import or construct is refused."""
    try:
        for opcode, _, _ in pickletools.genops(data):
            if opcode.name in FORBIDDEN_OPCODES:
                raise ValidationFailed(
                    f"This pickle would run code, not just carry data: it uses "
                    f"{opcode.name}. Save the fitted values as .npz or JSON instead.",
                    opcode=opcode.name,
                )
    except ValidationFailed:
        raise
    except Exception as exc:  # noqa: BLE001 - a truncated or malformed pickle
        raise ValidationFailed(f"Not a readable pickle: {exc}") from exc
    import pickle  # the scan above is what makes this safe

    # every opcode that imports or constructs was refused by the scan above, so what
    # remains builds plain data; the scan is tested against a hostile pickle
    return pickle.loads(data)  # noqa: S301  # nosec B301 - scanned above


def _onnx(data: bytes) -> dict[str, Any]:
    from maya.core.backends import has_module

    if not has_module("onnx"):
        raise CapabilityRefused(
            "Reading ONNX parameters needs the onnx package (pip install onnx); "
            "export the fitted values as .npz or JSON instead"
        )
    import onnx
    from onnx import numpy_helper

    try:
        model = onnx.load_from_string(data)
    except Exception as exc:  # noqa: BLE001 - onnx raises its own parse errors
        raise ValidationFailed(f"Not a readable ONNX model: {exc}") from exc
    tensors = {t.name: numpy_helper.to_array(t) for t in model.graph.initializer}
    if not tensors:
        raise ValidationFailed(
            "This ONNX graph carries no initializers, so it holds no fitted parameters"
        )
    return tensors


def _plain(values: Any) -> dict[str, Any]:
    """Names to JSON-safe numbers and lists, with a size cap and a named refusal."""
    if not isinstance(values, dict):
        raise ValidationFailed(
            f"Parameters are named values; this file holds a {type(values).__name__}"
        )
    out: dict[str, Any] = {}
    total = 0
    for name, value in values.items():
        if not isinstance(name, str):
            raise ValidationFailed(f"Parameter names are text; found {type(name).__name__}")
        plain, count = _one(name, value)
        total += count
        if total > MAX_ELEMENTS:
            raise ValidationFailed(
                f"These parameters hold more than {MAX_ELEMENTS} numbers; that is a dataset, "
                "not a fitted parameter set"
            )
        out[name] = plain
    return out


def _one(name: str, value: Any) -> tuple[Any, int]:
    if isinstance(value, bool | int | float | str) or value is None:
        return value, 1
    if isinstance(value, dict | list | tuple):
        as_list = list(value.values()) if isinstance(value, dict) else list(value)
        counted = [_one(name, v) for v in as_list]
        plain = [p for p, _ in counted]
        if isinstance(value, dict):
            return dict(zip(value.keys(), plain)), sum(c for _, c in counted)
        return plain, sum(c for _, c in counted)
    tolist = getattr(value, "tolist", None)
    if tolist is not None:  # a numpy array or scalar
        plain = tolist()
        return plain, int(getattr(value, "size", 1))
    raise ValidationFailed(
        f"Parameter '{name}' is a {type(value).__name__}, which MAYA cannot store as a "
        "number or a list of numbers"
    )


__all__ = ["FORBIDDEN_OPCODES", "FORMATS", "MAX_ELEMENTS", "read"]
