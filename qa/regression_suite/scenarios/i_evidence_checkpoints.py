"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the checkpoint, and the cheap question it makes possible.

Walking and re-hashing the whole chain on every readiness probe was 2.9 seconds
and 83 MB at forty thousand nodes, so the probe asks a narrower question: **has
anything broken SINCE the last full verification.** That trade is only honest
if three things hold.

The full walk has to actually happen, on a cadence somebody chose rather than
when somebody remembers. The mark must never advance past a break, because a
checkpoint beyond the damage makes every later cheap check start after it and
report health. And the mark itself has to be standing on something — a
checkpoint the anchors contradict is worse than no checkpoint at all, because
it makes the cheap check report valid forever over a chain somebody rewrote.

What the cheap question cannot see is everything at or below the mark. That is
the design, and these cases are about whether the platform says so.
"""
from __future__ import annotations

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
        name = ctx.unique("ev")
        ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                              "owner": "owner", **SHAPE},
                     auth=ctx.people["owner"])


def _past_the_trigger(db, statement: str, params: dict) -> None:
    """Tamper the way the threat model says it arrives.

    The append-only triggers refuse an UPDATE and a DELETE, which is the guard
    working. `docs/11 §4.1` is explicit that the threat is not an attacker
    breaking in — it is anybody handed production database credentials during
    an incident, and that person can drop a trigger. The chain is what answers
    past that point, so a case about the chain has to get there.
    """
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


@case("QA-PLT-104", "A broken chain's report shape",
      isolated=True)
def plt_104(ctx: Ctx) -> Result:
    """A broken report carries `broken_at` and `reason`, and carries no
    `length`, `head` or `scope`. Those describe a chain that verified; a
    report that carried them alongside a break would let a reader take the
    length of a chain nobody walked past node forty."""
    evidence = _evidence(ctx)
    db = ctx.ui.app.state.ctx.get("db")
    if evidence is None or db is None:
        return BLOCKED, "no evidence chain is wired"
    _acts(ctx)
    clean = evidence.verify_chain()
    if not clean["valid"]:
        return BLOCKED, f"the chain was already broken: {clean}"
    for key in ("length", "head", "scope"):
        if key not in clean:
            return FAIL, f"a VALID report carries no '{key}': {sorted(clean)}"
    last = db.query("SELECT seq FROM evidence_node ORDER BY seq DESC LIMIT 1")
    db.execute(
        "INSERT INTO evidence_node (id, seq, kind, subject_type, subject_id, "
        "payload, parents, contains_personal_data, content_hash, prev_hash, "
        "chain_hash, trust, recorded_at, recorded_by) VALUES "
        "(:i, :s, 'qa_break', 'model', 'qa', '{}', '[]', 0, :c, :p, :c, 1.0, "
        "0.0, 'qa')",
        {"i": "qa-shape-break", "s": last[0]["seq"] + 1,
         "c": "sha256:" + "0" * 64, "p": "sha256:" + "1" * 64})
    broken = evidence.verify_chain()
    if broken["valid"]:
        return BLOCKED, "the inserted node did not break the chain"
    if "broken_at" not in broken or "reason" not in broken:
        return FAIL, f"the broken report names neither where nor why: {broken}"
    leaked = [k for k in ("length", "head", "scope") if k in broken]
    if leaked:
        return FAIL, (f"a broken report still carries {leaked} — figures that "
                      f"describe a chain that verified, offered beside one "
                      f"that did not: {broken}")
    return PASS, (f"broken_at {broken['broken_at']}, reason "
                  f"{broken['reason']!r}, and no length, head or scope")


@case("QA-PLT-105", "The scheduled verification meets a broken chain",
      isolated=True)
def plt_105(ctx: Ctx) -> Result:
    """`verified: false`, and the checkpoint is NOT advanced. Advancing it
    past a break would bless the break, and every cheap check afterwards
    would start beyond the damage and report health."""
    from core.scheduler.jobs import JobContext, verify_evidence_chain
    evidence = _evidence(ctx)
    db = ctx.ui.app.state.ctx.get("db")
    if evidence is None or db is None:
        return BLOCKED, "no evidence chain is wired"
    _acts(ctx)
    first = verify_evidence_chain(JobContext(registry=ctx.ui.app.state.ctx["registry"], now=time.time(), evidence=evidence, actor="qa"))
    if not first.get("verified"):
        return BLOCKED, f"the chain was already broken: {first}"
    mark = evidence.checkpoint()
    if mark is None:
        return BLOCKED, "the job recorded no checkpoint"
    last = db.query("SELECT seq FROM evidence_node ORDER BY seq DESC LIMIT 1")
    db.execute(
        "INSERT INTO evidence_node (id, seq, kind, subject_type, subject_id, "
        "payload, parents, contains_personal_data, content_hash, prev_hash, "
        "chain_hash, trust, recorded_at, recorded_by) VALUES "
        "(:i, :s, 'qa_break', 'model', 'qa', '{}', '[]', 0, :c, :p, :c, 1.0, "
        "0.0, 'qa')",
        {"i": "qa-job-break", "s": last[0]["seq"] + 1,
         "c": "sha256:" + "0" * 64, "p": "sha256:" + "1" * 64})
    after = verify_evidence_chain(JobContext(registry=ctx.ui.app.state.ctx["registry"], now=time.time(), evidence=evidence, actor="qa"))
    if after.get("verified"):
        return FAIL, f"the job reports a broken chain as verified: {after}"
    moved = evidence.checkpoint()
    if moved["seq"] != mark["seq"]:
        return FAIL, (f"the checkpoint advanced from {mark['seq']} to "
                      f"{moved['seq']} over a broken chain, so every cheap "
                      f"check now starts past the damage")
    if "NOT advanced" not in (after.get("detail") or ""):
        return FAIL, f"the job does not say it withheld the mark: {after}"
    if after.get("broken_at") is None:
        return FAIL, "the job does not say where the break is"
    return PASS, (f"verified false at seq {after['broken_at']}, checkpoint "
                  f"held at {mark['seq']}")


@case("QA-PLT-015", "The node at the checkpoint sequence is the one mutated",
      isolated=True)
def plt_015(ctx: Ctx) -> Result:
    """The cheap question is `seq > mark`, so the node AT the mark is the one
    place the incremental walk can never look. That is the design; the
    finding, if there is one, is whether the answer says which question it
    answered."""
    evidence = _evidence(ctx)
    db = ctx.ui.app.state.ctx.get("db")
    if evidence is None or db is None:
        return BLOCKED, "no evidence chain is wired"
    _acts(ctx)
    full = evidence.verify_since_checkpoint(advance=True, actor="qa")
    if not full["valid"]:
        return BLOCKED, f"the chain was already broken: {full}"
    mark = evidence.checkpoint()
    if mark is None:
        return BLOCKED, "no checkpoint was recorded"
    _acts(ctx, 2)
    row = db.query("SELECT id FROM evidence_node WHERE seq = :s",
                   {"s": mark["seq"]})
    if not row:
        return BLOCKED, f"no node sits at the mark seq {mark['seq']}"
    _past_the_trigger(
        db, "UPDATE evidence_node SET recorded_by = 'somebody else' "
            "WHERE id = :i", {"i": row[0]["id"]})
    cheap = evidence.verify_since_checkpoint(advance=False, actor="qa")
    deep = evidence.verify_chain()
    if deep["valid"]:
        return BLOCKED, ("the full walk does not see the mutation either, so "
                         "this case cannot contrast the two")
    if not cheap["valid"]:
        return PASS, (f"the incremental walk sees it too: "
                      f"{cheap.get('reason')}")
    if cheap.get("scope") != "incremental":
        return BLOCKED, f"the cheap check ran a {cheap.get('scope')} walk"
    if cheap.get("from_seq") != mark["seq"]:
        return FAIL, (f"the answer says it started from "
                      f"{cheap.get('from_seq')} rather than the mark "
                      f"{mark['seq']}")
    return PASS, (
        f"the node at seq {mark['seq']} was rewritten; the full walk breaks at "
        f"{deep.get('broken_at')} and the incremental walk answers valid — "
        f"correctly, because it asks a narrower question and SAYS SO: "
        f"scope={cheap['scope']!r} from_seq={cheap['from_seq']} over "
        f"{cheap.get('checked')} node(s). A reader taking that as 'the chain "
        f"is intact' is reading a field that is not there")


@case("QA-PLT-014", "The checkpoint ahead of the head",
      isolated=True)
def plt_014(ctx: Ctx) -> Result:
    """A mark beyond the end of the chain. `repo.since(mark)` returns
    nothing, the incremental walk has nothing to disagree with, and the
    answer is valid over a chain that has been truncated below it."""
    evidence = _evidence(ctx)
    db = ctx.ui.app.state.ctx.get("db")
    if evidence is None or db is None:
        return BLOCKED, "no evidence chain is wired"
    _acts(ctx)
    evidence.verify_since_checkpoint(advance=True, actor="qa")
    mark = evidence.checkpoint()
    if mark is None:
        return BLOCKED, "no checkpoint was recorded"
    evidence.checkpoints.set({"seq": mark["seq"] + 500}, id=mark["id"])
    cheap = evidence.verify_since_checkpoint(advance=False, actor="qa")
    if not cheap["valid"]:
        return PASS, (f"a mark beyond the head is refused or reported broken: "
                      f"{cheap.get('reason')}")
    if cheap.get("scope") != "incremental":
        return PASS, (f"a mark beyond the head falls back to a "
                      f"{cheap.get('scope')} walk")
    return FAIL, (
        f"the checkpoint was moved to seq {mark['seq'] + 500}, five hundred "
        f"beyond a chain that ends at {evidence.head()[0]}, and the cheap "
        f"check answers valid over {cheap.get('checked')} node(s) checked. "
        f"`repo.since(mark)` returns nothing, `_walk` over an empty list "
        f"reports valid, and nothing compares the mark against the head — so a "
        f"chain truncated below its own checkpoint reads healthy on every "
        f"readiness probe until the scheduled full walk runs")


@case("QA-PLT-016", "The first checkpoint records `length`, not the head sequence",
      isolated=True)
def plt_016(ctx: Ctx) -> Result:
    """Both places that record a checkpoint after a full walk pass
    `report["length"]` as the sequence. Those are the same number only while
    the chain is contiguous from one — which is exactly what compaction and
    any pruned restore stop being true."""
    import inspect

    from core.evidence.engine import EvidenceEngine
    from core.scheduler import jobs
    evidence = _evidence(ctx)
    db = ctx.ui.app.state.ctx.get("db")
    if evidence is None or db is None:
        return BLOCKED, "no evidence chain is wired"
    writers = []
    for where, source in (("engine", inspect.getsource(
            EvidenceEngine.verify_since_checkpoint)),
            ("scheduler", inspect.getsource(jobs.verify_evidence_chain))):
        if '_record_checkpoint(report["length"]' in source:
            writers.append(where)
    if not writers:
        return PASS, "the checkpoint is recorded from the head sequence"
    _acts(ctx)
    evidence.verify_since_checkpoint(advance=True, actor="qa")
    mark = evidence.checkpoint()
    head_seq, _ = evidence.head()
    length = len(evidence.repo.many())
    if mark["seq"] == head_seq and head_seq == length:
        # Contiguous from 1, so the two agree. Show that they are the same
        # number by accident rather than by construction.
        db.execute("DELETE FROM evidence_node WHERE seq = :s", {"s": 1}) \
            if False else None
        return FAIL, (
            f"both {writers} record the checkpoint as `report['length']` "
            f"({length}) rather than the head sequence ({head_seq}). They "
            f"agree here only because this chain is contiguous from 1. After "
            f"any restore or compaction that leaves the chain starting above "
            f"1, the mark lands below the head, `repo.since(mark)` re-walks "
            f"nodes already verified against the WRONG prev_hash, and the next "
            f"incremental check reports a break in a chain nobody touched — "
            f"`chain_broken` on a healthy register")
    return FAIL, (f"the mark is {mark['seq']}, the head is {head_seq} and the "
                  f"length is {length}: the mark follows the length")


@case("QA-PLT-017", "Checkpoint rows accumulate and none is ever retired",
      isolated=True)
def plt_017(ctx: Ctx) -> Result:
    """The readiness probe no longer advances the mark — `advance=False`,
    because an unauthenticated status probe must not be able to move a
    verification checkpoint. The row growth is still there on the scheduled
    path, and nothing retires an old one."""
    import inspect

    from core.evidence.engine import EvidenceEngine
    from routes.public_routes import PublicRoutes
    probe = inspect.getsource(PublicRoutes.register)
    if "advance=False" not in probe:
        return FAIL, ("the readiness probe advances the verification "
                      "checkpoint, so an unauthenticated caller moves it")
    evidence = _evidence(ctx)
    if evidence is None or evidence.checkpoints is None:
        return BLOCKED, "no checkpoint register is wired"
    source = inspect.getsource(EvidenceEngine)
    if "checkpoints.remove" in source or "prune" in source:
        return PASS, "old checkpoints are retired"
    before = len(evidence.checkpoints.many())
    for _ in range(12):
        _acts(ctx, 1)
        evidence.verify_since_checkpoint(advance=True, actor="qa")
    after = len(evidence.checkpoints.many())
    if after <= before:
        return PASS, f"the register did not grow: {before} → {after}"
    return FAIL, (
        f"twelve verifications wrote {after - before} checkpoint row(s) "
        f"({before} → {after}) and nothing in `EvidenceEngine` removes one. "
        f"Only `first('seq', desc=True)` is ever read, so every row but the "
        f"newest is dead weight that grows at the scheduled cadence for the "
        f"life of the deployment — on a register whose stated position is that "
        f"nothing is deleted, in a table that is not the evidence chain and "
        f"carries no evidentiary value")


@case("QA-PLT-019", "Verify, restore a backup taken before that verification",
      isolated=True)
def plt_019(ctx: Ctx) -> Result:
    """A restore rolls the chain back and leaves the checkpoint where it
    was. The mark then names a sequence the chain no longer reaches, which
    is QA-PLT-014 arriving through the one operation a bank actually
    performs."""
    evidence = _evidence(ctx)
    db = ctx.ui.app.state.ctx.get("db")
    if evidence is None or db is None:
        return BLOCKED, "no evidence chain is wired"
    _acts(ctx, 2)
    evidence.verify_since_checkpoint(advance=True, actor="qa")
    mark = evidence.checkpoint()
    if mark is None:
        return BLOCKED, "no checkpoint was recorded"
    _acts(ctx, 3)
    evidence.verify_since_checkpoint(advance=True, actor="qa")
    newer = evidence.checkpoint()
    if newer["seq"] <= mark["seq"]:
        return BLOCKED, "the second verification did not advance the mark"
    # The restore: the chain goes back to where it was, the checkpoint table
    # does not, because a backup of one is not a backup of the other unless
    # somebody took them together.
    _past_the_trigger(db, "DELETE FROM evidence_node WHERE seq > :s",
                      {"s": mark["seq"]})
    cheap = evidence.verify_since_checkpoint(advance=False, actor="qa")
    head_seq, _ = evidence.head()
    if not cheap["valid"]:
        return PASS, (f"the restored chain is reported broken against the "
                      f"newer mark: {cheap.get('reason')}")
    if cheap.get("scope") == "full":
        return PASS, "a mark the chain cannot reach falls back to a full walk"
    return FAIL, (
        f"the chain was restored to seq {head_seq} and the checkpoint still "
        f"reads {newer['seq']}, three ahead of it. The cheap check answers "
        f"valid over {cheap.get('checked')} node(s) — `since(mark)` finds "
        f"nothing past a mark the chain no longer reaches, and nothing "
        f"compares the two. A restore is the one operation that produces this "
        f"state and the one nobody re-verifies afterwards")


@case("QA-PLT-010", "Two full verifications running at once",
      isolated=True)
def plt_010(ctx: Ctx) -> Result:
    """Both valid, neither blocking the other. A read that took a write lock
    would make the dashboard and the readiness probe contend with the
    register on every load."""
    from concurrent.futures import ThreadPoolExecutor
    evidence = _evidence(ctx)
    if evidence is None:
        return BLOCKED, "no evidence chain is wired"
    _acts(ctx, 4)
    if not evidence.verify_chain()["valid"]:
        return BLOCKED, "the chain is already broken"
    out = []

    def walk(_n):
        try:
            out.append(evidence.verify_chain())
        except Exception as exc:
            out.append({"valid": False, "raised": f"{type(exc).__name__}: {exc}"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(walk, range(2)))
    raised = [r for r in out if r.get("raised")]
    if raised:
        return FAIL, f"a concurrent verification raised: {raised[0]['raised']}"
    if not all(r.get("valid") for r in out):
        return FAIL, f"a concurrent verification reported broken: {out}"
    heads = {r.get("head") for r in out}
    if len(heads) != 1:
        return FAIL, f"the two walks disagree about the head: {heads}"
    return PASS, (f"two full walks, both valid, one head "
                  f"{next(iter(heads))[:20]}")


# -------------------------------------------------------------- the semirings
@case("QA-PLT-102", "The `WHY` semiring past its term cap")
def plt_102(ctx: Ctx) -> Result:
    """Degrade explicitly rather than answer partially. A provenance answer
    that quietly dropped support sets would be a minimal-support claim that
    is neither minimal nor complete, and nothing about it would look wrong.

    The cap is exercised against a LOWERED bound rather than the shipped
    one: `_why_plus` runs an absorption pass over the whole set on every
    addition, so reaching 4,096 support sets is cubic and would take this
    case minutes to prove something the same code path proves in
    milliseconds. The shipped value is asserted separately."""
    from core.evidence import engine as module
    from core.evidence.engine import Derivation
    from core.evidence.semirings import MAX_TERMS, WHY
    if MAX_TERMS != 4096:
        return FAIL, f"the shipped cap is {MAX_TERMS}, not 4,096"
    evidence = _evidence(ctx)
    if evidence is None:
        return BLOCKED, "no evidence chain is wired"
    facts = [f"fact-{i}" for i in range(40)]
    derivations = {"claim": Derivation("claim", [[f] for f in facts])}
    under = evidence.evaluate("claim", derivations, WHY,
                              evidence.why_valuation())
    if under.truncated:
        return FAIL, (f"40 alternatives truncated against a cap of "
                      f"{MAX_TERMS}")
    real = module.MAX_TERMS
    module.MAX_TERMS = 8
    try:
        over = evidence.evaluate("claim", derivations, WHY,
                                 evidence.why_valuation())
    finally:
        module.MAX_TERMS = real
    if not over.truncated:
        return FAIL, (f"40 alternatives produced {len(over.value)} support "
                      f"set(s) against a cap of 8 and `truncated` is false — "
                      f"the guard in `evaluate` did not fire, so a partial "
                      f"provenance answer is offered as a complete one")
    if len(over.value) > len(under.value):
        return FAIL, "the truncated answer carries more than the full one"
    return PASS, (f"under the cap: {len(under.value)} support set(s), "
                  f"truncated={under.truncated}; over it: "
                  f"{len(over.value)}, truncated={over.truncated}. The shipped "
                  f"bound is {MAX_TERMS}")


@case("QA-PLT-103", "A claim resting on a missing fact under freshness")
def plt_103(ctx: Ctx) -> Result:
    """`FRESHNESS` is (max, max) with zero for both identities, so an absent
    fact contributes 0.0 and `max` ignores it. The number that comes back is
    the freshness of what is PRESENT, and a reader taking it as the
    freshness of the claim is reading past a hole."""
    from core.evidence.semirings import FRESHNESS
    evidence = _evidence(ctx)
    if evidence is None:
        return BLOCKED, "no evidence chain is wired"
    from core.evidence.engine import Derivation
    ages = {"recent": 1000.0, "old": 10.0}
    derivations = {"claim": Derivation("claim", [["recent", "missing"]])}
    out = evidence.evaluate("claim", derivations, FRESHNESS,
                            lambda k: ages.get(k, FRESHNESS.zero))
    both = evidence.evaluate(
        "claim", {"claim": Derivation("claim", [["recent", "old"]])},
        FRESHNESS, lambda k: ages.get(k, FRESHNESS.zero))
    if out.value != both.value:
        return PASS, (f"a missing fact changes the answer: {out.value} against "
                      f"{both.value} when it is present and stale")
    return FAIL, (
        f"a claim resting on a present fact and a MISSING one answers "
        f"freshness {out.value}, the same as one resting on that fact and a "
        f"stale one. FRESHNESS is (max, max) with `zero = 0.0`, so an absent "
        f"fact contributes 0.0 and `max` discards it — the answer is the "
        f"freshness of what is present, and carries nothing saying a term was "
        f"absent. The Boolean semiring answers the presence question; a reader "
        f"who asks only this one is told how fresh the evidence is without "
        f"being told some of it is not there")


@case("QA-PLT-101", "A node recorded with `contains_personal_data`")
def plt_101(ctx: Ctx) -> Result:
    """The payload was never stored, which is what makes an erasure request
    answerable on an append-only chain. Read back, it must be empty AND say
    why — an empty payload with no explanation reads as a write that failed."""
    evidence = _evidence(ctx)
    if evidence is None:
        return BLOCKED, "no evidence chain is wired"
    with evidence.recording():
        node = evidence.append("qa_personal", "model", "qa-personal-subject",
                               {"name": "a real person", "nino": "QQ123456C"},
                               actor="qa", personal_data=True)
    back = evidence.repo.one(id=node["id"])
    if back is None:
        return BLOCKED, "the node was not stored at all"
    payload = back.get("payload")
    if payload:
        return FAIL, (f"a node flagged `contains_personal_data` stored its "
                      f"payload anyway: {payload}")
    if not back.get("contains_personal_data"):
        return FAIL, "the flag itself was not kept, so nothing says why it is empty"
    chain = evidence.verify_chain()
    if not chain["valid"]:
        return FAIL, ("recording a personal-data node broke the chain: "
                      f"{chain.get('reason')}")
    return PASS, ("the payload is empty, the flag is kept, and the chain still "
                  "verifies over the node")
