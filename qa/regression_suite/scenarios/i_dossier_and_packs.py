"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the documentation graph, and what leaves the building.

The dossier walks a model's pins: versions, the parameter sets fitted under
them, the featureset VERSION each was fitted from, and the features in it. The
export pack carries that walk to somebody who will never be given a login.

**`gaps.md` is the property the whole format rests on.** A pack that silently
omits what it could not reach is worse than no pack, because the recipient
reads absence as evidence. So the one thing every case here asks is whether a
gap is recorded, whether it is recorded ONCE, and whether it says the right
thing — a false gap teaches a reader to skip the file, and an unreadable source
reported as an absence sends somebody looking for a document that is already
filed.

The digests carry the other half. `content_digest` is over the members only,
because the manifest carries the moment the pack was cut and a digest that
moved with the clock would answer *has this changed* with *you asked twice*.
"""
from __future__ import annotations

import io
import json
import time
import zipfile

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

M = "/api/v1/models"
PACKS = "/api/v1/export-packs"
DOSSIERS = "/api/v1/dossiers"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    """The NAME, not the URN.

    `POST /export-packs/{name:path}` and `GET /dossiers/{name:path}` both
    prefix what they are given, and an httpx client collapses the `//` in a
    URN inside a path — so passing the URN answers `not_found` for a model
    that was registered a line earlier."""
    name = ctx.unique("dp")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **SHAPE}, auth=ctx.people["owner"])
    return name


def _version(ctx: Ctx, name: str, semver: str = "1.0.0"):
    return ctx.api.post(f"{M}/{name}/versions", json={"semver": semver},
                        auth=ctx.people["developer"])


def _parameters(ctx: Ctx, model: str, semver: str = "1.0.0", **over):
    body = {"urn": f"maya://model/{model}", "semver": semver,
            "name": "declared-coefficients", "kind": "coefficients",
            "provenance": "declared", "values": {"a": 1.0}, "note": "qa"}
    body.update(over)
    return ctx.api.post("/api/v1/parameters", json=body,
                        auth=ctx.people["developer"])


def _dossier_engine(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("dossier")


def _packer(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("export")


def _pack(ctx: Ctx, name: str, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return ctx.api.post(f"{PACKS}/{name}" + (f"?{query}" if query else ""),
                        auth=ctx.people["risk"])


def _members(response) -> dict:
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        return {n: archive.read(n) for n in archive.namelist()}


# ------------------------------------------------------------------- digests
@case("QA-PLT-155", "Two packs of unchanged state")
def plt_155(ctx: Ctx) -> Result:
    """`content_digest` equal, archive `digest` different. The content digest
    is the one a recipient compares; if it moved with the clock nothing could
    be shown to be the same pack, and if the archive digest did NOT move the
    manifest would not be carrying when it was cut."""
    urn = _model(ctx)
    first = _pack(ctx, urn)
    if first.status_code >= 400:
        return BLOCKED, f"the pack could not be cut: {first.text[:170]}"
    second = _pack(ctx, urn)
    if second.status_code >= 400:
        return FAIL, f"the second pack was refused: {second.text[:150]}"
    content = (first.headers.get("X-Pack-Content-Digest"),
               second.headers.get("X-Pack-Content-Digest"))
    archive = (first.headers.get("X-Pack-Digest"),
               second.headers.get("X-Pack-Digest"))
    if not all(content):
        return BLOCKED, "the pack carries no content digest header"
    if content[0] != content[1]:
        return FAIL, (f"two packs of unchanged state carry different content "
                      f"digests ({content[0][:20]} against {content[1][:20]}), "
                      f"so a recipient cannot tell 'nothing changed' from "
                      f"'you asked twice'")
    if archive[0] == archive[1]:
        return FAIL, ("the archive digest is identical too, so the manifest "
                      "is not recording when the pack was cut")
    return PASS, (f"content {content[0][:20]} on both; archive digests differ "
                  f"because the manifest carries the moment")


@case("QA-PLT-126", "The same document through the export packer instead")
def plt_126(ctx: Ctx) -> Result:
    """The packer RENDERS where the API compiles, so cutting a pack monthly
    does not author four documents a month. The two paths must still agree
    about what the document says — a pack whose document differed from the
    compiled one would answer *has this changed* differently depending on
    which door you came through."""
    urn = _model(ctx)
    docs = ctx.ui.app.state.ctx.get("documents")
    if docs is None:
        return BLOCKED, "no document compiler is wired"
    before = len(docs.for_model(
        ctx.ui.app.state.ctx["registry"].require(f"maya://model/{urn}")["id"]))
    got = _pack(ctx, urn)
    if got.status_code >= 400:
        return BLOCKED, f"the pack could not be cut: {got.text[:170]}"
    after = len(docs.for_model(
        ctx.ui.app.state.ctx["registry"].require(f"maya://model/{urn}")["id"]))
    if after != before:
        return FAIL, (f"cutting a pack authored {after - before} document(s); "
                      f"a monthly export would silently write a document a "
                      f"month into the register")
    members = _members(got)
    named = [n for n in members if n.startswith("documents/")]
    if not named:
        return BLOCKED, f"the pack carries no documents: {sorted(members)[:6]}"
    compiled = ctx.api.post(
        f"/api/v1/documents?urn=maya://model/{urn}&kind=model_development_document",
        auth=ctx.people["validator"])
    if compiled.status_code >= 400:
        return BLOCKED, f"the document could not be compiled: {compiled.text[:150]}"
    digest = (compiled.json() or {}).get("digest")
    carried = [json.loads(members[n]) for n in named
               if n.endswith(".json")]
    digests = {d.get("digest") for d in carried if isinstance(d, dict)}
    if digest not in digests:
        return FAIL, (f"the document the packer rendered does not carry the "
                      f"digest the compiler authored ({digest[:20]} against "
                      f"{sorted(d[:20] for d in digests if d)}), so the two "
                      f"paths disagree about what this document says")
    return PASS, (f"the pack renders without authoring, and the rendered "
                  f"document carries the compiler's digest {digest[:20]}")


@case("QA-PLT-156", "A pack cut while the evidence chain is broken")
def plt_156(ctx: Ctx, ) -> Result:
    """The pack is still cut, and the manifest says `chain.verified: false`.
    A pack that quietly asserted a verified chain is the single worst
    artefact this platform can produce — every other claim in it rests on
    the chain being what it says it is."""
    urn = _model(ctx)
    evidence = ctx.ui.app.state.ctx.get("evidence")
    db = ctx.ui.app.state.ctx.get("db")
    if evidence is None or db is None:
        return BLOCKED, "no evidence chain is wired"
    clean = _pack(ctx, urn)
    if clean.status_code >= 400:
        return BLOCKED, f"the pack could not be cut: {clean.text[:170]}"
    if json.loads(_members(clean)["manifest.json"])["chain"]["verified"] is not True:
        return BLOCKED, "the chain is already unverified before the tamper"
    last = db.query("SELECT seq FROM evidence_node ORDER BY seq DESC LIMIT 1")
    if not last:
        return BLOCKED, "the chain is empty"
    # INSERTED, not updated. The append-only trigger refuses an UPDATE — which
    # is the guard working — so the break has to arrive the way a real one
    # would: a node appended with a prev_hash that does not follow.
    db.execute(
        "INSERT INTO evidence_node (id, seq, kind, subject_type, subject_id, "
        "payload, parents, contains_personal_data, content_hash, prev_hash, "
        "chain_hash, trust, recorded_at, recorded_by) VALUES "
        "(:i, :s, 'qa_break', 'model', 'qa', '{}', '[]', 0, :c, :p, :c, 1.0, "
        ":t, 'qa')",
        {"i": "qa-broken-node", "s": last[0]["seq"] + 1,
         "c": "sha256:" + "0" * 64, "p": "sha256:" + "1" * 64,
         "t": time.time()})
    got = _pack(ctx, urn)
    if got.status_code >= 400:
        return FAIL, (f"the pack could not be cut at all with a broken chain "
                      f"({got.status_code}); refusing to export is refusing "
                      f"the one artefact an investigation needs")
    manifest = json.loads(_members(got)["manifest.json"])
    if manifest["chain"]["verified"] is not False:
        return FAIL, (f"the chain is broken and the manifest reports "
                      f"verified={manifest['chain']['verified']!r} — a pack "
                      f"asserting a chain it did not verify")
    return PASS, "the pack is cut and the manifest reports verified: false"


# ---------------------------------------------------------------------- gaps
@case("QA-PLT-130", "A pack cut while a subsystem is unreadable")
def plt_130(ctx: Ctx) -> Result:
    """`gaps.md` is the one file in the format that promises never to omit
    anything silently. The context builder records what it could not read;
    the packer has to carry it."""
    import inspect

    from core.docs.context import ContextBuilder
    from core.export.pack import ExportPacker
    written = set()
    for line in inspect.getsource(ContextBuilder).splitlines():
        if 'ctx["' in line and "=" in line:
            written.add(line.split('ctx["')[1].split('"]')[0])
    read = set()
    for line in inspect.getsource(ExportPacker).splitlines():
        if "ctx.get(" in line:
            read.add(line.split('ctx.get("')[1].split('"')[0]
                     if 'ctx.get("' in line else "")
    urn = _model(ctx)
    monitoring = ctx.ui.app.state.ctx.get("monitoring")
    if monitoring is None:
        return BLOCKED, "no monitoring service is wired"
    real = type(monitoring).status

    def explode(self, *a, **k):
        raise RuntimeError("the monitoring service is unreachable")

    type(monitoring).status = explode
    try:
        got = _pack(ctx, urn)
    finally:
        type(monitoring).status = real
    if got.status_code >= 400:
        return BLOCKED, f"the pack could not be cut: {got.text[:170]}"
    gaps = _members(got).get("gaps.md", b"").decode()
    if "monitor" in gaps.lower() or "unreadable" in gaps.lower():
        return PASS, "the unreadable subsystem is named in gaps.md"
    missing = read - written
    return FAIL, (
        f"the monitoring service raised while this pack was cut and `gaps.md` "
        f"does not mention it. `ContextBuilder` records what it could not "
        f"read under `ctx['unreadable']`; `ExportPacker.build` reads "
        f"`ctx.get('_gaps')`, which nothing writes — so the loop that turns "
        f"context failures into gap entries iterates an empty list every time. "
        f"Keys read by the packer and never written by the context builder: "
        f"{sorted(k for k in missing if k)}. The file whose entire purpose is "
        f"to say what could not be included says: "
        f"{gaps.strip().splitlines()[-1][:90] if gaps.strip() else '(empty)'}")


@case("QA-PLT-142", "Dossier gaps carried into the pack")
def plt_142(ctx: Ctx) -> Result:
    """The pack is what leaves the building, so a gap that stops at the
    dossier is a gap the recipient never sees. Each one appears prefixed
    under `documentation/`, and the manifest's count agrees with the file."""
    urn = _model(ctx)
    if _version(ctx, urn).status_code >= 400:
        return BLOCKED, "the version could not be created"
    dossier = _dossier_engine(ctx)
    if dossier is None:
        return BLOCKED, "no dossier is wired"
    graph = dossier.of(f"maya://model/{urn}")
    expected = graph.get("gaps") or []
    if not expected:
        return BLOCKED, "the dossier reports no gaps to carry"
    got = _pack(ctx, urn)
    if got.status_code >= 400:
        return BLOCKED, f"the pack could not be cut: {got.text[:170]}"
    members = _members(got)
    gaps = members["gaps.md"].decode()
    manifest = json.loads(members["manifest.json"])
    absent = [g["what"] for g in expected
              if f"documentation/{g['what']}" not in gaps]
    if absent:
        return FAIL, (f"{len(absent)} of {len(expected)} dossier gap(s) do not "
                      f"reach gaps.md: {absent[:4]}")
    listed = gaps.count("\n- ") or gaps.count("\n| ")
    if manifest["gaps"] < len(expected):
        return FAIL, (f"the manifest counts {manifest['gaps']} gap(s) against "
                      f"{len(expected)} from the dossier alone")
    return PASS, (f"{len(expected)} dossier gap(s) carried under "
                  f"documentation/, manifest counts {manifest['gaps']} "
                  f"({listed} listed)")


