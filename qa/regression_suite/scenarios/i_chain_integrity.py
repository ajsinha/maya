"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the chain against somebody who can write to the database.

Every case that damages the chain is `isolated`. They share one instance
otherwise, and a chain broken by an earlier case makes the next one pass for
the wrong reason — "the chain does not verify" is then true before the case
does anything.

`verify_chain` compares the chain against ITSELF, which a rewritten chain
passes. The anchor is the only verification here that an attacker with
database access alone cannot satisfy, because it compares the chain against a
second medium — and that is why anchoring refuses to run over a chain that
does not already verify: writing the broken state down would make every later
comparison agree with it.

The content hash is where the subtler attacks land. `recorded_by` and `trust`
are inside it, and the omission of `recorded_by` was worse than it sounds:
segregation of duties is decided entirely by reading that column off these
nodes, so a single UPDATE reassigning authorship turned the control off for
that subject while `verify_chain` went on reporting the chain intact.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _engine(ctx: Ctx):
    return ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")


def _grow(ctx: Ctx, n: int = 3) -> None:
    for _ in range(n):
        name = ctx.unique("ci")
        ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                              "owner": "owner", **SHAPE})


def _nodes(engine) -> list:
    return sorted(engine.repo.many(), key=lambda n: n.get("seq") or 0)


def _db(ctx: Ctx):
    return ctx.made.get("db") or ctx.ui.app.state.ctx.get("db")


#: The append-only guard is a DATABASE TRIGGER, not a repository check, so
#: raw SQL is refused too. A tamper case therefore has to do what the threat
#: model's attacker would: drop the trigger first. It is restored afterwards.
_GUARDS = ("append_only_evidence_node_update",
           "append_only_evidence_node_delete")


def _unguarded(ctx: Ctx):
    """Drop the append-only triggers for the duration of one tamper."""
    db = _db(ctx)
    if db is None:
        return None
    held = {}
    for name in _GUARDS:
        row = db.query_one("SELECT sql FROM sqlite_master WHERE name = :n",
                           {"n": name})
        if row and row.get("sql"):
            held[name] = row["sql"]
            db.execute(f"DROP TRIGGER {name}")
    return (db, held) if held else None


def _reguard(state) -> None:
    if not state:
        return
    db, held = state
    for sql in held.values():
        db.execute(sql)


def _tamper(ctx: Ctx, node_id: str, column: str, value) -> bool:
    """Rewrite one column the way somebody with database access would.

    The repository refuses it (QA-PLT-4763) and so does the trigger behind
    the repository, so this drops the guard, writes, and puts it back — which
    is exactly the access the anchors exist to defend against.
    """
    state = _unguarded(ctx)
    if state is None:
        return False
    db, _held = state
    try:
        db.execute(
            f"UPDATE evidence_node SET {column} = :value WHERE id = :id",
            {"value": value, "id": node_id})
    finally:
        _reguard(state)
    return True


def _drop(ctx: Ctx, node_id: str) -> bool:
    state = _unguarded(ctx)
    if state is None:
        return False
    db, _held = state
    try:
        db.execute("DELETE FROM evidence_node WHERE id = :id", {"id": node_id})
    finally:
        _reguard(state)
    return True


@case("QA-PLT-099", "`recorded_at` moved on a node, chain unchanged", isolated=True)
def plt_099(ctx: Ctx) -> Result:
    """`recorded_at` is NOT in the content hash, and that is a decision
    rather than an oversight — the hash covers what was asserted, and a
    timestamp the platform wrote is not part of the assertion. What matters
    is that the case says which it is, because a reader who assumes the
    timestamp is sealed is relying on something that is not."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    _grow(ctx)
    nodes = _nodes(engine)
    if not nodes:
        return BLOCKED, "the chain is empty"
    target = nodes[-1]
    before = engine.content_hash_of(target)
    moved = {**target, "recorded_at": (target.get("recorded_at") or 0) + 9999}
    if engine.content_hash_of(moved) != before:
        return PASS, "the recorded time is inside the content hash"
    if not _tamper(ctx, target["id"], "recorded_at", moved["recorded_at"]):
        return BLOCKED, "no database handle to tamper with"
    report = engine.verify_chain()
    if not report.get("valid"):
        return PASS, ("moving the recorded time breaks the chain by some "
                      "other path")
    return FAIL, ("a node's `recorded_at` was moved by 9,999 seconds and the "
                  "chain still verifies: the timestamp is outside the "
                  "content hash, so WHEN a governance act was recorded can "
                  "be rewritten with a single UPDATE while every "
                  "verification reports the chain intact")


@case("QA-PLT-100", "`contains_personal_data` flipped on a node", isolated=True)
def plt_100(ctx: Ctx) -> Result:
    """The flag decides what a deletion request can reach and what an export
    may carry. If it is outside the content hash, flipping it to false takes
    a node out of scope of L-18 with nothing recording the change."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    _grow(ctx)
    nodes = _nodes(engine)
    if not nodes:
        return BLOCKED, "the chain is empty"
    target = nodes[-1]
    field = next((f for f in ("contains_personal_data", "personal_data")
                  if f in target), "")
    if not field:
        return BLOCKED, f"the node carries no personal-data flag: {sorted(target)}"
    before = engine.content_hash_of(target)
    flipped = {**target, field: not target.get(field)}
    if engine.content_hash_of(flipped) != before:
        return PASS, f"'{field}' is inside the content hash"
    if not _tamper(ctx, target["id"], field,
                   0 if target.get(field) else 1):
        return BLOCKED, "no database handle to tamper with"
    if not engine.verify_chain().get("valid"):
        return PASS, f"flipping '{field}' breaks the chain by another path"
    anchors = engine.verify_against_anchors()
    seen = "" if anchors.get("agrees") else " — though the anchors notice"
    return FAIL, (f"'{field}' was flipped on a node and the chain still "
                  f"verifies{seen}: it sits outside the content hash, so the "
                  f"chain hash does not move and the anchors cannot see it "
                  f"either. The flag decides what a deletion request reaches "
                  f"under L-18 and what an export may carry")


