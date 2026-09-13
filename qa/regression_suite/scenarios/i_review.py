"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — reviewing a compiled document.

A compiled document cannot be edited: every sentence cites a node, and editing
the prose would break the citation without changing the record it cites. So a
comment is the only way to disagree with one, and the controls on a comment
are the controls on the whole review.
"""
from __future__ import annotations

from core.docs.review import ASKS, NEEDS_SOMEBODY_ELSE
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

D = "/api/v1/document-review"
DOCS = "/api/v1/documents"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _document(ctx: Ctx) -> tuple:
    """A compiled document, and one of its real section keys."""
    name = ctx.unique("dr")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    # `urn` and `kind` are QUERY parameters on this route, not a body. Sent
    # as JSON they are simply absent, the call is a 422, and every case in
    # the module then blocks on "no document could be compiled".
    made = ctx.api.post(
        f"{DOCS}?urn=maya://model/{name}&kind=model_development_document",
        # `document:compile` is not the developer's — it sits with the owner
        # and the second line.
        auth=ctx.people["owner"])
    if made.status_code >= 400:
        return "", ""
    body = made.json() or {}
    did = body.get("id") or body.get("document_id")
    sections = [s.get("key") or s.get("title")
                for s in (body.get("sections") or []) if isinstance(s, dict)]
    return did, (sections[0] if sections else "")


def _comment(ctx: Ctx, did: str, section: str, who="validator", **over):
    body = {"section": section, "body": "this section is wrong",
            "asks_for": "comment", "quote": ""}
    body.update(over)
    return ctx.api.post(f"{D}?document_id={did}", json=body,
                        auth=ctx.people[who])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


def _newest(made) -> str:
    """The id of the comment just raised.

    `POST /document-review` answers the document's whole REVIEW STATE —
    `{document_id, comments, open, by_section, ...}` — not the comment. There
    is no top-level `id`, so reading one gives None and every later call
    refuses `unknown_comment`.
    """
    body = made.json() if made.status_code < 400 else {}
    comments = body.get("comments") or []
    if not comments:
        return ""
    newest = max(comments, key=lambda c: c.get("raised_at") or 0)
    return newest.get("id") or ""


@case("QA-PLT-151", "A comment on a section the document does not have")
def plt_151(ctx: Ctx) -> Result:
    """A comment on a section that is not there cannot be resolved by
    changing anything."""
    did, section = _document(ctx)
    if not did:
        return BLOCKED, "no document could be compiled"
    if not section:
        return BLOCKED, "the document declares no sections to compare against"
    got = _comment(ctx, did, "chapter nine")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("a comment was raised against a section that does not "
                      "exist, so nothing can ever resolve it")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-2600", "A comment asking for something that is not an ask")
def plt_2600(ctx: Ctx) -> Result:
    """*Please look at this* and *this is factually wrong* are different
    obligations, and a free-text field makes them the same one."""
    did, section = _document(ctx)
    if not did:
        return BLOCKED, "no document could be compiled"
    got = _comment(ctx, did, section, asks_for="a chat")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "a comment asked for something outside the closed list"
    if not any(a in got.text for a in ASKS):
        return FAIL, "the refusal does not name the asks"
    return PASS, f"refused '{code_of(got)}', naming the {len(ASKS)} asks"


@case("QA-PLT-2601", "A comment with no body")
def plt_2601(ctx: Ctx) -> Result:
    did, section = _document(ctx)
    if not did:
        return BLOCKED, "no document could be compiled"
    got = _comment(ctx, did, section, body="   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "a comment with no body is a mark on a page"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-149", "The raiser closing their own point")
def plt_149(ctx: Ctx) -> Result:
    """For the asks that need somebody else — factual and objection — the
    person who raised it may not be the person who says it is dealt with."""
    did, section = _document(ctx)
    if not did:
        return BLOCKED, "no document could be compiled"
    made = _comment(ctx, did, section, asks_for=NEEDS_SOMEBODY_ELSE[0])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    cid = _newest(made)
    got = ctx.api.post(f"{D}/{cid}/resolve",
                       json={"resolution": "I have dealt with it",
                             "evidence_id": ""},
                       auth=ctx.people["validator"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("the person who raised a factual objection closed it "
                      "themselves")
    if code_of(got) in DENIAL:
        return BLOCKED, "the caller never reached the check"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-150", "The raiser under a different spelling of their name")
def plt_150(ctx: Ctx) -> Result:
    """`resolve` compares `comment["raised_by"] == actor`. Everywhere else
    the platform uses `same_person`, because it writes an identity as
    `person/j.okafor` and authenticates the same human as `j.okafor` — and a
    duties check comparing the two with `==` is one anybody steps around by
    dropping seven characters.
    """
    did, section = _document(ctx)
    if not did:
        return BLOCKED, "no document could be compiled"
    made = _comment(ctx, did, section, asks_for=NEEDS_SOMEBODY_ELSE[0])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    cid = _newest(made)
    comments = (made.json() or {}).get("comments") or []
    raised_by = next((c.get("raised_by") for c in comments
                      if c.get("id") == cid), "") or "validator"
    review = ctx.ui.app.state.ctx.get("document_review")
    if review is None:
        return BLOCKED, "no review service reachable from this run"
    from core.docs.common import DocumentError
    # The same human, written the other way round.
    other = (raised_by.split("/", 1)[-1] if "/" in raised_by
             else f"person/{raised_by}")
    try:
        review.resolve(cid, "I have dealt with it", actor=other)
    except DocumentError as exc:
        if exc.code != "raiser_may_not_close":
            return FAIL, f"refused '{exc.code}', not raiser_may_not_close"
        return PASS, f"'{other}' is recognised as '{raised_by}'"
    return FAIL, (
        f"the raiser closed their own factual objection by writing their name "
        f"as '{other}' instead of '{raised_by}'. The check is "
        f"`raised_by == actor`, not `same_person`, so seven characters step "
        f"around it — the same failure the register already fixed for "
        f"validation independence and for the finding workflow")


@case("QA-PLT-2602", "Somebody else may close it")
def plt_2602(ctx: Ctx) -> Result:
    """The refusal has to admit the legitimate case, or a factual objection
    can never be closed at all."""
    did, section = _document(ctx)
    if not did:
        return BLOCKED, "no document could be compiled"
    made = _comment(ctx, did, section, asks_for=NEEDS_SOMEBODY_ELSE[0])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    cid = _newest(made)
    got = ctx.api.post(f"{D}/{cid}/resolve",
                       json={"resolution": "the record was corrected",
                             "evidence_id": ""},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return FAIL, (f"a second person could not close a factual objection: "
                      f"{got.text[:130]}")
    return PASS, "somebody other than the raiser closed it"


@case("QA-PLT-2603", "A plain comment may be closed by its raiser")
def plt_2603(ctx: Ctx) -> Result:
    """Only `factual` and `objection` need somebody else. A remark that the
    raiser cannot close is a remark nobody will ever raise."""
    did, section = _document(ctx)
    if not did:
        return BLOCKED, "no document could be compiled"
    plain = [a for a in ASKS if a not in NEEDS_SOMEBODY_ELSE]
    if not plain:
        return BLOCKED, "every ask needs somebody else"
    made = _comment(ctx, did, section, asks_for=plain[0])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(f"{D}/{_newest(made)}/resolve",
                       json={"resolution": "noted", "evidence_id": ""},
                       auth=ctx.people["validator"])
    if got.status_code >= 400:
        return FAIL, (f"a '{plain[0]}' could not be closed by the person who "
                      f"raised it: {got.text[:120]}")
    return PASS, f"a '{plain[0]}' closes without a second person"


@case("QA-PLT-147", "Two people resolving one comment")
def plt_147(ctx: Ctx) -> Result:
    """A closed comment is closed. A second resolution would be a second
    answer to a question already answered."""
    did, section = _document(ctx)
    if not did:
        return BLOCKED, "no document could be compiled"
    made = _comment(ctx, did, section)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    cid = _newest(made)
    first = ctx.api.post(f"{D}/{cid}/resolve",
                         json={"resolution": "dealt with", "evidence_id": ""},
                         auth=ctx.people["validator"])
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    again = ctx.api.post(f"{D}/{cid}/resolve",
                         json={"resolution": "dealt with again",
                               "evidence_id": ""}, auth=ctx.people["risk"])
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code < 400:
        return FAIL, "a resolved comment was resolved a second time"
    return PASS, f"refused '{code_of(again)}'"


@case("QA-PLT-2604", "Resolve with no resolution")
def plt_2604(ctx: Ctx) -> Result:
    """"Nothing was done and here is why" is a legitimate resolution and an
    invisible one if it is not written down."""
    did, section = _document(ctx)
    if not did:
        return BLOCKED, "no document could be compiled"
    made = _comment(ctx, did, section)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(f"{D}/{_newest(made)}/resolve",
                       json={"resolution": "  ", "evidence_id": ""},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a comment was closed with nothing said about how"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-144", "Withdraw a comment that was already resolved")
def plt_144(ctx: Ctx) -> Result:
    """Withdrawing a closed comment would erase somebody else's answer."""
    did, section = _document(ctx)
    if not did:
        return BLOCKED, "no document could be compiled"
    made = _comment(ctx, did, section)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    cid = _newest(made)
    if ctx.api.post(f"{D}/{cid}/resolve",
                    json={"resolution": "dealt with", "evidence_id": ""},
                    auth=ctx.people["risk"]).status_code >= 400:
        return BLOCKED, "the comment could not be resolved"
    got = ctx.api.post(f"{D}/{cid}/withdraw?reason=changed+my+mind",
                       auth=ctx.people["validator"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a resolved comment was withdrawn, erasing the answer "
                      "somebody gave it")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-135", "A dossier for a URN that is not registered")
def plt_135(ctx: Ctx) -> Result:
    got = ctx.api.get("/api/v1/dossiers/qa-no-such-model",
                      auth=ctx.people["auditor"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a dossier was built for a model nobody registered"
    return PASS, f"refused ({got.status_code})"


@case("QA-PLT-136", "A dossier for a registered model with nothing filed")
def plt_136(ctx: Ctx) -> Result:
    """An empty dossier is a real answer and must not be an error: the gaps
    are what the reader came for."""
    name = ctx.unique("dr")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    got = ctx.api.get(f"/api/v1/dossiers/{name}", auth=ctx.people["auditor"])
    if got.status_code >= 400:
        return FAIL, (f"a dossier for a bare model was refused "
                      f"({got.status_code}); the gaps are the answer")
    body = got.json() or {}
    if not body.get("gaps"):
        return FAIL, ("a model with nothing filed reports no gaps, so an "
                      "undocumented model reads as a complete one")
    return PASS, f"{len(body['gaps'])} gap(s) named"