@case("QA-PLT-137", "A dossier for a model with three empty versions")
def plt_137(ctx: Ctx) -> Result:
    """Gap counts drive a screen, so an off-by-one understates documentation
    debt across the whole estate. One gap for the model and one for each
    version with nothing filed."""
    urn = _model(ctx)
    for semver in ("1.0.0", "1.1.0", "1.2.0"):
        made = _version(ctx, urn, semver)
        if made.status_code >= 400:
            return BLOCKED, f"version {semver} failed: {made.text[:130]}"
    dossier = _dossier_engine(ctx)
    if dossier is None:
        return BLOCKED, "no dossier is wired"
    graph = dossier.of(f"maya://model/{urn}")
    gaps = graph.get("gaps") or []
    subjects = [g["what"] for g in gaps]
    versions = [s for s in subjects if s.startswith("model_version")]
    models = [s for s in subjects if s.startswith("model ")]
    if len(versions) != 3:
        return FAIL, (f"three versions with nothing filed produced "
                      f"{len(versions)} version gap(s): {subjects}")
    if len(models) != 1:
        return FAIL, f"{len(models)} model-level gap(s): {subjects}"
    if len(gaps) != 4:
        return FAIL, (f"{len(gaps)} gaps rather than four (one model, three "
                      f"versions): {subjects}")
    for gap in gaps:
        if "nothing is filed here" not in gap["why"]:
            return FAIL, f"a gap does not say what it is: {gap}"
        if "expected" not in gap["why"]:
            return FAIL, f"a gap does not say what was expected: {gap['why']}"
    return PASS, f"exactly four gaps: {subjects}"


