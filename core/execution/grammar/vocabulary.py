"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The warrant grammar's vocabulary.

Every model a bank runs — a Black-Scholes closed form, a Hull-White calibration,
a gradient-boosted PD model, a logistic scorecard, a prompt bundle over a
foundation model, an agent with tools, a credit policy rulebook, a spreadsheet,
a vendor black box — differs along exactly **four independent axes**:

  1. **How the parameter object is inhabited** — ``parameters.kind``
  2. **How the kernel becomes runnable** — ``realisation.runtime``
  3. **What is being asked of it** — ``operation.verb``
  4. **Where its data comes from** — ``data.*.binding``

The grammar is the **product** of those four vocabularies, not a union of special
cases. That is what makes it general: QuantLib pricing is
``(none, quantlib, score, market_data)``; a Hull-White calibration is the same
runtime at ``(calibration_set, quantlib, fit, market_data)``; an XGBoost PD model
is ``(learned_weights, onnx, score, feature_namespace)``; an LLM summariser is
``(llm_configuration, llm.prompt, generate, request)``. One structure, different
coordinates.

And it extends the right way. A new model technology is a new **value** in one
vocabulary — usually a runtime — not a new section, not a new document type, and
not a change to anything that already works.
"""
from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

WARRANT_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Axis 3 — the operation. What is being asked of the morphism f : P (x) X -> Y.
# ---------------------------------------------------------------------------
SCORE = "score"          # evaluate f on inputs
FIT = "fit"              # inhabit P from data; the procedure comes from the version
VALIDATE = "validate"    # run the test catalogue against it
BACKTEST = "backtest"    # score over history and compare against outcomes
EXPLAIN = "explain"      # attributions for a scored instance
SIMULATE = "simulate"    # sample from the output distribution
STRESS = "stress"        # score under prescribed scenarios
OPTIMISE = "optimise"    # solve the decision problem the model expresses
GENERATE = "generate"    # produce text or structured output
MONITOR = "monitor"      # compute monitoring statistics

VERBS: Tuple[str, ...] = (SCORE, FIT, VALIDATE, BACKTEST, EXPLAIN, SIMULATE,
                          STRESS, OPTIMISE, GENERATE, MONITOR)

VERB_MEANING: Dict[str, str] = {
    SCORE: "evaluate the model on supplied inputs",
    FIT: "inhabit the parameter object from data — calibrate, estimate, train, "
         "configure, elicit or author, whichever this version declares",
    VALIDATE: "run the registered test catalogue against this version",
    BACKTEST: "score a historical window and compare against realised outcomes",
    EXPLAIN: "produce attributions for a scored instance",
    SIMULATE: "draw from the model's output distribution",
    STRESS: "score under prescribed scenarios rather than observed inputs",
    OPTIMISE: "solve the decision problem the model expresses",
    GENERATE: "produce text or structured output",
    MONITOR: "compute the statistics a monitor asks for",
}

# ---------------------------------------------------------------------------
# Axis 2 — the realisation. How a kernel becomes something an engine can invoke.
# Each runtime declares the keys its ``entry`` block must carry; an engine that
# understands the runtime needs nothing further to locate and call the artifact.
# ---------------------------------------------------------------------------
RUNTIME_ENTRY: Dict[str, Tuple[str, ...]] = {
    # --- code -------------------------------------------------------------
    "python.callable": ("module", "attr"),
    "container": ("image",),
    "rest": ("endpoint",),
    # --- portable model formats -------------------------------------------
    "onnx": ("graph",),
    "pmml": ("document",),
    "pfa": ("document",),
    # --- quantitative libraries -------------------------------------------
    "quantlib": ("instrument", "pricing_engine"),
    "solver": ("formulation", "solver"),
    # --- statistical platforms --------------------------------------------
    "sas": ("program",),
    "r": ("script",),
    "matlab": ("function",),
    # --- declarative ------------------------------------------------------
    "sql": ("statement", "dialect"),
    "spreadsheet": ("workbook", "sheet", "input_cells", "output_cells"),
    "rules": ("ruleset", "engine"),
    # --- generative -------------------------------------------------------
    "llm.prompt": ("provider", "base_model", "prompt_digest"),
    "llm.agent": ("provider", "base_model", "graph", "max_steps"),
    # --- the honest one ---------------------------------------------------
    # MAYA describes the model but cannot locate an artifact: a vendor black
    # box under licence, or a model that runs somewhere we do not reach. The
    # warrant carries governance and no execution.
    "descriptor_only": (),
}
RUNTIMES: Tuple[str, ...] = tuple(RUNTIME_ENTRY)

# Runtimes whose output is not reproducible from inputs alone unless pinned.
STOCHASTIC_RUNTIMES: FrozenSet[str] = frozenset({"llm.prompt", "llm.agent"})

# ---------------------------------------------------------------------------
# Axis 4 — data bindings. Where X comes from, and where Y goes.
# ---------------------------------------------------------------------------
BINDING_KEYS: Dict[str, Tuple[str, ...]] = {
    "inline": ("values",),                       # carried in the warrant itself
    "request": (),                               # supplied by the caller at run time
    "feature_namespace": ("namespace",),         # a pinned feature view version
    "dataset_snapshot": ("snapshot",),           # a digested, PIT-verified dataset
    "delta_table": ("table",),
    "sql_query": ("statement", "dialect"),
    "stream": ("topic",),
    "market_data": ("curve_set", "as_of"),       # what a pricing model reads
    "document_corpus": ("corpus", "revision"),   # what a RAG pipeline retrieves
    "scenario_set": ("scenarios",),              # what a stress run applies
    "artifact": ("uri",),
}
BINDINGS: Tuple[str, ...] = tuple(BINDING_KEYS)

# Bindings that can answer "what was known at time t". Training data must use
# one of these, because a training set assembled from a source that cannot be
# read as-of cannot be shown point-in-time correct.
BITEMPORAL_BINDINGS: FrozenSet[str] = frozenset(
    {"feature_namespace", "dataset_snapshot"})

SINKS: Tuple[str, ...] = ("response", "delta_table", "stream", "artifact",
                          "parameter_object", "evidence")

# ---------------------------------------------------------------------------
# The document's sections. Each answers exactly one question.
# ---------------------------------------------------------------------------
SECTIONS: Dict[str, str] = {
    "subject": "which model and version this is about",
    "operation": "what is being asked of it",
    "parameters": "where the parameter object comes from",
    "realisation": "how to obtain and invoke the artifact",
    "data": "where the inputs come from and where the outputs go",
    "io_contract": "the input and output schemas",
    "constraints": "the operating boundary and the resource limits",
    "authority": "who may do this, for what, until when",
    "governance": "the state of the record at the moment of issue",
    "signature": "integrity",
}
REQUIRED_SECTIONS: Tuple[str, ...] = tuple(SECTIONS)
