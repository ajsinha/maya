"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — idempotency, preconditions, and immutability at the storage layer.

The two questions underneath all of it: **did this act happen twice**, and
**did the thing I am overwriting change while I was deciding**. Both are
invisible when they go wrong. A duplicated governance act looks like two
governance acts, and a lost update looks like a successful one.
"""
from __future__ import annotations

from tools.qa.scenarios.common import (BLOCKED, FAIL, PASS, Ctx, Result, case,
                                       code_of, expect_accepted,
                                       expect_refused)

KEY = "idempotency-key"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _body(ctx: Ctx) -> dict:
    name = ctx.unique("idem")
    return {"urn": f"maya://model/{name}", "name": name, "owner": "owner",
            **TIER}


# ------------------------------------------------------------- idempotency
@case("QA-PLT-041", "The same key and body twice in sequence")
def plt_041(ctx: Ctx) -> Result:
    key, body = ctx.unique("k"), _body(ctx)
    first = ctx.api.post("/api/v1/models", json=body, headers={KEY: key})
    if first.status_code >= 400:
        return BLOCKED, f"the first call failed: {first.text[:160]}"
    second = ctx.api.post("/api/v1/models", json=body, headers={KEY: key})
    if second.status_code >= 400:
        return FAIL, (f"the replay was refused rather than replayed: "
                      f"{second.text[:160]}")
    if second.headers.get("idempotency-replayed") is None:
        return FAIL, ("the second answer does not say it was a replay — a "
                      "caller cannot tell a retry that worked from an act "
                      "that happened twice")
    return PASS, "replayed, and said so"


@case("QA-PLT-042", "The same key with a corrected body")
def plt_042(ctx: Ctx) -> Result:
    """The dangerous one. A caller who fixed a typo and kept the key must not
    silently receive the answer to their mistake."""
    key = ctx.unique("k")
    ctx.api.post("/api/v1/models", json=_body(ctx), headers={KEY: key})
    return expect_refused(
        ctx.api.post("/api/v1/models", json=_body(ctx), headers={KEY: key}),
        "idempotency_key_reused")


@case("QA-PLT-043", "The same key with the same fields in a different order")
def plt_043(ctx: Ctx) -> Result:
    """A replay, not a conflict. JSON object order is not meaning, and
    refusing on it would make every client library's field ordering a
    correctness question."""
    key, body = ctx.unique("k"), _body(ctx)
    ctx.api.post("/api/v1/models", json=body, headers={KEY: key})
    reordered = dict(reversed(list(body.items())))
    got = ctx.api.post("/api/v1/models", json=reordered, headers={KEY: key})
    if got.status_code >= 400:
        return FAIL, (f"reordering the same fields was treated as a different "
                      f"request: {got.text[:150]}")
    return PASS, "replayed"


@case("QA-PLT-045", "A key whose first attempt was refused, retried")
def plt_045(ctx: Ctx) -> Result:
    """The retry must really run. Replaying a refusal would mean a caller who
    fixed the problem is told about the old one forever."""
    key = ctx.unique("k")
    bad = dict(_body(ctx))
    bad["urn"] = "not-a-urn"
    first = ctx.api.post("/api/v1/models", json=bad, headers={KEY: key})
    if first.status_code < 400:
        return BLOCKED, "the deliberately bad body was accepted"
    good = ctx.api.post("/api/v1/models", json=_body(ctx), headers={KEY: key})
    if good.status_code >= 400:
        return FAIL, (f"the retry after a refusal was itself refused "
                      f"('{code_of(good)}') — a caller who corrected the "
                      f"problem can never get past it")
    return PASS, "the retry ran"


@case("QA-PLT-047", "A key of 256 characters")
def plt_047(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post("/api/v1/models", json=_body(ctx),
                     headers={KEY: "k" * 256}),
        "idempotency_key_too_long")


@case("QA-PLT-048", "Two principals choosing the same key")
def plt_048(ctx: Ctx) -> Result:
    """Both acts must happen. A key is scoped to who sent it, or one tenant
    can silently suppress another's writes by guessing a UUID."""
    key = ctx.unique("k")
    first = ctx.api.post("/api/v1/models", json=_body(ctx), headers={KEY: key})
    if first.status_code >= 400:
        return BLOCKED, first.text[:160]
    second = ctx.api.post("/api/v1/models", json=_body(ctx),
                          headers={KEY: key}, auth=ctx.people["owner"])
    if second.status_code >= 400:
        return FAIL, (f"a second principal reusing the same key was refused "
                      f"('{code_of(second)}') — one caller can suppress "
                      f"another's writes by guessing a key")
    return PASS, "both acts happened"


@case("QA-PLT-051", "An idempotent act's EFFECTS do not happen twice")
def plt_051(ctx: Ctx) -> Result:
    """The response can be replayed from a cache and still leave two evidence
    nodes behind, which is the failure that looks like success."""
    key, body = ctx.unique("k"), _body(ctx)
    before = ctx.made["evidence"].verify_chain()["length"]
    ctx.api.post("/api/v1/models", json=body, headers={KEY: key})
    middle = ctx.made["evidence"].verify_chain()["length"]
    ctx.api.post("/api/v1/models", json=body, headers={KEY: key})
    after = ctx.made["evidence"].verify_chain()["length"]
    if after != middle:
        return FAIL, (f"the replay appended {after - middle} more evidence "
                      f"node(s); the answer was cached and the act was not")
    return PASS, f"chain grew {middle - before} on the act and 0 on the replay"