@case("QA-PLT-140", "The attachment register throws while a dossier is built")
def plt_140(ctx: Ctx) -> Result:
    """Unreadable, not absent. A source that could not be read reported as
    an absence is somebody chasing a document that is already filed — and
    doing it from a pack, where they cannot check."""
    urn = _model(ctx)
    dossier = _dossier_engine(ctx)
    attachments = ctx.ui.app.state.ctx.get("attachments")
    if dossier is None or attachments is None:
        return BLOCKED, "no dossier or attachment register is wired"
    real = type(attachments).about

    def explode(self, *a, **k):
        raise RuntimeError("the attachment store is unreachable")

    type(attachments).about = explode
    try:
        graph = dossier.of(f"maya://model/{urn}")
    finally:
        type(attachments).about = real
    gaps = graph.get("gaps") or []
    if not gaps:
        return BLOCKED, "the dossier reported no gaps at all"
    unreadable = [g for g in gaps
                  if "could not be read" in g["why"]
                  or "unreadable" in g["why"].lower()]
    if unreadable:
        return PASS, f"reported as unreadable: {unreadable[0]['why'][:110]}"
    return FAIL, (
        f"the attachment register raised for every subject and the dossier "
        f"records {len(gaps)} gap(s) all saying "
        f"{gaps[0]['why'][:80]!r}. `_attached` catches the exception, logs it "
        f"and returns `[]`, so `_node` cannot tell 'nothing is filed' from "
        f"'the store did not answer' — and reports the first. A reader sent to "
        f"file a document that is already filed cannot discover that from the "
        f"pack, which is the only thing they have")


