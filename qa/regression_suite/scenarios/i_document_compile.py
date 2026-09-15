"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — compiling a document, and reviewing one that cannot be edited.

A compiled document is **derived**, so the interesting properties are the ones
derivation makes possible and the ones it makes fragile. Two renderings of
unchanged state must be the same document — not a second row with the same
words — because review comments are keyed on the document id, and a recompile
that authored a copy would orphan every open comment onto a version nobody is
reading.

Staleness is computed from the chain rather than remembered, so a document
cannot be stale without the platform being able to say so. It is computed
across the model AND its versions, because reading the model's id alone left a
document reporting "nothing has been recorded since" through a full quorum
approval.

And a document cannot be edited at all. Every sentence cites a node, so editing
the prose would break the citation without changing the record it cites — the
fix for a wrong sentence is a fix to the record and a recompilation. That is
what the review vocabulary is for, and what makes `evidence_id` on a resolution
the load-bearing field.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

D = "/api/v1/documents"
R = "/api/v1/document-review"
M = "/api/v1/models"
KIND = "model_development_document"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx, **over) -> str:
    name = ctx.unique("doc")
    body = {"urn": f"maya://model/{name}", "name": name, "owner": "owner",
            **SHAPE}
    body.update(over)
    ctx.api.post(M, json=body, auth=ctx.people["owner"])
    return body["urn"]


def _compile(ctx: Ctx, urn: str, kind: str = KIND):
    return ctx.api.post(f"{D}?urn={urn}&kind={kind}",
                        auth=ctx.people["validator"])


