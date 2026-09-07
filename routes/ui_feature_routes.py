"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The screens for the feature algebra: defining, loading, and reading back.

Split out of `ui_routes.py` rather than added to it. That file holds the pages
that *read* the register; these author into it, and the two have different
failure modes — a read page that breaks shows nothing, an authoring page that
breaks writes something wrong.

**These screens decide nothing.** Every refusal a user sees here is the API's,
rendered; nothing about whether an act is permitted is computed in the browser
or in this module. A page that made a governance decision locally would be a
second implementation of a rule, and a second implementation disagrees with the
first eventually, in the direction of permitting more — because that is the
direction in which nobody files a bug.

## The four free endpoints, and why they are here

A definition, a fill rule and a point-in-time read are each refused for reasons
an author cannot see from a form: the expression does not parse, an input is not
in the catalogue, the fill rule reaches into the future, the row was known too
late. Without somewhere to ask, the only way to find out is to submit — and the
register fills with attempts, which is the failure the featureset preview
endpoint already exists to prevent.

So `check`, `trial`, `alignment-trial` and `as-of` are **free**, in the same
sense the rule-set editor's `check` and `trial` are: they carry the read
permission, record nothing, append no evidence, and can be called on every
keystroke. Each answers by calling the function the real act calls —
`Expression`, `catalogue.missing`, `derived.certification_of`,
`alignment.align`, `TrainingSetBuilder.latest_admissible` — rather than by
paraphrasing it. Where a paraphrase would be needed, the answer is left to the
real act and the response says so.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import Request
from fastapi.responses import HTMLResponse
from pydantic import Field

from core.features import alignment, shapes
from core.features import policy as retrieval_policy
from core.features.assembly import TrainingSetBuilder
from core.features.catalogue import LEVELS
from core.features.common import ENTITY, INGEST_TIME, RESERVED, VALID_TIME, FeatureError
from core.features.derived import (CERTIFICATION_ORDER, EVALUATORS, EXTERNAL,
                                   ON_ERROR, DerivedFeatures)
from core.features.composition import describe as describe_composition
from core.features.expressions import Expression, describe as describe_language
from core.features.preparation import describe as describe_preparation
from core.features.transfer import FORMAT_MEANING, MEDIA_TYPE, UPLOAD_FORMATS
from core.log import get_logger, swallowed
from core.features.common import SUGGESTED_DTYPES
from core.features.transfer import accept_attribute
from routes.base import Body, Routes, login_required

logger = get_logger(__name__)

PRIMITIVE, DERIVED, COMPOSED = "primitive", "derived", "composed"

# A clock stamp early enough that the bound it is compared against always
# accepts it. Used only to ask the point-in-time operator which of the two
# clocks refused a row — never returned to a caller.
BEFORE_EVERYTHING = float("-inf")

# How many stored rows a free probe will read. The probe is for a person
# reading twenty rows and understanding the rule, not for a job.
PROBE_ROWS = 500

# What the definition check does NOT answer, said out loud rather than left to
# be discovered. A screen implying a clean check meant a guaranteed define would
# be claiming a control that is not there.
UNCHECKED = (
    "the define call itself is the authority; this check writes nothing and "
    "holds no lock, so a name free now can be taken between the two",
    "whether a featureset that uses this feature declares one of its inputs as "
    "the label — leakage is checked when the featureset is published, against "
    "the label that set declares",
)


