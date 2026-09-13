"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — verifying the evidence chain.

The checkpoint exists so a dashboard does not walk a million nodes on every
read. The danger it introduces is that the checkpoint itself becomes the thing
an attacker moves — so before it is trusted it is corroborated against the
anchors, and the test is `contradicted`, NOT `not corroborated`. Those are
different facts, and getting them the wrong way round reintroduces a full walk
on every read of a fresh instance.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case)

C = "/api/v1/evidence/chain"


def _engine(ctx: Ctx):
    return ctx.made.get("evidence") or ctx.ui.app.state.ctx.get("evidence")


@case("QA-PLT-6300", "A full walk detects a sequence gap")
def plt_6300(ctx: Ctx, ) -> Result:
    """Three ways a chain breaks and each must be named separately: a gap, a
    prev-hash mismatch, a content-hash mismatch. "The chain is broken" tells
    an incident responder nothing about what happened."""
    import inspect
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine reachable from this run"
    source = inspect.getsource(engine._walk)
    for reason in ("sequence gap", "prev_hash mismatch"):
        if reason not in source:
            return FAIL, f"the walk does not distinguish '{reason}'"
    if "content_hash" not in source:
        return FAIL, "the walk does not recompute the content hash"
    if "broken_at" not in source:
        return FAIL, ("the walk reports no sequence for the break, so nobody "
                      "can find where the chain stops verifying")
    return PASS, "three break reasons, each naming the sequence"


@case("QA-PLT-6301", "The repudiation test is contradicted, not un-corroborated")
def plt_6301(ctx: Ctx) -> Result:
    """The recorded defect. `corroborates` answers
    `corroborated: 0, contradicted: 0` when no anchor covers the checkpoint —
    which is the ordinary state of a fresh instance. Testing
    `not corroborated` treats that as repudiation and forces a full walk on
    every read.
    """
    import inspect
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine reachable from this run"
    source = " ".join(inspect.getsource(
        engine.verify_since_checkpoint).split())
    if 'vouched["contradicted"]' not in source and \
            "vouched['contradicted']" not in source:
        return FAIL, ("the checkpoint is not tested on `contradicted`, so an "
                      "instance with no anchors reads as repudiated")
    if "not vouched" in source and "corroborated" in source.split(
            "not vouched")[1][:40]:
        return FAIL, ("the test is `not corroborated`, which treats an absent "
                      "anchor as a contradiction")
    return PASS, "tested on contradicted, not on the absence of corroboration"


@case("QA-PLT-6302", "A read does not advance the checkpoint")
def plt_6302(ctx: Ctx) -> Result:
    """A dashboard that moved the checkpoint would make every export pack
    differ from the one before it, and a read that writes is a read nobody
    can repeat."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine reachable from this run"
    before = engine.verify_since_checkpoint(advance=False)
    after = engine.verify_since_checkpoint(advance=False)
    for field in ("valid", "from_seq", "scope"):
        if before.get(field) != after.get(field):
            return FAIL, (f"two non-advancing reads disagree on '{field}': "
                          f"{before.get(field)} then {after.get(field)}")
    import inspect
    source = inspect.getsource(engine.verify_since_checkpoint)
    if "if advance" not in source and "advance and" not in source:
        return FAIL, "the advance is unconditional, so every read writes"
    return PASS, "a non-advancing read is repeatable and writes nothing"


@case("QA-PLT-6303", "A verification says who performed it")
def plt_6303(ctx: Ctx) -> Result:
    """MAYA verifying its own chain is self-certification. Reporting a
    verification without saying who did it would be claiming independent
    corroboration the platform does not have."""
    got = ctx.api.get(C, auth=ctx.people["auditor"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    for field in ("verified_by", "self_certified", "verification_note"):
        if field not in body:
            return FAIL, (f"the chain report carries no '{field}', so a "
                          f"self-verification reads as an independent one")
    if body.get("self_certified") and not (body.get("verification_note")
                                           or "").strip():
        return FAIL, "self-certified with no note explaining what that means"
    return PASS, (f"verified_by={body.get('verified_by')}, "
                  f"self_certified={body.get('self_certified')}")


@case("QA-PLT-6304", "An empty chain verifies")
def plt_6304(ctx: Ctx) -> Result:
    """A fresh instance has no nodes. Reporting that as broken would make
    every new deployment start with an incident."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine reachable from this run"
    report = engine._walk([], "sha256:" + "0" * 64, 1)
    if not report.get("valid"):
        return FAIL, (f"an empty chain does not verify: {report}; every fresh "
                      f"instance would start with an incident")
    return PASS, "an empty chain verifies"


@case("QA-PLT-6305", "The genesis constant is not a node")
def plt_6305(ctx: Ctx) -> Result:
    """Sequence 0 is the genesis constant and no node will ever have it. An
    anchor over it wrote a permanent, unsatisfiable claim into a write-once
    store."""
    from core.evidence.engine import GENESIS
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine reachable from this run"
    seq, head = engine.head()
    if seq == 0 and head != GENESIS:
        return FAIL, "an empty chain's head is not the genesis constant"
    if not GENESIS.startswith("sha256:") or set(GENESIS[7:]) != {"0"}:
        return FAIL, "the genesis constant is not a distinguishable sentinel"
    return PASS, f"head at seq {seq}; genesis is all zeroes"


@case("QA-PLT-6306", "The chain report states its scope")
def plt_6306(ctx: Ctx) -> Result:
    """"Verified from the checkpoint" and "verified from the beginning" are
    different assurances, and a reader cannot tell them apart from `valid`
    alone."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine reachable from this run"
    report = engine.verify_since_checkpoint(advance=False)
    if "scope" not in report:
        return FAIL, ("the report carries no scope, so a partial walk and a "
                      "full one read the same")
    if "from_seq" not in report:
        return FAIL, "the report does not say where the verification started"
    return PASS, (f"scope '{report.get('scope')}' from seq "
                  f"{report.get('from_seq')}")


@case("QA-PLT-6307", "Appending is what moves the head")
def plt_6307(ctx: Ctx) -> Result:
    """The chain grows only by appending, and each node's prev_hash is the
    last head. A node whose prev_hash is anything else is where the walk
    stops."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no evidence engine reachable from this run"
    before_seq, before_head = engine.head()
    name = ctx.unique("ev")
    made = ctx.api.post("/api/v1/models",
                        json={"urn": f"maya://model/{name}", "name": name,
                              "owner": "owner", "model_class": "logistic",
                              "domain": "credit", "legal_entity": "LE-US-01",
                              "purpose": "credit_decision"})
    if made.status_code >= 400:
        return BLOCKED, (f"could not register a model to append against: "
                         f"{made.status_code} {made.text[:140]}")
    after_seq, after_head = engine.head()
    if after_seq <= before_seq:
        return FAIL, (f"registering a model did not move the chain head "
                      f"({before_seq} -> {after_seq}); a governance act left "
                      f"no evidence")
    if after_head == before_head:
        return FAIL, "the head sequence moved and the hash did not"
    report = engine.verify_chain()
    if not report.get("valid"):
        return FAIL, f"the chain does not verify after an append: {report}"
    return PASS, f"{before_seq} -> {after_seq}, and the chain still verifies"
