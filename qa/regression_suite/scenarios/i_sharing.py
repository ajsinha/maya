"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — export shares: the moment a pack leaves the building.

The design decision worth testing is an ABSENCE. `content_digest` is required
and there is no field for a path, because "a share pointing at a location
would serve whatever is at that location later, which is how a document a firm
handed over becomes one nobody can reproduce".
"""
from __future__ import annotations

from core.export.sharing import (EXHAUSTED, EXPIRED, MAX_DAYS, OPEN, REVOKED)
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

S = "/api/v1/export-shares"
E = "/api/v1/export-packs"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _packed(ctx: Ctx) -> tuple:
    """A model and the content digest of its pack."""
    name = ctx.unique("sh")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    got = ctx.api.get(f"{E}/{name}/manifest", auth=ctx.people["auditor"])
    if got.status_code >= 400:
        raise AssertionError(f"could not read a manifest: {got.text[:170]}")
    return f"maya://model/{name}", (got.json() or {}).get("content_digest", "")


def _share(ctx: Ctx, urn: str, digest: str, **over):
    body = {"urn": urn, "recipient": "the PRA", "purpose": "a QA review",
            "content_digest": digest, "days": 30.0}
    body.update(over)
    return ctx.api.post(S, json=body, auth=ctx.people["risk"])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-PLT-5400", "A share names a digest and never a path")
def plt_5400(ctx: Ctx) -> Result:
    """The absence is the control. A path would serve whatever is at that
    location later, and a document a firm handed over becomes one nobody can
    reproduce."""
    from routes.export_routes import ShareIn
    fields = set(ShareIn.model_fields)
    for path_like in ("path", "location", "uri", "url", "file_path"):
        if path_like in fields:
            return FAIL, (f"a share may name a '{path_like}', so it serves "
                          f"whatever is there when it is read")
    if "content_digest" not in fields:
        return FAIL, "a share does not name a content digest at all"
    return PASS, f"digest required, no location field among {sorted(fields)}"


@case("QA-PLT-5401", "A share with no content digest")
def plt_5401(ctx: Ctx) -> Result:
    urn, _ = _packed(ctx)
    got = _share(ctx, urn, "   ")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("a share was opened with no digest, so what it serves "
                      "is whatever the pack happens to be later")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-5402", "A share with no recipient or no purpose")
def plt_5402(ctx: Ctx) -> Result:
    """Who took a copy and why is what an auditor asks about later. A share
    with neither is a link."""
    urn, digest = _packed(ctx)
    for field in ("recipient", "purpose"):
        got = _share(ctx, urn, digest, **{field: "   "})
        if got.status_code >= 500:
            return FAIL, f"{field}: {got.status_code}"
        if got.status_code < 400:
            return FAIL, f"a share was opened with no {field}"
    return PASS, "both recipient and purpose required"


@case("QA-PLT-5403", "A share window outside the permitted range")
def plt_5403(ctx: Ctx) -> Result:
    """An open-ended share is a copy of a firm's model record with no end
    date, and it is the one somebody forgets."""
    urn, digest = _packed(ctx)
    accepted = []
    for days in (0, -1, MAX_DAYS + 1, 3650):
        got = _share(ctx, urn, digest, days=days)
        if got.status_code >= 500:
            return FAIL, f"{days}: {got.status_code}"
        if got.status_code < 400:
            accepted.append(days)
    if accepted:
        return FAIL, f"these windows were accepted: {accepted}"
    inside = _share(ctx, urn, digest, days=MAX_DAYS)
    if inside.status_code >= 400 and _reached(inside):
        return FAIL, (f"exactly {MAX_DAYS} days was refused "
                      f"'{code_of(inside)}'; the limit excludes itself")
    return PASS, f"0, -1, {MAX_DAYS + 1} and 3650 refused; {MAX_DAYS} accepted"


@case("QA-PLT-5404", "A revoked share stops serving")
def plt_5404(ctx: Ctx) -> Result:
    """Revocation that does not bite is a note in a table, and the pack is
    already on somebody's laptop — what revocation buys is that no FURTHER
    copy is taken."""
    urn, digest = _packed(ctx)
    made = _share(ctx, urn, digest)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    reference = (made.json() or {}).get("reference")
    gone = ctx.api.post(f"{S}/{reference}/revoke",
                        json={"reason": "the review closed"},
                        auth=ctx.people["risk"])
    if gone.status_code >= 400:
        return BLOCKED, f"could not revoke: {gone.text[:140]}"
    sharing = ctx.ui.app.state.ctx.get("export_sharing")
    if sharing is None:
        return PASS, f"revoked ({gone.status_code}); no register to read back"
    # `open_share`, not `fetch` — the verb names what a recipient does.
    from core.export.sharing import ExportError
    try:
        sharing.open_share(reference)
    except ExportError as exc:
        if exc.code != "share_revoked":
            return FAIL, f"refused '{exc.code}', not share_revoked"
        return PASS, "a revoked share refuses to serve"
    return FAIL, "a revoked share still serves the pack"


@case("QA-PLT-5405", "Revoke a share twice")
def plt_5405(ctx: Ctx) -> Result:
    urn, digest = _packed(ctx)
    made = _share(ctx, urn, digest)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    reference = (made.json() or {}).get("reference")
    if ctx.api.post(f"{S}/{reference}/revoke", json={"reason": "done"},
                    auth=ctx.people["risk"]).status_code >= 400:
        return BLOCKED, "the first revoke failed"
    again = ctx.api.post(f"{S}/{reference}/revoke", json={"reason": "again"},
                         auth=ctx.people["risk"])
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code < 400:
        return FAIL, "a revoked share was revoked again"
    return PASS, f"refused '{code_of(again)}'"


@case("QA-PLT-5406", "Revoke with no reason")
def plt_5406(ctx: Ctx) -> Result:
    """Why a firm stopped serving a copy to a supervisor is part of the
    record of having served it."""
    urn, digest = _packed(ctx)
    made = _share(ctx, urn, digest)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    got = ctx.api.post(f"{S}/{(made.json() or {}).get('reference')}/revoke",
                       json={"reason": "   "}, auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    # Establish that the reason really is absent rather than defaulted.
    sharing = ctx.ui.app.state.ctx.get("export_sharing")
    stored = ""
    if sharing is not None:
        row = sharing.require((made.json() or {}).get("reference"))
        stored = (row.get("revoke_reason") or "").strip()
    if stored:
        return PASS, f"a blank reason was replaced by {stored!r}"
    return FAIL, (
        "a share was revoked with no reason recorded — `revoke` strips the "
        "reason and never checks it, so the record says a firm stopped "
        "serving a supervisor a copy and not why")


@case("QA-PLT-5407", "A read limit is honoured")
def plt_5407(ctx: Ctx) -> Result:
    """`max_reads` bounds how many copies are taken. A limit that did not
    bite would be a number on a screen."""
    urn, digest = _packed(ctx)
    made = _share(ctx, urn, digest, max_reads=1)
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    reference = (made.json() or {}).get("reference")
    sharing = ctx.ui.app.state.ctx.get("export_sharing")
    if sharing is None:
        return BLOCKED, "no sharing register reachable from this run"
    from core.export.sharing import ExportError
    try:
        sharing.open_share(reference)
    except ExportError as exc:
        return BLOCKED, f"the first read failed: {exc.code}"
    try:
        sharing.open_share(reference)
    except ExportError as exc:
        if exc.code != "share_exhausted":
            return FAIL, f"refused '{exc.code}', not share_exhausted"
        return PASS, "a second read of a one-read share is refused"
    return FAIL, ("a share limited to one read served a second copy, so the "
                  "limit is a number on a screen")


@case("QA-PLT-5408", "The four states are four")
def plt_5408(ctx: Ctx) -> Result:
    """Open, expired, revoked and exhausted are different facts about why a
    link stopped working, and a recipient told only "unavailable" cannot tell
    a lapsed window from a withdrawn one."""
    states = {OPEN, EXPIRED, REVOKED, EXHAUSTED}
    if len(states) != 4:
        return FAIL, f"the states collide: {states}"
    from core.export import sharing
    import inspect
    source = inspect.getsource(sharing)
    for code in ("share_expired", "share_revoked", "share_exhausted"):
        if code not in source:
            return FAIL, f"'{code}' is not a refusal the register makes"
    return PASS, f"{sorted(states)} with a distinct refusal for each"


@case("QA-PLT-5409", "The share posture is readable")
def plt_5409(ctx: Ctx) -> Result:
    """Who holds a copy of what, right now, is the question this whole
    feature exists to answer."""
    got = ctx.api.get(f"{S}/posture", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if not (body.get("detail") or "").strip():
        return FAIL, ("the share posture says nothing, so an estate with no "
                      "shares and a broken report look the same")
    return PASS, str(body.get("detail"))[:100]
