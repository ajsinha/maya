"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — compiling a document out of the register.

**Rendering and compiling are different acts.** Compiling AUTHORS a document
and records that it was authored; rendering says what it would contain and
writes nothing. Cutting an export pack monthly must not silently author four
documents a month, and a pack whose own production changed the record would
differ from the last one for no reason but that somebody had asked for it.

A rendering therefore carries no moment of its own: the digest is over the
kind, the subject and the sections, so two renderings of unchanged state are
identical.

**Staleness is computed from the chain rather than remembered**, so a document
cannot be stale without the platform being able to say so — and it is measured
across the model AND its versions, because reading the model's id alone let a
new version go through a full quorum approval while the document reported that
nothing had happened.
"""
from __future__ import annotations

from core.docs.common import KINDS
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

D = "/api/v1/documents"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _docs(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("documents")


def _model(ctx: Ctx, *, version: bool = True) -> tuple:
    name = ctx.unique("dc")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE},
                 auth=ctx.people["owner"])
    if version:
        ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                     auth=ctx.people["developer"])
    return name, urn


def _compile(ctx: Ctx, urn: str, kind: str):
    return ctx.api.post(f"{D}?urn={urn}&kind={kind}", auth=ctx.people["risk"])


@case("QA-PLT-4930", "Rendering writes nothing and records nothing")
def plt_4930(ctx: Ctx) -> Result:
    """The separation the module exists around. An export pack cut monthly
    must not author four documents a month, and a pack whose own production
    changed the record would differ from the last one for no reason but that
    somebody asked for it."""
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    _name, urn = _model(ctx)
    kind = KINDS[0]
    before = len(docs.documents.many())
    evidence = ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")
    chain_before = evidence.head()[0] if evidence else None
    rendered = docs.render(kind, urn)
    if not rendered.get("sections"):
        return FAIL, "a rendering produced no sections"
    if len(docs.documents.many()) != before:
        return FAIL, "a rendering authored a document"
    if evidence and evidence.head()[0] != chain_before:
        return FAIL, "a rendering appended to the evidence chain"
    if "compiled_at" in rendered:
        return FAIL, ("a rendering carries a compiled_at, so it has a moment "
                      "of its own and two renderings differ by when they ran")
    return PASS, f"{len(rendered['sections'])} sections, nothing written"


@case("QA-PLT-4931", "Two renderings of unchanged state are identical")
def plt_4931(ctx: Ctx) -> Result:
    """The digest is over the kind, the subject and the sections — not over
    the moment. Two renderings that differed would make an export pack
    differ from the last one every time it was cut."""
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    _name, urn = _model(ctx)
    kind = KINDS[0]
    first = docs.render(kind, urn)
    second = docs.render(kind, urn)
    if first["digest"] != second["digest"]:
        return FAIL, (f"two renderings of unchanged state gave "
                      f"{first['digest'][:16]} and {second['digest'][:16]}")
    if first != second:
        differing = [k for k in first if first[k] != second.get(k)]
        return FAIL, f"two renderings differ on {differing}"
    return PASS, f"identical, digest {first['digest'][:20]}"


@case("QA-PLT-133", "A compiled document that cites nothing")
def plt_133(ctx: Ctx) -> Result:
    """`sound: true` over zero citations, and that is right: soundness is
    *every cited node resolves*, which is vacuously true of none. What must
    NOT happen is the count being hidden — a document citing nothing and one
    citing forty resolving citations both report sound, and only the count
    tells them apart."""
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    _name, urn = _model(ctx)
    made = _compile(ctx, urn, KINDS[0])
    if made.status_code >= 400:
        return BLOCKED, f"the compile failed: {made.text[:140]}"
    document_id = (made.json() or {}).get("id")
    report = docs.verify_citations(document_id)
    if not report.get("sound"):
        return FAIL, f"a fresh document is not sound: {report}"
    if "cited" not in report:
        return FAIL, ("the citation report does not carry a count, so a "
                      "document citing nothing reads like one citing forty")
    if report.get("dangling"):
        return FAIL, f"a fresh document has dangling citations: {report['dangling']}"
    return PASS, f"sound over {report['cited']} citation(s), count reported"


@case("QA-PLT-4932", "A citation to an evidence node that does not exist")
def plt_4932(ctx: Ctx) -> Result:
    """The other side. Soundness is a real check and must fail when a cited
    node is not there — a document whose citations do not resolve is one
    whose claims cannot be followed back."""
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    _name, urn = _model(ctx)
    made = _compile(ctx, urn, KINDS[0])
    if made.status_code >= 400:
        return BLOCKED, f"the compile failed: {made.text[:140]}"
    document_id = (made.json() or {}).get("id")
    row = docs.require(document_id)
    docs.documents.set({"citations": ["evidence-nobody-wrote"]},
                       id=document_id)
    report = docs.verify_citations(document_id)
    docs.documents.set({"citations": row["citations"]}, id=document_id)
    if report.get("sound"):
        return FAIL, ("a document citing a node that does not exist reports "
                      "itself sound, so a claim nobody can follow back reads "
                      "as evidenced")
    if "evidence-nobody-wrote" not in (report.get("dangling") or []):
        return FAIL, f"the dangling citation is not named: {report}"
    if "do not resolve" not in (report.get("detail") or ""):
        return FAIL, f"the detail does not say what is wrong: {report.get('detail')}"
    return PASS, "not sound, and the dangling citation is named"


@case("QA-PLT-4933",
      "Staleness is measured across the model and its versions")
def plt_4933(ctx: Ctx) -> Result:
    """The recorded defect. Staleness read the model's id alone, so creating
    a new version and taking it through a full quorum approval left the
    document reporting *nothing has been recorded since it was compiled* —
    and the worklist derives its stale-document item from this, so the item
    never appeared on anybody's dashboard either."""
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    name, urn = _model(ctx)
    made = _compile(ctx, urn, KINDS[0])
    if made.status_code >= 400:
        return BLOCKED, f"the compile failed: {made.text[:140]}"
    document_id = (made.json() or {}).get("id")
    fresh = docs.staleness(document_id)
    if fresh.get("stale"):
        return BLOCKED, f"the document is stale before anything happened: {fresh}"
    added = ctx.api.post(f"{M}/{name}/versions", json={"semver": "2.0.0"},
                         auth=ctx.people["developer"])
    if added.status_code >= 400:
        return BLOCKED, f"the version could not be added: {added.text[:140]}"
    after = docs.staleness(document_id)
    if not after.get("stale"):
        held = docs.require(document_id).get("subjects") or []
        return FAIL, (
            f"a new version left the document reporting that nothing has been "
            f"recorded since it was compiled. `subjects` is captured AT "
            f"COMPILE TIME ({len(held)} id(s)) and `version_created` is "
            f"recorded against the NEW version's id, which is not in it — so "
            f"the fix that widened staleness from the model alone to the "
            f"model and its versions still cannot see a version created "
            f"afterwards, which is the case the defect was reported for. The "
            f"worklist derives its stale-document item from this, so the item "
            f"never appears on anybody's dashboard either")
    if not after.get("kinds_since"):
        return FAIL, "the document is stale and nothing says what happened"
    return PASS, (f"stale after {after['events_since']} event(s): "
                  f"{after['kinds_since']}")


