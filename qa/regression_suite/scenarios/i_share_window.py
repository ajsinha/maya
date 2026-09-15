"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the window and the read limit on a shared pack.

A share points at a pack **by content, not by path**: a share naming a
location would serve whatever is at that location later, which is how a
document a firm handed over becomes one nobody can reproduce. It names a
recipient and a purpose, because *who did we give this to* is the first
question asked when a pack turns up somewhere unexpected, and a year later
the purpose is the only part that explains why a model record left the
building.

It also establishes NO identity. There is no credential behind the link by
design, because issuing one means issuing it to somebody outside the firm —
so `identity_established` is false on every read, said out loud rather than
left to be assumed.
"""
from __future__ import annotations

import time

from core.export.sharing import MAX_DAYS
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)
from qa.regression_suite.scenarios.i_sharing import S, _packed, _share

DAY = 86400.0


def _service(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("export_sharing") or \
        ctx.ui.app.state.ctx.get("sharing")


def _reference(made) -> str:
    if made.status_code >= 400:
        return ""
    body = made.json() or {}
    return (body.get("share") or body).get("reference", "")


def _status(ctx: Ctx, reference: str) -> dict:
    got = ctx.api.get(f"{S}?reference={reference}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return {}
    body = got.json() or {}
    rows = body.get("shares") or []
    for row in rows:
        if row.get("reference") == reference:
            return row
    return body.get("share") or body


@case("QA-PLT-165", "The share window at 90 days and at 91")
def plt_165(ctx: Ctx) -> Result:
    """A supervisory request has a response date and a share should not
    outlive it. Ninety days is the ceiling and it is inclusive; where a firm
    genuinely needs longer it renews, which is a decision somebody takes
    again."""
    urn, digest = _packed(ctx)
    at = _share(ctx, urn, digest, days=MAX_DAYS)
    if at.status_code >= 400:
        return FAIL, (f"refused '{code_of(at)}' at exactly {MAX_DAYS:.0f} "
                      f"days, so the documented ceiling is a day lower")
    over = _share(ctx, urn, digest, days=MAX_DAYS + 1)
    if over.status_code < 400:
        return FAIL, f"{MAX_DAYS + 1:.0f} days was accepted"
    if code_of(over) != "window_out_of_range":
        return FAIL, f"refused '{code_of(over)}'"
    if "renew" not in over.text:
        return FAIL, ("the refusal does not name renewal, so a firm that "
                      "genuinely needs longer is told no with nowhere to go")
    return PASS, f"{MAX_DAYS:.0f} accepted, {MAX_DAYS + 1:.0f} refused"


@case("QA-PLT-166", "A share created without a purpose or a recipient")
def plt_166(ctx: Ctx) -> Result:
    """Both are required and both refuse on whitespace, which is the form
    the omission actually takes — a script filling a template leaves a space,
    not a missing key."""
    urn, digest = _packed(ctx)
    no_one = _share(ctx, urn, digest, recipient="   ")
    if no_one.status_code < 400:
        return FAIL, "a share was created for nobody"
    if code_of(no_one) != "recipient_required":
        return FAIL, f"the empty recipient refused '{code_of(no_one)}'"
    no_why = _share(ctx, urn, digest, purpose="  ")
    if no_why.status_code < 400:
        return FAIL, "a share was created for no stated reason"
    if code_of(no_why) != "purpose_required":
        return FAIL, f"the empty purpose refused '{code_of(no_why)}'"
    return PASS, "refused 'recipient_required' and 'purpose_required'"


@case("QA-PLT-158", "A share created with `max_reads: 0`")
def plt_158(ctx: Ctx) -> Result:
    """`int(max_reads) if max_reads else None` — and 0 is falsy, so a share
    asking for NO permitted reads is stored with no limit at all. The
    request and its opposite produce the same row."""
    urn, digest = _packed(ctx)
    got = _share(ctx, urn, digest, max_reads=0)
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — a share nobody may read is "
                      f"not a share")
    reference = _reference(got)
    row = _status(ctx, reference) or (got.json() or {})
    if row.get("max_reads") == 0:
        return PASS, "stored as 0, so no read is permitted"
    return FAIL, (f"`max_reads: 0` was stored as {row.get('max_reads')!r}: "
                  f"the guard is `if max_reads`, and zero is falsy, so asking "
                  f"for NO permitted reads produces a share with NO LIMIT — "
                  f"the exact inverse of the request, and the one direction "
                  f"that cannot be noticed by reading the row back")


@case("QA-PLT-159", "A share created with `max_reads: -1`")
def plt_159(ctx: Ctx) -> Result:
    """A negative read limit is not a quantity. `_state` compares
    `reads >= max_reads`, so -1 makes the share exhausted before it is ever
    opened — which is at least safe, and is still a row nobody can read as
    intended."""
    urn, digest = _packed(ctx)
    got = _share(ctx, urn, digest, max_reads=-1)
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    reference = _reference(got)
    row = _status(ctx, reference) or (got.json() or {})
    if row.get("max_reads") == -1 and row.get("state") == "exhausted":
        return FAIL, ("`max_reads: -1` was accepted and the share is born "
                      "exhausted: nothing validates the field, so a typo "
                      "produces a link that refuses every read and reads on "
                      "the register as one somebody used up")
    return FAIL, (f"`max_reads: -1` was accepted and stored as "
                  f"{row.get('max_reads')!r} in state {row.get('state')!r}")


@case("QA-PLT-157", "A share read at exactly its expiry instant")
def plt_157(ctx: Ctx) -> Result:
    """`moment > expires_at` is expired, so the instant itself is still open
    — the same exclusive boundary the rest of the platform uses. A share
    that closed AT its expiry would refuse a reader who arrived on time."""
    service = _service(ctx)
    if service is None:
        return BLOCKED, "no sharing service is wired"
    urn, digest = _packed(ctx)
    made = _share(ctx, urn, digest, days=30.0)
    reference = _reference(made)
    if not reference:
        return BLOCKED, f"the share could not be created: {made.text[:140]}"
    row = service.require(reference)
    at = row["expires_at"]
    served = service.open_share(reference, seen_from="qa", now=at)
    if not served:
        return FAIL, "a read at the expiry instant returned nothing"
    from core.export.common import ExportError
    try:
        service.open_share(reference, seen_from="qa", now=at + 1.0)
    except ExportError as exc:
        if getattr(exc, "code", "") != "share_expired":
            return FAIL, f"a second past expiry refused '{exc}'"
        return PASS, "open at the instant, expired a second later"
    return FAIL, "a read a second past the expiry was served"


@case("QA-PLT-162", "`days_left` on an expired share")
def plt_162(ctx: Ctx) -> Result:
    """Never negative. A negative number of days left is not a quantity, and
    on a list of shares it sorts as though the link had the longest to run."""
    service = _service(ctx)
    if service is None:
        return BLOCKED, "no sharing service is wired"
    urn, digest = _packed(ctx)
    reference = _reference(_share(ctx, urn, digest, days=1.0))
    if not reference:
        return BLOCKED, "the share could not be created"
    row = service.require(reference)
    later = service.status(reference, now=row["expires_at"] + 10 * DAY)
    if later.get("state") != "expired":
        return FAIL, f"ten days past expiry the state reads '{later.get('state')}'"
    left = later.get("days_left")
    if left is None:
        return FAIL, "an expired share reports no days_left at all"
    if left < 0:
        return FAIL, (f"an expired share reports {left} days left: a negative "
                      f"number sorts on a list as the link with the longest "
                      f"to run")
    return PASS, f"expired, days_left {left}"


@case("QA-PLT-161", "Revoking a share that has already expired")
def plt_161(ctx: Ctx) -> Result:
    """Revocation and expiry are different facts. A share that ran out is
    not one somebody withdrew, and a firm asked *why did you stop serving
    this* has to be able to answer with the right one."""
    service = _service(ctx)
    if service is None:
        return BLOCKED, "no sharing service is wired"
    urn, digest = _packed(ctx)
    reference = _reference(_share(ctx, urn, digest, days=1.0))
    if not reference:
        return BLOCKED, "the share could not be created"
    row = service.require(reference)
    service.shares.set({"expires_at": time.time() - DAY}, id=row["id"])
    got = ctx.api.post(f"{S}/{reference}/revoke?reason=the+matter+closed",
                       auth=ctx.people["risk"])
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — an expired share is not "
                      f"revoked, it has already stopped serving")
    after = service.status(reference)
    if after.get("state") != "revoked":
        return FAIL, (f"the revoke was accepted and the state reads "
                      f"'{after.get('state')}'")
    if not (after.get("revoke_reason") or "").strip():
        return FAIL, "revoked with no reason kept"
    return PASS, ("an expired share can still be revoked, and the record "
                  "keeps both the expiry and the revocation")


@case("QA-PLT-164", "Recovering a share reference after creation")
def plt_164(ctx: Ctx) -> Result:
    """The reference is a secret token, and an operator who loses it has to
    be able to find the share to revoke it. The listing has to let them
    identify it by recipient and purpose without printing the token to
    everybody who can read the estate."""
    urn, digest = _packed(ctx)
    made = _share(ctx, urn, digest, recipient="the PRA",
                  purpose="the 2026 thematic review")
    reference = _reference(made)
    if not reference:
        return BLOCKED, f"the share could not be created: {made.text[:140]}"
    got = ctx.api.get(S, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the share list answered {got.status_code}"
    body = got.json() or {}
    rows = body.get("shares") or []
    mine = [r for r in rows if r.get("purpose") == "the 2026 thematic review"]
    if not mine:
        return FAIL, ("a share cannot be found again by its purpose, so an "
                      "operator who lost the reference cannot revoke it")
    if not mine[0].get("reference"):
        return FAIL, ("the listing names the share and not its reference, so "
                      "it cannot be revoked from what the listing gives")
    return PASS, f"found by purpose, with its reference, among {len(rows)}"


@case("QA-PLT-163", "Redeem a share link end to end")
def plt_163(ctx: Ctx) -> Result:
    """The reader's end of the feature. A share is created, a token is
    handed over, and the recipient exchanges it for the pack — that last
    step is what the whole module is for."""
    urn, digest = _packed(ctx)
    reference = _reference(_share(ctx, urn, digest))
    if not reference:
        return BLOCKED, "the share could not be created"
    service = _service(ctx)
    if service is None:
        return BLOCKED, "no sharing service is wired"
    before = len(service.reads.many())
    tried = []
    for path in (f"/share/{reference}", f"{S}/{reference}",
                 f"{S}/{reference}/open", f"{S}/{reference}/pack",
                 f"/api/v1/shared/{reference}", f"/shared/{reference}",
                 f"/s/{reference}"):
        got = ctx.ui.get(path)
        tried.append(f"{path}:{got.status_code}")
        if got.status_code >= 400:
            continue
        # Served — now the three things that make it a share rather than a
        # download: the bytes are a pack, the read is on the record, and no
        # identity is claimed for whoever opened it.
        if not got.content.startswith(b"PK"):
            return FAIL, (f"{path} answered {got.status_code} and the body is "
                          f"not an archive: {got.content[:40]!r}")
        after = service.reads.many()
        if len(after) <= before:
            return FAIL, (f"the pack was served at {path} and no read was "
                          f"recorded; a link whose use leaves no trace is one "
                          f"nobody can answer for")
        newest = max(after, key=lambda r: r.get("at") or 0)
        if newest.get("outcome") != "served":
            return FAIL, f"the read was recorded as {newest.get('outcome')!r}"
        # Unauthenticated ON PURPOSE: a share exists for somebody who will
        # never be given a login. What must NOT happen is the platform
        # claiming to know who they were.
        from fastapi.testclient import TestClient
        with TestClient(ctx.ui.app, raise_server_exceptions=False) as stranger:
            anonymous = stranger.get(path)
        if anonymous.status_code >= 400:
            return FAIL, (f"the link needs a session ({anonymous.status_code}); "
                          f"a share is for somebody outside the firm and "
                          f"issuing them a credential is what it exists to "
                          f"avoid")
        return PASS, (f"the pack is served at {path} to a caller with no "
                      f"session, the read is recorded as "
                      f"'{newest.get('outcome')}', and no identity is claimed")
    if service is None:
        return BLOCKED, "no sharing service is wired"
    served = service.open_share(reference, seen_from="qa")
    if not served.get("content_digest"):
        return FAIL, f"the service does not serve the pack either: {served}"
    if served.get("identity_established"):
        return FAIL, ("the read claims an identity was established; there is "
                      "no credential behind a share link by design")
    return FAIL, (f"the service serves the pack and NO ROUTE reaches it: "
                  f"`open_share` is called from nowhere but a unit test, so a "
                  f"share can be created, listed and revoked and never "
                  f"opened. Tried {', '.join(tried)}")
