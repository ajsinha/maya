"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The grammar's admissibility laws.

A warrant can be well-formed and still be nonsense: asking a Black-Scholes
closed form to be *fitted*, training on a data source that cannot be read
as-of, generating text from a gradient-boosting model. These are the rules that
make such a document a refusal rather than a runtime failure.

The important ones are not invented here. They fall out of the algebra already
in ``core/domain``: the trainability class is derived from how the parameter
object is inhabited, and ``requires_fitting_evidence`` is exactly the predicate
that says whether ``fit`` means anything for this model. T0 (parameters from
theory) and T6 (parameters exist but are not ours to see) are precisely the
classes for which fitting is a type error — so the grammar refuses it, and the
refusal says which class and why.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from core.execution.grammar.vocabulary import (BACKTEST, BITEMPORAL_BINDINGS, FIT,
                                               GENERATE, MONITOR, OPTIMISE,
                                               PARAMETER_SOURCE_KEYS,
                                               PARAMETER_SOURCES, SCORE, SIMULATE,
                                               STOCHASTIC_RUNTIMES,
                                               UNFITTED_SOURCES, VERBS)

# ---------------------------------------------------------------------------
# Which verbs each trainability class admits.
#
# T0 analytic and T6 opaque cannot be fitted -- one has no parameters to
# inhabit, the other has parameters nobody outside the vendor can reach. That
# is not a policy choice; it is what the class means.
# ---------------------------------------------------------------------------
NON_FITTABLE: FrozenSet[str] = frozenset({"T0", "T6"})

WHY_NOT_FITTABLE: Dict[str, str] = {
    "T0": "its parameters come from theory, not from data — there is nothing to fit",
    "T6": "its parameters are inside a vendor black box and cannot be reached",
}

# Verbs that need outcomes to compare predictions against.
NEEDS_OUTCOMES: FrozenSet[str] = frozenset({BACKTEST})

# Verbs that produce free-form output and therefore need a generative runtime.
GENERATIVE_VERBS: FrozenSet[str] = frozenset({GENERATE})
GENERATIVE_RUNTIMES: FrozenSet[str] = frozenset({"llm.prompt", "llm.agent"})

# What each verb must declare. Checked as sets of dotted paths.
REQUIRED_FOR_VERB: Dict[str, Tuple[str, ...]] = {
    SCORE: ("data.inputs",),
    FIT: ("data.inputs", "data.outputs"),
    GENERATE: ("data.inputs",),
    BACKTEST: ("data.inputs",),
    SIMULATE: ("data.inputs",),
    OPTIMISE: ("data.inputs",),
    MONITOR: ("data.inputs",),
}


@dataclass(frozen=True)
class Problem:
    """One thing wrong with a warrant, and what to do about it."""
    law: str
    path: str
    detail: str
    remediation: str

    def as_dict(self) -> Dict[str, str]:
        return {"law": self.law, "path": self.path, "detail": self.detail,
                "remediation": self.remediation}


def admissible_verbs(trainability_class: str) -> List[str]:
    """Every verb this class of model can meaningfully be asked to perform."""
    if trainability_class in NON_FITTABLE:
        return [v for v in VERBS if v != FIT]
    return list(VERBS)


def check_verb_against_class(verb: str, trainability_class: str) -> Optional[Problem]:
    """L-W1. Fitting is a type error for T0 and T6, not a runtime failure."""
    if verb == FIT and trainability_class in NON_FITTABLE:
        return Problem(
            "L-W1", "operation.verb",
            f"a {trainability_class} model cannot be fitted: "
            f"{WHY_NOT_FITTABLE[trainability_class]}",
            "ask for 'score', 'validate' or 'explain'; if this model really is "
            "fitted, its parameter_kind and fit_procedure are wrong")
    return None


def check_generative(verb: str, runtime: str) -> Optional[Problem]:
    """L-W2. 'generate' produces free text; only a generative runtime can."""
    if verb in GENERATIVE_VERBS and runtime not in GENERATIVE_RUNTIMES:
        return Problem(
            "L-W2", "operation.verb",
            f"'{verb}' asks for free-form output, which the '{runtime}' runtime "
            "does not produce",
            f"use one of {', '.join(sorted(GENERATIVE_RUNTIMES))}, or ask for 'score'")
    return None


def check_training_bindings(verb: str, inputs: List[Dict[str, Any]]) -> List[Problem]:
    """L-W3. Training data must come from a source that can be read as-of.

    A training set assembled from a source with no transaction time cannot be
    shown point-in-time correct, so it cannot be shown not to have leaked. The
    grammar refuses the warrant rather than leaving the leak to be discovered by
    a model that scores well and then does not.
    """
    if verb != FIT:
        return []
    problems = []
    for i, binding in enumerate(inputs):
        kind = binding.get("binding")
        if kind not in BITEMPORAL_BINDINGS:
            problems.append(Problem(
                "L-W3", f"data.inputs[{i}].binding",
                f"training from a '{kind}' binding cannot be shown point-in-time "
                "correct, because that source cannot answer what was known at a "
                "given moment",
                f"train from {' or '.join(sorted(BITEMPORAL_BINDINGS))}"))
    return problems


def check_fit_output(verb: str, outputs: List[Dict[str, Any]]) -> Optional[Problem]:
    """L-W4. A fit must say where the parameters it produces will go."""
    if verb != FIT:
        return None
    if not any(o.get("sink") == "parameter_object" for o in outputs):
        return Problem(
            "L-W4", "data.outputs",
            "a 'fit' produces a new parameter object and must say where it goes",
            "add an output with sink 'parameter_object'")
    return None


