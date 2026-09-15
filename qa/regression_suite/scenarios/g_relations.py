"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the edges between models, and the two questions computed from them.

`g_composition.py` covers the algebra of composing a model DEFINITION.
This covers the graph of models standing to one another, which is a different
object with a different failure: a blast radius is what somebody consults to
decide how much care a change needs, so an answer that is too LARGE is as
damaging as one that is too small — a challenger counted as downstream inflates
every radius it appears in until nobody reads them.

The composite cases at the end are about the boundary MAYA will not cross. A
composite is resolved node by node and there is no single signed descriptor for
the whole, because signing one would be MAYA asserting something about a
pipeline it does not run.
"""
from __future__ import annotations

from core.registry.composition import (CHALLENGER_OF, INPUT_TO, KINDS,
                                       PROPAGATING)
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of,
                                                  refused_by_the_control)

M = "/api/v1/models"
REL = "/api/v1/model-relations"
BLAST = "/api/v1/blast-radius"
SHARED = "/api/v1/shared-dependencies"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("rel")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    return urn


def _relate(ctx: Ctx, source: str, target: str, kind: str = INPUT_TO):
    return ctx.api.post(REL, json={"from_urn": source, "to_urn": target,
                                   "kind": kind, "note": "a QA edge"},
                        auth=ctx.people["owner"])


def _radius(ctx: Ctx, body):
    return ctx.api.post(BLAST, json=body, auth=ctx.people["owner"])


@case("QA-FX-1100", "An edge from a model that does not exist")
def fx_1100(ctx: Ctx) -> Result:
    """Both ends are required to exist. An edge from a phantom is a dependency
    in every graph and a model on no register — and `blast_radius` walking it
    would name something nobody can look up."""
    return refused_by_the_control(
        _relate(ctx, f"maya://model/{ctx.unique('absent')}", _model(ctx)),
        "an edge was recorded from a model that is not registered, so the "
        "dependency graph names something nobody can look up")


@case("QA-FX-1101", "An edge of a kind that is not one")
def fx_1101(ctx: Ctx) -> Result:
    """The vocabulary is closed because the kinds do DIFFERENT WORK: only
    `input_to` and `calibrated_by` propagate. An unrecognised kind stored as
    itself would be followed by nothing and appear on no radius, so the
    dependency would be recorded and invisible."""
    got = _relate(ctx, _model(ctx), _model(ctx), kind="sort_of_related_to")
    answer = refused_by_the_control(
        got, "an edge of an unrecognised kind was recorded, so a dependency "
             "exists in the register and propagates to nothing")
    if answer[0] != PASS:
        return answer
    if INPUT_TO not in got.text:
        return FAIL, f"refused '{code_of(got)}' without naming the kinds"
    return PASS, f"refused '{code_of(got)}', naming the {len(KINDS)} kinds"


@case("QA-FX-1102", "A model composed with itself")
def fx_1102(ctx: Ctx) -> Result:
    """A one-node cycle. Walked, it never terminates or terminates at the
    depth cap and reports the model as its own downstream — so a change to it
    would be recorded as reaching itself."""
    urn = _model(ctx)
    return refused_by_the_control(
        _relate(ctx, urn, urn),
        "a model was recorded as an input to itself, so it appears in its own "
        "blast radius")


@case("QA-FX-1103", "A cycle across two models")
def fx_1103(ctx: Ctx) -> Result:
    """Refused at the point the cycle would CLOSE, which is the only place it
    can be refused: the first edge is legitimate and only the second makes the
    pair circular."""
    a, b = _model(ctx), _model(ctx)
    first = _relate(ctx, a, b)
    if first.status_code >= 400:
        return BLOCKED, f"the first edge was refused: {first.text[:130]}"
    return refused_by_the_control(
        _relate(ctx, b, a),
        "two models were recorded as inputs to each other, so the graph is "
        "circular and every walk over it depends on where it started")


@case("QA-FX-1104", "Blast radius with no urn")
def fx_1104(ctx: Ctx) -> Result:
    """`body["urn"]` was a bare KeyError here and therefore a 500 with no body
    — a caller who forgot the field was told nothing about what they had
    forgotten. The refusal names the field AND shows the shape."""
    got = _radius(ctx, {})
    if got.status_code >= 500:
        return FAIL, (f"{got.status_code} — the absent field is still a bare "
                      f"error: {got.text[:130]}")
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "a blast radius was computed from no model at all"
    if "maya://model/" not in got.text:
        return FAIL, (f"refused '{code_of(got)}' without showing the body that "
                      f"would work: {got.text[:120]}")
    return PASS, f"refused '{code_of(got)}', showing the shape"


@case("QA-FX-1105", "Blast radius over a model that does not exist")
def fx_1105(ctx: Ctx) -> Result:
    """An empty radius and a radius over nothing must not print the same. *No
    model downstream* is the answer that lets a change go ahead."""
    got = _radius(ctx, {"urn": f"maya://model/{ctx.unique('absent')}"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, (f"a blast radius over an unregistered model answered "
                      f"{got.status_code}: {got.text[:120]} — which reads as "
                      f"'nothing downstream', the answer that lets a change go "
                      f"ahead")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-FX-1106", "Blast radius follows only propagating relations")
def fx_1106(ctx: Ctx) -> Result:
    """The property the number is worth having for. A challenger is not
    downstream of the model it argues with: counting it inflates the answer
    precisely where the answer decides how much care a change needs, and a
    radius nobody believes is a radius nobody consults."""
    source, downstream, challenger = _model(ctx), _model(ctx), _model(ctx)
    if _relate(ctx, source, downstream, INPUT_TO).status_code >= 400:
        return BLOCKED, "the propagating edge could not be recorded"
    argued = _relate(ctx, source, challenger, CHALLENGER_OF)
    if argued.status_code >= 400:
        return BLOCKED, f"the challenger edge was refused: {argued.text[:120]}"
    got = _radius(ctx, {"urn": source})
    if got.status_code >= 400:
        return BLOCKED, f"the radius answered {got.status_code}"
    reached = {r.get("urn") for r in (got.json() or {}).get("reaches") or []}
    if downstream not in reached:
        return FAIL, (f"an `{INPUT_TO}` edge was recorded and the downstream "
                      f"model is not in the radius: {sorted(reached)}")
    if challenger in reached:
        return FAIL, (f"a `{CHALLENGER_OF}` edge put the challenger in the "
                      f"blast radius, so every radius is inflated by the "
                      f"models that merely argue with it "
                      f"(propagating: {sorted(PROPAGATING)})")
    return PASS, (f"the downstream model is reached and the challenger is "
                  f"not; {len(reached)} model(s) in the radius")


@case("QA-FX-1107", "Shared dependencies over an empty list")
def fx_1107(ctx: Ctx) -> Result:
    """Nothing is shared by nobody, and the honest answer is an empty set with
    a sentence — not an error, and certainly not the set of everything that is
    depended on by two models SOMEWHERE in the estate."""
    got = ctx.api.post(SHARED, json={"urns": []}, auth=ctx.people["owner"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    body = got.json() or {}
    shared = body.get("shared")
    if shared:
        return FAIL, (f"asking what NO models share answered with "
                      f"{len(shared)} dependenc(ies), so the empty list is "
                      f"being read as the whole estate")
    if not str(body.get("detail") or "").strip():
        return FAIL, "an empty answer with nothing saying what was asked"
    return PASS, f"empty, and says so: {str(body.get('detail'))[:90]}"


@case("QA-FX-1108", "A composite refuses if any node refuses")
def fx_1108(ctx: Ctx) -> Result:
    """All or nothing, and it has to be nothing. A composite that resolved the
    nodes it could and reported partial success would hand back a pipeline
    authorisation with a hole in it — and the hole is exactly the model that
    was blocked.

    Asked through `check`, which is the endpoint a caller uses to find out, and
    which answers rather than raising. The refusal must NAME the node: *the
    chain does not resolve* sends somebody to look at five models.
    """
    upstream, terminal = _model(ctx), _model(ctx)
    if _relate(ctx, upstream, terminal, INPUT_TO).status_code >= 400:
        return BLOCKED, "the chain could not be built"
    # Block the upstream node and nothing else.
    blocked = ctx.api.post("/api/v1/findings",
                           json={"urn": upstream, "severity": "Critical",
                                 "title": "a QA blocking finding",
                                 "owner": "person/owner", "description": "qa",
                                 "category": "general", "source": "validation",
                                 "blocking": True},
                           auth=ctx.people["risk"])
    if blocked.status_code >= 400:
        return BLOCKED, f"the upstream node could not be blocked: {blocked.text[:120]}"
    got = ctx.api.post("/api/v1/composites/check",
                       json={"terminal": terminal, "environment": "prod",
                             "principal": "svc/qa",
                             "declared_use": "credit_decision"},
                       auth=ctx.people["owner"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' for the whole chain"
    body = got.json() or {}
    if body.get("resolves"):
        return FAIL, (f"a chain whose upstream node carries an open blocking "
                      f"finding reports `resolves: true`, so the pipeline "
                      f"authorisation has a hole exactly where the block is: "
                      f"{got.text[:130]}")
    if upstream not in got.text:
        return FAIL, (f"the chain does not resolve and the answer does not "
                      f"name which node: {got.text[:140]}")
    return PASS, (f"`resolves: false`, naming the blocked node and "
                  f"'{body.get('error')}'")


@case("QA-FX-1109", "A composite has no single signed descriptor")
def fx_1109(ctx: Ctx) -> Result:
    """The boundary, and it is deliberate. Signing one descriptor for a chain
    would assert that the chain AS A WHOLE is authorised, and nothing
    established that — MAYA does not run the pipeline and cannot see the
    arrangement the nodes sit in. So a resolution is a SET of descriptors, each
    signed for the model it is about, and the absence of a composite signature
    is the honest part of the answer rather than a gap in it.
    """
    upstream, terminal = _model(ctx), _model(ctx)
    if _relate(ctx, upstream, terminal, INPUT_TO).status_code >= 400:
        return BLOCKED, "the chain could not be built"
    got = ctx.api.post("/api/v1/composites/resolve",
                       json={"terminal": terminal, "environment": "prod",
                             "principal": "svc/qa",
                             "declared_use": "credit_decision"},
                       auth=ctx.people["owner"])
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code >= 400:
        # Refused for a governance reason — the chain is ungranted. The claim
        # under test is about the SHAPE of a resolution, so read the published
        # chain instead and assert the same thing about what it promises.
        chain = ctx.api.get(f"/api/v1/composites?urn={terminal}",
                            auth=ctx.people["owner"])
        if chain.status_code >= 400:
            return BLOCKED, (f"the chain would not resolve "
                             f"('{code_of(got)}') and could not be read")
        if "signature" in chain.text.lower():
            return FAIL, (f"the chain publishes a signature over the whole: "
                          f"{chain.text[:130]}")
        return PASS, (f"the chain does not resolve here ('{code_of(got)}') and "
                      f"publishes no composite signature")
    body = got.json() or {}
    nodes = body.get("nodes") or []
    if not isinstance(nodes, list) or not nodes:
        return FAIL, f"a resolution that is not a set of nodes: {got.text[:130]}"
    for key in ("signature", "composite_signature", "maya_warrant"):
        if key in body:
            return FAIL, (f"the composite itself carries '{key}', which asserts "
                          f"the chain as a whole is authorised — and nothing "
                          f"established that")
    unsigned = [n.get("urn") for n in nodes
                if not ((n.get("warrant") or n).get("signature")
                        or (n.get("warrant") or n).get("maya_warrant"))]
    if unsigned:
        return FAIL, (f"{len(unsigned)} node(s) in the chain came back without "
                      f"a descriptor of their own: {unsigned[:3]}")
    return PASS, (f"{len(nodes)} per-node descriptor(s) and no signature over "
                  f"the composite")