@case("QA-PLT-4760", "`recorded_by` rewritten on a node", isolated=True)
def plt_4760(ctx: Ctx) -> Result:
    """The recorded defect, and the reason the hash covers authorship.
    Segregation of duties is decided entirely by reading `recorded_by` off
    these nodes, so an UPDATE reassigning it turns the control off for that
    subject — and before the fix `verify_chain` went on reporting the chain
    intact."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    _grow(ctx)
    nodes = _nodes(engine)
    if not nodes:
        return BLOCKED, "the chain is empty"
    target = nodes[-1]
    before = engine.content_hash_of(target)
    if engine.content_hash_of({**target, "recorded_by": "somebody-else"}) == before:
        return FAIL, ("`recorded_by` is outside the content hash, so a single "
                      "UPDATE reassigning authorship turns segregation of "
                      "duties off for that subject with the chain still "
                      "verifying")
    if not _tamper(ctx, target["id"], "recorded_by", "somebody-else"):
        return BLOCKED, "no database handle to tamper with"
    report = engine.verify_chain()
    if report.get("valid"):
        return FAIL, ("authorship was rewritten and the chain still verifies")
    if report.get("broken_at") != target.get("seq"):
        return FAIL, (f"the chain broke at {report.get('broken_at')} rather "
                      f"than at the rewritten node {target.get('seq')}")
    return PASS, (f"broken at seq {report.get('broken_at')}: "
                  f"{report.get('reason')}")


@case("QA-PLT-4761", "`trust` re-weighted on a node", isolated=True)
def plt_4761(ctx: Ctx) -> Result:
    """`trust` weights the TRUST semiring, so a silently re-weighted
    valuation is a conclusion nobody can check. It is in the hash for the
    same reason authorship is."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    _grow(ctx)
    nodes = _nodes(engine)
    if not nodes:
        return BLOCKED, "the chain is empty"
    target = nodes[-1]
    before = engine.content_hash_of(target)
    other = 0.5 if (target.get("trust") or 1.0) != 0.5 else 0.25
    if engine.content_hash_of({**target, "trust": other}) == before:
        return FAIL, ("`trust` is outside the content hash, so a valuation "
                      "can be re-weighted with the chain still verifying")
    if not _tamper(ctx, target["id"], "trust", other):
        return BLOCKED, "no database handle to tamper with"
    if engine.verify_chain().get("valid"):
        return FAIL, "trust was re-weighted and the chain still verifies"
    return PASS, "re-weighting trust breaks the chain"


@case("QA-PLT-013",
      "Break a node **before** the checkpoint, then ask the cheap question", isolated=True)