# -------------------------------------------------------------- preconditions
@case("QA-PLT-052", "A stale If-Match after somebody else wrote")
def plt_052(ctx: Ctx) -> Result:
    body = _body(ctx)
    ctx.api.post("/api/v1/models", json=body)
    name = body["name"]
    read = ctx.api.get(f"/api/v1/models/{name}")
    tag = read.headers.get("etag")
    if not tag:
        return BLOCKED, "the resource carries no ETag to be stale about"
    ctx.api.patch(f"/api/v1/models/{name}", json={"fields": {"owner": "risk"}})
    return expect_refused(
        ctx.api.patch(f"/api/v1/models/{name}",
                      json={"fields": {"owner": "validator"}},
                      headers={"If-Match": tag}),
        "precondition_failed", status=412)


@case("QA-PLT-053", "If-Match against a resource that does not exist")
def plt_053(ctx: Ctx) -> Result:
    got = ctx.api.patch("/api/v1/models/qa-never",
                        json={"fields": {"owner": "risk"}},
                        headers={"If-Match": "*"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "If-Match: * matched a resource that does not exist"
    return PASS, f"refused ({got.status_code} {code_of(got) or 'no code'})"


@case("QA-PLT-058", "A fresh If-Match succeeds")
def plt_058(ctx: Ctx) -> Result:
    """The other half. A precondition that always refuses is not a
    precondition, and this is what would catch an ETag that never matches."""
    body = _body(ctx)
    ctx.api.post("/api/v1/models", json=body)
    name = body["name"]
    tag = ctx.api.get(f"/api/v1/models/{name}").headers.get("etag")
    if not tag:
        return BLOCKED, "no ETag issued"
    return expect_accepted(
        ctx.api.patch(f"/api/v1/models/{name}",
                      json={"fields": {"owner": "risk"}},
                      headers={"If-Match": tag}))


# --------------------------------------------------------------- immutability
@case("QA-PLT-070", "An immutable column on an attested version")
def plt_070(ctx: Ctx) -> Result:
    """Enforced by a trigger at the storage layer, not by a service that
    somebody could route around."""
    db = ctx.made["db"]
    body = _body(ctx)
    ctx.api.post("/api/v1/models", json=body)
    ctx.api.post(f"/api/v1/models/{body['name']}/versions",
                 json={"semver": "1.0.0"}, auth=ctx.people["developer"])
    row = db.query_one("SELECT id FROM model_version WHERE semver = '1.0.0' "
                       "ORDER BY created_at DESC")
    if not row:
        return BLOCKED, "no version to attack"
    try:
        db.execute("UPDATE model_version SET semver = '9.9.9' WHERE id = :i",
                   {"i": row["id"]})
    except Exception as refused:
        return PASS, f"the trigger refused: {str(refused)[:130]}"
    return FAIL, ("an immutable column was rewritten — the enforcement is a "
                  "convention, not a constraint")


@case("QA-PLT-071", "A mutable column on the same row still moves")
def plt_071(ctx: Ctx) -> Result:
    """`status` is deliberately NOT immutable: a version is approved after it
    is created. A guard that froze the whole row would stop the lifecycle."""
    db = ctx.made["db"]
    body = _body(ctx)
    ctx.api.post("/api/v1/models", json=body)
    ctx.api.post(f"/api/v1/models/{body['name']}/versions",
                 json={"semver": "1.0.0"}, auth=ctx.people["developer"])
    row = db.query_one("SELECT id FROM model_version WHERE semver = '1.0.0' "
                       "ORDER BY created_at DESC")
    try:
        db.execute("UPDATE model_version SET status = 'approved' "
                   "WHERE id = :i", {"i": row["id"]})
    except Exception as refused:
        return FAIL, (f"`status` is frozen, so no version can ever be "
                      f"approved: {str(refused)[:120]}")
    return PASS, "status moves, as the lifecycle requires"


@case("QA-PLT-072", "The evidence chain refuses a DELETE")
def plt_072(ctx: Ctx) -> Result:
    db = ctx.made["db"]
    try:
        db.execute("DELETE FROM evidence_node WHERE seq = 1")
    except Exception as refused:
        return PASS, f"refused: {str(refused)[:130]}"
    return FAIL, "a row was deleted from the evidence chain"


@case("QA-PLT-073", "The evidence chain refuses an UPDATE")
def plt_073(ctx: Ctx) -> Result:
    db = ctx.made["db"]
    try:
        db.execute("UPDATE evidence_node SET recorded_by = 'x' WHERE seq = 1")
    except Exception as refused:
        return PASS, f"refused: {str(refused)[:130]}"
    return FAIL, "a row in the evidence chain was rewritten"
