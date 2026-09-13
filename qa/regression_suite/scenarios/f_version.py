"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — creating and approving a version.

**The digest is the address.** Storing the same weights twice stores them
once, an artifact cannot be edited in place because edited bytes are a
different address, and *these are the bytes the warrant names* is true by
construction rather than by a check somebody remembered to write. Two of the
cases here are about what happens when a caller's declaration disagrees with
what the store actually holds — and the store is the authority on its own
contents.

The format disagreement is the sharp one. `builder.py` picks the runtime from
the kernel's declaration and `EXECUTES_ON_LOAD` is a property of the FORMAT,
so a version declaring `onnx` over bytes stored as `torchscript` routes code
out of the sandbox that exists to contain it.
"""
from __future__ import annotations

import hashlib

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

M = "/api/v1/models"
A = "/api/v1/artifacts"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
FACTS = {"exposure": 1_000_000.0, "purpose_class": "credit_decision",
         "feature_count": 3, "interpretable": True,
         "uses_alternative_data": False}
TIER_1 = {**FACTS, "exposure": 5_000_000_000.0,
          "purpose_class": "policy_decision"}


def _model(ctx: Ctx) -> tuple:
    name = ctx.unique("vs")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    return name, urn


def _version(ctx: Ctx, name: str, semver: str = "1.0.0", *,
             digest: str = "", **kernel):
    """`artifact_digest` is a version field, not a kernel key — the kernel
    says what the model IS and refuses any key nothing reads, so putting the
    digest inside it is refused for a reason that has nothing to do with the
    digest."""
    body = {"semver": semver}
    if kernel:
        body["kernel"] = kernel
    if digest:
        body["artifact_digest"] = digest
    return ctx.api.post(f"{M}/{name}/versions", json=body,
                        auth=ctx.people["developer"])


#: `pickle` is NOT one of them, and the refusal says why: working the format
#: out at load time is how a pickle gets deserialised in a control plane.
STORED_FORMAT = "onnx"


def _upload(ctx: Ctx, payload: bytes, fmt: str = STORED_FORMAT):
    got = ctx.api.post(f"{A}?format={fmt}", content=payload,
                       auth=ctx.people["developer"])
    return (got.json() or {}).get("digest", "") if got.status_code < 400 else ""


@case("QA-GOV-073", "Create a version on a `submitted` record")
def gov_073(ctx: Ctx) -> Result:
    """A record put forward for approval is a record whose contents somebody
    is reading. A version arriving mid-review changes what was submitted
    without an amendment."""
    name, _urn = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the first version could not be created"
    ctx.api.post(f"{M}/{name}/assess", json=dict(FACTS))
    moved = ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    if moved.status_code >= 400:
        return BLOCKED, f"the model could not be submitted: {moved.text[:140]}"
    got = _version(ctx, name, "2.0.0")
    outcome = refused_by_the_control(
        got, "a version was created on a record under review")
    if outcome[0] is not PASS:
        return outcome
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-075",
      "Create a version with a digest of exactly 63 hex characters")
def gov_075(ctx: Ctx) -> Result:
    """The recorded defect: `sha256:not-a-digest-at-all` went onto a version
    with a 201. One character short is the case that matters, because the
    store refuses a malformed address when it goes looking for the bytes — so
    the only versions where this was never noticed are exactly the T6 vendor
    models, where the digest is the entire control."""
    name, _urn = _model(ctx)
    short = "sha256:" + "a" * 63
    got = _version(ctx, name, digest=short)
    outcome = refused_by_the_control(
        got, "a version carrying a digest one character short")
    if outcome[0] is not PASS:
        return outcome
    if "64" not in got.text:
        return FAIL, ("the refusal does not say how long a digest is, so the "
                      "caller cannot see what is wrong with theirs")
    return PASS, f"refused '{code_of(got)}', naming the length"


@case("QA-GOV-4650", "Create a version with a digest nothing has stored")
def gov_4650(ctx: Ctx) -> Result:
    """The other side of QA-GOV-075, and it must NOT be refused. Plenty of
    artefacts live in somebody else's engine — a T6 vendor model is the whole
    point — so a well-formed digest the store cannot resolve is accepted,
    while a malformed one is not. A version with no digest is honest; one
    carrying a digest nothing can resolve would not be."""
    name, _urn = _model(ctx)
    absent = "sha256:" + hashlib.sha256(b"never uploaded").hexdigest()
    got = _version(ctx, name, digest=absent)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — a well-formed digest the "
                      f"store does not hold is how a vendor model is "
                      f"registered at all")
    body = got.json() or {}
    stored = (body.get("manifest") or body).get("artifact_digest")
    if stored != absent:
        return FAIL, f"the digest was stored as {stored!r}"
    return PASS, "a well-formed unresolvable digest is accepted and kept"


@case("QA-GOV-077",
      "Declared `artifact_format` disagrees with the stored artifact")
def gov_077(ctx: Ctx) -> Result:
    """The store filled this in when the kernel was silent and BELIEVED the
    kernel when it was not, so the two could disagree about the same bytes
    and the version's word won. The format decides which runtime loads the
    bytes and whether that load path executes code."""
    name, _urn = _model(ctx)
    digest = _upload(ctx, b"qa-artifact-bytes-for-format-disagreement")
    if not digest:
        return BLOCKED, "the artifact could not be stored"
    got = _version(ctx, name, digest=digest, artifact_format="torchscript")
    outcome = refused_by_the_control(
        got, "a version declared a format the stored bytes are not")
    if outcome[0] is not PASS:
        return outcome
    if STORED_FORMAT not in got.text:
        return FAIL, ("the refusal does not say what the store actually "
                      "holds, so the caller cannot correct the declaration")
    return PASS, f"refused '{code_of(got)}', naming the stored format"


@case("QA-GOV-4651",
      "Declare no `artifact_format` over a stored artifact")
def gov_4651(ctx: Ctx) -> Result:
    """The store is the authority on its own contents, so silence is filled
    in from what it holds rather than left blank. This is the half of
    QA-GOV-077 that must keep working — refusing here would make every
    caller restate a fact the store already knows."""
    name, _urn = _model(ctx)
    digest = _upload(ctx, b"qa-artifact-bytes-for-silent-format")
    if not digest:
        return BLOCKED, "the artifact could not be stored"
    got = _version(ctx, name, digest=digest)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' when the format was left to "
                      f"the store, which is the store's own job")
    body = got.json() or {}
    # The kernel travels inside `manifest`, which is what the manifest digest
    # is taken over — reading a top-level `kernel` finds nothing and reports
    # the store as having filled in nothing.
    kernel = (body.get("manifest") or {}).get("kernel") or {}
    if kernel.get("artifact_format") != STORED_FORMAT:
        return FAIL, (f"the format reads {kernel.get('artifact_format')!r} "
                      f"rather than being filled in from the stored bytes")
    return PASS, f"the store filled in '{STORED_FORMAT}' where the kernel was silent"


@case("QA-GOV-081", "Approve a tier 1 version directly")
def gov_081(ctx: Ctx) -> Result:
    """Where the tier demands a quorum, approval is the CONSEQUENCE of one
    rather than an act in itself. A single-signature approval of a tier 1
    version is the hole this closes, and the refusal has to name the endpoint
    that does the right thing — somebody told no finds another way."""
    name, _urn = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be created"
    if ctx.api.post(f"{M}/{name}/assess",
                    json=dict(TIER_1)).status_code >= 400:
        return BLOCKED, "the model could not be assessed at tier 1"
    got = ctx.api.post(f"{M}/{name}/versions/1.0.0/approve", json={},
                       auth=ctx.people["risk"])
    outcome = refused_by_the_control(
        got, "a tier 1 version was approved on one signature")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "quorum_required":
        return FAIL, f"refused '{code_of(got)}'"
    if "version-approvals" not in got.text:
        return FAIL, ("the refusal does not name the endpoint that opens a "
                      "quorum, so the caller is told no with nowhere to go")
    return PASS, "refused 'quorum_required', naming the quorum endpoint"


@case("QA-GOV-082", "Approve a version whose model has no tier")
def gov_082(ctx: Ctx) -> Result:
    """Approving before assessing would be choosing your own control depth:
    the tier decides how many signatures the approval needs, so an untiered
    model needs whatever the caller is willing to provide."""
    name, _urn = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be created"
    got = ctx.api.post(f"{M}/{name}/versions/1.0.0/approve", json={},
                       auth=ctx.people["risk"])
    outcome = refused_by_the_control(
        got, "a version of an untiered model was approved")
    if outcome[0] is not PASS:
        return outcome
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-083", "Approve an already-approved tier 4 version")
def gov_083(ctx: Ctx) -> Result:
    """EXPLORATORY. A second approval of an approved version writes a second
    `version_approved` node for one decision, which makes the chain say the
    version was approved twice by two people when it was approved once."""
    name, _urn = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be created"
    if ctx.api.post(f"{M}/{name}/assess",
                    json={**FACTS, "exposure": 100.0,
                          "purpose_class": "commercial"}).status_code >= 400:
        return BLOCKED, "the model could not be assessed low"
    first = ctx.api.post(f"{M}/{name}/versions/1.0.0/approve", json={},
                         auth=ctx.people["risk"])
    if first.status_code >= 400:
        return BLOCKED, f"the first approval failed: {first.text[:140]}"
    got = ctx.api.post(f"{M}/{name}/versions/1.0.0/approve", json={},
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return PASS, (f"the second approval is refused '{code_of(got)}' — a "
                      f"decision is recorded once")
    engine = ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")
    version = ctx.ui.app.state.ctx["registry"].version(
        f"maya://model/{name}", "1.0.0")
    nodes = [n for n in engine.for_subject(version["id"])
             if n.get("kind") == "version_approved"]
    if len(nodes) > 1:
        return FAIL, (f"approving an approved version wrote a second "
                      f"`version_approved` node: the chain now says this "
                      f"version was approved {len(nodes)} times, and an "
                      f"examiner counting approvals counts decisions that "
                      f"were never taken")
    return PASS, f"accepted twice, {len(nodes)} approval node on the chain"


@case("QA-GOV-084",
      "Approve a version of a model with an open blocking finding")
def gov_084(ctx: Ctx) -> Result:
    """The recorded defect: `blocking_findings` was defaulted to 0 for the
    life of the gate, so the built-in rule's *not approved over an open
    blocking finding* had never been able to fire. Every fact the gate
    advertises is supplied now, not the four the service could see."""
    name, urn = _model(ctx)
    if _version(ctx, name).status_code >= 400:
        return BLOCKED, "the version could not be created"
    if ctx.api.post(f"{M}/{name}/assess",
                    json={**FACTS, "exposure": 100.0,
                          "purpose_class": "commercial"}).status_code >= 400:
        return BLOCKED, "the model could not be assessed"
    raised = ctx.api.post("/api/v1/findings",
                          json={"urn": urn, "severity": "High",
                                "title": "Blocks approval", "owner": "person/owner",
                                "description": "qa", "category": "general",
                                "source": "validation", "blocking": True},
                          auth=ctx.people["risk"])
    if raised.status_code >= 400:
        return BLOCKED, f"the finding could not be raised: {raised.text[:140]}"
    got = ctx.api.post(f"{M}/{name}/versions/1.0.0/approve", json={},
                       auth=ctx.people["risk"])
    outcome = refused_by_the_control(
        got, "a version was approved over an open blocking finding")
    if outcome[0] is not PASS:
        return outcome
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-086",
      "The creator is recorded `person/a.dev` and approves as `a.dev`")
def gov_086(ctx: Ctx) -> Result:
    """The identity comparison, at the approval. The platform writes a
    creator as `person/a.dev` and authenticates the same human as `a.dev`, so
    a `==` here is a duties check anybody can step around by dropping the
    prefix.

    The creator is the developer and the approver needs `version:approve`,
    which no first-line role holds — so the case asks the segregation policy
    directly, with the two spellings, rather than through a role pairing the
    store refuses to create."""
    policy = ctx.ui.app.state.ctx.get("authz")
    policy = getattr(policy, "segregation", None)
    if policy is None:
        return BLOCKED, "no segregation policy is wired"
    import inspect
    source = inspect.getsource(type(policy))
    if "same_person(" not in source:
        return FAIL, ("the segregation policy compares actors without "
                      "`same_person`, so `person/a.dev` and `a.dev` are two "
                      "people and every duties check here is optional")
    name, urn = _model(ctx)
    made = _version(ctx, name)
    if made.status_code >= 400:
        return BLOCKED, "the version could not be created"
    engine = ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")
    version = ctx.ui.app.state.ctx["registry"].version(urn, "1.0.0")
    created = [n for n in engine.for_subject(version["id"])
               if n.get("kind") == "version_created"]
    if not created:
        return FAIL, ("no `version_created` node was written, so the "
                      "segregation rule has nothing to read and permits "
                      "everybody")
    # The node's author column is `recorded_by`, not `actor` — reading
    # `actor` returns None and `same_person(None, None)` is a comparison of
    # two nothings that says nothing about the platform.
    actor = created[0].get("recorded_by")
    if not actor:
        return FAIL, (f"the `version_created` node names no author: "
                      f"{sorted(created[0])}")
    from core.authz.common import same_person
    if not same_person(f"person/{actor}", actor):
        return FAIL, (f"`same_person` does not equate 'person/{actor}' with "
                      f"'{actor}'")
    return PASS, (f"the creator is on the chain as '{actor}', and the policy "
                  f"resolves both spellings to one person")