def plt_013(ctx: Ctx) -> Result:
    """The whole risk of a checkpoint. The cheap read starts ABOVE the mark,
    so damage below it is invisible to the question a dashboard asks — which
    is exactly why the mark is corroborated against the anchors before it is
    trusted, and why the full walk still exists."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    _grow(ctx, 4)
    advanced = engine.verify_since_checkpoint(advance=True)
    if not advanced.get("valid"):
        return BLOCKED, f"the chain does not verify to start with: {advanced}"
    mark = engine.checkpoint()
    if not mark or not mark.get("seq"):
        return BLOCKED, "no checkpoint was recorded"
    below = [n for n in _nodes(engine) if (n.get("seq") or 0) < mark["seq"]]
    if not below:
        return BLOCKED, "nothing sits below the checkpoint to damage"
    if not _tamper(ctx, below[0]["id"], "recorded_by", "rewritten"):
        return BLOCKED, "no database handle to tamper with"
    full = engine.verify_chain()
    if full.get("valid"):
        return FAIL, ("a node below the checkpoint was rewritten and the FULL "
                      "walk still reports the chain valid")
    cheap = engine.verify_since_checkpoint(advance=False)
    if not cheap.get("valid"):
        return PASS, ("the cheap read notices damage below the mark as well "
                      "as above it")
    if cheap.get("from_seq", 0) <= below[0]["seq"]:
        return FAIL, (f"the cheap read starts at {cheap.get('from_seq')} and "
                      f"reports valid over a chain broken at "
                      f"{full.get('broken_at')}")
    return PASS, (f"the full walk reports broken at {full.get('broken_at')}; "
                  f"the cheap read starts at {cheap.get('from_seq')} and "
                  f"cannot see below it — which is what the anchors are for")


@case("QA-PLT-018",
      "`verify_since_checkpoint(advance=False)` must write nothing")
def plt_018(ctx: Ctx) -> Result:
    """Loading a page is not a verification run. Only the scheduled job and
    the explicit endpoint move the mark, so a GET never writes — and a
    checkpoint row written on every page load is a table that grows without
    bound and a mark that advances past damage nobody looked for."""
    engine = _engine(ctx)
    if engine is None or engine.checkpoints is None:
        return BLOCKED, "no checkpoint store is wired"
    _grow(ctx)
    before = len(engine.checkpoints.many())
    for _ in range(3):
        engine.verify_since_checkpoint(advance=False)
    after = len(engine.checkpoints.many())
    if after != before:
        return FAIL, (f"three non-advancing reads wrote {after - before} "
                      f"checkpoint row(s)")
    page = ctx.ui.get("/", auth=ctx.people["risk"])
    if page.status_code >= 400:
        return BLOCKED, f"the dashboard answered {page.status_code}"
    if len(engine.checkpoints.many()) != before:
        return FAIL, ("loading the dashboard wrote a checkpoint row, so a "
                      "page view advances the mark past damage nobody looked "
                      "for")
    return PASS, f"three reads and a page load, {before} checkpoint row(s) still"


@case("QA-PLT-022", "Anchor on an empty chain")
def plt_022(ctx: Ctx) -> Result:
    """The recorded defect. `head()` answers an empty chain with
    `(0, GENESIS)` and anchoring sequence 0 wrote a permanent, unsatisfiable
    claim into a write-once store — every later verification then reported
    the chain shorter than its anchor, and it could not be cleared. A control
    whose first act on a fresh instance is to accuse it teaches people to
    clear anchors, which is the one thing that defeats the arrangement."""
    from core.evidence.anchor import AnchorError
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    if engine.anchors is None:
        return BLOCKED, "no anchor root is configured"
    try:
        engine.anchors.anchor(0, "sha256:" + "0" * 64, length=0, actor="qa")
    except AnchorError as exc:
        if getattr(exc, "code", "") != "nothing_to_anchor":
            return FAIL, f"refused '{getattr(exc, 'code', exc)}'"
        return PASS, "refused 'nothing_to_anchor' at sequence 0"
    return FAIL, ("sequence 0 was anchored: the genesis constant is not a "
                  "node, so this is a permanent unsatisfiable claim in a "
                  "write-once store")


@case("QA-PLT-020", "Anchor a head when no anchor root is configured")
def plt_020(ctx: Ctx) -> Result:
    """Reported, not raised, and the detail has to say the chain is
    SELF-CERTIFIED — an instance with no second medium is one where
    `verify_chain` proves nothing against somebody with database access, and
    that has to be visible rather than inferred from a zero."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    was, engine.anchors = engine.anchors, None
    try:
        report = engine.anchor_head(actor="qa")
        verified = engine.verify_against_anchors()
    finally:
        engine.anchors = was
    if report.get("anchored") != 0:
        return FAIL, f"anchoring with no root reports {report.get('anchored')}"
    if "self-certified" not in (report.get("detail") or ""):
        return FAIL, (f"the detail does not say the chain is self-certified: "
                      f"{report.get('detail')}")
    if not verified.get("agrees"):
        return FAIL, ("with no anchors the chain is reported as disagreeing, "
                      "so an instance with no second medium looks compromised")
    if "self-certified" not in (verified.get("detail") or ""):
        return FAIL, (f"the verification does not say why nothing contradicts "
                      f"the chain: {verified.get('detail')}")
    return PASS, "anchored 0, and both readings say self-certified"


