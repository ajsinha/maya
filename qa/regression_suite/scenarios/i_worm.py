"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the write-once store, and the anchors that rest on it.

"The refusal is the guarantee." Every claim the platform makes about tamper
detection rests on `WormStore.put` declining a second write, rather than on
callers remembering not to ask for one. So the cases go at that method
directly, and at the anchor that depends on it.

These damage or read raw filesystem state, so several run isolated.
"""
from __future__ import annotations

import os
import pathlib

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)


def _fresh(ctx: Ctx, tmp: str):
    """A store of its own, so a case that damages one damages nothing else.

    The class is `FilesystemWORM` — the store is one implementation of a
    write-once contract rather than the contract itself, and the name says
    which guarantees are the filesystem's.
    """
    from core.evidence.worm import FilesystemWORM
    root = pathlib.Path("data") / "qa-worm" / tmp
    return FilesystemWORM(root), root


def _anchors(ctx: Ctx):
    """The anchor register hangs off the evidence engine, not the context."""
    return getattr(ctx.ui.app.state.ctx.get("evidence"), "anchors", None)


@case("QA-PLT-029", "An existing anchor file rewritten")
def plt_029(ctx: Ctx) -> Result:
    """The one refusal everything else rests on."""
    store, _ = _fresh(ctx, ctx.unique("w"))
    from core.evidence.worm import WormError
    store.put("anchor-1.json", b'{"seq": 1}')
    try:
        store.put("anchor-1.json", b'{"seq": 1, "tampered": true}')
    except WormError as exc:
        if exc.code != "worm_overwrite_refused":
            return FAIL, f"refused '{exc.code}', not worm_overwrite_refused"
        if store.get("anchor-1.json") != b'{"seq": 1}':
            return FAIL, "the refusal still changed the held object"
        return PASS, "refused, and the held copy is unchanged"
    return FAIL, ("a write-once object was overwritten, so every claim above "
                  "it about tamper detection rests on nothing")


@case("QA-PLT-2100", "Writing the same object twice is not an overwrite")
def plt_2100(ctx: Ctx) -> Result:
    """Idempotent on identical content, because a retried anchor is not
    tampering and refusing it would make the store unusable under retry."""
    store, _ = _fresh(ctx, ctx.unique("w"))
    store.put("anchor-1.json", b'{"seq": 1}')
    try:
        store.put("anchor-1.json", b'{"seq": 1}')
    except Exception as exc:
        return FAIL, f"an identical re-write was refused: {exc}"
    return PASS, "identical content, accepted twice"


@case("QA-PLT-030", "An anchor filename that is not a flat object name")
def plt_030(ctx: Ctx) -> Result:
    """A name with a separator would let a caller write outside the root, and
    this store's whole value is that its contents are somewhere else."""
    store, root = _fresh(ctx, ctx.unique("w"))
    from core.evidence.worm import WormError
    escaped = []
    for name in ("../escaped.json", "sub/dir.json", "..", ".", "",
                 "a\\b.json"):
        try:
            store.put(name, b"x")
        except WormError as exc:
            if exc.code != "worm_bad_name":
                escaped.append(f"{name!r}->{exc.code}")
        except Exception as exc:
            escaped.append(f"{name!r}->{type(exc).__name__}")
        else:
            escaped.append(f"{name!r}->written")
    if escaped:
        return FAIL, f"names not refused as worm_bad_name: {escaped}"
    outside = (root.parent / "escaped.json")
    if outside.exists():
        return FAIL, "a write landed outside the store root"
    return PASS, "every separator and dot name refused worm_bad_name"


@case("QA-PLT-028", "The store made unreadable")
def plt_028(ctx: Ctx) -> Result:
    """An object that cannot be read must not be treated as absent. Reporting
    it as missing turns tampering into a gap, which is exactly the reading an
    adversary wants."""
    store, root = _fresh(ctx, ctx.unique("w"))
    from core.evidence.worm import WormError
    store.put("anchor-1.json", b'{"seq": 1}')
    path = root / "anchor-1.json"
    try:
        os.chmod(path, 0o000)
    except OSError as exc:
        return BLOCKED, f"cannot make the object unreadable here: {exc}"
    try:
        store.get("anchor-1.json")
    except WormError as exc:
        os.chmod(path, 0o644)
        if exc.code != "worm_unreadable":
            return FAIL, f"refused '{exc.code}', not worm_unreadable"
        return PASS, "refused 'worm_unreadable' rather than reported absent"
    except Exception as exc:
        os.chmod(path, 0o644)
        return FAIL, f"raised {type(exc).__name__} rather than a WormError"
    os.chmod(path, 0o644)
    if os.geteuid() == 0:
        return BLOCKED, "running as root; permissions do not bite"
    return FAIL, ("an unreadable object was read anyway, so nothing "
                  "distinguishes damage from absence")


@case("QA-PLT-2101", "A held object is read-only after writing")
def plt_2101(ctx: Ctx) -> Result:
    """Stops an accident, not an adversary — and the platform says so rather
    than claiming immutability it cannot enforce."""
    store, root = _fresh(ctx, ctx.unique("w"))
    store.put("anchor-1.json", b'{"seq": 1}')
    mode = (root / "anchor-1.json").stat().st_mode & 0o222
    if mode:
        return FAIL, (f"the written object is still writable (mode bits "
                      f"{oct(mode)}), so an ordinary mistake overwrites it")
    return PASS, "written objects are read-only on disk"