def _docs(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("documents")


def _comment(ctx: Ctx, document_id: str, **over):
    body = {"section": "identity", "body": "this section is wrong",
            "asks_for": "comment", "quote": ""}
    body.update(over)
    return ctx.api.post(f"{R}?document_id={document_id}", json=body,
                        auth=ctx.people["validator"])


# ------------------------------------------------------------- compiling twice
@case("QA-PLT-123", "Compile one document twice with nothing changed between")
def plt_123(ctx: Ctx) -> Result:
    """The same document, not a second row carrying the same words. The
    digest is over the kind, the subject and the content — and a rendering
    deliberately carries no `compiled_at`, because a rendering has no moment
    of its own."""
    urn = _model(ctx)
    first = _compile(ctx, urn)
    if first.status_code >= 400:
        return BLOCKED, f"the document could not be compiled: {first.text[:160]}"
    second = _compile(ctx, urn)
    if second.status_code >= 400:
        return FAIL, f"the recompile was refused: {second.text[:160]}"
    a, b = first.json() or {}, second.json() or {}
    if a["digest"] != b["digest"]:
        return FAIL, (f"two renderings of unchanged state produced different "
                      f"digests ({a['digest'][:16]} against "
                      f"{b['digest'][:16]}), so nothing downstream can tell a "
                      f"changed document from a recompiled one")
    if a["id"] != b["id"]:
        return FAIL, (f"identical content was authored as a second document "
                      f"({a['id'][:12]} then {b['id'][:12]}), so every open "
                      f"review comment is now against a document nobody is "
                      f"looking at")
    return PASS, f"the same document id and digest {a['digest'][:16]}"


@case("QA-PLT-124", "Compile the same document five times and count the citations")
def plt_124(ctx: Ctx) -> Result:
    """Citations are a SET over the nodes the lenses cited, so a recompile
    cannot accumulate them. A count that grew by one per compile would make
    the provenance claim a function of how often somebody pressed a button."""
    urn = _model(ctx)
    first = _compile(ctx, urn)
    if first.status_code >= 400:
        return BLOCKED, f"the document could not be compiled: {first.text[:160]}"
    start = len((first.json() or {}).get("citations") or [])
    counts = [start]
    for _ in range(4):
        again = _compile(ctx, urn)
        if again.status_code >= 400:
            return FAIL, f"a recompile was refused: {again.text[:150]}"
        counts.append(len((again.json() or {}).get("citations") or []))
    if len(set(counts)) != 1:
        return FAIL, (f"the citation count moved across five compiles of "
                      f"unchanged state: {counts}")
    cited = (first.json() or {}).get("citations") or []
    if len(cited) != len(set(cited)):
        return FAIL, "the citation list carries duplicates"
    return PASS, f"{start} citations, unchanged across five compiles"


@case("QA-PLT-125", "Recompile a document that has open review comments")
def plt_125(ctx: Ctx) -> Result:
    """The comments stay against the current document. This is the reason
    the identical-rendering rule exists: a recompile that authored a copy
    would leave the reviewer's unresolved question attached to a document
    nobody opens, and nothing would say so."""
    urn = _model(ctx)
    first = _compile(ctx, urn)
    if first.status_code >= 400:
        return BLOCKED, f"the document could not be compiled: {first.text[:160]}"
    document_id = (first.json() or {})["id"]
    made = _comment(ctx, document_id, body="the owner is out of date")
    if made.status_code >= 400:
        return BLOCKED, f"the comment could not be raised: {made.text[:150]}"
    again = _compile(ctx, urn)
    if again.status_code >= 400:
        return FAIL, f"the recompile was refused: {again.text[:150]}"
    now_id = (again.json() or {})["id"]
    review = ctx.api.get(f"{R}?document_id={now_id}",
                         auth=ctx.people["validator"])
    if review.status_code >= 400:
        return BLOCKED, f"the review could not be read: {review.text[:150]}"
    body = review.json() or {}
    still = [c for c in (body.get("comments") or [])
             if c.get("state") == "open"]
    if now_id != document_id:
        return FAIL, (f"the recompile authored {now_id[:12]} while the comment "
                      f"is against {document_id[:12]}, so an open question is "
                      f"attached to a superseded document")
    if not still:
        return FAIL, ("the open comment is not on the current document's "
                      "review after a recompile")
    return PASS, f"{len(still)} open comment(s) still against {now_id[:12]}"


# ----------------------------------------------------------------- refusals
@case("QA-PLT-127", "An unknown kind against an unknown URN")
def plt_127(ctx: Ctx) -> Result:
    """Two things are wrong and the caller is told about the one they can
    act on first. The URN is resolved before the kind, so this answers
    `not_found` — which is correct and worth pinning, because the published
    expectation was the other way round and the order is a decision."""
    got = ctx.api.post(f"{D}?urn=maya://model/does-not-exist&kind=nonsense",
                       auth=ctx.people["validator"])
    if got.status_code < 400:
        return FAIL, "a document was compiled for an unknown model and kind"
    code = code_of(got)
    if code in ("not_found", "registry_refused"):
        real = _model(ctx)
        kinded = ctx.api.post(f"{D}?urn={real}&kind=nonsense",
                              auth=ctx.people["validator"])
        if code_of(kinded) != "unknown_document_kind":
            return FAIL, (f"with a real model the unknown kind answers "
                          f"'{code_of(kinded)}' rather than "
                          f"'unknown_document_kind'")
        if kinded.status_code != 422:
            return FAIL, (f"the unknown kind answers {kinded.status_code} "
                          f"rather than 422")
        from core.docs.common import KINDS
        if not any(k in kinded.text for k in KINDS):
            return FAIL, "the refusal does not list the kinds that are allowed"
        return PASS, (f"the subject is resolved first — '{code}' "
                      f"{got.status_code} for the URN, then "
                      f"'unknown_document_kind' 422 once the model exists, "
                      f"listing the kinds")
    if code != "unknown_document_kind":
        return FAIL, f"refused '{code}' at {got.status_code}"
    return PASS, f"refused 'unknown_document_kind' at {got.status_code}"


@case("QA-PLT-128", "A model with nothing recorded, compiled anyway")
def plt_128(ctx: Ctx) -> Result:
    """A document for a model with no evidence is the most useful one the
    platform produces, provided it says so: every required section marked
    unfillable, and `coverage.complete` false. A pack that looked complete
    because the gaps rendered as empty prose is the failure this design is
    against."""
    urn = _model(ctx)
    got = _compile(ctx, urn)
    if got.status_code >= 400:
        return FAIL, (f"a model with nothing recorded cannot be documented at "
                      f"all: {got.text[:160]}")
    doc = got.json() or {}
    coverage = doc.get("coverage") or {}
    if coverage.get("complete"):
        return FAIL, (f"a model with nothing recorded compiled a COMPLETE "
                      f"document: {coverage}")
    if not coverage.get("missing_required"):
        return FAIL, "nothing is listed as a missing required section"
    unfilled = [s for s in doc["sections"] if not s["filled"]]
    if not unfilled:
        return FAIL, "coverage says incomplete and every section reports filled"
    for section in unfilled:
        if "Nothing in the register supports" not in section["body"]:
            return FAIL, (f"section '{section['key']}' is empty without saying "
                          f"why: {section['body'][:120]}")
        if section["required"] and "**This section is required" not in section["body"]:
            return FAIL, (f"required section '{section['key']}' does not say "
                          f"it is required")
    if "not about this document" not in unfilled[0]["body"]:
        return FAIL, ("the gap does not say whose failing it is — a reader "
                      "must not read a thin document as a broken compiler")
    return PASS, (f"{len(unfilled)} of {coverage['sections']} sections "
                  f"unfillable, {len(coverage['missing_required'])} of them "
                  f"required, complete=False")


@case("QA-PLT-129", "A subsystem that throws during compilation")
def plt_129(ctx: Ctx) -> Result:
    """The prediction on file was that the section says it could not be
    compiled while `coverage.complete` stays true — a swallow that produces
    a document claiming completeness it has not got. Whatever the answer is,
    it must not be that."""
    urn = _model(ctx)
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    from core.docs import lenses as L
    from core.docs.templates import TEMPLATES
    lens = next((x for x in TEMPLATES[KIND] if x.key == "findings"), None)
    if lens is None:
        return BLOCKED, "no findings lens in this template"
    real = L.findings

    def explode(_ctx):
        raise RuntimeError("the findings register is unreachable")

    object.__setattr__(lens, "render", explode)
    try:
        got = _compile(ctx, urn)
    finally:
        object.__setattr__(lens, "render", real)
    if got.status_code >= 500:
        return PASS, (f"the compile fails loudly ({got.status_code}) rather "
                      f"than authoring a document with a silent hole; the "
                      f"section is not swallowed")
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' rather than compiling around "
                      f"the unreachable subsystem")
    doc = got.json() or {}
    section = next((s for s in doc["sections"] if s["key"] == "findings"), None)
    if section is None:
        return FAIL, ("the section vanished from the document entirely, so a "
                      "reader cannot tell it was meant to be there")
    if section.get("filled"):
        return FAIL, "a section whose subsystem threw reports itself as filled"
    if (doc.get("coverage") or {}).get("complete"):
        return FAIL, (
            "a subsystem threw, the section is a gap, and the document still "
            "reports `coverage.complete: true` — so an unreadable register and "
            "a register with nothing in it produce the same claim, and the "
            "claim is that the document is complete")
    return PASS, (f"the section is a gap and completeness is withheld: "
                  f"{section['body'][:100]}")


