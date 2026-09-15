"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section G — the revocation floor, and the residual it does not close.

MAYA does not run engines and has no channel to push a withdrawal down one. So
revocation reaches an engine indirectly: the epoch advances on every
withdrawal, every descriptor carries the epoch it was minted at, and an engine
that has been handed epoch 7 refuses anything stamped below it — **offline**,
needing nothing but what it has already been shown.

What that does not buy is the larger half, and it is stated rather than
implied: an engine that never sees a newer descriptor honours a revoked warrant
until it expires. The bound on that residual is the severity-scaled TTL, which
is why a Tier 1 descriptor lives sixty seconds with no grace — for the models
the original finding was about there is almost nothing left for a floor to do.

The epoch is estate-wide, so what it counts is *how many times authority has
been withdrawn anywhere*, and both halves of that matter: a bump per grant
would make every outstanding descriptor stale for the wrong reason, and a
skipped bump would leave a hole somebody's descriptor falls through.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)
from qa.regression_suite.scenarios.g_execution import governed

W = "/api/v1/warrants"


def _grants(ctx: Ctx):
    """The GRANT register, which owns the epoch.

    `ctx["warrants"]` is the `WarrantService` above it; its `epoch` property
    delegates to `self.grants`, and the counter lives there."""
    service = ctx.ui.app.state.ctx.get("warrants")
    return getattr(service, "grants", None)


def _grant(ctx: Ctx, urn: str, principal: str = "svc-pricing"):
    return ctx.api.post(W, json={"urn": urn, "principal": principal,
                                 "environment": "prod",
                                 "declared_use": "credit_decision"})


def _resolve(ctx: Ctx, urn: str, principal: str = "svc-pricing"):
    return ctx.api.post("/api/v1/resolve",
                        json={"urn": urn, "principal": principal,
                              "environment": "prod",
                              "declared_use": "credit_decision"})