@case("QA-PLT-2102", "The store lists nothing when it holds nothing")
def plt_2102(ctx: Ctx) -> Result:
    """An empty store and a missing store must answer the same way, or a
    fresh instance looks like a damaged one."""
    store, _ = _fresh(ctx, ctx.unique("w"))
    if store.names() != []:
        return FAIL, f"a store that was never written lists {store.names()}"
    store.put("anchor-1.json", b"{}")
    if store.names() != ["anchor-1.json"]:
        return FAIL, f"after one write the store lists {store.names()}"
    return PASS, "empty lists nothing; one write lists one"


@case("QA-PLT-2103", "A staging file is not listed as an object")
def plt_2103(ctx: Ctx) -> Result:
    """`put` writes to a staging path and renames. A crash between the two
    leaves a partial file, and listing it as an anchor would make a truncated
    write look like evidence."""
    store, root = _fresh(ctx, ctx.unique("w"))
    store.put("anchor-1.json", b"{}")
    from core.evidence.worm import _STAGING
    (root / f"anchor-2{_STAGING}").write_bytes(b'{"partial')
    listed = store.names()
    if any(n.endswith(_STAGING) for n in listed):
        return FAIL, f"a partial write is listed as an object: {listed}"
    return PASS, "staging files are not objects"


@case("QA-PLT-021", "Anchor a chain that does not verify")
def plt_021(ctx: Ctx) -> Result:
    """An anchor over a broken chain would freeze the damage into the
    write-once store as though it were the truth."""
    evidence = ctx.ui.app.state.ctx.get("evidence")
    if evidence is None:
        return BLOCKED, "no evidence engine reachable from this run"
    import inspect
    # The guard is on the ENGINE's `anchor_head`, not on the register's
    # `anchor`. The register takes a sequence and a hash and does not know
    # where they came from; the engine is what verifies first and refuses.
    # Reading the register alone would report the control as absent.
    source = inspect.getsource(evidence.anchor_head)
    if "chain_broken" not in source:
        return FAIL, ("nothing stops a broken chain being anchored, so damage "
                      "can be written into the write-once store as truth")
    if source.index("verify_chain") > source.index("chain_broken"):
        return FAIL, "the chain is anchored before it is verified"
    return PASS, "verified first; a broken chain refuses 'chain_broken'"


@case("QA-PLT-023", "Anchor the same head twice with no act in between")
def plt_023(ctx: Ctx) -> Result:
    """Two anchors over one head are two claims about one moment, and the
    second proves nothing the first did not."""
    anchors = _anchors(ctx)
    if anchors is None:
        return BLOCKED, "no anchor register reachable from this run"
    import inspect
    source = inspect.getsource(anchors.anchor)
    if "anchor_disagreement" not in source:
        return FAIL, ("re-anchoring a sequence with a different hash is not "
                      "refused, so a rewritten chain can be re-anchored over "
                      "its own evidence")
    if "nothing_to_anchor" not in source:
        return FAIL, ("anchoring an unchanged head is not refused, so the "
                      "store fills with duplicate claims about one moment")
    return PASS, "an unchanged head refuses 'nothing_to_anchor'"


@case("QA-PLT-031", "An anchor written by the process it certifies")
def plt_031(ctx: Ctx) -> Result:
    """The limit is real and has to be stated: MAYA anchoring its own chain
    is self-certification, and a report that did not say so would be claiming
    independent corroboration it does not have."""
    got = ctx.api.get("/api/v1/evidence/chain", auth=ctx.people["auditor"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if "self_certified" not in body:
        return FAIL, ("the chain report does not say whether it was verified "
                      "by the process it certifies")
    if body.get("self_certified") and not (body.get("verification_note")
                                           or "").strip():
        return FAIL, "self-certified with no note saying what that means"
    return PASS, (f"self_certified={body.get('self_certified')}, "
                  f"verified_by={body.get('verified_by')}")


@case("QA-PLT-032", "Time-stamping with no authority wired")
def plt_032(ctx: Ctx) -> Result:
    """No authority is a stated absence, not a silent pass. A posture that
    reported nothing would read as a posture with nothing wrong."""
    got = ctx.api.get("/api/v1/evidence/timestamps/posture",
                      auth=ctx.people["auditor"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    if not (body.get("detail") or "").strip():
        return FAIL, ("the time-stamping posture says nothing, so an "
                      "unwired authority and a healthy one look the same")
    return PASS, str(body.get("detail"))[:100]


@case("QA-PLT-037", "The period before the first token is explicitly uncovered")
def plt_037(ctx: Ctx) -> Result:
    """Everything before the first time-stamp is unbounded in time. Leaving
    that implicit would let a reader assume the whole chain is stamped."""
    got = ctx.api.get("/api/v1/evidence/timestamps",
                      auth=ctx.people["auditor"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    text = got.text.lower()
    if "uncovered" not in text and "before" not in text and "not " not in text:
        return FAIL, ("the time-stamp report does not say what it does not "
                      "cover")
    return PASS, "the uncovered period is named"