# ---------------------------------------------------------------- the bodies
class DefinitionCheckIn(Body):
    """A draft definition. Nothing here is recorded.

    It carries every field `FeatureIn` carries, because the question it answers
    is *would `define` accept this* — and a check that refuses a field the real
    call accepts is answering a different question about a different object.
    The divergence was invisible while unknown fields were silently dropped:
    a caller building one draft and sending it to both got a cheerful 200 from
    a check that had quietly discarded half of it.
    """
    kind: str = PRIMITIVE
    name: str = ""
    entity: str = ""
    dtype: str = "numeric"
    description: str = ""
    # Everything `define` takes and does not decide for itself. Governance
    # attributes rather than type: they do not change whether the definition is
    # well-formed, and refusing them here would still be wrong.
    owner: str = ""
    business_definition: str = ""
    source_system: str = ""
    sensitivity: str = "internal"
    pii: bool = False
    protected_basis: bool = False
    proxy_risk: str = "none"
    # An ephemeral feature expires; the check has to be able to say whether a
    # draft that declares one would be accepted.
    ephemeral: bool = False
    ttl_days: Optional[float] = None
    # Primitive and composed.
    shape: Any = None
    components: Optional[List[str]] = None
    defaults: Optional[Dict[str, Any]] = None
    # Composed only: the parents, in fold order, and this feature's own edits.
    composes: Optional[List[Any]] = None
    operations: Optional[List[Dict[str, Any]]] = None
    # Derived only.
    expression: str = ""
    evaluator: str = "internal"
    on_error: str = "null"
    inputs: List[str] = Field(default_factory=list)


class ExpressionTrialIn(Body):
    """A draft expression and some rows to read it over."""
    expression: str
    on_error: str = "null"
    rows: List[Dict[str, Any]] = Field(default_factory=list)


class AlignmentTrialIn(Body):
    """Rows, an axis and a fill rule. Aligns nothing that is stored."""
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    axis: str = VALID_TIME
    rule: str = alignment.FORWARD
    grid: str = alignment.OBSERVED
    start: Optional[float] = None
    stop: Optional[float] = None
    step: Optional[float] = None
    points: Optional[List[float]] = None
    carry_limit: Optional[float] = None


class AsOfIn(Body):
    """A decision moment and an assembly moment — the two bounds of the read."""
    label_ts: float
    as_of: float
    entity_id: Optional[str] = None
    limit: int = PROBE_ROWS


# ------------------------------------------------------------- the checkers
def _upload_formats() -> List[Dict[str, str]]:
    """The formats a load may arrive in, from the transfer layer's own tables.

    A screen holding its own list of media types is a second list, and the one
    that drifts is always the copy.
    """
    return [{"format": f, "media_type": MEDIA_TYPE[f], "means": FORMAT_MEANING[f]}
            for f in UPLOAD_FORMATS]


def _check_primitive(features, body: DefinitionCheckIn) -> Dict[str, Any]:
    """What the catalogue can say about a primitive before one exists.

    The shape, the component names and the retrieval policy are checked by the
    functions `FeatureCatalogue.define` checks them with, so a draft that passes
    here fails there only on what a check cannot hold: the name being taken in
    the meantime, and anything the register learns after this call.
    """
    name = body.name.strip()
    if not name:
        raise FeatureError("a feature needs a name: it is what a view, a "
                           "featureset and a contract all pin it by")
    if not body.entity.strip():
        raise FeatureError(
            f"'{name}' needs an entity — the thing one row is about. A feature "
            f"with no grain cannot be joined to a spine, and settling the grain "
            f"later is how a per-account number becomes a per-customer one")
    if features.catalogue.get(name):
        raise FeatureError(f"feature '{name}' is already defined")
    dims = shapes.parse(body.shape)
    named = shapes.check_components(dims, body.components)
    retrieval_policy.check(body.defaults)
    near = features.similar(name, body.description)
    return {
        "ok": 1, "kind": PRIMITIVE, "name": name, "entity": body.entity.strip(),
        "dimensionality": shapes.describe(dims, named),
        "components": list(named or []),
        # Stated rather than offered: `define` lands every feature here, and a
        # form offering a level would be offering something the API does not take.
        "certification": "experimental",
        "possible_duplicates": [{"name": f["name"], "owner": f.get("owner", ""),
                                 "description": f.get("description", "")}
                                for f in near],
        "not_checked": [UNCHECKED[0]],
        "detail": f"'{name}' would be a {shapes.describe(dims, named)['kind']} on "
                  f"{body.entity.strip()}, landing experimental — certification "
                  f"is a later act, by somebody else",
    }