def check_parameter_source(verb: str, parameters: Dict[str, Any]) -> Optional[Problem]:
    """L-W8. Every run must say which point in P it is running at.

    Training does not change the kernel; it inhabits the parameter object. So a
    warrant that asks a model to do anything other than fit has to name the
    inhabitant, or its output is not attributable to a set of parameters anybody
    approved. Only a fit may leave it unfilled, because the fit is what produces it.
    """
    source = (parameters.get("source") or {}).get("binding")
    if source is None:
        # A terminal parameter object has nothing to bind: T0 carries its
        # constants in the kernel, and there is no point in P to name.
        return None
    if source not in PARAMETER_SOURCES:
        return Problem(
            "L-W8", "parameters.source",
            f"'{source}' is not a known parameter source",
            f"use one of {', '.join(PARAMETER_SOURCES)}")
    if verb == FIT and source not in UNFITTED_SOURCES:
        return Problem(
            "L-W8", "parameters.source",
            f"a 'fit' produces the parameter object, so it cannot also run from "
            f"'{source}'",
            "a fit warrant binds its parameters as 'to_be_fitted'")
    if verb != FIT and source in UNFITTED_SOURCES:
        return Problem(
            "L-W8", "parameters.source",
            f"a '{verb}' has to run at some point in the parameter object, and "
            f"'to_be_fitted' names none",
            "name the parameter set this run uses, or declare the values")
    missing = [k for k in PARAMETER_SOURCE_KEYS[source]
               if (parameters.get("source") or {}).get(k) is None]
    if missing:
        return Problem(
            "L-W8", "parameters.source",
            f"a '{source}' parameter source needs {', '.join(missing)}",
            f"a '{source}' source carries "
            f"{', '.join(PARAMETER_SOURCE_KEYS[source]) or 'nothing'}")
    return None


def check_featureset_bounds(verb: str, inputs: List[Dict[str, Any]]) -> List[Problem]:
    """L-W9. A featureset read for training must be bounded in both clocks.

    The featureset itself fixes the point-in-time rule; what it deliberately does
    not fix is the window, because the same set is meant to be reusable across
    periods. So the warrant supplies it — and a warrant that supplies neither an
    as_of nor a window is asking for "everything we know now", which cannot be
    shown point-in-time correct however carefully the set was pinned.
    """
    if verb != FIT:
        return []
    problems = []
    for i, binding in enumerate(inputs):
        if binding.get("binding") != "featureset":
            continue
        if not binding.get("as_of"):
            problems.append(Problem(
                "L-W9", f"data.inputs[{i}].as_of",
                "a featureset read for fitting must say as of when it is read; "
                "without it the assembly reads whatever has since arrived",
                "pin as_of to the moment the training set is assembled at"))
        window = binding.get("window") or {}
        # `is None` and not falsiness: 1970-01-01 is a real instant, and a
        # window that legitimately opens at the epoch was being refused as
        # unbounded -- the rule reading "you gave me nothing" off a bound that
        # happened to be zero.
        if window.get("from") is None or window.get("to") is None:
            problems.append(Problem(
                "L-W9", f"data.inputs[{i}].window",
                "a featureset read for fitting must bound the period it covers",
                "give the window a from and a to; the featureset fixes the "
                "columns, the warrant fixes the period"))
    return problems


def check_determinism(operation: Dict[str, Any], runtime: str) -> Optional[Problem]:
    """L-W5. A run claiming determinism from a stochastic runtime must pin it.

    An LLM at temperature 0.7 is not reproducible, and a warrant asserting that
    it is will be believed by whatever reads the result.
    """
    claims_determinism = operation.get("determinism") == "deterministic"
    if not claims_determinism or runtime not in STOCHASTIC_RUNTIMES:
        return None
    if operation.get("seed") is None:
        return Problem(
            "L-W5", "operation.seed",
            f"the '{runtime}' runtime is not deterministic unless it is pinned, "
            "but this operation claims determinism",
            "set operation.seed, or declare determinism as 'stochastic'")
    return None


def check_descriptor_only(runtime: str, verb: str) -> Optional[Problem]:
    """L-W6. A model MAYA cannot locate cannot be fitted by a warrant from MAYA.

    Descriptor-only is a legitimate state, not a defect: for a vendor black box
    the bank holds the licence and the engine holds the artifact, while MAYA
    holds the governance. Such a warrant carries authority, schemas and the
    operating boundary, and the engine supplies the model.

    What it cannot carry is an instruction to inhabit a parameter object that
    nothing on this side can reach.
    """
    if runtime == "descriptor_only" and verb == FIT:
        return Problem(
            "L-W6", "realisation.runtime",
            "this model is registered descriptor-only — MAYA holds its governance "
            "but not a locatable artifact — so it cannot be warranted for fitting",
            "register a locatable artifact, or ask the vendor for a refitted "
            "version and register that as a new version")
    return None


def check_outcomes(verb: str, inputs: List[Dict[str, Any]]) -> Optional[Problem]:
    """L-W7. A backtest without outcomes is a re-score, not a backtest."""
    if verb not in NEEDS_OUTCOMES:
        return None
    if not any(b.get("labels") or b.get("outcome_column") for b in inputs):
        return Problem(
            "L-W7", "data.inputs",
            "a backtest compares predictions against outcomes, and none of the "
            "inputs supplies them",
            "name the outcome column, or bind a dataset that carries labels")
    return None
