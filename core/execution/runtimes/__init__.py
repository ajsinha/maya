"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Runtimes: how the captive engine turns a realisation into an answer.

Five are implemented — registered Python callables for development, ONNX
graphs, the regression and scorecard subset of PMML evaluated natively rather
than through a JVM, a QuantLib runtime for the valuations that have no parameter
object to fit, and an estimator that inhabits one. Everything else the grammar
names is refused by name.

The estimator is the odd one out and deliberately so: every other runtime here
answers "what does this model say about this input", and it answers "what
parameters does this data imply". It is what closes the loop from a featureset
to an approved point of P.

Every runtime that loads an artifact verifies its digest against the warrant
first. That is the point at which the whole chain either does or does not
describe the bytes about to run.
"""
from core.execution.runtimes.base import Invocation, Runtime, digest_of, verify_artifact
from core.execution.runtimes.estimator import EstimatorRuntime
from core.execution.runtimes.callables import CallableRuntime
from core.execution.runtimes.onnx import OnnxRuntime
from core.execution.runtimes.pmml import PmmlRuntime
from core.execution.runtimes.quantlib import QuantLibRuntime
from core.execution.runtimes.registry import RuntimeRegistry

__all__ = ["RuntimeRegistry", "Runtime", "Invocation", "CallableRuntime",
           "OnnxRuntime", "PmmlRuntime", "QuantLibRuntime", "EstimatorRuntime",
           "digest_of", "verify_artifact"]