@case("QA-PLT-138", "A dangling featureset pin on a non-fitted parameter set")
def plt_138(ctx: Ctx) -> Result:
    """A gap naming the dangling pin. The code comment above `_pin` says a
    pin that does not resolve is a real gap and a different one from having
    no pin at all — this is whether the code does what the comment says, for
    the provenance the gap branch does not cover."""
    urn = _model(ctx)
    if _version(ctx, urn).status_code >= 400:
        return BLOCKED, "the version could not be created"
    parameters = ctx.ui.app.state.ctx.get("parameters")
    dossier = _dossier_engine(ctx)
    if parameters is None or dossier is None:
        return BLOCKED, "no parameter register or dossier is wired"
    recorded = _parameters(ctx, urn)
    if recorded.status_code >= 400:
        return BLOCKED, f"the parameter set could not be recorded: {recorded.text[:170]}"
    row = recorded.json() or {}
    # The state the register reaches when a featureset version is destroyed
    # underneath a set that named it.
    parameters.parameters.set(
        {"featureset_version_id": "featureset-version-that-is-gone"},
        id=row["id"])
    graph = dossier.of(f"maya://model/{urn}")
    gaps = graph.get("gaps") or []
    dangling = [g for g in gaps
                if "featureset-version-that-is-gone" in g["why"]
                or "cannot resolve" in g["why"]
                or "points at nothing" in g["why"]]
    if dangling:
        return PASS, f"the dangling pin is named: {dangling[0]['why'][:110]}"
    named = [g["what"] for g in gaps]
    return FAIL, (
        f"a '{row.get('provenance')}' parameter set names a featureset version "
        f"the register cannot resolve, and the dossier records no gap for it. "
        f"`_pin` returns (None, None) for an unresolvable id — the same value "
        f"it returns for no pin at all — and the gap branch below it is guarded "
        f"on `provenance == 'fitted'`, so for every other provenance the "
        f"dangling pin is dropped without a word. Gaps recorded: {named}")


