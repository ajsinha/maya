"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The evidence chain's anchor: chain heads written outside the database.

## The problem this addresses

The chain is hash-linked, so a node cannot be altered without breaking every
link after it — *provided somebody checks*. Verification compared the chain
against itself, and `evidence_checkpoint` is an ordinary table advanced by the
same process that verifies. An attacker with write access to the database
therefore had everything needed: rewrite the nodes, recompute the links, update
the checkpoint. Every subsequent verification passes, continuously, and reports
success.

That is self-consistency, not tamper evidence, and the distinction is the whole
of the control. A chain that certifies itself certifies nothing.

## What an anchor is

A **chain head, written once, to a different medium.** Each anchor is a small
file under the WORM root recording the sequence number, the chain hash at that
point, and when it was taken. Verification then asks a different question:
*does the chain still agree with what was written down before?*

An attacker who rewrites the database must now also rewrite every anchor file.
That is not impossible — see the limits below — but it is a second, separate act
against a second, separate medium, and the two can be given different custody.

## What this is not

**The shipped store is a directory, and a directory is not WORM.** Anyone with
filesystem access as this user can delete or replace an anchor; the read-only
bit stops an accident, not an adversary. What it buys is *separation of medium*:
compromising the database is no longer sufficient on its own.

**This class does not know that.** It writes through `WORMWriter` and reads
through `WORMReader` (`core/ports.py`), so the medium is a deployment decision —
`FilesystemWORM` here, S3 with Object Lock or an append-only volume in a bank
that needs the guarantee enforced rather than conventional. The seam is
deliberate: if the anchor opened files itself, hardening the storage would mean
editing the control, and nobody should have to re-audit a control to change
where it writes.

Genuine tamper evidence also wants an external timestamping authority (RFC 3161)
signing the head with a key nobody here holds. That is not built.

**It cannot see backwards past the first anchor.** Tampering that happened
before an anchor was taken leaves nothing to disagree with. The control begins
when anchoring begins.

Both limits are stated here, in `docs/00 §12`, and on the readiness report,
rather than being left for somebody to discover.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from core.evidence.worm import FilesystemWORM, WormError
from core.log import get_logger

logger = get_logger(__name__)

#: Anchor filenames sort in sequence order, so the newest is the last entry and
#: a directory listing is already the history.
_NAME = "{seq:012d}.anchor"