def _check_composed(features, body: DefinitionCheckIn) -> Dict[str, Any]:
    """What a feature composed from others would actually have.

    Composition is a left-to-right fold in which the rightmost parent wins, and
    the feature's own operations are applied last — so the answer is never what
    was typed, it is what the parents plus the operations say. Working that out
    is MAYA's job, and this asks it of the same `Resolver` that `define` refuses
    an unresolvable composition with.

    Every operation is total: dropping a member no parent has, adding one they
    all have, overriding one that is not there — each is refused rather than
    quietly doing nothing, because a no-op leaves a child that differs from what
    its author believed they had written.
    """
    name = body.name.strip()
    if not name:
        raise FeatureError("a composed feature needs a name")
    if not body.composes:
        raise FeatureError(
            f"'{name}' composes nothing, so it is a primitive rather than a "
            f"composition; the empty composition is the thing itself")
    if features.catalogue.get(name):
        raise FeatureError(f"feature '{name}' is already defined")
    draft = {"name": name, "entity": body.entity.strip(), "dtype": body.dtype,
             "components": list(body.components or []),
             "composes": list(body.composes),
             "operations": list(body.operations or [])}
    members = features.catalogue.resolve(draft)
    provenance = features.catalogue.resolver.explain(draft)
    ancestry = features.catalogue.resolver.lineage(draft)
    dims = shapes.parse(body.shape)
    # The first axis follows the components: composing a tenor onto a curve
    # makes it longer, and a shape that disagreed would be the stale half.
    effective = ((len(members),) + tuple(dims[1:])) if members else dims
    return {
        "ok": 1, "kind": COMPOSED, "name": name,
        "members": list(members),
        "dimensionality": shapes.describe(effective, list(members)),
        "provenance": [{"member": member, "from": where.get("from"),
                        "version": where.get("version"),
                        "overrode": where.get("overrode")}
                       for member, where in provenance.items()],
        "ancestry": ancestry,
        "not_checked": [UNCHECKED[0]],
        "detail": f"'{name}' would have {len(members)} component(s): "
                  f"{', '.join(members) or 'none'}",
    }


def _parse_or_declare(body: DefinitionCheckIn, name: str):
    """The expression's inputs, by parse or by declaration.

    Exactly the fork `DerivedFeatures.define` takes: MAYA parses what it can,
    and an `external` definition whose expression it cannot parse falls back to
    the inputs the author declared — so lineage and the leakage check still have
    something to work with where the arithmetic is opaque.
    """
    try:
        parsed = Expression(body.expression)
        return 0, parsed.source, parsed.feature_names(), int(parsed.reads_clock())
    except FeatureError as exc:
        if body.evaluator != EXTERNAL:
            raise
        swallowed(logger, exc, "checked a draft derived expression",
                  detail=f"'{name}' is external and its expression is opaque to "
                         f"MAYA, so the check falls back to the declared inputs, "
                         f"as define does",
                  level=logging.INFO)
        return 1, body.expression.strip(), list(dict.fromkeys(body.inputs)), 0


