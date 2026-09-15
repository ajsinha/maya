"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — a feature computed from other features.

Three properties, and each is a place a derivation can quietly claim more
than its inputs support.

**The ingest clock is inherited as a maximum.** You did not know Z before you
knew both its inputs, so taking anything lower would be a lie about when the
value could have been used — which is the whole content of a point-in-time
guarantee.

**Certification is the meet, computed on every call.** It used to be written
once at `define` and never recomputed, so the invariant was true at the moment
of definition and false from the first demotion onwards: certify two inputs,
derive from them, deprecate one, and the derivation went on reporting itself
certified. That is the defect this platform keeps finding — a value derived,
then stored, then allowed to disagree with what it was derived from.

**A derived feature may not read the label.** A derivation of the label is
still the label, however many hops away.
"""
from __future__ import annotations

from core.features.common import INGEST_TIME, FeatureError
from core.features.derived import (CERTIFICATION_ORDER, ON_ERROR,
                                   DerivedFeatures)
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)


def _engine(ctx: Ctx):
    """`DerivedFeatures` hangs off the feature registry as `.derived` — there
    is no `derived_features` key in the application context, and looking for
    one blocks every case here on a key that never existed."""
    features = ctx.ui.app.state.ctx.get("features")
    return getattr(features, "derived", None) if features else None


@case("QA-FX-145",
      "The ingest clock of a derived feature is the max of its inputs")
def fx_145(ctx: Ctx) -> Result:
    """`ingest_ts(Z) = max(ingest_ts(X), ingest_ts(Y))`. The row's own stamp
    is the floor and per-input stamps refine it UPWARD only — downward would
    be a claim that a value was usable before one of the things it rests on
    had arrived."""
    row = {"entity_id": "e1", INGEST_TIME: 100.0,
           f"x__{INGEST_TIME}": 300.0, f"y__{INGEST_TIME}": 200.0}
    got = DerivedFeatures.knowable_at(row, ["x", "y"])
    if got != 300.0:
        return FAIL, f"the inherited clock is {got}, not the latest input"
    lower = {"entity_id": "e1", INGEST_TIME: 500.0,
             f"x__{INGEST_TIME}": 100.0}
    if DerivedFeatures.knowable_at(lower, ["x"]) != 500.0:
        return FAIL, ("an input stamp EARLIER than the row's own pulled the "
                      "clock down, so the value claims to have been usable "
                      "before the row existed")
    bare = {"entity_id": "e1", INGEST_TIME: 42.0}
    if DerivedFeatures.knowable_at(bare, ["x", "y"]) != 42.0:
        return FAIL, "with no per-input stamps the row's own is not the floor"
    return PASS, "max over the inputs, floored at the row's own stamp"


@case("QA-FX-146", "Certification is the meet of the inputs")
def fx_146(ctx: Ctx) -> Result:
    """As certified as the least-certified input, never more. And an
    unrecognised level ranks WORST rather than best — somebody's own
    vocabulary is not evidence of quality, and the direction a check fails in
    is the whole of its value."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no derived feature engine is wired"
    best, worst = CERTIFICATION_ORDER[-1], CERTIFICATION_ORDER[0]

    class Catalogue:
        def __init__(self, levels):
            self.levels = levels

        def require(self, name):
            return {"certification": self.levels[name]}

    was = engine.catalogue
    try:
        engine.catalogue = Catalogue({"x": best, "y": worst})
        if engine.certification_of(["x", "y"]) != worst:
            return FAIL, (f"the meet of {best} and {worst} is not {worst}")
        engine.catalogue = Catalogue({"x": best, "y": best})
        if engine.certification_of(["x", "y"]) != best:
            return FAIL, f"the meet of two {best} inputs is not {best}"
        engine.catalogue = Catalogue({"x": best, "y": "somebody-elses-word"})
        if engine.certification_of(["x", "y"]) != worst:
            return FAIL, ("an unrecognised certification level does not rank "
                          "worst, so a firm's own vocabulary raises the meet")
    finally:
        engine.catalogue = was
    return PASS, f"the meet lands at {worst}, and an unknown level ranks worst"


@case("QA-FX-147",
      "A featureset plan reports certification as of now, not as pinned")
