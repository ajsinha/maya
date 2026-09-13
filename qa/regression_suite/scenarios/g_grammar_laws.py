"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the admissibility laws of the warrant grammar.

The laws are pure functions over a document, and they are tested here as
functions rather than through thirty assembled warrants: what is being checked
is the LAW, and a case that builds a document to trip one law tests the
document at least as much as the rule.

Two properties run through all of them. Each law is keyed on a fact the
platform DERIVES — the parameter kind, the source binding, the runtime — so
none needs a category anybody declares. And admissibility reports every
problem at once, because a warrant fixed one refusal at a time is a warrant
whose author never sees its shape.
"""
from __future__ import annotations

from core.execution.grammar import rules, validator
from core.execution.grammar.vocabulary import (BITEMPORAL_BINDINGS,
                                               UNVERIFIABLE_DETERMINISM,
                                               WARRANT_VERSION)
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case


def _code(problem) -> str:
    return getattr(problem, "law", "") or getattr(problem, "code", "")


@case("QA-FX-325", "L-W1 — `fit` on a T0")
def fx_325(ctx: Ctx) -> Result:
    """Fitting is a TYPE ERROR for a terminal parameter object, not a runtime
    failure: there is nothing in P to inhabit. Refusing it at the grammar is
    what stops it being discovered by an engine at three in the morning."""
    problem = rules.check_verb_against_class("fit", "T0")
    if problem is None:
        return FAIL, "a 'fit' on a T0 model is admissible"
    if _code(problem) != "L-W1":
        return FAIL, f"refused under {_code(problem)} rather than L-W1"
    said = f"{problem}"
    if "T0" not in said and "T0" not in getattr(problem, "detail", ""):
        return FAIL, "the refusal does not name the class"
    if rules.check_verb_against_class("score", "T0") is not None:
        return FAIL, "a 'score' on a T0 is also refused, so the law is on the verb"
    if rules.check_verb_against_class("fit", "T2") is not None:
        return FAIL, "a 'fit' on a T2 is refused, so the law is on the class"
    return PASS, "fit refused on T0, score allowed, fit allowed on T2"


@case("QA-FX-326", "L-W2 — `generate` on `onnx`")
def fx_326(ctx: Ctx) -> Result:
    """`generate` asks for free-form output and only a generative runtime
    produces it. A warrant authorising generation over a scorer would be
    authorising something the runtime cannot do, and the refusal has to name
    what can."""
    problem = rules.check_generative("generate", "onnx")
    if problem is None:
        return FAIL, "'generate' on an onnx runtime is admissible"
    if _code(problem) != "L-W2":
        return FAIL, f"refused under {_code(problem)} rather than L-W2"
    if rules.check_generative("score", "onnx") is not None:
        return FAIL, "'score' on onnx is refused, so the law is not on the verb"
    from core.execution.grammar.rules import GENERATIVE_RUNTIMES
    allowed = [r for r in GENERATIVE_RUNTIMES
               if rules.check_generative("generate", r) is None]
    if not allowed:
        return FAIL, ("no runtime may generate at all, so the verb exists and "
                      "nothing can carry it")
    return PASS, f"refused on onnx, admissible on {sorted(allowed)}"


@case("QA-FX-327", "L-W3 — a `fit` reading a `sql_query`")
def fx_327(ctx: Ctx) -> Result:
    """A training set assembled from a source with no transaction time cannot
    be shown point-in-time correct, so it cannot be shown not to have leaked.
    The grammar refuses the warrant rather than leaving the leak to be found
    by a model that scores well and then does not."""
    found = rules.check_training_bindings(
        "fit", [{"binding": "sql_query", "query": "SELECT 1"}])
    if not found:
        return FAIL, "a fit reading a sql_query is admissible"
    if _code(found[0]) != "L-W3":
        return FAIL, f"refused under {_code(found[0])} rather than L-W3"
    clean = rules.check_training_bindings(
        "fit", [{"binding": sorted(BITEMPORAL_BINDINGS)[0]}])
    if clean:
        return FAIL, (f"a fit from a bitemporal binding is also refused: "
                      f"{clean[0]}")
    scoring = rules.check_training_bindings("score", [{"binding": "sql_query"}])
    if scoring:
        return FAIL, "the law applies to a 'score', which reads no training set"
    return PASS, (f"refused for a fit, admissible for a score and for "
                  f"{sorted(BITEMPORAL_BINDINGS)}")


@case("QA-FX-328",
      "L-W3 — a fit with one bitemporal input and one that is not")
def fx_328(ctx: Ctx) -> Result:
    """EVERY input must qualify. One unqualified source in a training set is
    a leak in the whole set, so a law that passed on *at least one* would be
    satisfied by the input nobody was worried about."""
    inputs = [{"binding": sorted(BITEMPORAL_BINDINGS)[0]},
              {"binding": "sql_query", "query": "SELECT 1"}]
    found = rules.check_training_bindings("fit", inputs)
    if not found:
        return FAIL, ("a fit mixing a bitemporal source with a sql_query is "
                      "admissible, so one clean input excuses the rest")
    paths = [getattr(p, "path", "") for p in found]
    if not any("[1]" in p for p in paths):
        return FAIL, (f"the refusal does not name which input is wrong: "
                      f"{paths}")
    if any("[0]" in p for p in paths):
        return FAIL, "the bitemporal input is also reported as a problem"
    return PASS, f"one problem, naming inputs[1]: {paths}"


@case("QA-FX-329", "L-W4 — a `fit` with no `parameter_object` sink")
def fx_329(ctx: Ctx) -> Result:
    """A fit produces a new parameter object and must say where it goes. A
    fit whose output went to a response would produce a point in P that the
    register never sees."""
    if rules.check_fit_output("fit", [{"sink": "response"}]) is None:
        return FAIL, "a fit writing only to a response is admissible"
    problem = rules.check_fit_output("fit", [{"sink": "response"}])
    if _code(problem) != "L-W4":
        return FAIL, f"refused under {_code(problem)} rather than L-W4"
    if rules.check_fit_output("fit", [{"sink": "response"},
                                      {"sink": "parameter_object"}]) is not None:
        return FAIL, "a fit that DOES name a parameter_object is refused"
    if rules.check_fit_output("score", [{"sink": "response"}]) is not None:
        return FAIL, "a score is made to produce a parameter object"
    return PASS, "refused without the sink, admissible with it, not on a score"


@case("QA-FX-330", "L-W5 — determinism on `container` with no seed")
def fx_330(ctx: Ctx) -> Result:
    """The case this law was written for and for a long time could not
    reach: the set it consulted held the two LLM runtimes and nothing else,
    so every Monte Carlo simulation, R script and MATLAB routine could claim
    reproducibility with nothing pinning it."""
    problem = rules.check_determinism(
        {"determinism": "deterministic"}, "container")
    if problem is None:
        return FAIL, ("a container claiming determinism with no seed is "
                      "admissible, so a simulation asserts reproducibility "
                      "and nothing pins it")
    if _code(problem) != "L-W5":
        return FAIL, f"refused under {_code(problem)} rather than L-W5"
    seeded = rules.check_determinism(
        {"determinism": "deterministic", "seed": 7}, "container")
    if seeded is not None:
        return FAIL, "a seeded container is still refused"
    stochastic = rules.check_determinism(
        {"determinism": "stochastic"}, "container")
    if stochastic is not None:
        return FAIL, "a container that claims nothing is refused"
    for runtime in ("r", "matlab", "solver", "python.callable"):
        if rules.check_determinism({"determinism": "deterministic"},
                                   runtime) is None:
            return FAIL, (f"'{runtime}' runs arbitrary code and may claim "
                          f"determinism unpinned")
    return PASS, (f"unpinned refused across {len(UNVERIFIABLE_DETERMINISM)} "
                  f"code-running runtimes; a seed or 'stochastic' satisfies it")


@case("QA-FX-331",
      "L-W5 — determinism on `onnx`, `pmml`, `sql`, `spreadsheet` and "
      "`descriptor_only`")
def fx_331(ctx: Ctx) -> Result:
    """The other side, and the reason the set is what it is: for these the
    determinism is a property of the FORMAT, not a claim MAYA has to take on
    trust. Demanding a seed here would make the law noise."""
    refused = []
    for runtime in ("onnx", "pmml", "sql", "spreadsheet", "descriptor_only"):
        if rules.check_determinism({"determinism": "deterministic"},
                                   runtime) is not None:
            refused.append(runtime)
    if refused:
        return FAIL, (f"{refused} are made to pin a determinism that is a "
                      f"property of their format")
    overlap = UNVERIFIABLE_DETERMINISM & {"onnx", "pmml", "sql", "spreadsheet",
                                          "descriptor_only"}
    if overlap:
        return FAIL, f"{sorted(overlap)} are in the unverifiable set"
    return PASS, "all five may claim determinism with no seed"


@case("QA-FX-332", "L-W5 — determinism on `quantlib` with no seed")
def fx_332(ctx: Ctx) -> Result:
    """`quantlib` is deliberately NOT in the unverifiable set, and the
    vocabulary says why. This pins the decision so a later edit that sweeps
    it in has to argue with a case rather than with a comment."""
    if "quantlib" in UNVERIFIABLE_DETERMINISM:
        return FAIL, ("quantlib has been added to the unverifiable set; the "
                      "vocabulary records the reasoning for its exclusion")
    if rules.check_determinism({"determinism": "deterministic"},
                               "quantlib") is not None:
        return FAIL, "quantlib is made to pin its determinism"
    return PASS, "quantlib may claim determinism unseeded, and is named as such"


@case("QA-FX-334", "L-W6 — `fit` on `descriptor_only`")
def fx_334(ctx: Ctx) -> Result:
    """Descriptor-only is a legitimate state, not a defect: the bank holds
    the licence, the engine holds the artifact and MAYA holds the
    governance. What such a warrant cannot carry is an instruction to
    inhabit a parameter object nothing on this side can reach."""
    problem = rules.check_descriptor_only("descriptor_only", "fit")
    if problem is None:
        return FAIL, "a fit on a descriptor-only model is admissible"
    if _code(problem) != "L-W6":
        return FAIL, f"refused under {_code(problem)} rather than L-W6"
    if rules.check_descriptor_only("descriptor_only", "score") is not None:
        return FAIL, ("a SCORE on a descriptor-only model is refused, which "
                      "would make the whole vendor-black-box case unusable")
    return PASS, "fit refused, score admitted — the vendor case still works"


@case("QA-FX-336", "L-W8 — a `fit` bound to `parameter_set`")
def fx_336(ctx: Ctx) -> Result:
    """A fit PRODUCES the parameter object, so it cannot also run from one.
    A warrant doing both is asking to fit at a point it has already fixed."""
    problem = rules.check_parameter_source(
        "fit", {"source": {"binding": "parameter_set", "digest": "sha256:x"}},
        "estimated_coefficients")
    if problem is None:
        return FAIL, "a fit running from a parameter_set is admissible"
    if _code(problem) != "L-W8":
        return FAIL, f"refused under {_code(problem)} rather than L-W8"
    ok = rules.check_parameter_source(
        "fit", {"source": {"binding": "to_be_fitted"}},
        "estimated_coefficients")
    if ok is not None:
        return FAIL, f"a fit bound 'to_be_fitted' is refused: {ok}"
    return PASS, "fit from a parameter_set refused, 'to_be_fitted' admitted"


@case("QA-FX-337", "L-W8 — a `score` bound to `to_be_fitted`")
def fx_337(ctx: Ctx) -> Result:
    """The mirror. A score has to run at some point in the parameter object,
    and `to_be_fitted` names none — so its output would be attributable to
    no parameters anybody approved."""
    problem = rules.check_parameter_source(
        "score", {"source": {"binding": "to_be_fitted"}},
        "estimated_coefficients")
    if problem is None:
        return FAIL, "a score bound 'to_be_fitted' is admissible"
    if _code(problem) != "L-W8":
        return FAIL, f"refused under {_code(problem)} rather than L-W8"
    return PASS, "refused under L-W8"


@case("QA-FX-340", "L-W8 — a source absent while the kind is not `none`")
def fx_340(ctx: Ctx) -> Result:
    """The recorded defect. The terminal exemption was ASSUMED rather than
    checked, so the law was bypassed by leaving the field out: a
    `learned_weights` scoring warrant that declined to say which point of P
    it ran at was admitted — the exact thing this law exists to refuse."""
    problem = rules.check_parameter_source("score", {}, "learned_weights")
    if problem is None:
        return FAIL, ("a scoring warrant omitting parameters.source entirely "
                      "is admissible over a learned_weights model: the law is "
                      "bypassed by leaving the field out")
    if _code(problem) != "L-W8":
        return FAIL, f"refused under {_code(problem)} rather than L-W8"
    terminal = rules.check_parameter_source("score", {}, "none")
    if terminal is not None:
        return FAIL, ("a T0 model with a terminal parameter object is made to "
                      "name a point in P that does not exist")
    if rules.check_parameter_source("score", {}, None) is not None:
        return FAIL, "an unstated kind is treated as inhabited"
    return PASS, ("omission refused where the object is inhabited, admitted "
                  "where it is terminal")


@case("QA-FX-323", "A clean shape with three admissibility failures")
def fx_323(ctx: Ctx) -> Result:
    """Every problem reported together. A warrant fixed one refusal at a time
    is a warrant whose author never sees its shape — and the shape is the
    thing the grammar exists to make visible."""
    # Shape is checked FIRST and admissibility only runs over a document
    # that passed it, so every required section has to be here — a missing
    # section reports L-W0 and the laws are never reached.
    doc = {
        "maya_warrant": WARRANT_VERSION,
        "subject": {"model_urn": "maya://model/x", "version": "1.0.0",
                    "trainability_class": "T0"},
        "operation": {"verb": "fit", "determinism": "deterministic"},
        "realisation": {"runtime": "container",
                        "entry": {"image": "x", "command": "y"}},
        # A `sql_query` binding carries `statement` and `dialect`, not
        # `query` — a shape problem here would stop admissibility running.
        "data": {"inputs": [{"binding": "sql_query", "statement": "SELECT 1",
                             "dialect": "ansi"}],
                 "outputs": [{"sink": "response"}]},
        "parameters": {"kind": "estimated_coefficients"},
        "io_contract": {"input_schema": [], "output_schema": []},
        "constraints": {},
        "authority": {"principal": "svc", "environment": "prod"},
        "governance": {"tier": 3},
        "signature": {"value": "x", "key_id": "k"},
    }
    shape = [p for p in validator.validate(doc).problems
             if _code(p) == "L-W0"]
    if shape:
        return FAIL, (f"the document does not pass SHAPE, so admissibility "
                      f"never runs: {[getattr(p, 'path', '') for p in shape]}")
    report = validator.validate(doc)
    problems = list(getattr(report, "problems", []) or [])
    laws = {_code(p) for p in problems}
    if len(laws) < 3:
        return FAIL, (f"a document breaking several laws reported {len(laws)} "
                      f"of them: {sorted(laws)} — an author fixes one at a "
                      f"time and never sees the shape")
    for expected in ("L-W1", "L-W3", "L-W4"):
        if expected not in laws:
            return FAIL, (f"{expected} was not reported alongside "
                          f"{sorted(laws)}")
    if getattr(report, "sound", None) is True:
        return FAIL, "the report calls a document with three failures sound"
    return PASS, f"{len(problems)} problems under {len(laws)} laws: {sorted(laws)}"


@case("QA-FX-4800", "Every admissibility law is reachable from the validator")
def fx_4800(ctx: Ctx) -> Result:
    """The recurring shape, asked of this module directly: a law written and
    never called is a control that reads as coverage. Every `check_` function
    in `rules` has to appear in `_admissibility`, or it decides nothing."""
    import inspect
    written = {name for name in dir(rules) if name.startswith("check_")}
    called = inspect.getsource(validator.GrammarValidator._admissibility)
    orphaned = sorted(name for name in written
                      if f"rules.{name}(" not in called)
    if orphaned:
        return FAIL, (f"{len(orphaned)} admissibility law(s) are written and "
                      f"never called by the validator: {orphaned} — each one "
                      f"reads as a control and decides nothing")
    return PASS, f"all {len(written)} check_ functions are called by the validator"