@case("QA-PLT-4934", "A document is not made stale by its own compilation")
def plt_4934(ctx: Ctx) -> Result:
    """`document_compiled` is excluded from the staleness walk. Without that
    every document would be stale the instant it was written, and the signal
    would mean nothing."""
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    _name, urn = _model(ctx)
    first = _compile(ctx, urn, KINDS[0])
    if first.status_code >= 400:
        return BLOCKED, f"the compile failed: {first.text[:140]}"
    document_id = (first.json() or {}).get("id")
    if docs.staleness(document_id).get("stale"):
        return FAIL, "a document is stale the instant it is compiled"
    second = _compile(ctx, urn, KINDS[1] if len(KINDS) > 1 else KINDS[0])
    if second.status_code >= 400:
        return BLOCKED, "the second compile failed"
    after = docs.staleness(document_id)
    if after.get("stale") and after.get("kinds_since") == ["document_compiled"]:
        return FAIL, ("compiling a SECOND document made the first stale, so "
                      "documenting a model invalidates its documentation")
    return PASS, "a compilation does not stale a document, its own or another's"


@case("QA-PLT-153",
      "A pack requesting a document kind that does not exist")
def plt_153(ctx: Ctx) -> Result:
    """Refused by name at the compiler, and the refusal lists the kinds —
    a caller who guessed is one keystroke from the right one."""
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    from core.docs.common import DocumentError
    _name, urn = _model(ctx)
    try:
        docs.render("a-kind-nobody-defined", urn)
    except DocumentError as exc:
        if getattr(exc, "code", "") != "unknown_document_kind":
            return FAIL, f"refused '{getattr(exc, 'code', exc)}'"
        said = f"{exc} {getattr(exc, 'remediation', '')}"
        missing = [k for k in KINDS if k not in said]
        if missing:
            return FAIL, f"the refusal does not name {missing}"
        return PASS, f"refused, naming all {len(KINDS)} kinds"
    return FAIL, "a document kind that is not one was rendered"