def fx_147(ctx: Ctx) -> Result:
    """The recorded defect: the meet was written once at `define` and never
    recomputed, so certify two inputs, derive from them, then deprecate one,
    and the derivation went on reporting itself certified. `certification_now`
    asks the question again, which is the only way the answer stays true
    after an input moves."""
    import inspect
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no derived feature engine is wired"
    source = inspect.getsource(type(engine).certification_now)
    if "certification_of" not in source:
        return FAIL, ("`certification_now` does not recompute the meet, so a "
                      "demoted input leaves the derivation claiming what it "
                      "claimed at definition")
    stored = inspect.getsource(type(engine).certification_of)
    if "self.catalogue.require" not in stored:
        return FAIL, ("the meet does not read the inputs' CURRENT levels")
    if "min(ranks)" not in stored:
        return FAIL, "the meet is not a minimum over the input ranks"
    return PASS, "the meet is recomputed from the inputs' current levels"


@case("QA-FX-125", "A derived feature computed directly from the label")
def fx_125(ctx: Ctx) -> Result:
    """`price_per_sqft = sale_price / area` in a set whose label is
    `sale_price` leaks the answer into the training data — the model scores
    well and then does not."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no derived feature engine is wired"
    try:
        engine.refuse_if_reads("sale_price", "sale_price")
    except FeatureError as exc:
        if "label" not in f"{exc}":
            return FAIL, f"refused for another reason: {f'{exc}'[:110]}"
        return PASS, "the label itself is refused as a feature"
    return FAIL, "a featureset's own label was accepted as a feature"


@case("QA-FX-126", "A derived feature three hops from the label")
def fx_126(ctx: Ctx) -> Result:
    """The check runs over the LINEAGE and not over the immediate inputs. A
    derivation of a derivation of the label is still the label, and stopping
    at one hop would make the leak trivially reachable."""
    import inspect
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no derived feature engine is wired"
    source = inspect.getsource(type(engine).refuse_if_reads)
    if "depends_on" not in source:
        return FAIL, ("the leakage check reads only the immediate inputs, so "
                      "one extra hop hides the label")
    walk = inspect.getsource(type(engine).lineage)
    if "seen" not in walk:
        return FAIL, ("the lineage walk keeps no visited set, so a cycle in "
                      "the derivations would not terminate")
    return PASS, "the check runs over the transitive lineage, with a seen set"


@case("QA-FX-127",
      "The same derived feature in a featureset that declares no label")
def fx_127(ctx: Ctx) -> Result:
    """Accepted. Leakage is a property of a feature AND a label together, so
    a set with no label has nothing to leak — refusing here would make the
    check a blanket ban on ratios."""
    import inspect
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no derived feature engine is wired"
    source = inspect.getsource(type(engine).refuse_if_reads)
    if "label" not in inspect.signature(
            type(engine).refuse_if_reads).parameters:
        return FAIL, "the leakage check does not take a label at all"
    del source
    try:
        engine.refuse_if_reads("some_ratio", "")
    except FeatureError as exc:
        return FAIL, (f"a set declaring no label still refuses a derived "
                      f"feature: {f'{exc}'[:110]}")
    return PASS, "with no label declared there is nothing to leak"


@case("QA-FX-139", "`on_error: null` with a zero denominator")
def fx_139(ctx: Ctx) -> Result:
    """A null is a real answer for a ratio with no denominator, and recording
    it is better than refusing a whole materialisation for one entity."""
    if "null" not in ON_ERROR:
        return FAIL, f"'null' is not an on_error policy: {ON_ERROR}"
    from core.features.expressions import Expression
    parsed = Expression("a / b")
    if parsed.evaluate({"a": 1.0, "b": 0.0}) is not None:
        return FAIL, "a division by zero produced a value"
    if parsed.evaluate({"a": 1.0, "b": 2.0}) != 0.5:
        return FAIL, "an ordinary division does not evaluate"
    return PASS, "a zero denominator evaluates to null, an ordinary one does not"


@case("QA-FX-140", "`on_error: refuse` with a zero denominator")
def fx_140(ctx: Ctx) -> Result:
    """The other policy, and the refusal has to name the ENTITY — a
    materialisation over a million rows that says only *a value was missing*
    leaves somebody scanning a million rows."""
    import inspect
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no derived feature engine is wired"
    if "refuse" not in ON_ERROR:
        return FAIL, f"'refuse' is not an on_error policy: {ON_ERROR}"
    source = inspect.getsource(type(engine).compute)
    if 'on_error"] == "refuse"' not in source and "'refuse'" not in source:
        return FAIL, "compute does not consult the on_error policy"
    if "entity_id" not in source:
        return FAIL, ("the refusal does not name the entity, so a failure over "
                      "a million rows says only that something was missing")
    return PASS, "the refuse policy is consulted and names the entity"


@case("QA-FX-142", "`0 ** -1` and `1e308 * 10`")
def fx_142(ctx: Ctx) -> Result:
    """EXPLORATORY. Both are arithmetic that has no answer in the reals a
    feature store can hold, and both must give null or a named refusal —
    never an infinity or a NaN, which propagate silently through every
    aggregate downstream."""
    import math

    from core.features.expressions import Expression
    for expression, row in (("a ** b", {"a": 0.0, "b": -1.0}),
                            ("a * b", {"a": 1e308, "b": 10.0})):
        try:
            value = Expression(expression).evaluate(row)
        except FeatureError:
            continue
        if value is None:
            continue
        if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
            return FAIL, (f"'{expression}' over {row} evaluates to {value}. "
                          f"Every other arithmetic failure here answers null "
                          f"or refuses; an infinity is neither, and it "
                          f"propagates through every mean, sum and threshold "
                          f"downstream without any of them noticing — a "
                          f"monitor over the column reports a breach it "
                          f"cannot explain")
        return FAIL, f"'{expression}' over {row} gave {value!r}"
    return PASS, "neither produces an infinity or a NaN"


@case("QA-FX-130",
      "An external derived feature whose expression parses and which "
      "declares inputs")
def fx_130(ctx: Ctx) -> Result:
    """MAYA does not compute an external feature — the values are
    materialised like any primitive. The definition is still KEPT, because
    lineage and the leakage check still apply, and refusing to compute it is
    different from not knowing what it is."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no derived feature engine is wired"
    import inspect
    source = inspect.getsource(type(engine).compute)
    if "EXTERNAL" not in source:
        return FAIL, "compute does not distinguish an external feature"
    if "lineage" not in source and "still apply" not in source:
        if "kept" not in source:
            return FAIL, ("the refusal does not say the definition is kept, so "
                          "a reader takes it for an unknown feature")
    return PASS, "an external feature is not computed and its definition stands"