def _check_derived(features, body: DefinitionCheckIn) -> Dict[str, Any]:
    """What the platform can say about Z = f(X, Y) before it is declared.

    Every refusal below is one `DerivedFeatures.define` raises, in the order it
    raises them, and each is raised by calling what define calls. It is repeated
    here rather than delegated because define writes, and an author needs the
    answer before that.
    """
    name = body.name.strip()
    if not name:
        raise FeatureError("a derived feature needs a name")
    if body.evaluator not in EVALUATORS:
        raise FeatureError(f"evaluator must be one of {', '.join(EVALUATORS)}")
    if body.on_error not in ON_ERROR:
        raise FeatureError(f"on_error must be one of {', '.join(ON_ERROR)}")
    declared = list(dict.fromkeys(body.inputs))
    if declared and body.evaluator != EXTERNAL:
        raise FeatureError(
            f"'{name}' is internal, so its inputs come from its expression; "
            f"declaring them as well gives the leakage check two lists that "
            f"can disagree")
    opaque, source, inputs, reads_clock = _parse_or_declare(body, name)
    if declared and not opaque and set(declared) != set(inputs):
        raise FeatureError(
            f"'{name}' parses, so its inputs are {', '.join(inputs) or 'none'}; "
            f"the declared list says {', '.join(declared)}. Omit it, or leave "
            f"the expression in a form MAYA cannot read")
    if opaque and not inputs:
        raise FeatureError(
            f"'{name}' is external and MAYA cannot parse its expression, so it "
            f"must declare the features it reads — without them there is no "
            f"lineage and no leakage check, which is the whole reason the "
            f"definition is kept")
    if not inputs and not reads_clock:
        raise FeatureError(f"'{name}' reads no features, so it is a constant "
                           f"rather than a derived feature")
    if name in inputs:
        raise FeatureError(f"'{name}' is defined in terms of itself")
    if missing := features.catalogue.missing(inputs):
        raise FeatureError(
            f"undefined inputs: {', '.join(missing)}; a derived feature can "
            f"only read features the catalogue knows about")
    # The cycle guard, over the same transitive closure define walks. A
    # derivation of a derivation of a feature is still that feature.
    for start in inputs:
        if name in features.derived.lineage(start):
            raise FeatureError(f"'{name}' would depend on itself through '{start}'")
    entities = sorted({features.catalogue.require(n)["entity"] for n in inputs})
    if len(entities) > 1:
        raise FeatureError(
            f"inputs span more than one entity ({', '.join(entities)}); a "
            f"derived feature has one grain, so combine them in a view first")
    rests_on = sorted(set(inputs).union(
        *[features.derived.lineage(i) for i in inputs])) if inputs else []
    history = features.derived.history(name)
    return {
        "ok": 1, "kind": DERIVED, "name": name, "expression": source,
        "opaque": opaque, "evaluator": body.evaluator,
        "inputs": inputs, "reads_clock": reads_clock,
        "entity": entities[0] if entities else "unknown",
        "rests_on": rests_on,
        # The meet, not the maximum: deriving from an uncertified feature does
        # not launder it. Shown per input so the weakest one is visible.
        "certification": features.derived.certification_of(inputs),
        "certification_of_inputs": [
            {"name": n,
             "certification": features.catalogue.require(n).get(
                 "certification", "experimental")}
            for n in inputs],
        "certification_order": list(CERTIFICATION_ORDER),
        "definition_version": len(history) + 1,
        "not_checked": list(UNCHECKED),
        "detail": (f"'{name}' would rest on {', '.join(rests_on) or 'the clock alone'}"
                   + (" — and MAYA cannot read the expression, so it records the "
                      "declared inputs and computes nothing"
                      if opaque else "")),
    }


def _trial_expression(body: ExpressionTrialIn) -> Dict[str, Any]:
    """Read a draft expression over rows. Records nothing, decides nothing.

    Two things are worth seeing before a definition exists, and neither is
    visible from the text of an expression:

    * **Where the arithmetic has no answer.** ``log`` of a non-positive number
      and division by zero are nulls, not failures — one bad row must not fail a
      materialisation of a million. ``on_error: refuse`` is the other choice,
      and it refuses the whole load rather than the row, which is why seeing
      which rows would trigger it matters before it is declared.
    * **The inherited ingest clock.** ``ingest_ts(Z) = max(ingest_ts(X), …)``:
      you did not know Z before you knew its inputs. Computed here by
      `DerivedFeatures.knowable_at`, the same function a materialisation uses.
    """
    if body.on_error not in ON_ERROR:
        raise FeatureError(f"on_error must be one of {', '.join(ON_ERROR)}")
    parsed = Expression(body.expression)
    inputs = parsed.feature_names()
    out, nulls, refused = [], 0, 0
    for number, row in enumerate(body.rows, 1):
        entry: Dict[str, Any] = {"row": number,
                                 ENTITY: row.get(ENTITY),
                                 VALID_TIME: row.get(VALID_TIME),
                                 INGEST_TIME: row.get(INGEST_TIME)}
        try:
            value = parsed.evaluate(row)
        except FeatureError as exc:
            # The expression and the row disagree — a name it reads is not
            # there. Reported per row rather than raised, because an author
            # pasting five rows wants to see which one is wrong.
            swallowed(logger, exc, "read a draft expression over a trial row",
                      detail=f"row {number} does not carry every name the "
                             f"expression reads", level=logging.INFO)
            entry.update({"value": None, "refused": 1, "detail": str(exc)})
            refused += 1
            out.append(entry)
            continue
        entry["value"] = value
        if value is None:
            nulls += 1
            entry["refused"] = 1 if body.on_error == "refuse" else 0
            entry["detail"] = (
                "the arithmetic has no answer for this row; on_error says "
                + ("refuse, so a real materialisation would stop here"
                   if body.on_error == "refuse" else "record a null"))
            refused += entry["refused"]
        else:
            entry["refused"] = 0
        entry["knowable_at"] = DerivedFeatures.knowable_at(row, inputs)
        entry["clock_moved"] = int(
            entry["knowable_at"] != (row.get(INGEST_TIME) or 0.0))
        out.append(entry)
    return {
        "expression": parsed.source, "inputs": inputs,
        "reads_clock": int(parsed.reads_clock()),
        "on_error": body.on_error, "rows": out,
        "nulls": nulls, "refused": refused,
        "detail": (f"{len(out)} rows, {nulls} with no answer"
                   + ("; on_error is refuse, so a materialisation would stop "
                      "at the first of them" if nulls and
                      body.on_error == "refuse" else "")),
        "clock_rule": "ingest_ts(Z) = max(ingest_ts of the inputs). Supply "
                      "'<input>__ingest_ts' on a row to see the inherited clock "
                      "move; without one the row's own stamp is the floor",
    }


