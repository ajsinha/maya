"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Runtimes: how the captive engine turns a realisation into an answer.

Seven are implemented — registered Python callables for development, ONNX
graphs, the regression and scorecard subset of PMML evaluated natively rather
than through a JVM, a QuantLib runtime for the valuations that have no parameter
object to fit, an estimator that inhabits one, a rule engine, and a **formula**
runtime where the version's own JSON is the model. Everything else the grammar
names is refused by name.

The formula runtime is the one with no artifact at all: `entry.expression` is
the whole of `f`, in the language this platform already parses. It closes the
gap the taxonomy had — the hundreds of small closed-form models a bank runs,
which previously had to be `descriptor_only` and unrunnable, or wrapped in a
container to turn four lines of arithmetic into an artifact somebody signs.

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
from core.execution.runtimes.formula import FormulaRuntime
from core.execution.runtimes.callables import CallableRuntime
from core.execution.runtimes.onnx import OnnxRuntime
from core.execution.runtimes.pmml import PmmlRuntime
from core.execution.runtimes.quantlib import QuantLibRuntime
from core.execution.runtimes.registry import RuntimeRegistry
from core.execution.runtimes.rules import RulesRuntime

__all__ = [
           "CallableRuntime",
           "EstimatorRuntime",
           "FormulaRuntime",
           "Invocation",
           "OnnxRuntime",
           "PmmlRuntime",
           "QuantLibRuntime",
           "RulesRuntime",
           "Runtime",
           "RuntimeRegistry",
           "digest_of",
           "verify_artifact",
]
