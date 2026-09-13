"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — compiled documents.

A document is the register rendered for somebody to read, and the property
that makes it worth anything is that **two renderings of unchanged state are
identical**. Everything downstream — has this changed since the board saw it,
are these review comments still about this document, do two export packs
agree — rests on that one claim.
"""
from __future__ import annotations

from tools.qa.scenarios.common import (BLOCKED, FAIL, PASS, Ctx, Result, case,
                                       expect_refused)

KIND = "model_development_document"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _subject(ctx: Ctx) -> str:
    name = ctx.unique("doc")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    return urn


def _compile(ctx: Ctx, urn: str, kind: str = KIND):
    return ctx.api.post("/api/v1/documents",
                        params={"urn": urn, "kind": kind})


@case("QA-PLT-123", "Compile twice with nothing changed — digests identical")
def plt_123(ctx: Ctx) -> Result:
    """The compiler's own docstring promises this, and it was false.

    Compiling appended a `document_compiled` node against the model, so the
    next compile found it in the model's evidence and cited it — a different
    citation list, and therefore a different digest, every time.
    """
    urn = _subject(ctx)
    first, second = _compile(ctx, urn), _compile(ctx, urn)
    if first.status_code >= 400 or second.status_code >= 400:
        return BLOCKED, f"{first.status_code}/{second.status_code}"
    a, b = first.json().get("digest"), second.json().get("digest")
    if a != b:
        return FAIL, (f"two renderings of unchanged state differ: "
                      f"{str(a)[:24]} vs {str(b)[:24]} — every downstream "
                      f"'has this changed' answers yes forever")
    return PASS, f"identical: {str(a)[:30]}"


@case("QA-PLT-124", "Compile five times and count the citations")
def plt_124(ctx: Ctx) -> Result:
    urn = _subject(ctx)
    counts = []
    for _ in range(5):
        got = _compile(ctx, urn)
        if got.status_code >= 400:
            return BLOCKED, got.text[:150]
        counts.append(len(got.json().get("citations") or []))
    if len(set(counts)) != 1:
        return FAIL, (f"the citation list grew because somebody pressed the "
                      f"button: {counts} — provenance documenting the act of "
                      f"documenting")
    return PASS, f"stable at {counts[0]} citation(s) across five compiles"


@case("QA-PLT-125", "Recompile with open review comments")
def plt_125(ctx: Ctx) -> Result:
    """Comments are keyed on the document, so a recompile that changes nothing
    must not orphan them."""
    urn = _subject(ctx)
    first = _compile(ctx, urn)
    if first.status_code >= 400:
        return BLOCKED, first.text[:150]
    document_id = first.json()["id"]
    # `document_id` is a QUERY parameter and the field is `body`, not
    # `comment` — the first version of this invented both and recorded
    # BLOCKED against a shape that never existed.
    raised = ctx.api.post("/api/v1/document-review",
                          params={"document_id": document_id},
                          json={"section": "methodology",
                                "asks_for": "clarification",
                                "body": "QA comment"})
    if raised.status_code >= 400:
        return BLOCKED, f"could not raise a comment: {raised.text[:150]}"
    _compile(ctx, urn)
    review = ctx.api.get("/api/v1/document-review",
                         params={"document_id": document_id})
    if review.status_code >= 400:
        return BLOCKED, review.text[:150]
    # The COUNT, not the field name. The first version of this searched the
    # response text for "earlier_version" — which is the name of the field
    # reporting zero of them — and reported a defect for the platform saying
    # nothing was orphaned.
    body = review.json()
    orphaned = body.get("raised_against_an_earlier_version", 0)
    if orphaned:
        return FAIL, (f"a recompile that changed nothing orphaned {orphaned} "
                      f"comment(s) onto an earlier version")
    second = _compile(ctx, urn)
    if second.status_code < 400 and second.json().get("id") != document_id:
        return FAIL, ("the recompile authored a second document with "
                      "identical content, so the comments are against a "
                      "document nobody is looking at")
    return PASS, f"{body.get('open')} comment(s) still on this document"


@case("QA-PLT-126", "Two export packs of unchanged state agree")
def plt_126(ctx: Ctx) -> Result:
    """The packer renders where the API compiles. Two paths to 'has this
    changed', and only one of them can be right."""
    urn = _subject(ctx)
    _compile(ctx, urn)
    # A pack is cut at `POST /export-packs/{name}`; the collection is a GET.
    name = urn.rsplit("/", 1)[-1]
    first = ctx.api.post(f"/api/v1/export-packs/{name}")
    second = ctx.api.post(f"/api/v1/export-packs/{name}")
    if first.status_code >= 400:
        return BLOCKED, f"packs unavailable: {first.status_code} " \
                        f"{first.text[:120]}"
    a = first.headers.get("x-pack-content-digest")
    b = second.headers.get("x-pack-content-digest")
    if a is None:
        return BLOCKED, "the pack carries no content digest header"
    if a != b:
        return FAIL, f"two packs of unchanged state disagree: {a} vs {b}"
    return PASS, f"stable: {a[:30]}"


@case("QA-PLT-127", "An unknown kind against an unknown URN")
def plt_127(ctx: Ctx) -> Result:
    """The kind is checked before the context is built, so a caller who fixed
    the URN first would keep getting the same 422 and never learn the URN was
    also wrong. Either order is defensible; what is not is a 500."""
    got = ctx.api.post("/api/v1/documents",
                       params={"urn": "maya://model/qa.nope",
                               "kind": "nonsense"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    return expect_refused(got, "unknown_document_kind", "registry_refused",
                          "not_found", "unknown_kind")


@case("QA-PLT-128", "A bare model, compiled anyway")
def plt_128(ctx: Ctx) -> Result:
    """A document that refuses to compile teaches people to stop compiling;
    one that compiles and hides its holes is worse."""
    got = _compile(ctx, _subject(ctx))
    if got.status_code >= 400:
        return FAIL, (f"a bare model could not be documented at all: "
                      f"{got.text[:150]}")
    coverage = got.json().get("coverage") or {}
    if coverage.get("complete"):
        return FAIL, ("a model with nothing recorded reports complete "
                      "coverage — the document hides its own holes")
    unfilled = [s for s in got.json().get("sections", []) if not s["filled"]]
    if not unfilled:
        return FAIL, "every section rendered as filled over an empty register"
    return PASS, (f"coverage.complete is false, {len(unfilled)} section(s) "
                  f"marked unfillable")


@case("QA-PLT-130", "Compile against a model that does not exist")
def plt_130(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post("/api/v1/documents",
                     params={"urn": "maya://model/qa.never", "kind": KIND}),
        "registry_refused", "not_found")


@case("QA-PLT-131", "Read a document that does not exist")
def plt_131(ctx: Ctx) -> Result:
    got = ctx.api.get("/api/v1/documents/qa-never")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an unknown document id returned a document"
    return PASS, f"refused ({got.status_code})"


@case("QA-PLT-132", "The published list of document kinds is closed")
def plt_132(ctx: Ctx) -> Result:
    got = ctx.api.get("/api/v1/document-kinds")
    if got.status_code >= 400:
        return FAIL, got.text[:150]
    kinds = {k["kind"] for k in got.json().get("kinds", [])}
    if KIND not in kinds:
        return FAIL, f"{KIND} is not among the published kinds"
    return PASS, f"{len(kinds)} kinds published"
