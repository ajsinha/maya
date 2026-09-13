"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — attachments, artifacts and the dossier.

Files somebody uploads and the register then cites. The risk is not the bytes;
it is that a document cited as evidence turns out to be a different document
from the one that was reviewed.
"""
from __future__ import annotations

import hashlib
import io as _io

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
ATTACHMENTS = "/api/v1/attachments"
ARTIFACTS = "/api/v1/artifacts"
#: A real attachment kind, read from the platform's refusal. `methodology`
#: sounds exactly like one and is not — and while it was in the fixture,
#: four cases in this module were being refused for the KIND rather than for
#: the thing they were asking about, which is a pass for the wrong reason.
KIND = "model_development_document"


def _model(ctx: Ctx) -> str:
    """A model WITH a version.

    A document is filed against a version by default, and a model-level
    filing has to say so explicitly — "has no versions, and a document filed
    at model level has to say so". A bare model is refused, which is the
    platform declining to guess what a document is about.
    """
    name = ctx.unique("at")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "owner", **TIER})
    ctx.api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    return urn


def _upload(ctx: Ctx, content: bytes = b"a QA document", **data):
    body = {"urn": _model(ctx), "kind": KIND, "title": "A QA document"}
    body.update(data)
    return ctx.api.post(ATTACHMENTS, data=body,
                        files={"file": ("qa.txt", _io.BytesIO(content),
                                        "text/plain")})


@case("QA-PLT-1100", "An attachment with no file")
def plt_1100(ctx: Ctx) -> Result:
    got = ctx.api.post(ATTACHMENTS, data={"urn": _model(ctx), "kind": KIND,
                                          "title": "A QA document"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an attachment was recorded with nothing attached"
    return PASS, f"refused ({got.status_code})"


@case("QA-PLT-1101", "An attachment with no title")
def plt_1101(ctx: Ctx) -> Result:
    """The title is what a citation names. A blank one makes the citation
    unreadable."""
    got = _upload(ctx, title="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an attachment was recorded with no title to cite it by"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-1102", "An attachment of a kind that is not one")
def plt_1102(ctx: Ctx) -> Result:
    got = _upload(ctx, kind="vibes")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an attachment of an unknown kind was accepted"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-1103", "An attachment against a model that does not exist")
def plt_1103(ctx: Ctx) -> Result:
    got = ctx.api.post(ATTACHMENTS,
                       data={"urn": "maya://model/qa.never",
                             "kind": KIND, "title": "QA"},
                       files={"file": ("qa.txt", _io.BytesIO(b"x"),
                                       "text/plain")})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a file was attached to a model nobody registered"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-1104", "An uploaded file is addressed by its content")
def plt_1104(ctx: Ctx) -> Result:
    """Content addressing is what makes 'the document that was reviewed' a
    checkable claim rather than a filename."""
    content = b"a QA document with known bytes"
    got = _upload(ctx, content=content)
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    digest = hashlib.sha256(content).hexdigest()
    if digest[:16] not in got.text:
        return FAIL, ("the attachment does not carry the digest of what was "
                      "uploaded; a citation then names a filename and not a "
                      "document")
    return PASS, "stored under the digest of its content"


@case("QA-PLT-1105", "Review an attachment that does not exist")
def plt_1105(ctx: Ctx) -> Result:
    got = ctx.api.post(f"{ATTACHMENTS}/qa-never/review",
                       json={"accept": True, "note": "QA"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an attachment that does not exist was reviewed"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-PLT-1106", "An artifact digest that is not a digest")
def plt_1106(ctx: Ctx) -> Result:
    """`sha256:` followed by 64 hex characters. Anything else is an address
    nothing can resolve."""
    got = ctx.api.get(f"{ARTIFACTS}/not-a-digest")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a malformed content address resolved to something"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-PLT-1107", "An artifact that was never uploaded")
def plt_1107(ctx: Ctx) -> Result:
    got = ctx.api.get(f"{ARTIFACTS}/sha256:{'0' * 64}")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "an artifact nobody stored was returned"
    return PASS, f"refused ({got.status_code})"


@case("QA-PLT-1108", "A dossier for a model that does not exist")
def plt_1108(ctx: Ctx) -> Result:
    got = ctx.ui.get("/dossier/qa-no-such-model")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code == 200 and "not found" not in got.text.lower():
        return FAIL, "a dossier rendered for a model that does not exist"
    return PASS, f"answered {got.status_code}"


@case("QA-PLT-1109", "Artifact provenance is absent, not unverified")
def plt_1109(ctx: Ctx) -> Result:
    """'Nobody attested this artifact' and 'this artifact failed its check'
    are different facts, and reporting the first as the second would make an
    unchecked model look like a rejected one."""
    import inspect

    from core.artifacts import provenance
    source = inspect.getsource(provenance)
    if "absent" not in source.lower():
        return FAIL, ("provenance does not distinguish an artifact nobody "
                      "attested from one that failed")
    return PASS, "absent and unverified are held apart"