@case("QA-PLT-4762", "Anchor the same head twice, then with a different hash", isolated=True)
def plt_4762(ctx: Ctx) -> Result:
    """Re-anchoring the same sequence with the SAME hash is a no-op, which is
    what makes the scheduled job idempotent — running it twice must not be an
    incident. With a DIFFERENT hash it is not a conflict to resolve; it is
    the exact observation the anchor exists to make."""
    from core.evidence.anchor import AnchorError
    engine = _engine(ctx)
    if engine is None or engine.anchors is None:
        return BLOCKED, "no anchor root is configured"
    _grow(ctx)
    first = engine.anchor_head(actor="qa")
    if not first.get("written") and not first.get("seq"):
        return BLOCKED, f"nothing was anchored: {first}"
    again = engine.anchor_head(actor="qa")
    if again.get("written"):
        return FAIL, ("re-anchoring an unchanged head wrote a second record, "
                      "so a nightly job accumulates anchors for one state")
    seq = first.get("seq")
    try:
        engine.anchors.anchor(seq, "sha256:" + "f" * 64, length=1, actor="qa")
    except AnchorError as exc:
        if getattr(exc, "code", "") != "anchor_disagreement":
            return FAIL, f"refused '{getattr(exc, 'code', exc)}'"
        if "incident" not in f"{exc}" and "incident" not in getattr(
                exc, "remediation", ""):
            return FAIL, "the refusal does not say this is a security incident"
        return PASS, (f"same hash is a no-op at seq {seq}; a different one "
                      f"raises 'anchor_disagreement'")
    return FAIL, (f"sequence {seq} was re-anchored with a different hash: the "
                  f"chain has been rewritten behind the anchor and the store "
                  f"took the new value")


@case("QA-PLT-024", "The chain truncated **below** the newest anchor", isolated=True)
def plt_024(ctx: Ctx) -> Result:
    """An append-only chain cannot get shorter, so a chain that no longer
    reaches an anchored sequence is itself the disagreement. Reported rather
    than raised, because a readiness probe has to be able to render it."""
    engine = _engine(ctx)
    if engine is None or engine.anchors is None:
        return BLOCKED, "no anchor root is configured"
    _grow(ctx, 3)
    anchored = engine.anchor_head(actor="qa")
    seq = anchored.get("seq")
    if not seq:
        return BLOCKED, f"nothing was anchored: {anchored}"
    node = engine.repo.one(seq=seq)
    if node is None:
        return BLOCKED, "the anchored node is not readable"
    if not _drop(ctx, node["id"]):
        return BLOCKED, "no database handle to truncate with"
    report = engine.verify_against_anchors()
    if report.get("agrees"):
        return FAIL, (f"the chain was truncated below the anchor at seq {seq} "
                      f"and still agrees with every anchor written")
    broken = report.get("broken") or []
    if not broken:
        return FAIL, "disagreement reported with nothing listed as broken"
    why = broken[0].get("why") or ""
    if "shorter" not in why:
        return FAIL, (f"the disagreement does not say the chain got shorter: "
                      f"{why}")
    return PASS, f"agrees 0, and the reason is: {why[:70]}"


@case("QA-PLT-4763", "The evidence table refuses an UPDATE and a DELETE")
def plt_4763(ctx: Ctx) -> Result:
    """The layer in front of the hash. Every case above has to reach past
    the repository with raw SQL, because `evidence_node` refuses both verbs
    outright — an UPDATE would change a row something downstream has already
    hashed, cited or acted on, and a DELETE would remove evidence somebody
    may already have been shown.

    Worth its own case because it is the control an ordinary defect meets
    first: a service that tried to `set()` on a node would fail loudly rather
    than quietly rewriting history.
    """
    from db.repositories import AppendOnlyViolation
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine is wired"
    _grow(ctx)
    nodes = _nodes(engine)
    if not nodes:
        return BLOCKED, "the chain is empty"
    target = nodes[-1]
    refused = []
    try:
        engine.repo.set({"recorded_by": "x"}, id=target["id"])
    except AppendOnlyViolation as exc:
        refused.append(f"update: {exc}"[:60])
    try:
        engine.repo.remove(id=target["id"])
    except AppendOnlyViolation as exc:
        refused.append(f"delete: {exc}"[:60])
    if len(refused) != 2:
        return FAIL, (f"the evidence table permits "
                      f"{2 - len(refused)} of update and delete through the "
                      f"repository: {refused}")
    if engine.repo.one(id=target["id"]) is None:
        return FAIL, "the refused delete removed the row anyway"
    return PASS, "both verbs refused as AppendOnlyViolation, row intact"