def _trial_alignment(body: AlignmentTrialIn) -> Dict[str, Any]:
    """Put rows on one axis by a stated rule, and say what the rule did.

    Alignment is where the two clocks stop being bookkeeping. Three of the five
    fill rules answer a gap with an observation from *after* it — which is the
    right answer for drawing a curve and the wrong one for training — and the
    platform does not refuse them. It stamps each filled value with the ingest
    time at which it actually became knowable, so an ordinary point-in-time read
    excludes it without anybody remembering a flag.

    This runs `alignment.align` on rows the caller pasted. Nothing stored is
    aligned, and nothing is written: the endpoint exists so the stamp can be
    *seen* moving before somebody relies on it.
    """
    if not body.rows:
        raise FeatureError("there are no rows to align")
    columns = body.columns or sorted(
        {k for r in body.rows for k in r} - set(RESERVED))
    grid = alignment.grid_for(body.rows, body.axis, body.grid, body.start,
                              body.stop, body.step, body.points)
    result = alignment.align(body.rows, columns, body.axis, body.rule, grid,
                             limit=body.carry_limit)
    return {**result, "columns": columns,
            "means": alignment.RULE_MEANING[body.rule],
            "looks_ahead": int(body.rule in alignment.LOOKS_AHEAD)}


def _verdict(record: Dict[str, Any], label_ts: float,
             as_of: float) -> Dict[str, Any]:
    """Whether this row is admissible, and which clock refused it.

    Every answer is a call to `TrainingSetBuilder.latest_admissible` over a
    one-row set rather than a comparison written here. The rule deciding what a
    model may read is not one this module gets to hold a second copy of, so the
    two "which clock" answers are obtained by asking the operator again with one
    clock pushed infinitely early: whichever substitution fails to rescue the
    row names the clock that refused it.
    """
    admissible = TrainingSetBuilder.latest_admissible(
        [record], label_ts, as_of) is not None
    entry = {ENTITY: record.get(ENTITY), VALID_TIME: record.get(VALID_TIME),
             INGEST_TIME: record.get(INGEST_TIME),
             "admissible": int(admissible)}
    if admissible:
        entry["detail"] = ("true by the decision moment and known by it — the "
                           "latest such row is the one that is read")
        return entry
    too_late_event = TrainingSetBuilder.latest_admissible(
        [{**record, INGEST_TIME: BEFORE_EVERYTHING}], label_ts, as_of) is None
    too_late_ingest = TrainingSetBuilder.latest_admissible(
        [{**record, VALID_TIME: BEFORE_EVERYTHING}], label_ts, as_of) is None
    entry["refused_by_event_clock"] = int(too_late_event)
    entry["refused_by_ingest_clock"] = int(too_late_ingest)
    reasons = []
    if too_late_event:
        reasons.append("it was not yet true at the decision moment")
    if too_late_ingest:
        reasons.append("it was not yet known at min(label_ts, as_of) — the "
                       "platform learned it later than the decision")
    entry["detail"] = "refused: " + "; and ".join(reasons)
    return entry


