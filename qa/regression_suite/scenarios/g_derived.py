"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — derived features, and the two things that make them dangerous.

`price_per_sqft = sale_price / living_area_sqft` is leakage with a division
sign in front of it, and the check has to walk the CLOSURE — a derivation of a
derivation of the label is still the label. And an expression language is an
execution surface, so what it will not evaluate matters as much as what it
will.
"""
from __future__ import annotations

from core.features.derived import EVALUATORS, MAX_DEPTH, ON_ERROR
from core.features.expressions import FUNCTIONS
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

F = "/api/v1/features"
D = "/api/v1/derived-features"


def _base(ctx: Ctx, entity: str = "customer") -> str:
    name = ctx.unique("bf").replace("-", "_")
    made = ctx.api.post(F, json={"name": name, "entity": entity,
                                 "dtype": "numeric", "owner": "owner",
                                 "description": "a QA base feature"},
                        auth=ctx.people["developer"])
    if made.status_code >= 400:
        raise AssertionError(f"could not define a base feature: "
                             f"{made.text[:180]}")
    return name


def _derive(ctx: Ctx, expression: str, **over):
    body = {"name": ctx.unique("df").replace("-", "_"),
            "expression": expression, "dtype": "numeric",
            "description": "a QA derived feature", "evaluator": "internal",
            "on_error": "null", "inputs": []}
    body.update(over)
    return ctx.api.post(D, json=body, auth=ctx.people["developer"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-FX-133", "A derived feature defined in terms of itself")
def fx_133(ctx: Ctx) -> Result:
    name = ctx.unique("df").replace("-", "_")
    got = _derive(ctx, f"{name} + 1", name=name)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "a feature was defined in terms of itself"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-134", "A two-hop cycle")
def fx_134(ctx: Ctx) -> Result:
    """The self-reference check catches one hop. A cycle needs the closure,
    which is the same walk the leakage check needs."""
    a = ctx.unique("df").replace("-", "_")
    b = ctx.unique("df").replace("-", "_")
    base = _base(ctx)
    if _derive(ctx, f"{base} + 1", name=a).status_code >= 400:
        return BLOCKED, "the first derived feature could not be defined"
    if _derive(ctx, f"{a} + 1", name=b).status_code >= 400:
        return BLOCKED, "the second derived feature could not be defined"
    # Redefine a in terms of b, closing the loop.
    got = _derive(ctx, f"{b} + 1", name=a)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, (f"'{a}' now reads '{b}' which reads '{a}'; the lineage "
                      f"walk will not terminate")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-132", "An expression reading no features at all")
def fx_132(ctx: Ctx) -> Result:
    """A constant is not a feature. It has no lineage, no leakage check and
    nothing to recompute."""
    got = _derive(ctx, "42 * 2")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "a constant was registered as a derived feature"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-137", "An undefined input")
def fx_137(ctx: Ctx) -> Result:
    """Naming it is the point: a derived feature reading something that does
    not exist fails at assembly, months later, over a cohort."""
    got = _derive(ctx, "qa_no_such_feature * 2")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a derived feature reads a feature nobody defined"
    if "qa_no_such_feature" not in got.text:
        return FAIL, f"the refusal does not name it: {got.text[:140]}"
    return PASS, f"refused '{code_of(got)}', naming the input"


@case("QA-FX-136", "Inputs spanning two entities")
def fx_136(ctx: Ctx) -> Result:
    """A row is keyed on one entity. Reading two means the join is happening
    somewhere nobody declared."""
    customer = _base(ctx, "customer")
    account = _base(ctx, "account")
    got = _derive(ctx, f"{customer} + {account}")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a derived feature reads two entities, so an undeclared "
                      "join decides what a row means")
    if "customer" not in got.text or "account" not in got.text:
        return FAIL, f"the refusal does not name both entities: {got.text[:140]}"
    return PASS, f"refused '{code_of(got)}', naming both entities"


@case("QA-FX-143", "The expression language will not evaluate a program")
def fx_143(ctx: Ctx) -> Result:
    """An expression language is an execution surface. Attribute access,
    subscripting, comprehensions, lambdas and calls to anything outside the
    function table are each a way out of it."""
    base = _base(ctx)
    escapes = {
        "attribute": f"{base}.__class__",
        "subscript": f"{base}[0]",
        "comprehension": f"[x for x in ({base},)]",
        "lambda": f"(lambda: {base})()",
        "unknown call": f"eval('{base}')",
        "import": "__import__('os')",
        "walrus": f"({base} := 1)",
    }
    allowed = []
    for what, expression in escapes.items():
        got = _derive(ctx, expression)
        if got.status_code >= 500:
            return FAIL, f"{what}: {got.status_code}"
        if got.status_code < 400:
            allowed.append(what)
    if allowed:
        return FAIL, ("the expression language accepted: "
                      + ", ".join(allowed))
    return PASS, f"all {len(escapes)} escapes refused"


@case("QA-FX-144", "A name beginning with a double underscore")
def fx_144(ctx: Ctx) -> Result:
    """`__class__`, `__globals__`, `__builtins__` — the dunder namespace is
    the standard way out of a Python sandbox, and it is refused as a NAME
    rather than by listing the dangerous ones."""
    got = _derive(ctx, "__builtins__ + 1")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a dunder name was accepted in an expression"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-129", "An internal derived feature declaring its inputs")
def fx_129(ctx: Ctx) -> Result:
    """Two lists that can disagree, and the leakage check would then run
    against whichever one it happened to read. The expression is the single
    source of truth for an internal definition."""
    base = _base(ctx)
    got = _derive(ctx, f"{base} * 2", inputs=[base])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an internal definition declared its inputs as well as "
                      "its expression, so two lists can disagree about what "
                      "the leakage check reads")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-131", "An external derived feature MAYA cannot parse, with no inputs")
def fx_131(ctx: Ctx) -> Result:
    """No lineage and no leakage check, which is the whole reason the
    declaration exists."""
    got = _derive(ctx, "SELECT median(x) OVER (PARTITION BY y)",
                  evaluator="external", inputs=[])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("an unparseable external expression was accepted with "
                      "no declared inputs, so it has no lineage and no "
                      "leakage check")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-138", "Evaluating an external derived feature")
def fx_138(ctx: Ctx) -> Result:
    """`external` means somebody else computes it. MAYA evaluating one would
    be MAYA guessing at a language it just said it cannot read."""
    base = _base(ctx)
    made = _derive(ctx, "median(x)", evaluator="external", inputs=[base])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    name = (made.json() or {}).get("name")
    # `derived` hangs off the feature registry, not the context.
    derived = getattr(ctx.ui.app.state.ctx.get("features"), "derived", None)
    if derived is None:
        return BLOCKED, "no derived register reachable from this run"
    from core.features.common import FeatureError
    # `compute(name, rows)`, not `evaluate` — it takes a list of rows.
    try:
        derived.compute(name, [{base: 1.0}])
    except FeatureError as exc:
        if "materialise" not in str(exc) and "external" not in str(exc):
            return FAIL, f"refused for another reason: {exc}"
        return PASS, f"refused: {str(exc)[:90]}"
    except Exception as exc:
        return FAIL, f"raised {type(exc).__name__} rather than refusing: {exc}"
    return FAIL, ("MAYA evaluated an expression it declared itself unable to "
                  "parse")


@case("QA-FX-141", "`log` of a non-positive number and `sqrt` of a negative")
def fx_141(ctx: Ctx) -> Result:
    """`log` of a non-positive number and `sqrt` of a negative one. A row
    whose arithmetic has no answer is a null, not a failed batch."""
    from core.features.expressions import FUNCTIONS as _F
    wrong = []
    for name, bad in (("log", 0.0), ("log", -1.0), ("sqrt", -1.0)):
        if name not in _F:
            continue
        try:
            got = _F[name](bad)
        except Exception as exc:
            wrong.append(f"{name}({bad}) raised {type(exc).__name__}")
            continue
        if got is not None:
            wrong.append(f"{name}({bad}) = {got}")
    if wrong:
        return FAIL, "; ".join(wrong)
    return PASS, f"undefined arithmetic gives null across {len(FUNCTIONS)} functions"


@case("QA-FX-3000", "The evaluator and on_error vocabularies are closed")
def fx_3000(ctx: Ctx) -> Result:
    """`on_error` decides whether a bad row becomes a null or stops the
    batch. A value outside the pair is a behaviour nobody chose."""
    base = _base(ctx)
    for field, values in (("evaluator", EVALUATORS), ("on_error", ON_ERROR)):
        got = _derive(ctx, f"{base} * 2", **{field: "whatever"})
        if got.status_code >= 500:
            return FAIL, f"{field}: {got.status_code}"
        if got.status_code < 400:
            return FAIL, f"'{field}' accepted a value outside {values}"
        if not any(v in got.text for v in values):
            return FAIL, f"the '{field}' refusal does not name the vocabulary"
    return PASS, "both vocabularies closed and named in their refusals"


@case("QA-FX-135", "Lineage exactly at the depth limit, then one deeper")
def fx_135(ctx: Ctx) -> Result:
    """`MAX_DEPTH` is declared as a MODELLING limit — "a derivation deeper
    than this is a modelling problem rather than a depth problem" — and is
    enforced in exactly one place: inside `provenance`, the recursive walk
    that computes the polynomial. Definition does not consult it.
    """
    previous = _base(ctx)
    depth = 0
    for _ in range(MAX_DEPTH + 2):
        name = ctx.unique("df").replace("-", "_")
        got = _derive(ctx, f"{previous} + 1", name=name)
        if got.status_code >= 400:
            if depth < MAX_DEPTH:
                return FAIL, (f"a lineage {depth + 1} deep was refused "
                              f"'{code_of(got)}', inside the limit of "
                              f"{MAX_DEPTH}")
            return PASS, (f"{depth} deep accepted, {depth + 1} refused "
                          f"'{code_of(got)}'")
        depth += 1
        previous = name
    # Definition accepted past the limit. Whether that is a defect turns on
    # whether anything downstream then refuses — so ask the one path that
    # enforces it.
    features = ctx.ui.app.state.ctx.get("features")
    derived = getattr(features, "derived", None)
    from core.features.common import FeatureError
    refused_later = False
    if derived is not None:
        try:
            derived.provenance(previous)
        except FeatureError:
            refused_later = True
        except Exception:
            refused_later = False
    return FAIL, (
        f"a lineage {depth} deep was defined, past the stated {MAX_DEPTH} "
        f"limit. The limit is enforced only inside `provenance`, the "
        f"recursive walk — "
        + ("which does refuse it, so the chain exists and the question the "
           "limit was written to keep answerable cannot be answered about it"
           if refused_later else
           "and nothing refused it there either") +
        ". The leakage check walks `lineage`, which has no depth guard at all")


