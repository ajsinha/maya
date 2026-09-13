"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the export pack: a model's whole record, handed to somebody else.

Three decisions carry it. The content digest EXCLUDES the manifest, so "has
anything changed since the last pack?" is a one-line check rather than always
yes. The act of cutting a pack is recorded against the pack and not the model,
or every pack would differ from the one before it for no reason except that
somebody took one. And personal data is not re-materialised, because a zip on
somebody's laptop is where an erasure request cannot reach.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

E = "/api/v1/export-packs"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("ex")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    return name


def _manifest(ctx: Ctx, name: str):
    return ctx.api.get(f"{E}/{name}/manifest", auth=ctx.people["auditor"])


@case("QA-PLT-5300", "Two packs of unchanged state share a content digest")
def plt_5300(ctx: Ctx) -> Result:
    """The whole reason the manifest is excluded. If the digest moved with
    the clock, "has anything changed since the last pack?" would always be
    yes and nobody could use it."""
    name = _model(ctx)
    first, second = _manifest(ctx, name), _manifest(ctx, name)
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    a, b = first.json() or {}, second.json() or {}
    if not a.get("content_digest"):
        return FAIL, f"the manifest carries no content digest: {sorted(a)}"
    if a["content_digest"] != b["content_digest"]:
        return FAIL, ("two packs of unchanged state have different content "
                      "digests, so nothing can tell a changed record from a "
                      "re-cut one")
    if a.get("built_at") == b.get("built_at"):
        return BLOCKED, "the two packs were cut at the same instant"
    return PASS, (f"digest stable at {a['content_digest'][:20]} across two "
                  f"cuts at different times")


@case("QA-PLT-5301", "The digest moves when the record does")
def plt_5301(ctx: Ctx) -> Result:
    """The other half. A digest that never moves is not a digest."""
    name = _model(ctx)
    before = _manifest(ctx, name)
    if before.status_code >= 400:
        return BLOCKED, before.text[:170]
    added = ctx.api.post(f"{M}/{name}/versions", json={"semver": "2.0.0"},
                         auth=ctx.people["developer"])
    if added.status_code >= 400:
        return BLOCKED, f"could not change the record: {added.text[:130]}"
    after = _manifest(ctx, name)
    if after.status_code >= 400:
        return BLOCKED, after.text[:170]
    if (before.json() or {}).get("content_digest") == \
            (after.json() or {}).get("content_digest"):
        return FAIL, ("a new version did not move the pack's content digest, "
                      "so the digest does not describe the record")
    return PASS, "the digest moves with the record"


@case("QA-PLT-5302", "The manifest says it cannot digest itself")
def plt_5302(ctx: Ctx) -> Result:
    """"A file cannot carry its own digest." Leaving that implicit would let
    a reader assume the manifest is covered."""
    got = _manifest(ctx, _model(ctx))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if not body.get("manifest_is_itself_undigested"):
        return FAIL, ("the manifest does not state that it is outside its own "
                      "digest, so a reader may take the whole pack as covered")
    members = body.get("files") or []
    named = {m.get("name") if isinstance(m, dict) else m for m in members}
    if any(str(n).startswith("manifest") for n in named):
        return FAIL, "the manifest lists itself among the digested members"
    return PASS, f"{len(members)} digested member(s), manifest excluded"


@case("QA-PLT-5303", "Every member carries its own digest")
def plt_5303(ctx: Ctx) -> Result:
    """A pack digest with undigested members means a changed file inside an
    unchanged pack."""
    got = _manifest(ctx, _model(ctx))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    # `files`, each with a name, a byte count and a digest. `members` is not
    # a key the manifest has, and reading one finds an empty list — which a
    # case then reports as a pack listing nothing.
    members = (got.json() or {}).get("files") or []
    if not members:
        return FAIL, "the manifest lists no files at all"
    undigested = [m.get("name") for m in members
                  if isinstance(m, dict) and not m.get("digest")]
    if undigested:
        return FAIL, (f"{len(undigested)} member(s) carry no digest: "
                      f"{undigested[:4]}")
    return PASS, f"all {len(members)} members digested"