def _as_of(features, view: str, version: int, body: AsOfIn) -> Dict[str, Any]:
    """The point-in-time read over one view version, explained row by row.

    `AsOf(R, ℓ, a)` takes the latest row true by `ℓ` and known by
    `min(ℓ, a)`. The two bounds refuse different things — `ℓ` is what could have
    been known when the decision was made, `a` is what the platform could have
    known when the set was built — and the `min` is the reproducibility law:
    every `a ≥ ℓ` gives the same answer, so a row assembled the day its label
    matured and the same row re-assembled a year later are identical, however
    many restatements arrived in between.
    """
    pin = features.pinned(view, version)
    page = features.transfer.rows(pin["namespace"], pin["delta_version"],
                                  None, min(body.limit, PROBE_ROWS))
    by_entity: Dict[Any, List[Dict[str, Any]]] = {}
    for record in page["rows"]:
        if body.entity_id and record.get(ENTITY) != body.entity_id:
            continue
        by_entity.setdefault(record.get(ENTITY), []).append(record)
    entities = []
    for key in sorted(by_entity, key=str):
        records = by_entity[key]
        chosen = TrainingSetBuilder.latest_admissible(
            records, body.label_ts, body.as_of)
        entities.append({
            ENTITY: key,
            "candidates": [_verdict(r, body.label_ts, body.as_of)
                           for r in sorted(records,
                                           key=lambda r: (r[VALID_TIME],
                                                          r[INGEST_TIME]))],
            "read": chosen,
            "detail": ("nothing this entity holds was both true and known by "
                       "then, so the feature is null for this row — which is an "
                       "answer, not a gap to be filled"
                       if chosen is None else
                       f"read the row true at {chosen[VALID_TIME]} and known at "
                       f"{chosen[INGEST_TIME]}"),
        })
    return {
        "view": view, "version": version, "namespace": pin["namespace"],
        "delta_version": pin["delta_version"],
        "label_ts": body.label_ts, "as_of": body.as_of,
        # The operator's own definition of the ingest bound, quoted for display.
        # No verdict above is taken from it: those come from the operator.
        "knowable_by": min(body.label_ts, body.as_of),
        "rows_examined": len(page["rows"]), "entities": entities,
        "truncated": int(bool(page.get("truncated"))),
        "operator": "AsOf(R, l, a) = argmax over (event_ts, ingest_ts) of "
                    "{ r in R : r.event_ts <= l and r.ingest_ts <= min(l, a) }",
        "detail": page.get("detail", ""),
    }


