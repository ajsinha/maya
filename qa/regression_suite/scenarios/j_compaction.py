"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section J — reclaiming the bytes a deletion leaves behind.

A deletion removes the record. The blobs it named are content-addressed and
shared, so nothing can be reclaimed by following the deleted model — the
question is the other way round: **which bytes on disk does no surviving row
name.**

**Never on first sight.** An upload writes the bytes and then the row that
references them, and a sweeper walking past in between sees exactly what a real
orphan looks like. Two sightings, and a mark on something that has since
acquired a reference is CLEARED rather than left to expire — a stale mark on a
live blob is a blob the next pass deletes.

And a refcount is not permission. A sweep is refused outright while an
estate-wide legal hold is active, because the refcount answers *is this needed*
and the hold answers *is anybody allowed to destroy it*.
"""
from __future__ import annotations

import hashlib
import pathlib

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

M = "/api/v1/models"
ART = "/api/v1/artifacts"
C = "/api/v1/compaction"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _compaction(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("compaction")


def _orphan(ctx: Ctx, body: bytes) -> str:
    """Bytes in the artifact store that no row names."""
    got = ctx.api.post(f"{ART}?format=onnx", content=body,
                       auth=ctx.people["developer"])
    if got.status_code >= 400:
        return ""
    return (got.json() or {})["digest"]


def _past_the_sidecar(ctx: Ctx) -> int:
    """Remove the `.fmt` sidecars before sweeping.

    QA-DEL-071 reports what they do: `_unreferenced` treats them as orphan
    blobs and the reclaim pass aborts on the malformed address. The cases
    below are about something else, and a case blocked by a defect it is not
    testing proves nothing about its own subject.
    """
    store = ctx.ui.app.state.ctx.get("artifacts")
    if store is None:
        return 0
    removed = 0
    for path in pathlib.Path(store.root).rglob("*.fmt"):
        path.unlink()
        removed += 1
    return removed


@case("QA-DEL-071", "Sweep twice", isolated=True)
def del_071(ctx: Ctx) -> Result:
    """Marked on the first pass, reclaimed on the second. The first sweep
    must not delete: an upload writes bytes before the row that references
    them, and a sweeper walking past in between cannot tell that from an
    orphan."""
    from core.retention.compaction import SIGHTINGS_BEFORE_SWEEP
    engine = _compaction(ctx)
    if engine is None:
        return BLOCKED, "no compaction engine is wired"
    digest = _orphan(ctx, b"orphan bytes nobody will ever reference")
    if not digest:
        return BLOCKED, "the artifact could not be stored"
    store = ctx.ui.app.state.ctx["artifacts"]
    path = store._path(digest)
    if not path.exists():
        return BLOCKED, "the artifact is not on disk"
    from core.artifacts.common import ArtifactError
    try:
        first = engine.sweep(actor="qa")
    except ArtifactError as exc:
        sidecars = [p.name for p in pathlib.Path(store.root).rglob("*.fmt")]
        return FAIL, (
            f"the first sweep raised '{exc.code}': {str(exc)[:90]}. "
            f"`ArtifactStore._remember` writes a `<digest>.fmt` sidecar beside "
            f"every stored artifact, and `Compaction._unreferenced` treats "
            f"every file under the root that is not `.partial` as a candidate "
            f"orphan — so it builds the address `sha256:<digest>.fmt`, no row "
            f"names it, and the sweep carries it forward. There are "
            f"{len(sidecars)} sidecar(s) in this store. Compaction cannot "
            f"complete on any artifact store that has ever stored an artifact")
    if first["swept"]:
        return FAIL, (f"the first sweep reclaimed {first['swept']} blob(s); "
                      f"an upload in flight looks exactly like this")
    if not first["marked"]:
        return FAIL, f"the first sweep marked nothing: {first}"
    if not path.exists():
        return FAIL, "the blob is gone after one pass"
    try:
        second = engine.sweep(actor="qa")
    except ArtifactError as exc:
        sidecars = [p.name for p in pathlib.Path(store.root).rglob("*.fmt")]
        return FAIL, (
            f"the first sweep marked {first['marked']} candidate(s) and the "
            f"second raised '{exc.code}': {str(exc)[:80]}. The marks include "
            f"the `<digest>.fmt` sidecar `ArtifactStore._remember` writes "
            f"beside every artifact ({len(sidecars)} in this store); "
            f"`Compaction._unreferenced` skips only `.partial`, so on the "
            f"reclaim pass `_remove` asks the store for the path of "
            f"`sha256:<digest>.fmt` and the address validator refuses it. "
            f"Nothing catches that, so the whole sweep aborts and NOTHING is "
            f"reclaimed — on any store that has ever held an artifact")
    if not second["swept"]:
        return FAIL, f"the second sweep reclaimed nothing: {second}"
    if path.exists():
        return FAIL, "the blob survives two passes with nothing naming it"
    if not second["reclaimed_bytes"]:
        return FAIL, "bytes were swept and none are counted"
    return PASS, (f"marked on pass 1, {second['swept']} blob(s) and "
                  f"{second['reclaimed_bytes']} byte(s) reclaimed on pass "
                  f"{SIGHTINGS_BEFORE_SWEEP}")


@case("QA-DEL-072", "A reference appears between the two passes", isolated=True)
def del_072(ctx: Ctx) -> Result:
    """The mark is CLEARED, not left to expire. A mark that stayed would be
    two passes old the next time a sweeper looked, and it would reclaim a
    blob a live version names."""
    engine = _compaction(ctx)
    db = ctx.ui.app.state.ctx.get("db")
    if engine is None or db is None:
        return BLOCKED, "no compaction engine is wired"
    body = b"bytes that acquire a reference after the first pass"
    digest = _orphan(ctx, body)
    if not digest:
        return BLOCKED, "the artifact could not be stored"
    path = ctx.ui.app.state.ctx["artifacts"]._path(digest)
    _past_the_sidecar(ctx)
    first = engine.sweep(actor="qa")
    if not first["marked"]:
        return BLOCKED, f"nothing was marked: {first}"
    # The reference arrives: a version naming the digest.
    name = ctx.unique("cmp")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **SHAPE}, auth=ctx.people["owner"])
    made = ctx.api.post(f"{M}/{name}/versions",
                        json={"semver": "1.0.0", "artifact_digest": digest},
                        auth=ctx.people["developer"])
    if made.status_code >= 400:
        return BLOCKED, f"the version could not be created: {made.text[:150]}"
    _past_the_sidecar(ctx)
    second = engine.sweep(actor="qa")
    _past_the_sidecar(ctx)
    third = engine.sweep(actor="qa")
    if not path.exists():
        return FAIL, ("a blob a live version names was reclaimed after the "
                      "reference appeared")
    if not second["cleared"]:
        return FAIL, (f"the stale mark was not cleared: {second} — the next "
                      f"pass would see a two-pass-old mark on a live blob")
    if third["swept"]:
        return FAIL, f"the third pass reclaimed {third['swept']} blob(s)"
    return PASS, (f"{second['cleared']} mark(s) cleared when the reference "
                  f"arrived; two further passes reclaim nothing")


@case("QA-DEL-073", "Two models sharing one artifact, delete one",
      isolated=True)
def del_073(ctx: Ctx) -> Result:
    """Content addressing means two models can name the same bytes, so
    reclaiming by following a deleted model would take a blob another model
    is still serving. The refcount is the whole answer."""
    engine = _compaction(ctx)
    if engine is None:
        return BLOCKED, "no compaction engine is wired"
    body = b"weights that two models both name"
    digest = _orphan(ctx, body)
    if not digest:
        return BLOCKED, "the artifact could not be stored"
    path = ctx.ui.app.state.ctx["artifacts"]._path(digest)
    names = []
    for _ in range(2):
        name = ctx.unique("shr")
        ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                              "owner": "owner", **SHAPE},
                     auth=ctx.people["owner"])
        made = ctx.api.post(f"{M}/{name}/versions",
                            json={"semver": "1.0.0",
                                  "artifact_digest": digest},
                            auth=ctx.people["developer"])
        if made.status_code >= 400:
            return BLOCKED, f"a version could not be created: {made.text[:150]}"
        names.append(name)
    db = ctx.ui.app.state.ctx["db"]
    model = ctx.ui.app.state.ctx["registry"].require(f"maya://model/{names[0]}")
    db.execute("DELETE FROM model_version WHERE model_id = :m",
               {"m": model["id"]})
    _past_the_sidecar(ctx)
    engine.sweep(actor="qa")
    _past_the_sidecar(ctx)
    engine.sweep(actor="qa")
    if not path.exists():
        left = db.query("SELECT COUNT(*) AS n FROM model_version "
                        "WHERE artifact_digest = :d", {"d": digest})
        return FAIL, (f"the blob was reclaimed while "
                      f"{left[0]['n'] if left else '?'} surviving version(s) "
                      f"still name it")
    return PASS, ("one of two models let the bytes go and the blob survives "
                  "two passes, because the refcount counts rows and not models")


@case("QA-DEL-076", "POST /compaction/sweep?dry_run=true", isolated=True)
def del_076(ctx: Ctx) -> Result:
    """Reports and reclaims nothing — including the marks. A dry run that
    advanced a sighting would make the second real sweep destructive one
    pass early, which is the one thing a dry run must not do."""
    engine = _compaction(ctx)
    if engine is None:
        return BLOCKED, "no compaction engine is wired"
    digest = _orphan(ctx, b"bytes a dry run must not touch")
    if not digest:
        return BLOCKED, "the artifact could not be stored"
    path = ctx.ui.app.state.ctx["artifacts"]._path(digest)
    _past_the_sidecar(ctx)
    engine.sweep(actor="qa")                      # one real sighting
    marks_before = len(engine.repo.many())
    dry = engine.sweep(actor="qa", dry_run=True)
    marks_after = len(engine.repo.many())
    if not dry.get("dry_run"):
        return FAIL, "the answer does not say it was a dry run"
    if not path.exists():
        return FAIL, "a dry run reclaimed the blob"
    if marks_after != marks_before:
        return FAIL, (f"a dry run changed the mark register: "
                      f"{marks_before} → {marks_after}")
    row = engine.repo.one(digest=digest)
    if row and row["sightings"] != 1:
        return FAIL, (f"a dry run advanced the sighting count to "
                      f"{row['sightings']}, so the next real sweep destroys a "
                      f"pass early")
    if not dry.get("swept") and dry.get("marked") is None:
        return FAIL, f"a dry run reports nothing at all: {dry}"
    return PASS, (f"reports {dry['swept']} would-be sweep(s) and "
                  f"{dry['marked']} mark(s), changes neither the store nor "
                  f"the register")


@case("QA-DEL-077", "`not_reclaimable` in the plan", isolated=True)
def del_077(ctx: Ctx) -> Result:
    """Delta keeps its own transaction log, so removing part files from
    outside it produces a manifest naming a file that is not there.
    Compacting a Delta table is Delta's operation — and silently not
    touching it would leave a deployer reading a reclaim figure that omits
    most of their disk."""
    got = ctx.api.get(f"{C}/plan", )
    if got.status_code >= 400:
        return BLOCKED, f"the plan could not be read: {got.text[:150]}"
    plan = got.json() or {}
    if "not_reclaimable" not in plan:
        return FAIL, (f"the plan says nothing about what it will not touch: "
                      f"{sorted(plan)}")
    unreachable = plan["not_reclaimable"]
    if "delta_bytes" not in unreachable:
        return FAIL, f"the plan does not size what it leaves: {unreachable}"
    why = unreachable.get("why") or ""
    if "Delta" not in why:
        return FAIL, f"the plan does not say why it leaves it: {why[:140]}"
    if "database_free_pages" not in plan:
        return FAIL, "the plan says nothing about the database's own slack"
    return PASS, (f"delta_bytes {unreachable['delta_bytes']} left alone with a "
                  f"reason, and {plan['database_free_pages']} free page(s) "
                  f"reported separately")


@case("QA-DEL-078", "Vacuum after a cascade", isolated=True)
def del_078(ctx: Ctx) -> Result:
    """Removed rows stop occupying the file. Asked for rather than done on
    the way out of a deletion, because it takes a write lock for its
    duration and needs free space equal to the database."""
    engine = _compaction(ctx)
    if engine is None:
        return BLOCKED, "no compaction engine is wired"
    for _ in range(8):
        name = ctx.unique("vac")
        ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                              "owner": "owner", **SHAPE},
                     auth=ctx.people["owner"])
        ctx.api.delete(f"{M}/maya://model/{name}?reason=qa")
    before = engine._free_pages()
    out = engine.vacuum(actor="qa")
    after = engine._free_pages()
    if not isinstance(out, dict):
        return FAIL, f"the vacuum reports nothing usable: {out!r}"
    if after > before:
        return FAIL, (f"free pages went up across a vacuum: {before} → {after}")
    for key in ("before_bytes", "after_bytes", "reclaimed_bytes"):
        if key not in out:
            return FAIL, f"the vacuum does not report '{key}': {out}"
    if out["before_bytes"] < out["after_bytes"]:
        return FAIL, (f"the file grew across a vacuum: "
                      f"{out['before_bytes']} → {out['after_bytes']}")
    if out["reclaimed_bytes"] != out["before_bytes"] - out["after_bytes"]:
        return FAIL, (f"the reclaimed figure does not follow from the two "
                      f"sizes: {out}")
    return PASS, (f"free pages {before} → {after}; file "
                  f"{out['before_bytes']} → {out['after_bytes']} bytes, "
                  f"{out['reclaimed_bytes']} reclaimed, "
                  f"measured={out.get('measured')}")


@case("QA-DEL-080", "Mark a tombstone compacted twice", isolated=True)
def del_080(ctx: Ctx) -> Result:
    """The tombstone stays either way, because it is the IDENTITY and not
    the storage. Marking it twice would say storage was reclaimed twice,
    which is a claim about bytes that are already gone."""
    engine = _compaction(ctx)
    if engine is None:
        return BLOCKED, "no compaction engine is wired"
    name = ctx.unique("tmb")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner",
                          **SHAPE}, auth=ctx.people["owner"])
    gone = ctx.api.delete(f"{M}/{urn}?reason=qa%20deletion")
    if gone.status_code >= 400:
        return BLOCKED, f"the deletion was refused: {gone.text[:150]}"
    first = engine.mark_compacted(urn, actor="qa", reclaimed={"bytes": 10})
    if not first.get("compacted_at"):
        return FAIL, f"the first mark recorded nothing: {first}"
    from core.retention.common import RetentionError
    try:
        engine.mark_compacted(urn, actor="qa", reclaimed={"bytes": 10})
    except RetentionError as exc:
        if exc.code != "already_compacted":
            return FAIL, f"refused '{exc.code}' rather than already_compacted"
        if "identity" not in str(getattr(exc, "remediation", "")):
            return FAIL, ("the refusal does not say the tombstone stays "
                          "either way")
        return PASS, f"refused 'already_compacted': {str(exc)[:110]}"
    return FAIL, "a tombstone was marked compacted twice"


@case("QA-DEL-083", "Sweep against a store directory that does not exist",
      isolated=True)
def del_083(ctx: Ctx) -> Result:
    """Reports zero, and must not report *nothing to reclaim* — a store the
    sweeper cannot read looks exactly like a store with nothing in it, and
    the two have opposite meanings for whoever is watching disk."""
    engine = _compaction(ctx)
    store = ctx.ui.app.state.ctx.get("artifacts")
    if engine is None or store is None:
        return BLOCKED, "no compaction engine or artifact store is wired"
    digest = _orphan(ctx, b"bytes behind a root that will vanish")
    if not digest:
        return BLOCKED, "the artifact could not be stored"
    real_root = store.root
    missing = pathlib.Path(str(real_root)) / "does-not-exist"
    store.root = missing
    try:
        out = engine.sweep(actor="qa")
    except Exception as exc:
        store.root = real_root
        return FAIL, (f"a missing store root raised "
                      f"{type(exc).__name__}: {str(exc)[:120]}")
    store.root = real_root
    if out["swept"] or out["marked"]:
        return FAIL, (f"a missing root produced work: {out}")
    intact = engine.sweep(actor="qa", dry_run=True)
    if not intact["marked"] and not intact["swept"]:
        return BLOCKED, "the real root has nothing to find either"
    return PASS, (f"a missing root sweeps to zero without raising, and the "
                  f"real root still sees {intact['marked']} candidate(s) — so "
                  f"the zero came from the root being absent rather than from "
                  f"the store being empty")


@case("QA-DEL-084", "`.partial` upload files are never marked", isolated=True)
def del_084(ctx: Ctx) -> Result:
    """An upload in progress is not an orphan. It is the one thing on disk
    that is guaranteed to have no row naming it yet, which makes it exactly
    what a refcount sweep would delete."""
    engine = _compaction(ctx)
    store = ctx.ui.app.state.ctx.get("artifacts")
    if engine is None or store is None:
        return BLOCKED, "no compaction engine or artifact store is wired"
    body = b"an upload that is still arriving"
    digest = hashlib.sha256(body).hexdigest()
    root = pathlib.Path(store.root)
    partial = root / digest[:2] / digest[2:4] / f"{digest}.partial"
    partial.parent.mkdir(parents=True, exist_ok=True)
    partial.write_bytes(body)
    try:
        _past_the_sidecar(ctx)
        engine.sweep(actor="qa")
        _past_the_sidecar(ctx)
        engine.sweep(actor="qa")
        if not partial.exists():
            return FAIL, ("an upload in progress was reclaimed by two sweeps; "
                          "a `.partial` is the one file guaranteed to have no "
                          "row naming it")
        marked = [m for m in engine.repo.many()
                  if digest in str(m.get("digest"))]
        if marked:
            return FAIL, f"a `.partial` was marked: {marked[0]}"
    finally:
        partial.unlink(missing_ok=True)
    return PASS, "skipped by both passes and never marked"


@case("QA-DEL-085", "A sweep under an estate-wide legal hold", isolated=True)
def del_085(ctx: Ctx) -> Result:
    """Refused entirely. A refcount answers *is this needed by the
    register*; a hold answers *is anybody permitted to destroy it*, and the
    first is not an answer to the second."""
    engine = _compaction(ctx)
    if engine is None:
        return BLOCKED, "no compaction engine is wired"
    digest = _orphan(ctx, b"bytes protected by a hold")
    if not digest:
        return BLOCKED, "the artifact could not be stored"
    path = ctx.ui.app.state.ctx["artifacts"]._path(digest)
    _past_the_sidecar(ctx)
    engine.sweep(actor="qa")
    placed = ctx.api.post("/api/v1/legal-holds",
                          json={"matter": "QA-2026-220",
                                "owner": "person/legal-counsel",
                                "scope_kind": "estate", "classes": []},
                          auth=ctx.people["risk"])
    if placed.status_code >= 400:
        return BLOCKED, f"the hold could not be placed: {placed.text[:150]}"
    from core.retention.common import RetentionError
    try:
        engine.sweep(actor="qa")
    except RetentionError as exc:
        if exc.code != "under_legal_hold":
            return FAIL, f"refused '{exc.code}' rather than under_legal_hold"
        if "QA-2026-220" not in str(exc) and "hold" not in str(exc):
            return FAIL, f"the refusal names no matter: {str(exc)[:140]}"
        if not path.exists():
            return FAIL, "refused, and the blob is gone anyway"
        over_http = ctx.api.post(f"{C}/sweep")
        if over_http.status_code < 400:
            return FAIL, (f"the service refuses and the route answers "
                          f"{over_http.status_code}")
        if code_of(over_http) != "under_legal_hold":
            return FAIL, (f"over HTTP the refusal is "
                          f"'{code_of(over_http)}' at "
                          f"{over_http.status_code}")
        return PASS, (f"refused 'under_legal_hold' at the service and at "
                      f"{over_http.status_code} over HTTP, blob intact")
    return FAIL, "a sweep ran with an estate-wide legal hold active"
