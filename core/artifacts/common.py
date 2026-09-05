"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The vocabulary of stored model artifacts.
"""
from __future__ import annotations

from typing import Dict, Tuple

# Formats the platform will store and name. The list is closed because an
# artifact's format decides how it is loaded, and "we will work it out at load
# time" is how a pickle gets deserialised in a control plane.
ONNX, PMML, SAFETENSORS, TORCHSCRIPT = "onnx", "pmml", "safetensors", "torchscript"
PFA, JSON_MODEL, TARBALL, GGUF = "pfa", "json", "tar", "gguf"

FORMATS: Tuple[str, ...] = (ONNX, PMML, SAFETENSORS, TORCHSCRIPT, PFA,
                            JSON_MODEL, TARBALL, GGUF)

FORMAT_MEANING: Dict[str, str] = {
    ONNX: "an ONNX graph. Portable, typed, and loadable without the framework "
          "that produced it",
    PMML: "PMML. Verbose and old and readable by anything",
    SAFETENSORS: "safetensors. Weights only, with no code path on load, which "
                 "is the reason to prefer it over a pickle",
    TORCHSCRIPT: "a TorchScript archive. Carries code, so it loads in the "
                 "sandbox and nowhere else",
    PFA: "a PFA document",
    JSON_MODEL: "a JSON document: a rule set, a scorecard, a configuration",
    TARBALL: "an archive. Used for a model that is several files — a tokenizer "
             "beside its weights, an adapter beside its base",
    GGUF: "a GGUF file. Quantised weights for local inference",
}

# Formats whose load path executes code the platform did not write. They are
# accepted and they run in the sandbox; the distinction is recorded so nobody
# has to remember which is which.
EXECUTES_ON_LOAD: frozenset = frozenset({TORCHSCRIPT, TARBALL})

# 8 GiB. Large enough for the weights of anything a bank runs on its own
# hardware, and small enough that somebody has to think before putting a
# foundation model checkpoint in a governance platform.
MAX_BYTES = 8 * 1024 * 1024 * 1024

# Read and hashed in chunks, because a model file does not fit in memory twice
# and a governance platform should not be the process that discovers this.
CHUNK = 4 * 1024 * 1024


class ArtifactError(RuntimeError):
    """An artifact operation was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}
