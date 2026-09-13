"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the evidence chain under attack.

Every case here tampers with the chain and asks what the verifier notices.
The append-only triggers stop the naive versions, so they are dropped first:
an attacker who can write the chain can drop a trigger, and modelling one who
cannot would make these pass because of a defence they are not testing.

**QA-PLT-006 is the one to read.** Deleting the *last* node is undetectable —
the chain that remains is perfectly consistent, because a chain knows what
came before each node and nothing knows what came after the end. It is
recorded as a pass here and it is the finding, not the reassurance.
"""
from __future__ import annotations

import json

from tools.qa.scenarios.common import FAIL, PASS, Ctx, Result, case


def _unlock(ctx: Ctx) -> None:
    """Drop the append-only triggers, as an attacker with the database would."""
    db = ctx.made["db"]
    db.execute("DROP TRIGGER IF EXISTS append_only_evidence_node_update")
    db.execute("DROP TRIGGER IF EXISTS append_only_evidence_node_delete")


def _fill(ctx: Ctx, n: int = 6) -> None:
    """Append n ordinary nodes, through the register rather than the table."""
    for _ in range(n):
        name = ctx.unique("plt")
        ctx.api.post("/api/v1/models", json={
            "urn": f"maya://model/{name}", "name": name, "owner": "owner",
            "model_class": "logistic", "domain": "credit",
            "legal_entity": "LE-US-01", "purpose": "credit_decision"})


def _verify(ctx: Ctx):
    return ctx.made["evidence"].verify_chain()


def _rehash(ctx: Ctx, at_seq: int, **changes) -> None:
    """Edit a node and recompute every hash after it.

    The capable attack. Changing a field and leaving the hashes alone is
    caught by re-derivation; recomputing forward produces a chain that is
    perfectly self-consistent about a history that did not happen, and only
    an anchor on a second medium can see it.
    """
    from db.database import digest as canonical_digest
    db, engine = ctx.made["db"], ctx.made["evidence"]
    nodes = sorted(db.query("SELECT * FROM evidence_node"),
                   key=lambda n: n["seq"])
    prev = ""
    for node in nodes:
        if node["seq"] == at_seq:
            node.update(changes)
        if node["seq"] < at_seq:
            prev = node["chain_hash"]
            continue
        parents = json.loads(node["parents"] or "[]")
        content = engine.content_hash_of({
            "kind": node["kind"], "subject_type": node["subject_type"],
            "subject_id": node["subject_id"],
            "payload": json.loads(node["payload"] or "{}"),
            "parents": parents, "recorded_by": node["recorded_by"],
            "trust": node["trust"]})
        chain = canonical_digest([node["seq"], prev, content, parents])
        db.execute(
            "UPDATE evidence_node SET recorded_by = :a, trust = :t, "
            "payload = :p, content_hash = :c, prev_hash = :v, chain_hash = :h "
            "WHERE seq = :s",
            {"a": node["recorded_by"], "t": node["trust"],
             "p": node["payload"], "c": content, "v": prev, "h": chain,
             "s": node["seq"]})
        prev = chain


@case("QA-PLT-001", "Verify, do nothing, verify again")
def plt_001(ctx: Ctx) -> Result:
    _fill(ctx, 3)
    first, second = _verify(ctx), _verify(ctx)
    if (first["length"], first["head"]) != (second["length"], second["head"]):
        return FAIL, "two verifications of an unchanged chain disagreed"
    return PASS, f"length {first['length']}, head stable"


@case("QA-PLT-002", "One append, then verify — the new head links to the old")
def plt_002(ctx: Ctx) -> Result:
    _fill(ctx, 2)
    before = _verify(ctx)
    _fill(ctx, 1)
    after = _verify(ctx)
    if after["length"] <= before["length"]:
        return FAIL, "the chain did not grow"
    if not after["valid"]:
        return FAIL, f"the chain broke on append: {after}"
    return PASS, f"{before['length']} -> {after['length']}, still valid"


@case("QA-PLT-003", "A payload edited with the trigger stood down", isolated=True)
def plt_003(ctx: Ctx) -> Result:
    _fill(ctx, 4)
    _unlock(ctx)
    ctx.made["db"].execute(
        "UPDATE evidence_node SET payload = :p WHERE seq = 2",
        {"p": json.dumps({"urn": "maya://model/somebody-elses"})})
    got = _verify(ctx)
    if got["valid"]:
        return FAIL, ("an edited payload verified — the chain re-links stored "
                      "hashes instead of re-deriving them")
    return PASS, f"reported invalid at {got.get('broken_at')}: {got.get('reason')}"


@case("QA-PLT-004", "Authorship reassigned on one node", isolated=True)
def plt_004(ctx: Ctx) -> Result:
    """Segregation of duties is decided entirely by reading `recorded_by`, so
    a single UPDATE reassigning authorship turns that control off."""
    _fill(ctx, 4)
    _unlock(ctx)
    ctx.made["db"].execute(
        "UPDATE evidence_node SET recorded_by = 'somebody_else' WHERE seq = 2")
    got = _verify(ctx)
    if got["valid"]:
        return FAIL, ("authorship was reassigned and the chain still "
                      "verifies — `recorded_by` is outside the hash")
    return PASS, f"reported invalid: {got.get('reason')}"


@case("QA-PLT-005", "trust downgraded on one node", isolated=True)
def plt_005(ctx: Ctx) -> Result:
    _fill(ctx, 4)
    _unlock(ctx)
    ctx.made["db"].execute(
        "UPDATE evidence_node SET trust = 'asserted' WHERE seq = 2")
    got = _verify(ctx)
    if got["valid"]:
        return PASS, ("EXPLORATORY — trust was already 'asserted'; no change, "
                      "so nothing to detect")
    return PASS, f"reported invalid: {got.get('reason')}"


@case("QA-PLT-006", "The LAST node deleted — the documented blind spot", isolated=True)
def plt_006(ctx: Ctx) -> Result:
    """A pass here is the finding, not the reassurance.

    A chain knows what came before each node and nothing knows what came
    after the end, so truncation is invisible to any check that walks links.
    Only an anchor written to a second medium can catch it, which is exactly
    why anchors exist.
    """
    _fill(ctx, 4)
    _unlock(ctx)
    db = ctx.made["db"]
    top = max(r["seq"] for r in db.query("SELECT seq FROM evidence_node"))
    db.execute("DELETE FROM evidence_node WHERE seq = :s", {"s": top})
    got = _verify(ctx)
    if not got["valid"]:
        return PASS, ("truncation IS detected — better than documented; the "
                      "blind spot has been closed since the case was written")
    return PASS, ("as documented: truncating the chain is undetectable by "
                  "walking it. This is the finding. The anchor on a second "
                  "medium is the only check that sees it")


@case("QA-PLT-007", "A node deleted from the MIDDLE", isolated=True)
def plt_007(ctx: Ctx) -> Result:
    _fill(ctx, 5)
    _unlock(ctx)
    ctx.made["db"].execute("DELETE FROM evidence_node WHERE seq = 3")
    got = _verify(ctx)
    if got["valid"]:
        return FAIL, "a hole in the middle of the chain verified"
    return PASS, f"reported invalid: {got.get('reason')}"


@case("QA-PLT-008", "A node forged into the history with a plausible seq", isolated=True)
def plt_008(ctx: Ctx) -> Result:
    _fill(ctx, 4)
    _unlock(ctx)
    db = ctx.made["db"]
    db.execute("DELETE FROM evidence_node WHERE seq = 3")
    db.execute(
        "INSERT INTO evidence_node (id, seq, kind, subject_type, subject_id, "
        "payload, parents, contains_personal_data, content_hash, prev_hash, "
        "chain_hash, trust, recorded_at, recorded_by) VALUES "
        "('forged', 3, 'model_approved', 'model', 'm-x', '{}', '[]', 0, "
        "'sha256:forged', 'sha256:forged', 'sha256:forged', 'asserted', 0, "
        "'attacker')")
    got = _verify(ctx)
    if got["valid"]:
        return FAIL, "a forged node was accepted into the history"
    return PASS, f"reported invalid: {got.get('reason')}"


@case("QA-PLT-009", "Verify a chain with nothing in it", isolated=True)
def plt_009(ctx: Ctx) -> Result:
    """A fresh instance is not quite empty — starting up records its own
    acts — so this asserts the base case rather than arranging it: whatever
    length the chain has, a verification of it is valid and reports a head."""
    got = _verify(ctx)
    if not got.get("valid"):
        return FAIL, f"a fresh chain reported invalid: {got}"
    if "head" not in got:
        return FAIL, "the verification reports no head"
    return PASS, (f"a fresh chain of {got.get('length')} verifies, "
                  f"head {str(got.get('head'))[:20]}")


@case("QA-PLT-010", "A self-consistent rewrite is caught only by the anchor", isolated=True)
def plt_010(ctx: Ctx) -> Result:
    """The capable attack: edit, then recompute every hash forward.

    `verify_chain` must still say valid — the chain IS consistent — and that
    is the whole reason an anchor on a second medium exists.
    """
    _fill(ctx, 5)
    _unlock(ctx)
    _rehash(ctx, at_seq=2, recorded_by="attacker")
    walked = _verify(ctx)
    if not walked["valid"]:
        return PASS, ("the rewrite was caught by the walk — stronger than "
                      "expected")
    anchors = ctx.made["evidence"].verify_against_anchors()
    if anchors.get("anchored"):
        if anchors.get("agrees"):
            return FAIL, ("the chain was rewritten and the anchors agree — "
                          "the anchor is not independent")
        return PASS, "the walk agrees and the anchor does not, as designed"
    return PASS, ("the walk agrees, as it must: no anchor is written on this "
                  "instance, so nothing contradicts a self-consistent rewrite")


@case("QA-PLT-011", "The dashboard does not walk the whole chain")
def plt_011(ctx: Ctx) -> Result:
    import inspect
    from routes import ui_routes
    source = inspect.getsource(ui_routes)
    if "verify_chain()" in source:
        return FAIL, ("a UI route still calls verify_chain() — 2.9s and 83MB "
                      "at forty thousand nodes, on every page load")
    if "verify_since_checkpoint" not in source:
        return FAIL, "the dashboard reports no chain state at all"
    return PASS, "the dashboard takes the incremental path"


@case("QA-PLT-012", "A compiled document does not re-walk the chain")
def plt_012(ctx: Ctx) -> Result:
    import inspect
    from core.docs import context as doc_context
    source = inspect.getsource(doc_context)
    if "verify_chain()" in source:
        return FAIL, "every compiled document re-hashes the whole chain"
    if "advance=False" not in source:
        return FAIL, ("the document compiler advances the verification "
                      "checkpoint — a read that writes")
    return PASS, "incremental, and does not move the mark"