# ---------------------------------------------------------------- staleness
@case("QA-PLT-131",
      "An event recorded at exactly the sequence the document recorded as head")
def plt_131(ctx: Ctx) -> Result:
    """`stale: false`. The head is the sequence that already existed when the
    document was compiled, so the boundary is `>` and not `>=` — an
    off-by-one here makes every document stale the moment it is written, and
    a staleness signal that is always on is one nobody reads."""
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    urn = _model(ctx)
    got = _compile(ctx, urn)
    if got.status_code >= 400:
        return BLOCKED, f"the document could not be compiled: {got.text[:160]}"
    document_id = (got.json() or {})["id"]
    reading = docs.staleness(document_id)
    if reading["stale"]:
        return FAIL, (f"a freshly compiled document is already stale: "
                      f"{reading['detail']}")
    head = reading["evidence_head_at_compile"]
    row = docs.require(document_id)
    at_head = [n for n in docs.evidence.for_subjects(
        row.get("subjects") or [row["model_id"]]) if n["seq"] == head]
    if not at_head:
        return BLOCKED, f"no event sits at the recorded head {head}"
    if docs.staleness(document_id)["stale"]:
        return FAIL, ("the event AT the head counts as being since the "
                      "compile, so every document is stale the moment it is "
                      "written")
    return PASS, (f"head {head} carries {len(at_head)} event(s) and the "
                  f"document is not stale; the boundary is exclusive")


