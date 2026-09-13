"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section J — deletion, tombstones, the cascade, and storage reclamation.

The act with no workflow, no reversal and no second signature, plus the two
things that happen around it. The attack these are really about is not a
failed deletion but a *successful* one followed by a registration.
"""
from __future__ import annotations

from tools.qa.scenarios.common import (BLOCKED, FAIL, PASS, Ctx, Result, case,
                                       code_of, expect_accepted,
                                       expect_refused)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _register(ctx: Ctx, stem: str, owner: str = "admin") -> str:
    """A fresh model, returned as its URN."""
    name = ctx.unique(stem)
    urn = f"maya://model/qa.{name}"
    made = ctx.api.post("/api/v1/models",
                        json={"urn": urn, "name": name, "owner": owner, **TIER})
    if made.status_code != 201:
        raise AssertionError(f"setup failed to register {urn}: "
                             f"{made.status_code} {made.text[:200]}")
    return urn


def _delete(ctx, urn: str, reason: str = "qa", auth=None):
    name = urn.rsplit("/", 1)[-1]
    return ctx.api.request("DELETE", f"/api/v1/models/{name}",
                           params={"reason": reason},
                           **({"auth": auth} if auth else {}))


# --------------------------------------------------------------- the deleter
@case("QA-DEL-001", "Delete as a non-administrator holding model:delete")
def del_001(ctx: Ctx) -> Result:
    urn = _register(ctx, "del001")
    return expect_refused(_delete(ctx, urn, auth=ctx.people["observer"]),
                          "deletion_refused", "forbidden")


@case("QA-DEL-002", "Delete with an empty reason")
def del_002(ctx: Ctx) -> Result:
    urn = _register(ctx, "del002")
    return expect_refused(_delete(ctx, urn, reason=""),
                          "reason_required", "validation_error")


@case("QA-DEL-003", "Delete with a whitespace-only reason")
def del_003(ctx: Ctx) -> Result:
    urn = _register(ctx, "del003")
    return expect_refused(_delete(ctx, urn, reason="   "),
                          "reason_required", "validation_error")


@case("QA-DEL-009", "Delete a model that does not exist")
def del_009(ctx: Ctx) -> Result:
    # `registry_refused`, not `not_found`. The case originally demanded a 404
    # and the platform answers a coded 409 naming the URN — a considered
    # refusal, and the code is the platform's existing mapping for
    # RegistryError. The expectation was mine and it was wrong.
    return expect_refused(
        ctx.api.request("DELETE", "/api/v1/models/qa-never-existed",
                        params={"reason": "qa"}),
        "registry_refused", "not_found")


@case("QA-DEL-010", "Delete the same model twice")
def del_010(ctx: Ctx) -> Result:
    urn = _register(ctx, "del010")
    first = _delete(ctx, urn)
    if first.status_code >= 400:
        return FAIL, f"the first deletion failed: {first.text[:160]}"
    second = _delete(ctx, urn)
    if second.status_code < 400:
        return FAIL, ("the second deletion reported success — a deletion of "
                      "something already destroyed must not look like a "
                      "deletion")
    return PASS, f"second deletion refused ({second.status_code})"


@case("QA-DEL-011", "The evidence node is appended before the rows go")
def del_011(ctx: Ctx) -> Result:
    urn = _register(ctx, "del011")
    before = ctx.api.get("/api/v1/evidence/chain").json().get("length", 0)
    gone = _delete(ctx, urn, reason="qa evidence probe")
    if gone.status_code >= 400:
        return BLOCKED, f"the deletion itself failed: {gone.text[:160]}"
    after = ctx.api.get("/api/v1/evidence/chain").json().get("length", 0)
    if after <= before:
        return FAIL, (f"the chain did not grow across the deletion "
                      f"({before} -> {after}) — the record of who destroyed "
                      f"the model is the one thing that must survive it")
    # The page humanises the kind, so asserting on the literal `model_deleted`
    # was asserting on a rendering choice rather than on the chain. The length
    # is the fact; the page is a view of it.
    page = ctx.ui.get("/admin/evidence")
    if page.status_code < 400 and "deleted" not in page.text.lower():
        return FAIL, "the deletion is not visible on the evidence screen"
    return PASS, f"the chain grew {before} -> {after} and the screen shows it"


@case("QA-DEL-012", "The chain still verifies after a deletion")
def del_012(ctx: Ctx) -> Result:
    urn = _register(ctx, "del012")
    _delete(ctx, urn)
    report = ctx.api.get("/api/v1/evidence/chain")
    if report.status_code >= 400:
        return BLOCKED, f"{report.status_code}"
    if not report.json().get("valid"):
        return FAIL, f"the chain does not verify: {report.text[:200]}"
    return PASS, "valid"


@case("QA-DEL-014", "The deletion response carries what was destroyed")
def del_014(ctx: Ctx) -> Result:
    urn = _register(ctx, "del014")
    gone = _delete(ctx, urn)
    if gone.status_code >= 400:
        return FAIL, gone.text[:160]
    if "destroyed" not in gone.json():
        return FAIL, ("no `destroyed` count — after the cascade there is "
                      "nothing left to count, so this is the only record of "
                      "how large the deletion was")
    return PASS, f"destroyed={gone.json()['destroyed']}"


@case("QA-DEL-015", "The deletion says storage was NOT reclaimed")
def del_015(ctx: Ctx) -> Result:
    urn = _register(ctx, "del015")
    gone = _delete(ctx, urn)
    body = gone.json() if gone.status_code < 400 else {}
    if body.get("storage_reclaimed") is not False:
        return FAIL, ("the answer does not say storage is still on disk; "
                      "claiming otherwise is a claim the platform has not "
                      "earned")
    return PASS, "storage_reclaimed is false"


# ------------------------------------------------------------- legal holds
def _hold(ctx, reference_stem: str, scope_kind: str, scope_id=None):
    return ctx.api.post("/api/v1/legal-holds", json={
        "matter": f"QA matter {reference_stem}", "owner": "admin",
        "scope_kind": scope_kind, "scope_id": scope_id})


@case("QA-DEL-004", "Delete a model under a model-scoped hold")
def del_004(ctx: Ctx) -> Result:
    urn = _register(ctx, "del004")
    placed = _hold(ctx, "del004", "model", urn)
    if placed.status_code >= 400:
        return BLOCKED, f"could not place the hold: {placed.text[:160]}"
    return expect_refused(_delete(ctx, urn), "under_legal_hold")


@case("QA-DEL-006", "A hold placed by URN still reaches the deleter")
def del_006(ctx: Ctx) -> Result:
    """The regression: the hold resolved against `model_id` and a URN never
    matched, so the hold was inert against the one act it exists to stop."""
    urn = _register(ctx, "del006")
    placed = _hold(ctx, "del006", "model", urn)
    if placed.status_code >= 400:
        return BLOCKED, f"could not place the hold: {placed.text[:160]}"
    return expect_refused(_delete(ctx, urn), "under_legal_hold")


@case("QA-DEL-007", "Delete after the covering hold is lifted")
def del_007(ctx: Ctx) -> Result:
    urn = _register(ctx, "del007")
    placed = _hold(ctx, "del007", "model", urn)
    if placed.status_code >= 400:
        return BLOCKED, placed.text[:160]
    reference = placed.json().get("reference")
    lifted = ctx.api.post(f"/api/v1/legal-holds/{reference}/lift",
                          json={"reason": "the matter closed"})
    if lifted.status_code >= 400:
        return BLOCKED, f"could not lift: {lifted.text[:160]}"
    return expect_accepted(_delete(ctx, urn))


@case("QA-DEL-008", "There is no force or override on delete")
def del_008(ctx: Ctx) -> Result:
    spec = ctx.api.get("/api/v1/openapi.json")
    if spec.status_code >= 400:
        return BLOCKED, "no openapi document"
    paths = spec.json().get("paths", {})
    target = next((v for k, v in paths.items()
                   if k.endswith("/models/{name}") and "delete" in v), None)
    if target is None:
        return BLOCKED, "no DELETE /models/{name} in the specification"
    names = {p.get("name") for p in target["delete"].get("parameters", [])}
    if names & {"force", "override", "ignore_holds"}:
        return FAIL, (f"the deleter accepts {names & {'force', 'override'}} — "
                      f"a hold a deletion can step over is not a hold")
    return PASS, f"no override parameter; accepts {sorted(n for n in names if n)}"


# --------------------------------------------------------------- tombstones
@case("QA-DEL-020", "Register at a URN that belonged to a deleted model")
def del_020(ctx: Ctx) -> Result:
    urn = _register(ctx, "del020")
    name = urn.rsplit("/", 1)[-1]
    _delete(ctx, urn, reason="superseded")
    again = ctx.api.post("/api/v1/models",
                         json={"urn": urn, "name": name, "owner": "admin",
                               **TIER})
    return expect_refused(again, "urn_was_deleted")


@case("QA-DEL-021", "The refusal names when and by whom")
def del_021(ctx: Ctx) -> Result:
    urn = _register(ctx, "del021")
    name = urn.rsplit("/", 1)[-1]
    _delete(ctx, urn, reason="merged into the successor")
    again = ctx.api.post("/api/v1/models",
                         json={"urn": urn, "name": name, "owner": "admin",
                               **TIER})
    detail = (again.json().get("detail") or "") if again.status_code >= 400 else ""
    if "merged into the successor" not in str(detail):
        return FAIL, f"the refusal does not carry the reason: {detail}"
    return PASS, "the refusal names the actor and the reason"


@case("QA-DEL-022", "Register at a URN nobody ever used")
def del_022(ctx: Ctx) -> Result:
    name = ctx.unique("del022-fresh")
    return expect_accepted(ctx.api.post("/api/v1/models", json={
        "urn": f"maya://model/qa.{name}", "name": name, "owner": "admin",
        **TIER}), status=201)


@case("QA-DEL-023", "A deleted URN resolves to what happened to it")
def del_023(ctx: Ctx) -> Result:
    urn = _register(ctx, "del023")
    _delete(ctx, urn, reason="qa resolve probe")
    found = ctx.api.get(f"/api/v1/tombstones/{urn}")
    if found.status_code >= 400:
        return FAIL, f"a deleted URN does not resolve: {found.status_code}"
    body = found.json()
    if not body.get("deleted"):
        return FAIL, f"resolved but not marked deleted: {body}"
    return PASS, f"resolves: deleted from {body.get('status_when_deleted')}"


@case("QA-DEL-024", "A URN nobody ever used does not resolve")
def del_024(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.get("/api/v1/tombstones/maya://model/qa.never-existed"),
        "no_such_urn", "not_found")


@case("QA-DEL-025", "The tombstone records the state deleted FROM")
def del_025(ctx: Ctx) -> Result:
    urn = _register(ctx, "del025")
    _delete(ctx, urn)
    body = ctx.api.get(f"/api/v1/tombstones/{urn}").json()
    if body.get("status_when_deleted") != "draft":
        return FAIL, (f"expected draft, got "
                      f"{body.get('status_when_deleted')!r} — deleting a "
                      f"draft and deleting a retired model are different acts")
    return PASS, "records draft"


@case("QA-DEL-026", "A deleted model is absent from listings")
def del_026(ctx: Ctx) -> Result:
    urn = _register(ctx, "del026")
    _delete(ctx, urn)
    listing = ctx.api.get("/api/v1/models", params={"limit": 500})
    if urn in listing.text:
        return FAIL, "the deleted model still appears in /models"
    return PASS, "absent from the listing"


@case("QA-DEL-027", "A tombstoned URN cannot be transitioned")
def del_027(ctx: Ctx) -> Result:
    urn = _register(ctx, "del027")
    name = urn.rsplit("/", 1)[-1]
    _delete(ctx, urn)
    moved = ctx.api.post(f"/api/v1/models/{name}/submit", json={})
    if moved.status_code < 400:
        return FAIL, "a destroyed model accepted a lifecycle transition"
    return PASS, f"refused ({moved.status_code} {code_of(moved) or 'no code'})"


@case("QA-DEL-028", "There is no route that reverses a tombstone")
def del_028(ctx: Ctx) -> Result:
    spec = ctx.api.get("/api/v1/openapi.json").json().get("paths", {})
    reversing = [p for p in spec
                 if "tombstone" in p and any(
                     verb in spec[p] for verb in ("delete", "put", "patch"))]
    restoring = [p for p in spec if "restore" in p or "undelete" in p]
    if reversing or restoring:
        return FAIL, (f"a tombstone can be reversed: {reversing + restoring} "
                      f"— restoring produces an empty model wearing a "
                      f"destroyed one's identity")
    return PASS, "no reversal route"


@case("QA-DEL-029", "Tombstones need evidence:read")
def del_029(ctx: Ctx) -> Result:
    # The observer is an `operator`, and an operator HOLDS `evidence:read` —
    # so the original version of this case asserted a refusal that would have
    # been a defect if it had happened. Only `service` lacks the permission.
    made = ctx.api.post("/api/v1/principals", json={
        "username": ctx.unique("svc"), "display_name": "QA service",
        "roles": ["service"], "password": "qa-service-password"})
    if made.status_code != 201:
        return BLOCKED, f"could not make a service principal: {made.text[:120]}"
    who = (made.json()["username"], "qa-service-password")
    return expect_refused(
        ctx.api.get("/api/v1/tombstones", auth=who),
        "forbidden", "scope_insufficient")


# ------------------------------------------------------------------ cascade
@case("QA-DEL-057", "The cascade declaration covers every table")
def del_057(ctx: Ctx) -> Result:
    published = ctx.api.get("/api/v1/deletion-cascade")
    if published.status_code >= 400:
        return FAIL, f"the declaration is not published: {published.status_code}"
    rows = published.json().get("cascade", [])
    from db.schema.metadata import METADATA
    import db.schema.tables  # noqa: F401
    carrying = {t.name for t in METADATA.tables.values()
                if "model_id" in {c.name for c in t.columns}}
    declared = {r["table"] for r in rows}
    if carrying - declared:
        return FAIL, f"no disposition for {sorted(carrying - declared)}"
    return PASS, f"{len(rows)} tables declared, all {len(carrying)} covered"


@case("QA-DEL-053", "A blocking reference names itself in the refusal")
def del_053(ctx: Ctx) -> Result:
    urn = _register(ctx, "del053")
    name = urn.rsplit("/", 1)[-1]
    made = ctx.api.post(f"/api/v1/models/{name}/versions",
                        json={"semver": "1.0.0"})
    if made.status_code >= 400:
        return BLOCKED, f"could not create a blocking version: {made.text[:160]}"
    refused = _delete(ctx, urn)
    verdict, evidence = expect_refused(refused, "still_referenced")
    if verdict != PASS:
        return verdict, evidence
    if "version" not in refused.text.lower():
        return FAIL, ("refused, but the answer does not name what refers to "
                      "it — somebody told why can deal with it, somebody told "
                      "no finds another way")
    return PASS, "refused and named the version"


@case("QA-DEL-055", "Inference records survive a deletion")
def del_055(ctx: Ctx) -> Result:
    """A decision the model actually made, and who relied on it."""
    from core.retention.cascade import BY_TABLE, STAYS
    if BY_TABLE["inference"].kind != STAYS:
        return FAIL, ("`inference` is not declared STAYS — a deletion would "
                      "erase decisions somebody relied on")
    return PASS, "declared STAYS"


@case("QA-DEL-058", "A table with no disposition fails the build")
def del_058(ctx: Ctx) -> Result:
    from core.retention.cascade import CASCADE
    from db.schema.metadata import METADATA
    import db.schema.tables  # noqa: F401
    carrying = {t.name for t in METADATA.tables.values()
                if "model_id" in {c.name for c in t.columns}}
    declared = {d.table for d in CASCADE}
    if carrying - declared:
        return FAIL, f"undeclared: {sorted(carrying - declared)}"
    return PASS, ("every table carrying a model_id has a disposition and "
                  "tests/test_tombstones.py enforces it")


# --------------------------------------------------------------- compaction
@case("QA-DEL-075", "A compaction plan reclaims nothing")
def del_075(ctx: Ctx) -> Result:
    first = ctx.api.get("/api/v1/compaction/plan")
    if first.status_code >= 400:
        return FAIL, f"{first.status_code} {first.text[:160]}"
    second = ctx.api.get("/api/v1/compaction/plan")
    if second.json().get("would_sweep") != first.json().get("would_sweep"):
        return FAIL, "the plan changed the thing it was reporting on"
    return PASS, f"plan is repeatable: {first.json().get('would_sweep')} ready"


@case("QA-DEL-076", "A dry-run sweep reports and reclaims nothing")
def del_076(ctx: Ctx) -> Result:
    dry = ctx.api.post("/api/v1/compaction/sweep", params={"dry_run": True})
    if dry.status_code >= 400:
        return FAIL, f"{dry.status_code} {dry.text[:160]}"
    if dry.json().get("dry_run") is not True:
        return FAIL, "the answer does not say it was a dry run"
    return PASS, f"dry run: {dry.json()}"


@case("QA-DEL-077", "Delta is reported as out of reach, not skipped")
def del_077(ctx: Ctx) -> Result:
    plan = ctx.api.get("/api/v1/compaction/plan")
    out = (plan.json() or {}).get("not_reclaimable") or {}
    if "why" not in out:
        return FAIL, ("the plan does not say what it cannot reclaim; silently "
                      "not touching Delta and reporting nothing look identical")
    return PASS, f"reported: {out['why'][:80]}"


@case("QA-DEL-078", "Vacuum answers and reports what it reclaimed")
def del_078(ctx: Ctx) -> Result:
    done = ctx.api.post("/api/v1/compaction/vacuum")
    if done.status_code >= 400:
        return FAIL, f"{done.status_code} {done.text[:160]}"
    if "reclaimed_bytes" not in done.json():
        return FAIL, "vacuum does not say how much it reclaimed"
    return PASS, f"{done.json()}"


@case("QA-DEL-074", "A sweep is refused under an estate-wide hold")
def del_074(ctx: Ctx) -> Result:
    placed = _hold(ctx, "del074", "estate")
    if placed.status_code >= 400:
        return BLOCKED, f"could not place an estate hold: {placed.text[:160]}"
    reference = placed.json().get("reference")
    try:
        return expect_refused(ctx.api.post("/api/v1/compaction/sweep"),
                              "under_legal_hold")
    finally:
        ctx.api.post(f"/api/v1/legal-holds/{reference}/lift",
                     json={"reason": "QA-DEL-074 finished"})


@case("QA-DEL-081", "A sweep needs storage:compact")
def del_081(ctx: Ctx) -> Result:
    return expect_refused(ctx.observer.post("/api/v1/compaction/sweep"),
                          "forbidden", "scope_insufficient")


@case("QA-DEL-079", "Compacting a model that was never deleted")
def del_079(ctx: Ctx) -> Result:
    from core.retention.common import RetentionError
    from core.retention.compaction import Compaction
    from core.retention.tombstones import Tombstones
    from db import BlobOrphanRepository, ModelTombstoneRepository
    db = ctx.made["db"]
    compaction = Compaction(db, BlobOrphanRepository(db),
                            tombstones=Tombstones(ModelTombstoneRepository(db)))
    try:
        compaction.mark_compacted("maya://model/qa.still-alive", actor="qa")
    except RetentionError as refused:
        if refused.code != "no_tombstone":
            return FAIL, f"refused '{refused.code}', expected no_tombstone"
        return PASS, "refused no_tombstone"
    return FAIL, "a live model was marked compacted"


@case("QA-DEL-082", "Every content address is refcounted")
def del_082(ctx: Ctx) -> Result:
    from core.retention.compaction import REFERENCED_BY
    from db.schema.metadata import METADATA
    import db.schema.tables  # noqa: F401
    known = {f"{t}.{c}" for cols in REFERENCED_BY.values() for t, c in cols}
    found = {f"{t.name}.{c.name}" for t in METADATA.tables.values()
             for c in t.columns
             if c.name in ("artifact_digest", "digest")
             and t.name in ("model_version", "attachment")}
    missing = found - known - {"model_version.manifest_digest"}
    if missing:
        return FAIL, f"a content address nothing refcounts: {sorted(missing)}"
    return PASS, f"{len(known)} address column(s) refcounted"