@case("QA-PLT-139", "A dangling pin on a fitted set versus no pin at all")
def plt_139(ctx: Ctx) -> Result:
    """Two distinguishable gaps. "The pin points at nothing" and "there is no
    pin" need opposite work — one is a register that lost something, the
    other is a fit nobody recorded the data for."""
    parameters = ctx.ui.app.state.ctx.get("parameters")
    dossier = _dossier_engine(ctx)
    if parameters is None or dossier is None:
        return BLOCKED, "no parameter register or dossier is wired"

    def _fitted(pin):
        urn = _model(ctx)
        if _version(ctx, urn).status_code >= 400:
            return None, None
        made = _parameters(ctx, urn, name="fit")
        if made.status_code >= 400:
            return None, None
        row = made.json() or {}
        parameters.parameters.set(
            {"provenance": "fitted", "featureset_version_id": pin}, id=row["id"])
        return urn, row

    urn_dangling, row_a = _fitted("featureset-version-that-is-gone")
    urn_absent, row_b = _fitted(None)
    if not (row_a and row_b):
        return BLOCKED, "the two parameter sets could not be built"
    dangling = [g["why"] for g in (dossier.of(f"maya://model/{urn_dangling}").get("gaps") or [])
                if g["what"].startswith("parameters")]
    absent = [g["why"] for g in (dossier.of(f"maya://model/{urn_absent}").get("gaps") or [])
              if g["what"].startswith("parameters")]
    if not dangling and not absent:
        return BLOCKED, "neither state produced a parameter-level gap"
    if not dangling:
        return FAIL, ("a fitted set whose pin does not resolve produced no gap "
                      "at all, while one with no pin did")
    if dangling == absent:
        return FAIL, (
            f"both states print the same sentence: {dangling[0][:130]!r}. It is "
            f"false for the dangling case — that set DOES name the featureset "
            f"version it came from, and the register has lost it. The comment "
            f"above `_pin` states the rule ('a pin that does not resolve is a "
            f"real gap, and a different one from having no pin at all') and "
            f"the code returns the same (None, None) for both, so the reader "
            f"is told to go and record a pin that is already there")
    return PASS, (f"distinguishable: {dangling[0][:70]!r} against "
                  f"{absent[0][:70]!r}")


# ------------------------------------------------------------- the mechanics
@case("QA-PLT-154",
      "Two attachments with the same filename and a colliding digest prefix")
def plt_154(ctx: Ctx) -> Result:
    """The member name is the digest's bytes 7:15 plus the filename. Two
    documents filed under the same name whose digests share those eight
    characters collide, and a dict assignment loses one of them without a
    gap — in the one format that promises never to omit anything silently."""
    import inspect

    from core.export.pack import ExportPacker
    source = inspect.getsource(ExportPacker._add_attachments)
    if "members[f\"attachments/" not in source:
        return BLOCKED, "attachments are no longer named that way"
    _model(ctx)
    packer = _packer(ctx)
    attachments = ctx.ui.app.state.ctx.get("attachments")
    if packer is None or attachments is None:
        return BLOCKED, "no packer or attachment register is wired"
    twins = [
        {"id": "a1", "kind": "methodology", "title": "one",
         "filename": "report.pdf", "digest": "sha256:AAAAAAAAdiffer1",
         "state": "accepted"},
        {"id": "a2", "kind": "methodology", "title": "two",
         "filename": "report.pdf", "digest": "sha256:AAAAAAAAdiffer2",
         "state": "accepted"},
    ]
    members, gaps = {}, []
    real = type(attachments).content
    type(attachments).content = lambda self, i: f"body of {i}".encode()
    try:
        packer._add_attachments(members, gaps, {"attachments": twins})
    finally:
        type(attachments).content = real
    carried = [n for n in members if n.startswith("attachments/")
               and n != "attachments/index.json"]
    if len(carried) == 2:
        return PASS, f"both members survive: {carried}"
    index = json.loads(members["attachments/index.json"])["attachments"]
    return FAIL, (
        f"two attachments named 'report.pdf' whose digests agree on bytes "
        f"7:15 produced {len(carried)} archive member(s) — {carried} — while "
        f"attachments/index.json lists {len(index)}. The name is "
        f"`digest[7:15] + filename`, a dict assignment overwrites, and no gap "
        f"is recorded: the index says two documents are in this pack and one "
        f"of them is not. {len(gaps)} gap(s) recorded")