class FeatureAuthoringRoutes(Routes):
    """Four pages and four free endpoints: define, load, read, and ask."""

    def register(self) -> None:
        features = self.ctx["features"]

        # ------------------------------------------------------------ define
        @self.app.get("/features/new", response_class=HTMLResponse, tags=["ui"])
        def define_page(request: Request):
            """Declare a feature, primitive or derived, before it has values.

            The declaration comes first because it is what a featureset pins and
            what an owner is accountable for. A view that materialised an
            undeclared column would be a feature nobody owns.
            """
            if (r := login_required(request)) is not None:
                return r
            if not self.may_view(request, "feature:read"):
                return self.refused_page(request, "The feature catalogue")
            catalogue = features.list_features()
            return self.page(
                request, "feature_author_define.html",
                dtypes=list(SUGGESTED_DTYPES),
                catalogue=catalogue,
                derived=features.derived.list() if features.derived else [],
                entities=sorted({f["entity"] for f in catalogue}),
                language=describe_language(),
                composition=describe_composition(),
                policy=retrieval_policy.describe(),
                preparation=describe_preparation(),
                evaluators=list(EVALUATORS), on_error=list(ON_ERROR),
                certification_order=list(CERTIFICATION_ORDER),
                clocks=_clocks(),
                # Whether this person may define is the API's answer, not the
                # page's; this only decides whether to say so up front rather
                # than after they have filled the form in.
                may_define=self.may_view(request, "feature:define"))

        # -------------------------------------------------------------- load
        @self.app.get("/features/load", response_class=HTMLResponse, tags=["ui"])
        def load_page(request: Request):
            """Create a view and put rows in it.

            A feature view is the namespace values live in, and **a version is
            a namespace**: loading again does not touch what an earlier version
            serves. That is why the page shows every version rather than only
            the newest.
            """
            if (r := login_required(request)) is not None:
                return r
            if not self.may_view(request, "feature:read"):
                return self.refused_page(request, "Feature values")
            return self.page(
                request, "feature_author_load.html",
                # The same list the view page offers, from the same place.
                upload_accepts=accept_attribute(),
                catalogue=features.list_features(),
                views=self._views(features),
                uploads=_upload_formats(),
                clocks=_clocks(),
                may_load=self.may_view(request, "feature:materialise"))

        # ----------------------------------------------- the two clocks, live
        @self.app.get("/features/point-in-time", response_class=HTMLResponse,
                      tags=["ui"])
        def point_in_time_page(request: Request):
            """Ask a point-in-time question and see it answered row by row.

            This is the idea the whole feature platform is built around, and
            until now it had no screen: a training row may only read what was
            *true* by the moment of the decision and *known* by then too. Most
            "model failures" are this rule not having been applied.
            """
            if (r := login_required(request)) is not None:
                return r
            if not self.may_view(request, "feature:read"):
                return self.refused_page(request, "Feature values")
            return self.page(
                request, "feature_author_pit.html",
                views=self._views(features),
                alignment=alignment.describe(),
                preparation=describe_preparation(),
                clocks=_clocks(),
                may_assemble=self.may_view(request, "feature:assemble"))

        # ----------------------------------------------------- read it back
        @self.app.get("/feature/{name}", response_class=HTMLResponse, tags=["ui"])
        def feature_page(request: Request, name: str):
            """One feature, and everything the platform can say about it.

            Lineage in both directions, certification and how it was arrived at,
            what would break if it were withdrawn, and the two clocks on every
            version of every view that carries its values.
            """
            if (r := login_required(request)) is not None:
                return r
            if not self.may_view(request, "feature:read"):
                return self.refused_page(request, f"The feature {name}")
            if features.catalogue.get(name) is None:
                return self.page(request, "not_found.html", http_status=404,
                                 what="feature", identifier=name,
                                 back_href="/features", back_label="Back to the feature catalogue")
            derived = features.derived.get(name) if features.derived else None
            return self.page(
                request, "feature_author_feature.html",
                feature=features.catalogue.resolved(name),
                derived=derived,
                history=features.derived.history(name) if derived else [],
                rests_on=self._rests_on(features, name),
                depended_on_by=(features.dependants_of(name)
                                if features.derived else []),
                carried_by=self._carried_by(features, name),
                levels=list(LEVELS),
                certification_order=list(CERTIFICATION_ORDER),
                clocks=_clocks(),
                may_certify=self.may_view(request, "feature:certify"),
                may_seal=self.may_view(request, "feature:seal"),
                may_define=self.may_view(request, "feature:define"))

        # ------------------------------------------------------------- check
        @self.app.post(f"{self.api}/features/check", tags=["features"])
        def check(request: Request, body: DefinitionCheckIn):
            """Would this definition be accepted? Records nothing either way.

            Carries `feature:read` and not `feature:define`, for the reason the
            rule-set editor's check does: requiring the writing permission in
            order to *look* at whether a draft is sound teaches authors to skip
            the step, and the step is what keeps the register clean.
            """
            self.authorise(request, "feature:read")
            if body.kind == DERIVED:
                return self.guard(lambda: _check_derived(features, body))
            if body.kind == COMPOSED:
                return self.guard(lambda: _check_composed(features, body))
            if body.kind != PRIMITIVE:
                raise self.not_found(f"no such kind of definition: {body.kind}")
            return self.guard(lambda: _check_primitive(features, body))

        @self.app.post(f"{self.api}/features/trial", tags=["features"])
        def trial(request: Request, body: ExpressionTrialIn):
            """Read a draft expression over sample rows. Records nothing.

            Where the arithmetic has no answer, and where the inherited ingest
            clock moves. Both are decided by the same functions a real
            materialisation uses.
            """
            self.authorise(request, "feature:read")
            return self.guard(lambda: _trial_expression(body))

        @self.app.post(f"{self.api}/features/alignment-trial", tags=["features"])
        def alignment_trial(request: Request, body: AlignmentTrialIn):
            """Align sample rows by a fill rule, and see what the rule did.

            Nothing stored is aligned. The three rules that answer a gap with a
            later observation are not refused here, because they are not refused
            anywhere: they are stamped with the ingest time at which the filled
            value actually became knowable, and the point-in-time read excludes
            them by the ordinary rule.
            """
            self.authorise(request, "feature:read")
            return self.guard(lambda: _trial_alignment(body))

        @self.app.post(
            f"{self.api}/feature-views/{{name}}/versions/{{version}}/as-of",
            tags=["features"])
        def as_of(request: Request, name: str, version: int, body: AsOfIn):
            """The point-in-time read over stored rows, explained row by row.

            A read and not an assembly: it writes no snapshot, appends no
            evidence and issues no warrant. Asking which row the rule admits is
            not the same act as building a training set out of the answer, and
            conflating them is why nobody looks.
            """
            self.authorise(request, "feature:read")
            return self.guard(lambda: _as_of(features, name, version, body))

    # ------------------------------------------------------------------ util
    @staticmethod
    def _views(features) -> List[Dict[str, Any]]:
        """Every view with its versions, whether each has been written to since
        it was pinned, and whether it could be retired.

        A version that has been restated still serves the bytes it pinned — but
        anybody comparing two runs needs to know the ground moved.
        """
        out = []
        for view in features.views.views.many():
            versions = []
            for v in features.views.versions_of(view["name"]):
                retirable, pinned_by = features.can_retire(view["name"],
                                                           v["version"])
                versions.append({**v,
                                 **features.restated(view["name"], v["version"]),
                                 "retirable": int(retirable),
                                 "pinned_by": pinned_by})
            out.append({**view, "versions": versions,
                        "latest": versions[-1] if versions else None})
        return out

    @staticmethod
    def _rests_on(features, name: str) -> List[Dict[str, Any]]:
        """The transitive closure, each member with its certification.

        Shown with the levels because a derived feature's certification is the
        *meet* of its inputs, and a meet is only legible beside the things it
        was taken over.
        """
        if features.derived is None:
            return []
        out = []
        for parent in features.lineage(name):
            row = features.catalogue.get(parent) or {}
            out.append({"name": parent,
                        "certification": row.get("certification", "unknown"),
                        "entity": row.get("entity", ""),
                        "derived": int(features.derived.is_derived(parent))})
        return out

    @staticmethod
    def _carried_by(features, name: str) -> List[Dict[str, Any]]:
        """The view versions whose rows hold this feature.

        A view's columns are recorded per *version* rather than on the view,
        because a later version may carry a column an earlier one did not. So
        this is a question about versions and is answered one version at a time.
        """
        out = []
        for view in features.views.views.many():
            for version in features.views.versions_of(view["name"]):
                if name not in (version.get("features") or []):
                    continue
                quality = (version.get("quality_report") or {}).get(name, {})
                retirable, pinned_by = features.can_retire(view["name"],
                                                           version["version"])
                out.append({"view": view["name"], "entity": view["entity"],
                            "version": version["version"],
                            "row_count": version["row_count"],
                            "valid_time_column": version["valid_time_column"],
                            "ingest_time_column": version["ingest_time_column"],
                            "null_rate": quality.get("null_rate"),
                            "distinct": quality.get("distinct"),
                            "retirable": int(retirable), "pinned_by": pinned_by,
                            **features.restated(view["name"],
                                                version["version"])})
        return out


def _clocks() -> Dict[str, str]:
    """The column names, from the vocabulary every feature module shares."""
    return {"entity": ENTITY, "valid_time": VALID_TIME,
            "ingest_time": INGEST_TIME}