@case("QA-PLT-132", "A document row with no `subjects` list")
def plt_132(ctx: Ctx) -> Result:
    """Staleness is computed across the model AND its versions, because
    reading the model's id alone left a document reporting "nothing has been
    recorded" through a full quorum approval. A row written before
    `subjects` existed falls back to the model id — so the question is
    whether that fallback silently restores the old blindness."""
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    urn = _model(ctx)
    got = _compile(ctx, urn)
    if got.status_code >= 400:
        return BLOCKED, f"the document could not be compiled: {got.text[:160]}"
    document_id = (got.json() or {})["id"]
    row = docs.require(document_id)
    if not (row.get("subjects") or []):
        return BLOCKED, "this compiler writes no subjects, so there is no fallback"
    docs.documents.set({"subjects": []}, id=document_id)
    made = ctx.api.post(f"{M}/{urn}/versions", json={"semver": "1.0.0"},
                        auth=ctx.people["developer"])
    if made.status_code >= 400:
        return BLOCKED, f"the version could not be created: {made.text[:150]}"
    reading = docs.staleness(document_id)
    if reading["stale"]:
        return PASS, (f"a row with no subjects still notices a version-scoped "
                      f"event: {reading['kinds_since']}")
    with_subjects = docs.documents.one(id=document_id)
    return FAIL, (
        f"a document row whose `subjects` list is empty falls back to the "
        f"model id alone, so a new version — the event a document most needs "
        f"to notice — leaves it reporting {reading['detail']!r}; the column "
        f"reads {with_subjects.get('subjects')!r}. Latent rather than live on "
        f"a fresh estate: `render` writes `subjects` on every compile, so the "
        f"`or [doc['model_id']]` fallback is only reached by a row that "
        f"predates the column. There are no migrations by design, so nothing "
        f"backfills such a row and nothing recompiles it — the fallback "
        f"silently restores the exact blindness it was added to fix, and a "
        f"document that has gone quiet is indistinguishable from one with "
        f"nothing to say")


@case("QA-PLT-134", "A citation to an evidence node the reader may not see")
def plt_134(ctx: Ctx) -> Result:
    """Two questions in one, and the second is the one that matters.
    Soundness is a question about the chain rather than about the reader, so
    `sound: true` over nodes a scoped reader cannot open is defensible. Being
    SERVED the document at all is not."""
    docs = _docs(ctx)
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    urn = _model(ctx)
    got = _compile(ctx, urn)
    if got.status_code >= 400:
        return BLOCKED, f"the document could not be compiled: {got.text[:160]}"
    document_id = (got.json() or {})["id"]
    who = ctx.unique("scoped")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["model_risk_manager"],
                              "password": f"{who}-pw",
                              "legal_entities": ["LE-XX-99"], "domains": []})
    if made.status_code >= 400:
        return BLOCKED, f"the scoped reader could not be created: {made.text[:150]}"
    auth = (who, f"{who}-pw")
    listing = ctx.api.get(f"{D}?urn={urn}", auth=auth)
    read = ctx.api.get(f"{D}/{document_id}", auth=auth)
    if read.status_code >= 400:
        return PASS, (f"the document itself is refused to an out-of-scope "
                      f"reader ('{code_of(read)}'), so the citation claim "
                      f"never reaches them")
    body = read.json() or {}
    verified = body.get("citations_verified") or {}
    sections = len(body.get("sections") or [])
    return FAIL, (
        f"`GET {D}/{{document_id}}` authorises `document:read` with NO model, "
        f"while `GET {D}?urn=` passes one and refuses this reader "
        f"'{code_of(listing)}'. So a principal scoped to LE-XX-99 is served an "
        f"LE-US-01 model's compiled document by id — {sections} sections of "
        f"its identity, methodology, findings and approvals — and told its "
        f"{verified.get('cited')} citation(s) are sound. The soundness claim "
        f"is itself unscoped (`verify_citations` walks the whole chain with "
        f"`self.evidence.repo.many()` and no principal), but that is the "
        f"smaller half: the document should not have been served. Same shape "
        f"as the findings register — the `?urn=` path is scoped and the "
        f"`/{{id}}` path is not")