@case("QA-PLT-152", "A pack over the size ceiling")
def plt_152(ctx: Ctx) -> Result:
    """`pack_too_large` is refused AFTER the whole archive has been built and
    zipped in memory, so the refusal that exists to protect the server
    requires the server to have already done the thing it is protecting
    itself from."""
    import inspect

    from core.export.pack import MAX_BYTES, ExportPacker
    source = inspect.getsource(ExportPacker.build)
    lines = source.splitlines()
    zipped = next((i for i, ln in enumerate(lines) if "self._zip(" in ln), None)
    checked = next((i for i, ln in enumerate(lines)
                    if "MAX_BYTES" in ln), None)
    if zipped is None or checked is None:
        return BLOCKED, "the build no longer zips or no longer checks a ceiling"
    if checked < zipped:
        return PASS, "the ceiling is checked before the archive is built"
    guarded = [ln for ln in lines
               if ("len(body)" in ln or "running" in ln) and "MAX" in ln]
    if guarded:
        return PASS, f"a running total is guarded while gathering: {guarded[0].strip()[:90]}"
    return FAIL, (
        f"`pack_too_large` is raised at source line {checked} and "
        f"`self._zip(members)` runs at line {zipped} — the whole archive is "
        f"built, compressed and held in memory before its size is measured "
        f"against the {MAX_BYTES / 1e9:.0f}GB ceiling. Every member is already "
        f"resident as bytes in `members` too, so the peak is the uncompressed "
        f"content plus the archive. The refusal protects the recipient from an "
        f"export nobody can open; it does not protect the server, which is the "
        f"thing a ceiling is usually for")


@case("QA-PLT-141", "A dossier over a large featureset estate")
def plt_141(ctx: Ctx) -> Result:
    """`_pin` resolves one id by scanning every featureset and every version
    of each, on every parameter set, on every dossier build. Reported as
    wall clock and as the shape of the growth, because a screen that is
    quick on a demo estate and slow on a bank's is a screen nobody sees
    fail until it matters."""
    import inspect

    from core.docs.dossier import Dossier
    source = inspect.getsource(Dossier._pin)
    if "for row in self.featuresets.list()" not in source:
        return PASS, "the pin no longer scans the estate"
    features = ctx.ui.app.state.ctx.get("features")
    dossier = _dossier_engine(ctx)
    parameters = ctx.ui.app.state.ctx.get("parameters")
    if not (features and dossier and parameters):
        return BLOCKED, "no feature registry, dossier or parameter register"
    urn = _model(ctx)
    if _version(ctx, urn).status_code >= 400:
        return BLOCKED, "the version could not be created"
    made = _parameters(ctx, urn, name="fit")
    if made.status_code >= 400:
        return BLOCKED, f"the parameter set could not be recorded: {made.text[:150]}"
    parameters.parameters.set(
        {"provenance": "fitted", "featureset_version_id": "gone"},
        id=(made.json() or {})["id"])
    # A handful of featuresets, so the scan has something to scan. Twenty is
    # not a bank's estate; the point is the SHAPE of the growth, measured
    # rather than asserted.
    for _ in range(20):
        ctx.api.post("/api/v1/featuresets",
                     json={"name": ctx.unique("fs"), "entity": "obligor",
                           "slots": {"dscr": {"dtype": "float"}},
                           "description": "qa"}, auth=ctx.people["owner"])
    reads = {"n": 0, "versions": 0}
    real_list = type(features.sets).list
    real_versions = type(features.sets).versions_of

    def counting_versions(self, *a, **k):
        reads["versions"] += 1
        return real_versions(self, *a, **k)

    def counting(self, *a, **k):
        reads["n"] += 1
        return real_list(self, *a, **k)

    type(features.sets).list = counting
    type(features.sets).versions_of = counting_versions
    try:
        started = time.time()
        dossier.of(f"maya://model/{urn}")
        elapsed = time.time() - started
    finally:
        type(features.sets).list = real_list
        type(features.sets).versions_of = real_versions
    estate = len(features.sets.list())
    return PASS, (
        f"one parameter set, one dossier build, an estate of {estate} "
        f"featureset(s): {reads['n']} full scan(s) of the register and "
        f"{reads['versions']} version read(s), {elapsed * 1000:.0f} ms. The "
        f"cost is O(parameter sets x featuresets x versions) per build, with "
        f"the register read whole each time and no index on "
        f"`featureset_version.id` being used — a screen that is quick here "
        f"and is not on a bank's estate")
