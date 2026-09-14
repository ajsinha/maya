"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the anchors, and the only check a rewritten database does not pass.

`verify_chain` compares the chain against itself, which is exactly what an
attacker with database access arranges. The anchors compare it against heads
written to a second medium, so they are the one verification here that somebody
holding the database alone cannot satisfy.

Which makes their limits worth stating precisely rather than discovering. An
anchor at sequence N says what the chain hash was at N. It says nothing about
what came after, nothing about whether a node below N was edited without
re-linking, and nothing at all if the anchor itself is gone — because an anchor
store with nothing in it and an anchor store somebody emptied read the same.

The store underneath is write-once, and the refusal to replace an object is the
whole guarantee: everything above it rests on `put` declining a second write
rather than on callers remembering not to ask for one.
"""
from __future__ import annotations

import json
import pathlib
import time

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _evidence(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("evidence")


def _acts(ctx: Ctx, how_many: int = 3) -> None:
    for _ in range(how_many):
        name = ctx.unique("an")
        ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                              "owner": "owner", **SHAPE},
                     auth=ctx.people["owner"])


def _past_the_trigger(db, statement: str, params: dict) -> None:
    """The threat is somebody holding production credentials, who can drop a
    trigger. The chain is what answers past that point."""
    from db.schema.immutable import sqlite_statements
    creates = [c for c in sqlite_statements()
               if c.startswith("CREATE") and "append_only_evidence_node" in c]
    for name in ("append_only_evidence_node_update",
                 "append_only_evidence_node_delete"):
        db.execute(f"DROP TRIGGER IF EXISTS {name}")
    try:
        db.execute(statement, params)
    finally:
        for create in creates:
            db.execute(create)


def _anchored(ctx: Ctx):
    """An estate with some acts and one anchor over them."""
    evidence = _evidence(ctx)
    _acts(ctx)
    return evidence.anchor_head(actor="qa")


@case("QA-PLT-107", "Tampering below the newest anchor", isolated=True)
def plt_107(ctx: Ctx) -> Result:
    """An anchor records the chain hash the chain REPORTS at one sequence,
    read from the stored column. Editing a node below it without re-linking
    leaves that column untouched, so the anchors go on agreeing — the full
    walk is what catches this, and the anchors are not a substitute for it."""
    evidence = _evidence(ctx)
    db = ctx.ui.app.state.ctx.get("db")
    if evidence is None or db is None:
        return BLOCKED, "no evidence chain is wired"
    _acts(ctx, 6)
    written = evidence.anchor_head(actor="qa")
    if not written.get("written") and not written.get("seq"):
        return BLOCKED, f"nothing was anchored: {written}"
    low = db.query("SELECT id, seq FROM evidence_node ORDER BY seq LIMIT 1")
    if not low:
        return BLOCKED, "the chain is empty"
    _past_the_trigger(
        db, "UPDATE evidence_node SET payload = '{\"rewritten\": true}' "
            "WHERE id = :i", {"i": low[0]["id"]})
    walk = evidence.verify_chain()
    anchors = evidence.verify_against_anchors()
    if not walk["valid"] and not anchors.get("agrees"):
        return PASS, (f"both catch it: the walk breaks at "
                      f"{walk.get('broken_at')} and the anchors disagree")
    if walk["valid"]:
        return BLOCKED, "the full walk does not see the edit either"
    if anchors.get("agrees"):
        return PASS, (
            f"the node at seq {low[0]['seq']} was rewritten. The full walk "
            f"catches it at {walk.get('broken_at')} because it RECOMPUTES each "
            f"content hash; the anchors report agrees=1 over "
            f"{anchors.get('checked')} anchor(s), because an anchor names one "
            f"sequence's stored chain_hash and that column was not touched. "
            f"Both answers are correct and they answer different questions — "
            f"the anchors bound what the chain SAID at a moment, not what it "
            f"contains. Only the scheduled full walk closes this, so the "
            f"anchors' value depends on that job running")
    return FAIL, f"unreachable: walk={walk['valid']} anchors={anchors}"


@case("QA-PLT-025", "Nodes deleted above the newest anchor", isolated=True)
def plt_025(ctx: Ctx) -> Result:
    """An anchor bounds the chain from BELOW. Everything appended since the
    last anchor is in a window nothing outside the database has seen, and
    truncating the chain back to the anchor leaves a chain that walks clean
    and agrees with every anchor written."""
    evidence = _evidence(ctx)
    db = ctx.ui.app.state.ctx.get("db")
    if evidence is None or db is None:
        return BLOCKED, "no evidence chain is wired"
    _acts(ctx, 4)
    written = evidence.anchor_head(actor="qa")
    at = written.get("seq")
    if not at:
        return BLOCKED, f"nothing was anchored: {written}"
    _acts(ctx, 4)
    after = evidence.head()[0]
    if after <= at:
        return BLOCKED, "no nodes were appended above the anchor"
    _past_the_trigger(db, "DELETE FROM evidence_node WHERE seq > :s", {"s": at})
    walk = evidence.verify_chain()
    anchors = evidence.verify_against_anchors()
    if not walk["valid"]:
        return PASS, f"the full walk catches it: {walk.get('reason')}"
    if not anchors.get("agrees"):
        return PASS, f"the anchors catch it: {anchors.get('detail')}"
    return FAIL, (
        f"{after - at} node(s) appended above the newest anchor (seq {at}) "
        f"were deleted, and nothing notices: the full walk is valid over "
        f"{walk.get('length')} node(s) and the anchors agree over "
        f"{anchors.get('checked')} of them. An anchor bounds the chain from "
        f"below — it says what the head was at seq {at} — and there is no "
        f"upper bound anywhere: nothing records how LONG the chain was "
        f"expected to be, so governance acts recorded between two anchor runs "
        f"sit in a window that can be erased without contradiction. The "
        f"anchor record carries a `length` field and no verification reads it")


@case("QA-PLT-026", "The anchor files deleted from the WORM root", isolated=True)
def plt_026(ctx: Ctx) -> Result:
    """An anchor store somebody emptied and one nobody has written to must
    not read the same. Clearing anchors is the single act that defeats the
    whole arrangement, so it is the one that must not be silent."""
    evidence = _evidence(ctx)
    if evidence is None or evidence.anchors is None:
        return BLOCKED, "no anchor store is wired"
    _anchored(ctx)
    before = evidence.verify_against_anchors()
    if not before.get("anchored"):
        return BLOCKED, f"nothing was anchored: {before}"
    root = pathlib.Path(evidence.anchors.root)
    removed = 0
    for path in root.glob("*.anchor"):
        path.chmod(0o600)
        path.unlink()
        removed += 1
    after = evidence.verify_against_anchors()
    if not after.get("agrees"):
        return PASS, f"the deletion is reported: {after.get('detail')}"
    if after.get("anchored"):
        return BLOCKED, f"{after['anchored']} anchor(s) survived the deletion"
    return FAIL, (
        f"{removed} anchor(s) were deleted from {root} and "
        f"`verify_against_anchors` answers anchored=0, agrees=1: "
        f"{after.get('detail')!r}. That is word for word the answer a fresh "
        f"instance gives. Nothing records that anchors ONCE existed — the "
        f"store is the only register of itself — so an estate whose anchors "
        f"were cleared is indistinguishable from one that has never run the "
        f"anchor job, and the readiness probe renders both as self-certified")


@case("QA-PLT-027", "The whole WORM directory removed while the instance runs",
      isolated=True)
def plt_027(ctx: Ctx) -> Result:
    """The next anchor meets a root that is not there. A store whose whole
    point is being somewhere the database cannot reach has to notice its own
    disappearance rather than repair it."""
    evidence = _evidence(ctx)
    if evidence is None or evidence.anchors is None:
        return BLOCKED, "no anchor store is wired"
    _anchored(ctx)
    root = pathlib.Path(evidence.anchors.root)
    if not root.exists():
        return BLOCKED, "the anchor root does not exist to begin with"
    import shutil
    for path in root.glob("*"):
        path.chmod(0o600)
    shutil.rmtree(root)
    _acts(ctx, 2)
    try:
        out = evidence.anchor_head(actor="qa")
    except Exception as exc:
        code = getattr(exc, "code", type(exc).__name__)
        return PASS, f"refused '{code}': {str(exc)[:120]}"
    if not root.exists():
        return FAIL, f"the anchor reported {out} and wrote nothing"
    return FAIL, (
        f"the entire anchor root was removed and the next anchor recreated it "
        f"({root}) and wrote seq {out.get('seq')} into it, reporting "
        f"written={out.get('written')}. `FilesystemWORM.put` opens with "
        f"`root.mkdir(parents=True, exist_ok=True)`, so a store that has "
        f"vanished is repaired rather than reported. Every earlier anchor is "
        f"gone, the new one agrees with the chain, and `verify_against_anchors` "
        f"now reports a chain corroborated by a store that was rebuilt after "
        f"the fact — the disappearance of the second medium is exactly the "
        f"observation this medium exists to make")


@case("QA-PLT-106", "The scheduled anchor meets a chain that disagrees",
      isolated=True)
def plt_106(ctx: Ctx) -> Result:
    """Nothing written, the existing anchors preserved. Anchoring over a
    disagreement would write the rewritten state down as the truth and every
    later comparison would then agree with it."""
    evidence = _evidence(ctx)
    db = ctx.ui.app.state.ctx.get("db")
    if evidence is None or db is None or evidence.anchors is None:
        return BLOCKED, "no evidence chain or anchor store is wired"
    _acts(ctx, 4)
    first = evidence.anchor_head(actor="qa")
    at = first.get("seq")
    if not at:
        return BLOCKED, f"nothing was anchored: {first}"
    node = db.query("SELECT id FROM evidence_node WHERE seq = :s", {"s": at})
    _past_the_trigger(
        db, "UPDATE evidence_node SET chain_hash = :h WHERE id = :i",
        {"h": "sha256:" + "9" * 64, "i": node[0]["id"]})
    held = len(list(pathlib.Path(evidence.anchors.root).glob("*.anchor")))
    try:
        out = evidence.anchor_head(actor="qa")
    except Exception as exc:
        code = getattr(exc, "code", type(exc).__name__)
        still = len(list(pathlib.Path(evidence.anchors.root).glob("*.anchor")))
        if still != held:
            return FAIL, (f"refused '{code}' and the anchor count moved "
                          f"{held} → {still}")
        if code not in ("chain_broken", "anchor_disagreement"):
            return FAIL, f"refused '{code}' rather than naming the disagreement"
        return PASS, (f"refused '{code}', {still} anchor(s) preserved: "
                      f"{str(exc)[:110]}")
    still = len(list(pathlib.Path(evidence.anchors.root).glob("*.anchor")))
    if out.get("written"):
        return FAIL, (f"a new anchor was written over a chain that disagrees "
                      f"with the one already held: {out}")
    return FAIL, (f"nothing raised and nothing was written ({out}); "
                  f"{still} anchor(s) held. A disagreement answered as a "
                  f"no-op is a disagreement nobody is told about")


@case("QA-PLT-098", "An anchor or WORM refusal reaching HTTP")
def plt_098(ctx: Ctx) -> Result:
    """Both carry `error`, `detail` and `remediation`, and both are mapped in
    `STATUS`. The question is whether anything routes them there —
    `Routes.guard` names thirty-odd refusal classes and these are not among
    them."""
    import inspect

    from core.evidence.anchor import AnchorError
    from core.evidence.worm import WormError
    from routes.base import STATUS, Routes
    guard = inspect.getsource(Routes.guard)
    mapped = [c for c in ("anchor_disagreement", "anchor_unreadable",
                          "chain_broken", "nothing_to_anchor",
                          "worm_overwrite_refused", "worm_unreadable",
                          "worm_bad_name") if c in STATUS]
    caught = [name for name in ("AnchorError", "WormError")
              if name in guard]
    if len(caught) == 2:
        return PASS, f"both are caught and {len(mapped)} code(s) are mapped"
    for problem in (AnchorError("anchor_disagreement", "d", "r").as_problem(),
                    WormError("worm_bad_name", "d", "r").as_problem()):
        if set(problem) != {"error", "detail", "remediation"}:
            return FAIL, f"the refusal is not shaped like one: {problem}"
    import pathlib as _p
    reachable = [p.name for p in _p.Path("routes").rglob("*.py")
                 if "anchor_head" in p.read_text(encoding="utf-8")
                 or "AnchorError" in p.read_text(encoding="utf-8")]
    return FAIL, (
        f"{len(mapped)} anchor and WORM refusal codes are mapped in STATUS — "
        f"{mapped} — and `Routes.guard` catches neither AnchorError nor "
        f"WormError (it caught {caught or 'neither'}). Both carry error, "
        f"detail and remediation, so the taxonomy is half-built: the status "
        f"map knows these codes and nothing delivers one to it. Latent, and "
        f"only just: no route calls the anchor directly "
        f"({reachable or 'none found'}), and the scheduler swallows a failing "
        f"job into its `error` string — so an anchor disagreement, which the "
        f"module itself calls a security incident, reaches a caller as a job "
        f"row that says `AnchorError: ...` rather than as a 409 anybody can "
        f"act on")


@case("QA-PLT-108", "The `_freeze` chmod fails and the store carries on")
def plt_108(ctx: Ctx) -> Result:
    """Read-only after writing stops an accident, not an adversary — worth
    doing and worth not overstating. A root that cannot hold the permission
    must still take the object, and must say it could not."""
    import logging
    evidence = _evidence(ctx)
    if evidence is None or evidence.anchors is None:
        return BLOCKED, "no anchor store is wired"
    store = evidence.anchors.store
    records = []

    class Catch(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler, root_logger = Catch(), logging.getLogger()
    root_logger.addHandler(handler)
    was = root_logger.level
    root_logger.setLevel(logging.WARNING)
    real = pathlib.Path.chmod

    def refusing(self, *a, **k):
        raise OSError("this filesystem does not support the permission")

    pathlib.Path.chmod = refusing
    try:
        store.put(f"qa-freeze-{int(time.time() * 1000)}.anchor", b"{}")
    except Exception as exc:
        return FAIL, (f"a chmod failure stopped the write: "
                      f"{type(exc).__name__}: {exc}")
    finally:
        pathlib.Path.chmod = real
        root_logger.removeHandler(handler)
        root_logger.setLevel(was)
    warned = [m for m in records if "read-only" in m]
    if not warned:
        return FAIL, ("the object was written and nothing warned that it is "
                      "not read-only, so the store reports a protection it "
                      "does not have")
    return PASS, f"written, and warned: {warned[0][:120]}"


@case("QA-PLT-109", "A crash part-way through a WORM write")
def plt_109(ctx: Ctx) -> Result:
    """A short object must never be readable as an anchor. The write goes to
    a staging name and is replaced into place, and `names()` never lists the
    staging suffix — so a crash leaves nothing that verification can mistake
    for a head."""
    from core.evidence.worm import _STAGING
    evidence = _evidence(ctx)
    if evidence is None or evidence.anchors is None:
        return BLOCKED, "no anchor store is wired"
    store = evidence.anchors.store
    name = f"qa-crash-{int(time.time() * 1000)}.anchor"
    real = pathlib.Path.replace

    def crash(self, *a, **k):
        raise KeyboardInterrupt("killed mid-write")

    pathlib.Path.replace = crash
    try:
        store.put(name, b'{"seq": 1}')
    except KeyboardInterrupt:
        pass
    finally:
        pathlib.Path.replace = real
    listed = store.names()
    staged = [n for n in pathlib.Path(evidence.anchors.root).iterdir()
              if n.name.endswith(_STAGING)]
    if name in listed:
        return FAIL, f"the interrupted object is listed as complete: {name}"
    if any(n.endswith(_STAGING) for n in listed):
        return FAIL, (f"a staging object is listed by `names()`: "
                      f"{[n for n in listed if n.endswith(_STAGING)]}")
    if not store.exists(name):
        return PASS, (f"nothing readable was left behind; {len(staged)} "
                      f"staging file(s) on disk and none of them listed")
    return FAIL, f"{name} exists after an interrupted write"


@case("QA-PLT-110", "An unwritable WORM root")
def plt_110(ctx: Ctx) -> Result:
    """Everything above this store rests on `put`. A root that cannot be
    written to is the same class of fact as an object that changed, and it
    has to arrive as a named refusal rather than as whatever the filesystem
    raised."""
    evidence = _evidence(ctx)
    if evidence is None or evidence.anchors is None:
        return BLOCKED, "no anchor store is wired"
    store = evidence.anchors.store
    real = pathlib.Path.write_bytes

    def refusing(self, *a, **k):
        raise PermissionError(13, "Permission denied", str(self))

    pathlib.Path.write_bytes = refusing
    try:
        store.put(f"qa-unwritable-{int(time.time() * 1000)}.anchor", b"{}")
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code:
            return PASS, f"refused '{code}': {str(exc)[:110]}"
        return FAIL, (
            f"an unwritable anchor root raises a bare "
            f"{type(exc).__name__} with no code, no detail and no "
            f"remediation — `put` catches nothing around `write_bytes`, while "
            f"`get` wraps its OSError as `worm_unreadable` with the note that "
            f"an object which cannot be read must not be treated as absent. "
            f"The write path has no equivalent, so the one condition that "
            f"stops the second medium existing at all arrives as "
            f"{exc!r} and is swallowed by the scheduler into a job error "
            f"string")
    finally:
        pathlib.Path.write_bytes = real
    return FAIL, "an unwritable root accepted the write"


@case("QA-PLT-5200", "The write-once store refuses a second, different write")
def plt_5200(ctx: Ctx) -> Result:
    """The refusal IS the guarantee. Same bytes twice is idempotent, so the
    anchor job can run twice without being an incident; different bytes
    under one name is the observation the store exists to make."""
    evidence = _evidence(ctx)
    if evidence is None or evidence.anchors is None:
        return BLOCKED, "no anchor store is wired"
    store = evidence.anchors.store
    name = f"qa-once-{int(time.time() * 1000)}.anchor"
    payload = json.dumps({"seq": 1, "chain_hash": "sha256:" + "a" * 64}).encode()
    store.put(name, payload)
    store.put(name, payload)                      # idempotent, must not raise
    try:
        store.put(name, payload + b" ")
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code != "worm_overwrite_refused":
            return FAIL, f"refused '{code}' rather than the overwrite"
        if "evidence" not in str(getattr(exc, "remediation", "")):
            return FAIL, "the refusal does not say the held copy is the evidence"
        for bad in ("../escape", "a/b", "", "."):
            try:
                store.put(bad, b"{}")
            except Exception as inner:
                if getattr(inner, "code", None) != "worm_bad_name":
                    return FAIL, (f"a name of {bad!r} refused "
                                  f"'{getattr(inner, 'code', None)}'")
                continue
            return FAIL, f"a name of {bad!r} was accepted"
        return PASS, ("the same bytes twice is a no-op, different bytes is "
                      "'worm_overwrite_refused', and four path-escaping names "
                      "are 'worm_bad_name'")
    return FAIL, "the write-once store accepted a second, different write"
