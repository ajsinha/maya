"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Runtimes: how the captive engine turns a realisation into an answer.

Three are implemented — registered Python callables for development, ONNX
graphs, and the regression and scorecard subset of PMML evaluated natively
rather than through a JVM. Everything else the grammar names is refused by name.

Every runtime that loads an artifact verifies its digest against the warrant
first. That is the point at which the whole chain either does or does not
describe the bytes about to run.
"""
from core.execution.runtimes.base import Invocation, Runtime, digest_of, verify_artifact
from core.execution.runtimes.callables import CallableRuntime
from core.execution.runtimes.onnx import OnnxRuntime
from core.execution.runtimes.pmml import PmmlRuntime
from core.execution.runtimes.registry import RuntimeRegistry

__all__ = ["RuntimeRegistry", "Runtime", "Invocation", "CallableRuntime",
           "OnnxRuntime", "PmmlRuntime", "digest_of", "verify_artifact"]