@case("QA-PLT-4935", "A required section nothing can fill")
def plt_4935(ctx: Ctx) -> Result:
    """The section is PRESENT with a gap note rather than omitted, and it is
    counted under `missing_required` so the document reports itself
    incomplete. A missing section silently dropped is a document that reads
    as finished."""
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    _name, urn = _model(ctx, version=False)
    rendered = docs.render(KINDS[0], urn)
    unfilled = [s for s in rendered["sections"] if not s["filled"]]
    if not unfilled:
        return BLOCKED, ("a bare model fills every section, so there is no "
                         "gap to inspect")
    for section in unfilled:
        if not (section.get("body") or "").strip():
            return FAIL, (f"section '{section['key']}' is unfilled and its "
                          f"body is empty, so it reads as a section with "
                          f"nothing to say rather than one nothing could fill")
        if "heading" not in section:
            return FAIL, f"section '{section['key']}' carries no heading"
    coverage = rendered.get("coverage") or {}
    required_gaps = [s["key"] for s in unfilled if s["required"]]
    if sorted(coverage.get("missing_required") or []) != sorted(required_gaps):
        return FAIL, (f"the coverage reports {coverage.get('missing_required')} "
                      f"missing and the sections show {required_gaps}")
    if required_gaps and coverage.get("complete"):
        return FAIL, "a document with unfilled required sections reports complete"
    if coverage.get("sections") != len(rendered["sections"]):
        return FAIL, "the coverage count disagrees with the sections"
    return PASS, (f"{len(unfilled)} unfilled of {coverage['sections']}, each "
                  f"present with a gap note, complete={coverage.get('complete')}")


@case("QA-PLT-4936", "Compiling records the act and the chain head it saw")
def plt_4936(ctx: Ctx) -> Result:
    """Compiling is an act. It writes the document, appends to the chain, and
    stores the head it was compiled against — which is what makes staleness
    computable rather than remembered."""
    docs = _docs(ctx)
    evidence = ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")
    if docs is None or evidence is None:
        return BLOCKED, "the compiler or the evidence engine is not wired"
    _name, urn = _model(ctx)
    before = evidence.head()[0]
    made = _compile(ctx, urn, KINDS[0])
    if made.status_code >= 400:
        return BLOCKED, f"the compile failed: {made.text[:140]}"
    body = made.json() or {}
    if evidence.head()[0] <= before:
        return FAIL, "compiling a document appended nothing to the chain"
    if not body.get("compiled_at"):
        return FAIL, "the document records no moment of compilation"
    if not body.get("compiled_by"):
        return FAIL, "the document records no author"
    head = body.get("evidence_head")
    if head is None:
        return FAIL, ("the document does not record the chain head it saw, so "
                      "staleness has nothing to measure against")
    if head < before:
        return FAIL, (f"the recorded head {head} predates the chain at compile "
                      f"time ({before})")
    return PASS, (f"authored by {body['compiled_by']} against head {head}")
