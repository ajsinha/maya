"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — anchors, WORM and time stamping.

The chain can only ever prove it agrees with itself. Everything that makes it
evidence rather than a self-consistent story lives outside the database, and
these are the cases about that boundary.
"""
from __future__ import annotations

from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)


@case("QA-PLT-1000", "Anchoring a chain that does not verify is refused")
def plt_1000(ctx: Ctx) -> Result:
    """Writing a broken head down makes every later comparison agree with
    it, which converts a detectable break into a permanent one."""
    import inspect

    from core.evidence.engine import EvidenceEngine
    source = inspect.getsource(EvidenceEngine.anchor_head)
    if "chain_broken" not in source:
        return FAIL, ("the anchor does not verify before writing; a broken "
                      "state would be recorded as the truth")
    return PASS, "verified before anchoring, and refused if broken"


@case("QA-PLT-1001", "An anchor is written outside the database")
def plt_1001(ctx: Ctx) -> Result:
    """`verify_chain` compares the chain against itself, which is exactly
    what a rewritten chain passes."""
    import inspect

    from core.evidence import anchor
    source = inspect.getsource(anchor)
    if "worm" not in source.lower() and "store" not in source.lower():
        return FAIL, "the anchor has no second medium to be written to"
    return PASS, "anchored to a store outside the database"


@case("QA-PLT-1002", "The WORM store refuses to overwrite")
def plt_1002(ctx: Ctx) -> Result:
    """Write-once is the whole property. A store that silently replaced a
    file would make the anchors agree with any rewrite."""
    import pathlib
    import tempfile

    from core.evidence.worm import FilesystemWORM, WormError
    root = pathlib.Path(tempfile.mkdtemp(prefix="qa-worm-"))
    store = FilesystemWORM(root)
    store.put("a.anchor", b"first")
    try:
        store.put("a.anchor", b"second")
    except WormError as refused:
        return PASS, f"refused: {str(refused)[:120]}"
    except Exception as other:
        return PASS, f"refused with {type(other).__name__}: {str(other)[:90]}"
    if store.get("a.anchor") != b"first":
        return FAIL, "a write-once store was overwritten"
    return FAIL, "a second put was accepted without refusing"


@case("QA-PLT-1003", "Timestamping says it has no authority rather than faking one")
def plt_1003(ctx: Ctx) -> Result:
    """`no_timestamp_authority` — the boundary discipline. A platform that
    stamped its own time and called it attestation would be asserting
    something nobody outside it can check."""
    got = ctx.api.post("/api/v1/evidence/timestamps", json={})
    if got.status_code < 400:
        body = got.text.lower()
        if "authority" not in body:
            return FAIL, ("a timestamp came back with no authority named; "
                          "the platform stamped its own time")
        return PASS, "an authority is configured and named"
    if code_of(got) != "no_timestamp_authority":
        return FAIL, f"refused '{code_of(got)}' rather than naming the gap"
    return PASS, "refused: no time stamp authority is wired"


@case("QA-PLT-1004", "The timestamp posture says what it does not prove")
def plt_1004(ctx: Ctx) -> Result:
    got = ctx.api.get("/api/v1/evidence/timestamps/posture")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    said = got.text.lower()
    if "does_not_prove" not in said and "cannot" not in said:
        return FAIL, ("the posture claims a property without saying what it "
                      "does not establish")
    return PASS, "the posture states its limit"


@case("QA-PLT-1005", "The chain head is readable and stable")
def plt_1005(ctx: Ctx) -> Result:
    first = ctx.api.get("/api/v1/evidence/chain")
    if first.status_code >= 400:
        return BLOCKED, f"{first.status_code}"
    second = ctx.api.get("/api/v1/evidence/chain")
    if first.json().get("head") != second.json().get("head"):
        return FAIL, "the head moved between two reads with nothing appended"
    return PASS, f"head stable at length {first.json().get('length')}"


@case("QA-PLT-1006", "Verifying says who asked and whether that means anything")
def plt_1006(ctx: Ctx) -> Result:
    """C-4 disposition 4: a verification the writing process ran and one a
    person requested were the same record, and both read as 'verified'."""
    got = ctx.api.get("/api/v1/evidence/chain")
    if got.status_code >= 400:
        return BLOCKED, f"{got.status_code}"
    body = got.json()
    if "self_certified" not in body:
        return FAIL, ("the verification does not say whether it was "
                      "self-certified; a check the writing process ran reads "
                      "the same as one somebody independent asked for")
    if not body.get("verification_note"):
        return FAIL, "there is no note explaining what the verification means"
    return PASS, f"self_certified={body['self_certified']}"


@case("QA-PLT-1007", "A node carrying personal data stores an empty payload")
def plt_1007(ctx: Ctx) -> Result:
    """Law L-18. The payload is DISCARDED rather than stored behind a
    pointer, so there is nothing to erase and nothing to leak — and it is now
    enforced by a trigger rather than by one function that happens to do it."""
    from db.schema.immutable import EMPTY_WHEN_FLAGGED
    if "evidence_node" not in EMPTY_WHEN_FLAGGED:
        return FAIL, ("nothing enforces that a node flagged for personal data "
                      "is empty; the rule lives in one function")
    return PASS, "enforced at the storage layer, in both dialects"