# ------------------------------------------------------------ review states
@case("QA-PLT-143", "The `superseded` review state")
def plt_143(ctx: Ctx) -> Result:
    """A published vocabulary is a claim about what can happen. Either
    something writes every state it offers, or the state is not in it — and
    if the fact is derived instead, the vocabulary has to say where to read
    it, because a reader who knows a comment can be superseded and finds no
    such state concludes the platform does not track it."""
    import inspect

    from core.docs import review as module
    from core.docs.review import STATES
    asks = ctx.api.get(f"{R}/asks", auth=ctx.people["validator"])
    if asks.status_code >= 400:
        return BLOCKED, f"the vocabulary could not be read: {asks.text[:130]}"
    published = (asks.json() or {}).get("states") or []
    source = inspect.getsource(module)
    unwritten = []
    for state in published:
        constant = state.upper()
        writes = [ln.strip() for ln in source.splitlines()
                  if f'"state": {constant}' in ln or f"'state': {constant}" in ln
                  or f'"state": "{state}"' in ln]
        if not writes:
            unwritten.append(state)
    if unwritten:
        derived = (asks.json() or {})
        explained = [s for s in unwritten
                     if any(s in str(k) for k in derived)]
        return FAIL, (
            f"{len(unwritten)} of the {len(published)} states the review "
            f"vocabulary publishes at GET {R}/asks are written by no path in "
            f"`core/docs/review.py`: {unwritten}. A client filtering or "
            f"reporting on one filters on a state that cannot occur, which "
            f"reads as 'none of those' rather than as 'that never happens "
            f"here'. Explained as derived: {explained or 'none'}")
    if sorted(published) != sorted(STATES):
        return FAIL, (f"the route publishes {published} and the module holds "
                      f"{list(STATES)}")
    if "superseded" in published:
        return FAIL, "superseded is published and was meant to be derived"
    said = (asks.json() or {}).get("superseded_is_derived") or ""
    if "digest" not in said:
        return FAIL, ("the vocabulary drops `superseded` and does not say "
                      "where supersession IS read from, so a reader concludes "
                      "the platform does not track it")
    # And the derived answer has to actually be on the review.
    urn = _model(ctx)
    got = _compile(ctx, urn)
    if got.status_code >= 400:
        return BLOCKED, f"the document could not be compiled: {got.text[:150]}"
    document_id = (got.json() or {})["id"]
    if _comment(ctx, document_id).status_code >= 400:
        return BLOCKED, "the comment could not be raised"
    review = ctx.api.get(f"{R}?document_id={document_id}",
                         auth=ctx.people["validator"]).json() or {}
    if "raised_against_an_earlier_version" not in review:
        return FAIL, ("the review does not report comments raised against an "
                      "earlier rendering, so the derived answer is not there "
                      "either")
    return PASS, (f"{len(published)} states, every one written by a path; "
                  f"supersession is derived from the digest and the review "
                  f"reports it as "
                  f"`raised_against_an_earlier_version`: "
                  f"{review['raised_against_an_earlier_version']}")


@case("QA-PLT-145", "Withdraw with an empty reason")
def plt_145(ctx: Ctx) -> Result:
    """`resolve` refuses a closure with no sentence about what was done, on
    the stated ground that a comment closed with nothing is indistinguishable
    a year later from one the reviewer gave up on. A withdrawal is the same
    act from the other side and takes the same column."""
    urn = _model(ctx)
    got = _compile(ctx, urn)
    if got.status_code >= 400:
        return BLOCKED, f"the document could not be compiled: {got.text[:160]}"
    document_id = (got.json() or {})["id"]
    made = _comment(ctx, document_id)
    if made.status_code >= 400:
        return BLOCKED, f"the comment could not be raised: {made.text[:150]}"
    comments = (made.json() or {}).get("comments") or []
    if not comments:
        return BLOCKED, "the comment was not returned"
    comment_id = comments[0]["id"]
    pulled = ctx.api.post(f"{R}/{comment_id}/withdraw",
                          auth=ctx.people["validator"])
    if pulled.status_code >= 400:
        code = code_of(pulled)
        if code not in ("reason_required", "validation_refused"):
            return FAIL, f"refused '{code}' rather than for the missing reason"
        return PASS, f"refused '{code}' on an empty reason"
    state = ctx.api.get(f"{R}?document_id={document_id}",
                        auth=ctx.people["validator"]).json() or {}
    row = next((c for c in (state.get("comments") or [])
                if c["id"] == comment_id), {})
    return FAIL, (
        f"a comment was withdrawn with no reason at all and the record now "
        f"reads state={row.get('state')!r} resolution={row.get('resolution')!r}. "
        f"`resolve` refuses exactly this — 'closing a comment needs a sentence "
        f"about what was done' — and `withdraw` writes the same column with "
        f"no check, so the review history has a closed objection and no "
        f"account of why it was dropped")