def _engine(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("engine")


@case("QA-FX-380", "A descriptor stamped exactly at the epoch seen")
def fx_380(ctx: Ctx) -> Result:
    """The boundary. A strict comparison is the difference between refusing
    a replay and refusing the descriptor the engine was just handed."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no execution engine is wired"
    at_seven = {"authority": {"revocation": {"epoch": 7}}}
    engine._seen_epoch = 0
    engine._refuse_stale_epoch(at_seven)
    if engine._seen_epoch != 7:
        return FAIL, (f"seeing epoch 7 left the engine at "
                      f"{engine._seen_epoch}")
    try:
        engine._refuse_stale_epoch({"authority": {"revocation": {"epoch": 7}}})
    except Exception as exc:
        return FAIL, (f"a descriptor stamped exactly at the epoch already seen "
                      f"was refused '{getattr(exc, 'code', type(exc).__name__)}'"
                      f" — the comparison is not strict, so the engine refuses "
                      f"the descriptor it was just handed")
    return PASS, "epoch 7 after epoch 7 is accepted; the comparison is `<`"


@case("QA-FX-379", "A descriptor stamped below the epoch the engine has seen")
def fx_379(ctx: Ctx) -> Result:
    """Refused offline, 410 `revoked_epoch`. A descriptor arriving stamped
    below one the engine has seen was minted before a withdrawal, so it is
    either a replay or one that waited in a queue across it."""
    from core.execution.errors import WarrantError
    from routes.base import STATUS
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no execution engine is wired"
    engine._seen_epoch = 0
    engine._refuse_stale_epoch({"authority": {"revocation": {"epoch": 7}}})
    try:
        engine._refuse_stale_epoch({"authority": {"revocation": {"epoch": 5}}})
    except WarrantError as exc:
        if exc.code != "revoked_epoch":
            return FAIL, f"refused '{exc.code}' rather than revoked_epoch"
        if STATUS.get("revoked_epoch") != 410:
            return FAIL, (f"'revoked_epoch' maps to "
                          f"{STATUS.get('revoked_epoch')} rather than 410")
        if "5" not in str(exc) or "7" not in str(exc):
            return FAIL, f"the refusal names neither epoch: {str(exc)[:130]}"
        if engine._seen_epoch != 7:
            return FAIL, "a refused descriptor moved the engine's floor"
        return PASS, f"refused 'revoked_epoch' → 410: {str(exc)[:110]}"
    return FAIL, "a descriptor minted before a seen withdrawal was accepted"


@case("QA-FX-381", "A descriptor stamped above, then one between")
def fx_381(ctx: Ctx) -> Result:
    """The floor only rises. Seeing 9 makes 8 stale, which is the whole
    mechanism: an engine's knowledge of how many withdrawals have happened
    is whatever the newest descriptor it has been shown says."""
    from core.execution.errors import WarrantError
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no execution engine is wired"
    engine._seen_epoch = 7
    engine._refuse_stale_epoch({"authority": {"revocation": {"epoch": 9}}})
    if engine._seen_epoch != 9:
        return FAIL, f"seeing epoch 9 left the floor at {engine._seen_epoch}"
    try:
        engine._refuse_stale_epoch({"authority": {"revocation": {"epoch": 8}}})
    except WarrantError as exc:
        if exc.code != "revoked_epoch":
            return FAIL, f"refused '{exc.code}'"
        return PASS, "9 accepted and the floor rises; 8 is then stale"
    return FAIL, ("epoch 8 was accepted after epoch 9, so the floor does not "
                  "rise and a descriptor from before a withdrawal still runs")


@case("QA-FX-382", "A descriptor carrying no epoch at all")
def fx_382(ctx: Ctx) -> Result:
    """`if stamped is None: return` — the check bypasses the floor entirely
    for an unstamped descriptor, which is exactly the shape a replay takes
    if the attacker controls the document."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no execution engine is wired"
    engine._seen_epoch = 12
    for what, descriptor in (
            ("no authority", {}),
            ("no revocation", {"authority": {}}),
            ("no epoch", {"authority": {"revocation": {}}}),
            ("a null epoch", {"authority": {"revocation": {"epoch": None}}})):
        try:
            engine._refuse_stale_epoch(descriptor)
        except Exception as exc:
            return PASS, (f"an unstamped descriptor ({what}) is refused "
                          f"'{getattr(exc, 'code', type(exc).__name__)}'")
    if engine._seen_epoch != 12:
        return FAIL, "an unstamped descriptor moved the floor"
    return FAIL, (
        "a descriptor carrying no revocation epoch bypasses the floor "
        "entirely: `_refuse_stale_epoch` returns early when `stamped is None`, "
        "and all four shapes of absence — no `authority`, no `revocation`, no "
        "`epoch`, a null `epoch` — take that branch against an engine sitting "
        "at epoch 12. The floor's premise is that a descriptor's stamp is "
        "trustworthy because the descriptor is signed; the early return is the "
        "one path where an unsigned or stripped document is treated as "
        "unremarkable rather than as the thing it most resembles. Refusing an "
        "unstamped descriptor outright would cost nothing: the builder stamps "
        "every one it mints")


@case("QA-FX-384", "`note_revocation` with a model URN", isolated=True)
def fx_384(ctx: Ctx) -> Result:
    """The URN survives a re-resolve, which is why it is the form that
    works. Driven through `engine.execute` rather than `/resolve` — the
    floor is the ENGINE's, for the case where it has been told to stop and
    cannot reach MAYA to have it confirmed."""
    from core.execution.errors import WarrantError
    made = governed(ctx)
    urn = made["urn"]
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no execution engine is wired"
    if _grant(ctx, urn).status_code >= 400:
        return BLOCKED, "the grant could not be issued"
    try:
        engine.execute(urn, "prod", "svc-pricing", "credit_decision", {})
    except WarrantError as exc:
        if exc.code in ("revoked", "revoked_epoch"):
            return BLOCKED, f"the warrant was already refused: {exc.code}"
    except Exception as runtime:
        # A runtime failure is not what this case asks about; the floor is
        # checked before anything is loaded.
        del runtime
    engine.note_revocation(urn)
    try:
        engine.execute(urn, "prod", "svc-pricing", "credit_decision", {})
    except WarrantError as exc:
        if exc.code != "revoked":
            return FAIL, f"refused '{exc.code}' rather than 'revoked'"
        if urn not in str(exc):
            return FAIL, f"the refusal does not name the subject: {str(exc)[:120]}"
        if "grace" not in str(getattr(exc, "remediation", "")):
            return FAIL, ("the refusal does not say grace never extends "
                          "revocation ignorance")
        return PASS, f"refused 'revoked' on the model URN: {str(exc)[:110]}"
    except Exception as exc:
        return FAIL, (f"a locally revoked model raised "
                      f"{type(exc).__name__} rather than refusing 'revoked': "
                      f"{str(exc)[:110]}")
    return FAIL, ("a model noted as revoked locally still executed; the floor "
                  "is for an engine that cannot reach MAYA and it did not fire")


@case("QA-FX-385", "`note_revocation` with a `warrant_id`", isolated=True)
def fx_385(ctx: Ctx) -> Result:
    """Every `build` mints a fresh id, so an id noted from one descriptor
    may never match the next. An identifier that moves while the thing it
    names stays the same is finding C-2 from the other side — and a local
    list that looks enabled and does nothing is the worse half."""
    from core.execution.errors import WarrantError
    made = governed(ctx)
    urn = made["urn"]
    engine = _engine(ctx)
    warrants = ctx.ui.app.state.ctx.get("warrants")
    if engine is None or warrants is None:
        return BLOCKED, "no execution engine is wired"
    if _grant(ctx, urn).status_code >= 400:
        return BLOCKED, "the grant could not be issued"
    first = warrants.resolve(urn, "prod", "svc-pricing", "credit_decision")
    second = warrants.resolve(urn, "prod", "svc-pricing", "credit_decision")
    if first["warrant_id"] == second["warrant_id"]:
        return PASS, (f"the descriptor id is stable across a re-resolve "
                      f"({first['warrant_id'][:16]}), so noting one works")
    engine.note_revocation(first["warrant_id"])
    try:
        engine.execute(urn, "prod", "svc-pricing", "credit_decision", {})
    except WarrantError as exc:
        if exc.code == "revoked":
            return PASS, ("noting a descriptor id refused the next execution "
                          "anyway")
    except Exception as runtime:
        del runtime
    return FAIL, (
        f"`note_revocation` accepts a `warrant_id`, and the id moves: two "
        f"resolutions of one grant minted {first['warrant_id'][:16]}… and "
        f"{second['warrant_id'][:16]}…, so an id noted from one never matches "
        f"the one `execute` checks and the floor cannot fire. An engine told "
        f"to stop by descriptor id holds a local revocation list that looks "
        f"enabled and does nothing — the model URN is the form that works, and "
        f"both are accepted with nothing distinguishing them")


@case("QA-FX-386", "Revocation bumps the epoch by exactly one", isolated=True)
def fx_386(ctx: Ctx) -> Result:
    """An epoch that jumped per grant would make every outstanding
    descriptor stale for the wrong reason: four withdrawals of one model's
    authority are one withdrawal, and the estate-wide counter should say
    so."""
    made = governed(ctx)
    urn = made["urn"]
    grants = _grants(ctx)
    if grants is None:
        return BLOCKED, "no grant register is wired"
    for n in range(4):
        if _grant(ctx, urn, principal=f"svc-{n}").status_code >= 400:
            return BLOCKED, f"grant {n} could not be issued"
    before = grants.epoch
    got = ctx.api.post(f"{W}/revoke",
                       json={"urn": urn, "reason": "qa withdrawal"})
    if got.status_code >= 400:
        return BLOCKED, f"the revocation was refused: {got.text[:150]}"
    body = got.json() or {}
    if body.get("revoked") != 4:
        return FAIL, f"{body.get('revoked')} of 4 grants were withdrawn"
    moved = grants.epoch - before
    if moved == 1:
        return PASS, f"4 grants withdrawn, epoch {before} → {grants.epoch}"
    return FAIL, (
        f"withdrawing one model's authority moved the estate-wide epoch by "
        f"{moved} ({before} → {grants.epoch}), one per grant. "
        f"`revoke_model` loops `revoke`, and `revoke` does `self.epoch += 1` — "
        f"so a model with forty grants advances the floor forty times. Every "
        f"descriptor outstanding anywhere in the estate is now stale by "
        f"{moved} rather than by one, and an engine refusing them reports "
        f"`revoked_epoch` — a withdrawal it was never told about, for a model "
        f"it does not serve")


@case("QA-FX-387", "Revoking a model with no grants", isolated=True)
def fx_387(ctx: Ctx) -> Result:
    """The epoch is estate-wide. Skipping the bump on an empty revocation
    leaves a hole in the sequence — and the question is whether an empty
    withdrawal is a withdrawal at all."""
    made = governed(ctx)
    urn = made["urn"]
    grants = _grants(ctx)
    if grants is None:
        return BLOCKED, "no grant register is wired"
    before = grants.epoch
    got = ctx.api.post(f"{W}/revoke",
                       json={"urn": urn, "reason": "qa withdrawal"})
    if got.status_code >= 400:
        return BLOCKED, f"the revocation was refused: {got.text[:150]}"
    body = got.json() or {}
    if body.get("revoked") != 0:
        return BLOCKED, f"{body.get('revoked')} grant(s) existed after all"
    if grants.epoch > before:
        return PASS, (f"an empty revocation still advanced the epoch "
                      f"{before} → {grants.epoch}")
    if body.get("epoch") != grants.epoch:
        return FAIL, (f"the answer reports epoch {body.get('epoch')} and the "
                      f"register holds {grants.epoch}")
    return FAIL, (
        f"revoking a model nobody holds a grant on reports `revoked: 0` and "
        f"leaves the epoch at {before}. `revoke_model` advances the counter "
        f"inside the per-grant loop, so an empty withdrawal advances it "
        f"nothing — the act is recorded as having happened and the mechanism "
        f"that carries a withdrawal to an engine does not move. A caller who "
        f"revokes a model, sees `revoked: 0` and an unchanged epoch has been "
        f"told two different things about whether anything happened")


@case("QA-FX-388", "The epoch after a restart")
def fx_388(ctx: Ctx) -> Result:
    """Resumed from the register, not reset to zero. A grant issued at epoch
    0 after a restart is indistinguishable from one predating every
    withdrawal, and every engine holding a newer descriptor would refuse
    it."""
    from core.execution.grants import WarrantGrants
    grants = _grants(ctx)
    db = ctx.ui.app.state.ctx.get("db")
    if grants is None or db is None:
        return BLOCKED, "no grant register is wired"
    made = governed(ctx)
    urn = made["urn"]
    for n in range(3):
        if _grant(ctx, urn, principal=f"svc-r{n}").status_code >= 400:
            return BLOCKED, f"grant {n} could not be issued"
        ctx.api.post(f"{W}/revoke", json={"urn": urn, "reason": "qa"})
    highest = db.query("SELECT MAX(epoch) AS e FROM warrant")[0]["e"]
    if not highest:
        return BLOCKED, "no grant carries an epoch"
    restarted = WarrantGrants(grants.repo, grants.registry, grants.evidence)
    if restarted.epoch == 0:
        return FAIL, (f"a restart reset the epoch to 0 against a register "
                      f"holding {highest}; every grant issued now is stamped "
                      f"as predating every withdrawal")
    if restarted.epoch != highest:
        return FAIL, (f"the restarted register resumed at {restarted.epoch} "
                      f"against a maximum of {highest}")
    return PASS, (f"the epoch resumed at {restarted.epoch} from the register "
                  f"rather than resetting to 0")
