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
    # The only runtime here whose job is to INHABIT a parameter object rather
    # than to read one. Its entry names the estimator family; what that family
    # needs beyond it -- a target and regressors, or a series -- is the family's
    # business and is checked when it runs.
    "estimator": ("family",),
    "solver": ("formulation", "solver"),
    # --- statistical platforms --------------------------------------------
    "sas": ("program",),
    "r": ("script",),
    "matlab": ("function",),
    # --- declarative ------------------------------------------------------
    # The one runtime with nothing to locate: the expression IS the model, in
    # the language this platform already parses for derived features. A
    # scorecard, a logistic link, a Basel risk weight — the small closed-form
    # models a bank has hundreds of — could previously be `descriptor_only`
    # (governed and unrunnable) or wrapped in a container, which turns four
    # lines of arithmetic into an artifact somebody has to build and sign.
    "formula": ("expression",),
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
#
# This held only the two LLM runtimes, on the reasoning that an LLM at
# temperature 0.7 is not reproducible. True, and far too narrow: it made the
# determinism law (`L-W5`) unable to fire on the canonical case for it. A Monte
# Carlo simulation in a `container`, an R script, a MATLAB routine — each is
# arbitrary code that MAYA cannot inspect, and a warrant claiming its output is
# reproducible was accepted with nothing pinning it.
#
# The name is the thing that misled. The question is not "is this runtime
# random", which is undecidable from a runtime name; it is **"can MAYA verify
# the determinism this warrant claims"** — and for arbitrary code it cannot, so
# a claim of determinism must be backed by a seed. The runtimes left out are
# left out because their determinism is a property of the format rather than of
# whatever somebody wrote: `pmml`, `pfa`, `onnx`, `sql`, `rules`, `spreadsheet`,
# and `descriptor_only`, which executes nothing here at all.
#
# `quantlib` is the honest gap. Its determinism is decidable — from the
# `pricing_engine` its own entry already declares, analytic or Monte Carlo — so
# demanding a seed for every QuantLib pricing would refuse a great many
# reproducible valuations to catch a few that are not. That check belongs
# against the engine name, and it is not built.
# `estimator` is deliberately absent. It is MAYA's own captive runtime — `ols`
# and `garch11`, whose code is in this repository — so it is the one executing
# runtime whose determinism MAYA genuinely *can* verify, and `L-3` does exactly
# that, running the same call twice and comparing bit for bit. Including it here
# would have demanded a seed to back a claim that is already proved by
# execution, which is the strongest evidence available and stronger than a seed.
UNVERIFIABLE_DETERMINISM: FrozenSet[str] = frozenset({
    "llm.prompt", "llm.agent", "container", "python.callable", "r", "matlab",
    "solver", "rest",
})

#: Retained under its old name: the two runtimes that are stochastic by nature
#: rather than merely opaque. `L-W13` reads this one — pinning a generative
#: build is a different obligation from pinning a seed.
STOCHASTIC_RUNTIMES: FrozenSet[str] = frozenset({"llm.prompt", "llm.agent"})

# ---------------------------------------------------------------------------
# Axis 4 — data bindings. Where X comes from, and where Y goes.
# ---------------------------------------------------------------------------
BINDING_KEYS: Dict[str, Tuple[str, ...]] = {
    "inline": ("values",),                       # carried in the warrant itself
    "request": (),                               # supplied by the caller at run time
    "feature_namespace": ("namespace",),         # a pinned feature view version
    # A named, versioned presentation of X. The engine resolves it and assembles,
    # which is what a recurring retrain wants; a snapshot is what an audit replay
    # wants, because it recomputes nothing.
    # as_of is NOT required here: scoring may legitimately read a featureset at
    # whatever is current. Training may not, and L-W9 requires it there.
    "featureset": ("featureset", "version"),
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
    {"feature_namespace", "featureset", "dataset_snapshot"})

# Bindings a FIT must bound in both clocks. A dataset_snapshot is already
# bounded by construction -- it is a fixed set of rows pinned at a Delta version
# -- so it needs no as_of or window on the warrant. The other two are live
# sources, and a read of one without bounds is "everything we know now".
BOUNDED_FOR_FITTING: FrozenSet[str] = frozenset(
    {"feature_namespace", "featureset"})

# The closed set of trainability classes. Checked at validation because the
# validator is what gates a warrant: the JSON Schema carries the same pattern
# and is not what runs, so a class of `"T6 "` -- one trailing space -- turned
# "fitting a vendor black box is a type error" into an admitted warrant.
TRAINABILITY_CLASSES: Tuple[str, ...] = tuple(f"T{i}" for i in range(9))

SINKS: Tuple[str, ...] = ("response", "delta_table", "stream", "artifact",
                          "parameter_object", "evidence")

# ---------------------------------------------------------------------------
# Where a run's parameters come from. Training does not change the kernel; it
# picks a point in P, so a run has to say WHICH point it is running at.
# ---------------------------------------------------------------------------
# These are the values ``parameters.source.binding`` may take. It is the same
# shape the section already had; what is new is that the vocabulary is closed and
# checked, so a run cannot decline to say which point in P it is running at.
PARAMETER_SOURCE_KEYS: Dict[str, Tuple[str, ...]] = {
    # The artifact carries them -- an ONNX graph, a PMML document. Where it
    # LIVES is realisation's job; saying it twice would let the two disagree.
    "artifact": (),
    "parameter_set": ("parameter_set", "digest"),   # a registered inhabitant of P
    "declared": ("values",),      # carried in the warrant: a closed form's constants
    "to_be_fitted": (),           # this warrant is the fit that produces them
    "vendor_internal": (),        # T6: they exist and are not ours to see
}
PARAMETER_SOURCES: Tuple[str, ...] = tuple(PARAMETER_SOURCE_KEYS)

# Only a fit may leave the parameters unfilled; everything else must say which
# point in P it is running at, or the result is not attributable to anything.
UNFITTED_SOURCES: FrozenSet[str] = frozenset({"to_be_fitted"})

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