@case("QA-PLT-5304", "Cutting a pack does not change the next pack")
def plt_5304(ctx: Ctx) -> Result:
    """"Recorded against the model it would land inside the next pack's own
    evidence segment, and every pack would then differ from the one before it
    for no reason except that somebody had taken one." """
    name = _model(ctx)
    first = _manifest(ctx, name)
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    # Cutting a pack is a POST — it is a governance act, not a read.
    cut = ctx.api.post(f"{E}/{name}", json={}, auth=ctx.people["auditor"])
    if cut.status_code >= 400:
        return BLOCKED, f"could not cut a pack: {cut.text[:130]}"
    after = _manifest(ctx, name)
    if after.status_code >= 400:
        return BLOCKED, after.text[:170]
    if (first.json() or {}).get("content_digest") != \
            (after.json() or {}).get("content_digest"):
        return FAIL, ("taking a pack changed the next pack's digest, so every "
                      "export makes the record look different")
    return PASS, "taking a pack leaves the next one identical"


@case("QA-PLT-5305", "Personal data is not re-materialised into the pack")
def plt_5305(ctx: Ctx) -> Result:
    """"A pack that helpfully resolved it would put personal data into a zip
    on somebody's laptop, where an erasure request cannot reach it — and the
    export would have quietly defeated the control the whole chain was built
    to respect."
    """
    import inspect

    from core.export import pack
    doc = " ".join((inspect.getdoc(pack) or "").split())
    if "not re-materialised" not in doc and "re-materialised" not in doc:
        return FAIL, ("the pack does not record that flagged evidence stays "
                      "unresolved")
    source = inspect.getsource(pack)
    if "contains_personal_data" not in source and "personal" not in source:
        return FAIL, "nothing in the pack consults the personal-data flag"
    # The schema-level guarantee this rests on.
    from db.schema.immutable import EMPTY_WHEN_FLAGGED
    if "evidence_node" not in EMPTY_WHEN_FLAGGED:
        return FAIL, ("no trigger keeps a flagged evidence node empty, so the "
                      "pack has something to re-materialise")
    return PASS, ("flagged nodes hold no payload at the schema level, and the "
                  "pack carries the pointer")


@case("QA-PLT-5306", "A pack for a model that does not exist")
def plt_5306(ctx: Ctx) -> Result:
    got = ctx.api.get(f"{E}/qa-no-such-model", auth=ctx.people["auditor"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a pack was cut for a model nobody registered"
    return PASS, f"refused '{code_of(got) or got.status_code}'"


@case("QA-PLT-5307", "The pack states the chain's condition")
def plt_5307(ctx: Ctx) -> Result:
    """A complete record handed to somebody outside has to say whether the
    evidence it rests on verifies. A pack cut over a broken chain that said
    nothing would be the most misleading document the platform can produce.
    """
    got = _manifest(ctx, _model(ctx))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    chain = (got.json() or {}).get("chain") or {}
    if "verified" not in chain:
        return FAIL, ("the manifest does not say whether the evidence chain "
                      "verified")
    for field in ("head_seq", "head_hash"):
        if field not in chain:
            return FAIL, f"the manifest does not pin the chain's {field}"
    return PASS, f"chain pinned at seq {chain.get('head_seq')}, "\
                 f"verified={chain.get('verified')}"


@case("QA-PLT-5308", "The pack version is stated")
def plt_5308(ctx: Ctx) -> Result:
    """A pack read three years later by a tool that has moved on needs to
    know what shape it is."""
    got = _manifest(ctx, _model(ctx))
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    if not (got.json() or {}).get("pack_version"):
        return FAIL, "the manifest states no pack version"
    return PASS, f"pack version {(got.json() or {})['pack_version']}"
