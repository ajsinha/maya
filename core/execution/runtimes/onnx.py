"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

ONNX graphs.

The format most of a bank's machine-learned estate can be exported to, and the
reason it is worth supporting directly: an ONNX graph is a self-contained,
digestible artifact, which is exactly what the rest of the platform assumes a
model is.

Sessions are cached by artifact digest rather than by path. Two versions that
happen to share a file share a session; a version whose file changed gets a new
one — and since the digest is verified against the warrant before anything is
loaded, a changed file is refused rather than cached.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from core.execution.errors import WarrantError
from core.execution.runtimes.base import Invocation, resolve_path, verify_artifact
import logging

from core.log import get_logger, swallowed

logger = get_logger(__name__)


class OnnxRuntime:
    """Runs an ONNX graph through onnxruntime."""

    key = "onnx"

    def __init__(self, artifact_dir: Optional[Path] = None):
        self.artifact_dir = Path(artifact_dir) if artifact_dir else None
        self._sessions: Dict[str, Any] = {}

    def available(self) -> Optional[str]:
        try:
            import onnxruntime  # noqa: F401
        except ImportError as exc:
            swallowed(logger, exc, "the onnx runtime is not usable here",
                      detail="warrants naming it will be refused with the reason",
                      level=logging.DEBUG)
            return (f"onnxruntime is not installed ({exc}); "
                    "pip install onnxruntime")
        return None

    def invoke(self, call: Invocation) -> Any:
        if (why := self.available()):
            raise WarrantError("runtime_unavailable", why,
                               "install the package, or route this warrant to an "
                               "engine that has it")
        path = resolve_path(call, self.artifact_dir)
        digest = call.artifact.get("digest")
        verify_artifact(path, digest)
        session = self._session(path, digest)
        return self._run(session, call)

    def _session(self, path: Path, digest: str):
        import onnxruntime
        if digest not in self._sessions:
            logger.info("loading ONNX graph %s", path.name)
            self._sessions[digest] = onnxruntime.InferenceSession(
                str(path), providers=["CPUExecutionProvider"])
        return self._sessions[digest]

    @staticmethod
    def _run(session, call: Invocation) -> Any:
        import numpy as np
        wanted = {i.name: i for i in session.get_inputs()}
        entry_names = call.entry.get("input_names") or list(wanted)

        feeds: Dict[str, Any] = {}
        for name in entry_names:
            spec = wanted.get(name)
            if spec is None:
                raise WarrantError(
                    "input_not_in_graph",
                    f"the warrant names an input '{name}' the graph does not have "
                    f"(it has {', '.join(wanted)})",
                    "the version's entry block does not match its artifact")
            # A single named tensor: take the io_contract's fields in order.
            fields = [f["name"] for f in
                      (call.warrant.get("io_contract") or {}).get("input_schema", [])]
            missing = [f for f in fields if f not in call.inputs]
            if missing:
                raise WarrantError(
                    "missing_inputs",
                    f"the call is missing {', '.join(missing)}",
                    "supply every field named in the warrant's input schema")
            row = [float(call.inputs[f]) for f in fields]
            feeds[name] = np.array([row], dtype=np.float32)

        outputs = session.run(None, feeds)
        names = call.output_names or [o.name for o in session.get_outputs()]
        flat = [_scalar(o) for o in outputs]
        return dict(zip(names, flat)) if len(names) == len(flat) else flat[0]


def _scalar(value):
    """One prediction from whatever shape the graph returned."""
    try:
        flattened = value.reshape(-1)
        return flattened[0].item() if flattened.size else None
    except AttributeError as exc:
        # Not an ndarray: some graphs return a plain sequence, or a scalar.
        swallowed(logger, exc, "graph output is not an array",
                  detail=f"reading it as {type(value).__name__}",
                  level=logging.DEBUG)
        return value[0] if isinstance(value, (list, tuple)) and value else value