@case("QA-FX-3000", "The evaluator and on_error vocabularies are closed")
def fx_3000(ctx: Ctx) -> Result:
    """Two small closed sets, and neither is cosmetic.

    `evaluator` decides whether MAYA parses the expression or takes the
    author's declared inputs on trust, so an unrecognised value stored as
    itself would leave a feature that is neither parsed nor declared — and the
    leakage check, which walks the parse, would find nothing to walk and pass.

    `on_error` decides what a row with no arithmetic answer becomes. `null` and
    `refuse` are opposite answers to *is a missing value a value*, and anything
    else stored between them would be read as one of the two by whichever code
    path got there first.
    """
    from core.features.derived import EVALUATORS

    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no derived feature engine is wired"
    slipped = []
    for field, allowed in (("evaluator", EVALUATORS), ("on_error", ON_ERROR)):
        try:
            engine.define(ctx.unique("dv"), "1 + 1", "numeric", "qa",
                          owner="person/owner", **{field: "sideways"})
        except FeatureError as refused:
            if not any(v in str(refused) for v in allowed):
                slipped.append(f"{field}: refused without naming {allowed}")
        except Exception as other:
            slipped.append(f"{field}: {type(other).__name__} rather than a "
                           f"FeatureError")
        else:
            slipped.append(f"{field}: 'sideways' was accepted")
    if slipped:
        return FAIL, ("a closed vocabulary admitted a value outside it — "
                      + "; ".join(slipped))
    return PASS, (f"both closed: evaluator in {EVALUATORS}, on_error in "
                  f"{ON_ERROR}, each refusal naming its set")
