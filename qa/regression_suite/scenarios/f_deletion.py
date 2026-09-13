"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — deleting a model.

The only act in this platform with no workflow, no reversal and no second
signature. Three things guard it and each is tested from both sides here: the
reference check (nineteen tables carry a `model_id`), the legal hold (no
`force`, deliberately), and the tombstone — which is not a wiring assertion
but a control, because a deletion with no tombstone frees the URN, the URN is
derived from the name, and the next model registered under that name silently
inherits every evidence node and closed finding belonging to the old one.

The ordering matters as much as the checks. The hold is asked BEFORE the
evidence node, so a refused deletion leaves no `model_deleted` in the chain
saying somebody destroyed a record they did not destroy.

Every case that places a hold is `isolated`: an estate hold covers every model
a later case creates.
"""
from __future__ import annotations

from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

M = "/api/v1/models"
H = "/api/v1/legal-holds"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> tuple:
    name = ctx.unique("dl")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    return name, urn


def _hold(ctx: Ctx, **over):
    body = {"matter": "SEC subpoena 2026-114", "owner": "person/legal-counsel",
            "scope_kind": "estate", "scope_id": None, "classes": []}
    body.update(over)
    return ctx.api.post(H, json=body, auth=ctx.people["risk"])


def _delete(ctx: Ctx, name: str, *, reason: str = "qa", who=ADMIN):
    return ctx.api.delete(f"{M}/{name}?reason={reason}", auth=who)


def _chain(ctx: Ctx) -> dict:
    engine = ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")
    seq, _head = engine.head()
    return {"seq": seq, "engine": engine}


def _deleted_nodes(ctx: Ctx, model_id: str) -> list:
    engine = ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")
    return [n for n in engine.for_subject(model_id)
            if n.get("kind") == "model_deleted"]


@case("QA-GOV-293",
      "Delete a model as a principal holding `model:delete` but not the admin")
def gov_293(ctx: Ctx) -> Result:
    """Only an administrator may delete; everyone else retires. Retiring
    withdraws the model from use and keeps every reference readable, which is
    what almost everybody asking to delete actually wants.

    Checked against the ROLE rather than only the permission, because a
    permission can be granted to a role by mistake and requiring `admin`
    explicitly means the mistake has to be made twice. So this case mints a
    role that holds `model:delete` — no shipped role does — and the caller
    reaches the control instead of being stopped at the door.
    """
    role = ctx.unique("role")
    if ctx.api.post("/api/v1/roles",
                    json={"name": role,
                          "description": "holds model:delete and nothing else",
                          "permissions": ["model:delete", "model:read"]},
                    auth=ADMIN).status_code >= 400:
        return BLOCKED, "the deleting role could not be defined"
    who = ctx.unique("dp")
    if ctx.api.post("/api/v1/principals",
                    json={"username": who, "display_name": who,
                          "roles": [role], "password": f"{who}-password",
                          "legal_entities": [], "domains": []},
                    auth=ADMIN).status_code >= 400:
        return BLOCKED, "the deleting principal could not be created"
    name, _urn = _model(ctx)
    got = _delete(ctx, name, who=(who, f"{who}-password"))
    outcome = refused_by_the_control(
        got, "a non-administrator deleted a model")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "deletion_refused":
        return FAIL, (f"refused '{code_of(got)}' — the permission stopped the "
                      f"caller, so the role check behind it is untested here")
    if "retire" not in got.text:
        return FAIL, ("the refusal does not name retirement, so somebody told "
                      "no finds another way rather than the right way")
    return PASS, "refused 'deletion_refused', naming retirement"


@case("QA-GOV-294", "Delete with no reason")
def gov_294(ctx: Ctx) -> Result:
    """The reason is the only thing the tombstone will carry about why."""
    name, _urn = _model(ctx)
    got = _delete(ctx, name, reason="")
    outcome = refused_by_the_control(got, "a model deleted with no reason")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "reason_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'reason_required'"


@case("QA-GOV-295", "Delete under an estate-wide legal hold", isolated=True)
def gov_295(ctx: Ctx) -> Result:
    """`estate` is deliberately available: a document request does not arrive
    scoped to the models somebody would have chosen."""
    name, _urn = _model(ctx)
    placed = _hold(ctx, scope_kind="estate")
    if placed.status_code >= 400:
        return BLOCKED, f"the hold could not be placed: {placed.text[:140]}"
    reference = ((placed.json() or {}).get("hold")
                 or placed.json() or {}).get("reference")
    got = _delete(ctx, name)
    outcome = refused_by_the_control(got, "a model deleted under an estate hold")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "under_legal_hold":
        return FAIL, f"refused '{code_of(got)}'"
    if reference and reference not in got.text:
        return FAIL, ("the refusal does not name the hold, so nobody knows "
                      "which matter to go and close")
    return PASS, f"refused 'under_legal_hold', naming {reference}"


@case("QA-GOV-296",
      "Delete under a hold scoped to the model by **URN** rather than "
      "internal id", isolated=True)
def gov_296(ctx: Ctx) -> Result:
    """The recorded defect from the other end. `applies` compares `scope_id`
    against the internal row id, and a URN is what a person has — so unless
    `place` resolves it, the hold a lawyer placed does not stop the deletion
    it was placed to stop."""
    name, urn = _model(ctx)
    placed = _hold(ctx, scope_kind="model", scope_id=urn)
    if placed.status_code >= 400:
        return BLOCKED, f"the hold could not be placed: {placed.text[:140]}"
    got = _delete(ctx, name)
    if got.status_code < 400:
        return FAIL, ("a model was deleted through a hold placed with its "
                      "URN: `place` stored the URN and `applies` compares "
                      "against the internal row id, so the hold matched "
                      "nothing")
    if code_of(got) != "under_legal_hold":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'under_legal_hold' on a URN-scoped hold"


@case("QA-GOV-298",
      "Delete under a hold whose `classes` do not include `model_record`",
      isolated=True)
def gov_298(ctx: Ctx) -> Result:
    """A hold over the telemetry is not a hold over the record. Narrowing by
    class is what makes a hold proportionate, and it has to actually
    narrow."""
    name, urn = _model(ctx)
    placed = _hold(ctx, scope_kind="model", scope_id=urn,
                   classes=["telemetry"])
    if placed.status_code >= 400:
        return BLOCKED, f"the hold could not be placed: {placed.text[:140]}"
    got = _delete(ctx, name)
    if got.status_code >= 400 and code_of(got) == "under_legal_hold":
        return FAIL, ("a hold over `telemetry` stopped a deletion of the "
                      "model record, so narrowing by class narrows nothing")
    if got.status_code >= 400:
        return BLOCKED, f"refused for another reason: {got.text[:140]}"
    return PASS, "a class-narrowed hold does not cover the model record"


@case("QA-GOV-299", "Delete under a hold with an empty `classes` list",
      isolated=True)
def gov_299(ctx: Ctx) -> Result:
    """The other side of QA-GOV-298, and the direction that must fail safe:
    an empty list is *everything*, not *nothing*. Reading it as nothing would
    make the default hold — the one a lawyer places without thinking about
    artefact classes — cover no artefact at all."""
    name, urn = _model(ctx)
    placed = _hold(ctx, scope_kind="model", scope_id=urn, classes=[])
    if placed.status_code >= 400:
        return BLOCKED, f"the hold could not be placed: {placed.text[:140]}"
    got = _delete(ctx, name)
    if got.status_code < 400:
        return FAIL, ("a hold with no classes named covered nothing: an empty "
                      "list is being read as *no artefact class* rather than "
                      "*every* one, so the hold a lawyer places without "
                      "naming classes holds nothing")
    if code_of(got) != "under_legal_hold":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'under_legal_hold' — an empty class list is all of them"


@case("QA-GOV-301", "Delete, then check the evidence chain")
def gov_301(ctx: Ctx) -> Result:
    """The evidence survives the deletion by design, and it is the only
    remaining record of the act. The node is appended BEFORE the rows go, so
    the chain records the intent even if the removal fails halfway."""
    name, urn = _model(ctx)
    model_id = (ctx.api.get(f"{M}/{name}", auth=ADMIN).json()
                or {}).get("model", {}).get("id")
    if not model_id:
        return BLOCKED, "the model id could not be read"
    got = _delete(ctx, name, reason="a QA deletion")
    if got.status_code >= 400:
        return BLOCKED, f"the deletion failed: {got.text[:140]}"
    nodes = _deleted_nodes(ctx, model_id)
    if not nodes:
        return FAIL, ("the model is gone and the chain holds no "
                      "`model_deleted` node, so the only remaining record of "
                      "the act is the log")
    engine = ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")
    report = engine.verify_chain()
    if not report.get("valid"):
        return FAIL, f"the chain does not verify after a deletion: {report}"
    body = got.json() or {}
    if not body.get("evidence_retained"):
        return FAIL, "the deletion does not report that the evidence is kept"
    if body.get("urn_reusable"):
        return FAIL, (f"'{urn}' is reported as reusable, so the next model "
                      f"under this name inherits its history")
    return PASS, (f"{len(nodes)} model_deleted node(s), chain verifies, the "
                  f"urn is not reusable")


@case("QA-GOV-302", "Refused deletion leaves no `model_deleted` node",
      isolated=True)
def gov_302(ctx: Ctx) -> Result:
    """The ordering the module promises. A `model_deleted` node written
    before the refusal would say somebody destroyed a record they did not
    destroy — and the chain is the one thing that survives, so that sentence
    would be the permanent one."""
    name, urn = _model(ctx)
    model_id = (ctx.api.get(f"{M}/{name}", auth=ADMIN).json()
                or {}).get("model", {}).get("id")
    if not model_id:
        return BLOCKED, "the model id could not be read"
    if _hold(ctx, scope_kind="model", scope_id=urn).status_code >= 400:
        return BLOCKED, "the hold could not be placed"
    before = _chain(ctx)["seq"]
    got = _delete(ctx, name)
    if got.status_code < 400:
        return BLOCKED, "the deletion was not refused, so there is nothing to test"
    nodes = _deleted_nodes(ctx, model_id)
    if nodes:
        return FAIL, (f"a refused deletion left {len(nodes)} `model_deleted` "
                      f"node(s) on the chain, which permanently records a "
                      f"destruction that did not happen")
    after = _chain(ctx)["seq"]
    read = ctx.api.get(f"{M}/{name}", auth=ADMIN)
    if read.status_code >= 400:
        return FAIL, "the model is gone after a refused deletion"
    return PASS, (f"no model_deleted node; the chain moved {after - before} "
                  f"node(s) and the model is still there")


@case("QA-GOV-303", "Delete the same model twice")
def gov_303(ctx: Ctx) -> Result:
    """The second deletion has nothing to delete, and it must not write a
    second tombstone for one act."""
    name, _urn = _model(ctx)
    if _delete(ctx, name).status_code >= 400:
        return BLOCKED, "the first deletion failed"
    got = _delete(ctx, name)
    outcome = refused_by_the_control(got, "a model was deleted twice")
    if outcome[0] is not PASS:
        return outcome
    stones = ctx.api.get("/api/v1/tombstones", auth=ADMIN)
    rows = [t for t in ((stones.json() or {}).get("tombstones") or [])
            if t.get("name") == name]
    if len(rows) > 1:
        return FAIL, f"{len(rows)} tombstones for one deletion"
    return PASS, f"refused '{code_of(got)}', one tombstone"


@case("QA-GOV-304", "Delete a model with an alias pointing into production")
def gov_304(ctx: Ctx) -> Result:
    """EXPLORATORY. An alias is a reference, and the reference check is what
    stands between a deletion and nineteen tables of rows pointing at an
    identifier that no longer resolves."""
    from qa.regression_suite.scenarios.g_execution import governed
    made = governed(ctx)
    got = _delete(ctx, made["name"])
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — a model serving from "
                      f"prod/champion cannot simply stop existing")
    return FAIL, ("a model with `prod/champion` bound to it was deleted: the "
                  "alias, the warrant grants and the version rows now point "
                  "at an identifier that no longer resolves")


@case("QA-GOV-305",
      "Read `GET /as-at` over a window containing a deleted model")
def gov_305(ctx: Ctx) -> Result:
    """History is what the register said at a moment, and a deletion today
    does not change what was true last week. A point-in-time read that hid
    the model would rewrite the past to match the present."""
    import time
    name, urn = _model(ctx)
    when = time.time()
    if _delete(ctx, name).status_code >= 400:
        return BLOCKED, "the deletion failed"
    got = ctx.api.get(f"/api/v1/as-at?at={when}", auth=ADMIN)
    if got.status_code >= 400:
        return BLOCKED, f"the as-at read answered {got.status_code}"
    if urn not in got.text:
        return FAIL, (f"'{urn}' existed at {when:.0f} and a point-in-time read "
                      f"over that moment does not show it, so deleting a "
                      f"model rewrites what the register said before it went")
    return PASS, "the deleted model is still in the history that contained it"