class AnchorError(RuntimeError):
    """An anchor is missing, unreadable, or disagrees with the chain."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


class ChainAnchor:
    """Writes chain heads to the WORM root, and checks the chain against them."""

    def __init__(self, store=None, evidence=None):
        """`store` satisfies both WORM ports. A path or a string is accepted for
        convenience and wrapped in the filesystem implementation, so callers
        that only want the default do not have to know there is a seam."""
        if store is None or isinstance(store, (str, bytes)) or hasattr(store, "joinpath"):
            store = FilesystemWORM(store) if store is not None else FilesystemWORM()
        self.store = store
        self.evidence = evidence

    @property
    def root(self):
        """Where the store writes, for logs and for the readiness report. Not
        every store has a filesystem root; those report themselves instead."""
        return getattr(self.store, "root", type(self.store).__name__)

    # ------------------------------------------------------------------ write
    def anchor(self, seq: int, chain_hash: str, *, length: Optional[int] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Write one head. Refuses to alter an existing anchor.

        Re-anchoring the same sequence with the **same** hash is a no-op, which
        makes the scheduler job idempotent — running it twice must not be an
        incident.

        Re-anchoring it with a **different** hash is not a conflict to resolve;
        it is the exact observation this exists to make, and it raises.
        """
        # Sequence 0 is the genesis constant, not a node, and no node will ever
        # have it. Anchoring it wrote a permanent, unsatisfiable claim — every
        # later verification reported "the chain is shorter than this anchor"
        # and the store is write-once, so the false alarm could not be cleared.
        #
        # It happened because an anchoring run can start before any evidence
        # exists, and `head()` answers an empty chain with `(0, GENESIS)`. A
        # control whose first act on a fresh instance is to accuse it is worse
        # than no control: whoever sees it learns to clear anchors, and clearing
        # anchors is the one thing that defeats the whole arrangement.
        if seq <= 0:
            raise AnchorError(
                "nothing_to_anchor",
                "sequence 0 is the genesis constant rather than a node, so "
                "there is no chain head to anchor yet",
                "append some evidence first; an empty chain has nothing an "
                "anchor could later contradict")
        name = _NAME.format(seq=seq)
        record = {"seq": seq, "chain_hash": chain_hash, "length": length,
                  "written_at": time.time(), "written_by": actor}

        if self.store.exists(name):
            held = self._read(name)
            if held.get("chain_hash") == chain_hash:
                logger.info("chain already anchored at seq %d; nothing written", seq)
                return {**held, "written": 0}
            logger.error("ANCHOR DISAGREEMENT at seq %d: anchored %s, now %s",
                         seq, held.get("chain_hash"), chain_hash)
            raise AnchorError(
                "anchor_disagreement",
                f"sequence {seq} was anchored with chain hash "
                f"{held.get('chain_hash')} and the chain now reports "
                f"{chain_hash}. The chain has been rewritten behind the anchor",
                "do not advance the checkpoint and do not clear the anchor; "
                "this is a security incident, and the anchor is the evidence")

        self.store.put(name, json.dumps(record, sort_keys=True).encode("utf-8"))
        logger.info("anchored chain head at seq %d (%s) in %s",
                    seq, chain_hash[:19], self.root)
        return {**record, "written": 1}

    # ------------------------------------------------------------------- read
    def anchors(self) -> List[Dict[str, Any]]:
        """Every anchor, oldest first. A listing is the history."""
        return [self._read(name) for name in self.store.names()
                if name.endswith(".anchor")]

    def latest(self) -> Optional[Dict[str, Any]]:
        held = self.anchors()
        return held[-1] if held else None

    def _read(self, name: str) -> Dict[str, Any]:
        try:
            return json.loads(self.store.get(name).decode("utf-8"))
        except (WormError, ValueError, UnicodeDecodeError) as exc:
            logger.error("anchor %s is unreadable: %s", name, exc)
            raise AnchorError(
                "anchor_unreadable",
                f"anchor {name} cannot be read: {exc}",
                "an anchor that cannot be read cannot exonerate the chain; "
                "treat this as tampering until it is explained") from exc

    def corroborates(self, seq: int, chain_hash_at) -> Dict[str, Any]:
        """Do the anchors still vouch for the chain *below* this sequence?

        The question a checkpoint has to survive before anything trusts it.

        `evidence_checkpoint` is an ordinary table in the same database as the
        chain, written by the process that verified it. `verify_since_checkpoint`
        then trusts the mark and checks only what came after — so an attacker
        who can write the database can rewrite history *and* move the mark, and
        the cheap verification, which is the one that runs continuously, reports
        valid forever. That is C-4's third disposition recurring one abstraction
        above where it was written: a chain compared against a mark the same
        process wrote.

        An anchor is in a different medium. If one exists at or below `seq` and
        the chain no longer agrees with it, everything above it — including the
        checkpoint — is standing on rewritten ground, and the checkpoint must be
        discarded rather than believed.

        Reports rather than raises. `corroborated: 0` with no anchors below the
        mark is not a failure; it is *nothing vouches for this yet*, which is a
        different and weaker statement than *something contradicts it*.
        """
        below = [a for a in self.anchors() if a["seq"] <= seq]
        if not below:
            return {"corroborated": 0, "contradicted": 0, "checked": 0,
                    "at_seq": None,
                    "detail": "no anchor has been written at or below this "
                              "checkpoint, so nothing outside the database "
                              "vouches for it — and nothing contradicts it"}
        contradicted = []
        for record in below:
            actual = chain_hash_at(record["seq"])
            if actual != record["chain_hash"]:
                contradicted.append(record["seq"])
        newest = below[-1]
        return {
            "corroborated": int(not contradicted),
            "contradicted": len(contradicted),
            "checked": len(below),
            "at_seq": newest["seq"],
            "detail": (f"{len(below)} anchor(s) at or below seq {seq} still "
                       f"agree with the chain"
                       if not contradicted else
                       f"the chain no longer matches the anchor(s) written at "
                       f"seq {contradicted}, so everything above them — this "
                       f"checkpoint included — is standing on rewritten ground"),
        }

    # ----------------------------------------------------------------- verify
    def verify(self, chain_hash_at) -> Dict[str, Any]:
        """Does the chain still agree with everything written down?

        `chain_hash_at(seq)` returns the chain hash the chain currently reports
        at that sequence, or None if the chain is shorter than the anchor —
        which is itself a disagreement, because a chain is append-only and
        cannot get shorter.

        Reports rather than raises, so a readiness probe can render the state.
        `agrees` being false is a security incident, not a failed check.
        """
        held = self.anchors()
        if not held:
            return {"anchored": 0, "agrees": 1, "checked": 0,
                    "detail": "no anchors written yet, so the chain is "
                              "self-certified and nothing here contradicts it",
                    "since_seq": None}

        broken = []
        for record in held:
            actual = chain_hash_at(record["seq"])
            if actual is None:
                broken.append({"seq": record["seq"], "anchored": record["chain_hash"],
                               "actual": None,
                               "why": "the chain is shorter than this anchor, and "
                                      "an append-only chain cannot get shorter"})
            elif actual != record["chain_hash"]:
                broken.append({"seq": record["seq"], "anchored": record["chain_hash"],
                               "actual": actual,
                               "why": "the chain hash at this sequence has changed "
                                      "since it was anchored"})
        if broken:
            logger.error("chain disagrees with %d of %d anchors; first at seq %s",
                         len(broken), len(held), broken[0]["seq"])
        return {"anchored": len(held), "agrees": 0 if broken else 1,
                "checked": len(held), "broken": broken,
                "since_seq": held[0]["seq"], "head_seq": held[-1]["seq"],
                "detail": ("the chain agrees with every anchor written"
                           if not broken else
                           f"the chain disagrees with {len(broken)} anchor(s)")}