@case("QA-PLT-146", "Withdraw under a read-only permission")
def plt_146(ctx: Ctx) -> Result:
    """The route authorises `document:read` while raising a comment needs
    `document:review`. The register's own check narrows it — only the raiser
    may withdraw — so the reachable gap is somebody whose review permission
    has been TAKEN AWAY still closing the objections they left behind."""
    import inspect

    from routes.document_routes import DocumentRoutes
    source = inspect.getsource(DocumentRoutes.register)
    block = source[source.index("def withdraw_comment"):][:400]
    if "document:review" in block:
        return PASS, "withdrawing asks for document:review"
    if "document:read" not in block:
        return BLOCKED, "the withdraw route authorises nothing readable"
    urn = _model(ctx)
    got = _compile(ctx, urn)
    if got.status_code >= 400:
        return BLOCKED, f"the document could not be compiled: {got.text[:160]}"
    document_id = (got.json() or {})["id"]
    made = _comment(ctx, document_id)
    if made.status_code >= 400:
        return BLOCKED, f"the comment could not be raised: {made.text[:150]}"
    comment_id = ((made.json() or {}).get("comments") or [{}])[0].get("id")
    other = ctx.api.post(f"{R}/{comment_id}/withdraw?reason=not+mine",
                         auth=ctx.people["owner"])
    if other.status_code < 400:
        return FAIL, ("somebody else's comment was withdrawn by a principal "
                      "who did not raise it")
    return FAIL, (
        f"`withdraw_comment` authorises `document:read` where `comment` "
        f"authorises `document:review`. Somebody else is stopped by the "
        f"register rather than by the route — '{code_of(other)}' — so the "
        f"reachable case is narrow and real: a reviewer whose "
        f"`document:review` has been revoked still holds `document:read`, and "
        f"can still close the objections they raised while they had it. The "
        f"permission that gates raising an objection does not gate retracting "
        f"one")


@case("QA-PLT-148", "Resolve citing an `evidence_id` that does not exist")
def plt_148(ctx: Ctx) -> Result:
    """`changed_the_record: true` is the strongest claim the review history
    makes — it says a wrong sentence was fixed by fixing the record rather
    than by agreeing to differ. It is `bool(evidence_id)`, and nothing checks
    the node is there."""
    urn = _model(ctx)
    got = _compile(ctx, urn)
    if got.status_code >= 400:
        return BLOCKED, f"the document could not be compiled: {got.text[:160]}"
    document_id = (got.json() or {})["id"]
    made = _comment(ctx, document_id, asks_for="comment")
    if made.status_code >= 400:
        return BLOCKED, f"the comment could not be raised: {made.text[:150]}"
    comment_id = ((made.json() or {}).get("comments") or [{}])[0].get("id")
    invented = "evidence-node-that-never-existed"
    closed = ctx.api.post(f"{R}/{comment_id}/resolve",
                          json={"resolution": "fixed in the register",
                                "evidence_id": invented},
                          auth=ctx.people["validator"])
    if closed.status_code >= 400:
        return PASS, (f"refused '{code_of(closed)}' on a citation that "
                      f"resolves to nothing")
    evidence = ctx.ui.app.state.ctx.get("evidence")
    node = evidence.repo.one(id=invented) if evidence else None
    if node is not None:
        return BLOCKED, "the invented id exists after all"
    state = ctx.api.get(f"{R}?document_id={document_id}",
                        auth=ctx.people["validator"]).json() or {}
    row = next((c for c in (state.get("comments") or [])
                if c["id"] == comment_id), {})
    return FAIL, (
        f"a comment was resolved citing '{invented}', which is in no chain, "
        f"and the act was recorded with `changed_the_record: true` — it is "
        f"`bool(evidence_id)` with no existence check. The review history now "
        f"asserts that a wrong sentence was fixed by fixing the record, and "
        f"points at nothing; the comment reads state={row.get('state')!r}. "
        f"`verify_citations` exists for exactly this question about a "
        f"document's citations and is not asked about a resolution's")
