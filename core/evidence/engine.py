"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The evidence engine: an append-only, hash-chained record with semiring
evaluation over the derivation DAG.

The DAG says what supports what; the linear seq/prev_hash chain makes deletion
of a leaf and insertion into the past detectable.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import (Any, Callable, Dict, List, Optional, Sequence,
                    Set, Tuple)

from core.evidence.anchor import AnchorError
from core.evidence.semirings import (WHY, MAX_TERMS, Semiring)
from sqlalchemy.exc import IntegrityError

from core.log import get_logger, swallowed
from db import EvidenceRepository
from db.database import digest as canonical_digest

logger = get_logger(__name__)

GENESIS = "sha256:" + "0" * 64


@dataclass
class Derivation:
    """A claim: a disjunction of conjunctions over evidence identifiers."""
    key: str
    alternatives: Tuple[Tuple[str, ...], ...] = ()      # OR of ANDs

    @property
    def is_leaf(self) -> bool:
        return not self.alternatives


@dataclass
class EvaluationResult:
    value: Any
    truncated: bool = False


# How many times an append re-reads the head before giving up. Contention is on
# one integer, so a handful of attempts covers far more concurrency than a
# governance platform will ever see; the cap exists so a genuine defect surfaces
# as a failure rather than as a hang.
APPEND_ATTEMPTS = 12
# Base for a jittered backoff between attempts. Small, because the contention is
# on one integer and the winner commits immediately.
BACKOFF_SECONDS = 0.01


class EvidenceEngine:
    """Append-only, hash-chained evidence with semiring evaluation over it."""

    def __init__(self, repo: EvidenceRepository, checkpoints=None, anchors=None):
        self.repo = repo
        # Optional. Without one, verification is always the full walk, which is
        # correct and slow; with one, readiness can ask the cheap question.
        self.checkpoints = checkpoints
        # Optional, and the only verification an attacker holding the database
        # cannot satisfy: heads written to a second medium, compared back. Absent
        # one, the chain is self-certified and `verify_against_anchors` says so
        # rather than reporting a pass.
        self.anchors = anchors

    # -------------------------------------------------------------- append
    def head(self) -> Tuple[int, str]:
        row = self.repo.first("seq", desc=True)
        return (row["seq"], row["chain_hash"]) if row else (0, GENESIS)

    def append(self, kind: str, subject_type: str, subject_id: str,
               payload: Optional[Dict[str, Any]] = None, parents: Optional[List[str]] = None,
               *, personal_data: bool = False, trust: float = 1.0,
               actor: str = "system") -> Dict[str, Any]:
        # The chain is a read-then-write -- take the head, insert head+1 -- and
        # that was neither atomic nor retried. Every statement opened its own
        # transaction, so two concurrent governance acts read the same head and
        # the loser hit the UNIQUE on `seq`. Measured at four threads: 7% of
        # appends raised, and every service commits its own row BEFORE appending
        # evidence, so the model existed and the record of its registration did
        # not. Twenty-four concurrent registrations produced twenty-four models
        # and fourteen evidence nodes.
        #
        # The consequence was worse than a missing row. Segregation of duties is
        # decided by reading the chain, so a lost `version_created` node did not
        # fail closed -- it meant "you cannot approve what you created" had
        # nothing to read, and the developer could approve their own version.
        #
        # Atomic AND serialised now. Atomic alone was not enough: a deferred
        # transaction reads the head without holding the write lock, so two
        # writers still read the same one and the loser died on the UNIQUE. The
        # retry below covered that until a loaded machine made four writers
        # exhaust all twelve attempts, and an append was lost after all —
        # exactly the outcome the retry existed to prevent, reached more slowly.
        #
        # `serialise="evidence_seq"` takes the write lock at BEGIN, before the
        # read, so the second writer waits and then reads a head that is current.
        # The retry stays for the case the lock does not cover: another PROCESS
        # against the same file, where SQLite's lock is held by a connection this
        # one cannot see.
        for attempt in range(APPEND_ATTEMPTS):
            try:
                with self.repo.db.transaction(serialise="evidence_seq"):
                    return self._append(kind, subject_type, subject_id, payload,
                                        parents, personal_data=personal_data,
                                        trust=trust, actor=actor)
            except IntegrityError as exc:
                # Back off before re-reading the head. Without this every loser
                # retries at the same instant and collides again, so eight
                # threads exhaust eight attempts without any of them making
                # progress -- the retry was there and the contention pattern
                # defeated it. Jittered, so the retries spread rather than
                # marching in step.
                time.sleep(random.uniform(0, BACKOFF_SECONDS * (attempt + 1)))
                if attempt == APPEND_ATTEMPTS - 1:
                    logger.error("evidence append lost the sequence race %d "
                                 "times for %s/%s; giving up",
                                 APPEND_ATTEMPTS, subject_type, subject_id)
                    raise
                swallowed(logger, exc, "appended to the evidence chain",
                          detail=f"another writer took sequence first; "
                                 f"retrying ({attempt + 1}/{APPEND_ATTEMPTS})",
                          level=logging.DEBUG)

    def _append(self, kind: str, subject_type: str, subject_id: str,
                payload: Optional[Dict[str, Any]] = None,
                parents: Optional[List[str]] = None,
                *, personal_data: bool = False, trust: float = 1.0,
                actor: str = "system") -> Dict[str, Any]:
        """One attempt, inside a transaction the caller opened."""
        payload, parents = payload or {}, sorted(parents or [])
        # Hashed over what is STORED, not over what was passed: a node carrying
        # personal data stores an empty payload (law L-18), and hashing the
        # original would make every such node fail its own verification.
        stored_payload = {} if personal_data else payload
        content_hash = self.content_hash_of(
            {"kind": kind, "subject_type": subject_type, "subject_id": subject_id,
             "payload": stored_payload, "parents": parents,
             "recorded_by": actor, "trust": trust})
        prev_seq, prev_hash = self.head()
        seq = prev_seq + 1
        node = {
            "seq": seq, "kind": kind,
            "subject_type": subject_type, "subject_id": subject_id,
            # Law L-18. The payload is DISCARDED, not replaced by a pointer:
            # there is no `payload_uri` column, no per-subject key and no shred
            # path anywhere in this repository. Several documents said "an
            # erasable pointer", which describes a design nobody built and reads
            # as though the data is still retrievable under authority.
            #
            # Discarding is the stronger guarantee for the law as stated — there
            # is nothing to erase, so nothing to leak — and the weaker one for
            # anybody who expected to resolve it later. Saying which is which
            # matters more than either.
            "payload": stored_payload,
            "parents": parents, "contains_personal_data": personal_data,
            "content_hash": content_hash, "prev_hash": prev_hash,
            "chain_hash": canonical_digest([seq, prev_hash, content_hash, parents]),
            "trust": trust, "recorded_at": time.time(), "recorded_by": actor,
        }
        return self.repo.add(node)

    @staticmethod
    def content_hash_of(node: Dict[str, Any]) -> str:
        """The digest a node's own fields imply. One definition, two callers.

        ``append`` and ``verify_chain`` must agree exactly, and the only way to
        guarantee that is for there to be one expression of it.
        """
        return canonical_digest({
            "kind": node["kind"],
            "subject": [node["subject_type"], node["subject_id"]],
            "payload": node.get("payload") or {},
            "parents": node.get("parents") or [],
            # WHO did it, and how much the platform believes them, are part of
            # what the chain attests. They were not, and the omission was worse
            # than it sounds: segregation of duties is decided entirely by
            # reading `recorded_by` off these nodes, so a single UPDATE
            # reassigning authorship turned the control off for that subject
            # while verify_chain went on reporting the chain intact. `trust` is
            # here for the same reason -- it weights the TRUST semiring, and a
            # silently re-weighted valuation is a conclusion nobody can check.
            "recorded_by": node.get("recorded_by"),
            "trust": node.get("trust")})

    # ------------------------------------------------------------- checkpoint
    def checkpoint(self) -> Optional[Dict[str, Any]]:
        """How far the chain has been verified, if anybody has recorded it."""
        if self.checkpoints is None:
            return None
        return self.checkpoints.first("seq", desc=True)

    def chain_hash_at(self, seq: int) -> Optional[str]:
        """The chain hash the chain currently reports at that sequence.

        Read for anchor verification (`core/evidence/anchor.py`), which asks a
        question the chain cannot ask of itself: does it still agree with what
        was written down elsewhere, before?
        """
        node = self.repo.one(seq=seq)
        return node.get("chain_hash") if node else None

    def anchor_head(self, actor: str = "system") -> Dict[str, Any]:
        """Write the current head to the anchor root, if there is one wired.

        Verifies before anchoring. Anchoring a chain that is already broken
        would write down the broken state as though it were the truth, and
        every later comparison would then agree with it.
        """
        if self.anchors is None:
            return {"anchored": 0,
                    "detail": "no anchor root is configured, so the chain is "
                              "self-certified"}
        report = self.verify_chain()
        if not report["valid"]:
            logger.error("refusing to anchor a chain that does not verify: %s",
                         report.get("detail") or report)
            raise AnchorError(
                "chain_broken",
                "the chain does not verify, so anchoring its head would write "
                "the broken state down as the truth",
                "do not anchor; this is a security incident and the last good "
                "anchor is the evidence")
        seq, head = self.head()
        if seq <= 0:
            # An empty chain, which a scheduled run on a fresh instance meets
            # routinely. Reported rather than raised: nothing is wrong, there is
            # simply nothing yet to anchor.
            return {"anchored": 0, "seq": 0,
                    "detail": "the chain is empty, so there is no head to "
                              "anchor yet"}
        return self.anchors.anchor(seq, head, length=report["length"], actor=actor)

    def verify_against_anchors(self) -> Dict[str, Any]:
        """Does the chain agree with the heads written outside the database?

        This is the only verification here that an attacker with database access
        alone cannot satisfy. `verify_chain` compares the chain against itself,
        which a rewritten chain passes; this compares it against a second medium.
        """
        if self.anchors is None:
            return {"anchored": 0, "agrees": 1, "checked": 0, "since_seq": None,
                    "detail": "no anchor root is configured, so the chain is "
                              "self-certified and nothing contradicts it"}
        return self.anchors.verify(self.chain_hash_at)

    def verify_since_checkpoint(self, advance: bool = True) -> Dict[str, Any]:
        """Has anything broken since the last full verification?

        O(nodes added since), rather than O(chain). This is the question a
        readiness probe should ask: verifying the whole chain on every probe was
        2.9 seconds and 83 MB at forty thousand nodes, and the same call sat on
        the dashboard — so a busy instance would have been taken out of service
        for being slow to answer whether it was healthy.

        **It is a different question from `verify_chain`, and deliberately so.**
        This one trusts that the chain was intact at the checkpoint and checks
        only what came after. Only the full walk can answer "is the whole chain
        intact", which is why it stays, and why `evidence.verify` runs it on the
        schedule rather than leaving it to whoever remembers.
        """
        mark = self.checkpoint()
        if mark is None:
            report = self.verify_chain()
            if advance and report["valid"]:
                self._record_checkpoint(report["length"], report["head"])
            return {**report, "scope": "full", "from_seq": 0}

        nodes = self.repo.since(mark["seq"])
        report = self._walk(nodes, mark["chain_hash"], mark["seq"] + 1)
        report = {**report, "scope": "incremental", "from_seq": mark["seq"],
                  "checked": len(nodes),
                  "verified_at": mark["verified_at"]}
        if advance and report["valid"] and nodes:
            self._record_checkpoint(nodes[-1]["seq"], report["head"])
        return report

    def _record_checkpoint(self, seq: int, chain_hash: str,
                           actor: str = "system") -> None:
        if self.checkpoints is None:
            return
        self.checkpoints.add({"seq": seq, "chain_hash": chain_hash,
                              "verified_at": time.time(), "verified_by": actor})

    def verify_chain(self) -> Dict[str, Any]:
        """Walk the WHOLE chain. Reports the first break, if any.

        Kept as the real control. `verify_since_checkpoint` is the cheap
        question and answers a narrower one.
        """
        nodes = self.repo.many()
        report = self._walk(nodes, GENESIS, 1)
        return {**report, "scope": "full"} if report["valid"] else report

    def _walk(self, nodes: List[Dict[str, Any]], prev_hash: str,
              expected_seq: int) -> Dict[str, Any]:
        """One verification loop, so the full walk and the incremental one
        cannot drift apart in what they consider a break."""
        for n in nodes:
            if n["seq"] != expected_seq:
                return {"valid": False, "broken_at": n["seq"], "reason": "sequence gap"}
            if n["prev_hash"] != prev_hash:
                return {"valid": False, "broken_at": n["seq"], "reason": "prev_hash mismatch"}
            # The content hash is RECOMPUTED from the node's own fields rather
            # than trusted as stored. Re-linking a stored content_hash proves
            # only that the links are intact; it says nothing about whether the
            # thing linked is still what was recorded, so an edited payload
            # would leave a chain that verifies and a record that lies.
            if self.content_hash_of(n) != n["content_hash"]:
                return {"valid": False, "broken_at": n["seq"],
                        "reason": "content_hash mismatch: the node's payload, "
                                  "kind or subject is not what was recorded"}
            recomputed = canonical_digest([n["seq"], n["prev_hash"], n["content_hash"], n["parents"]])
            if recomputed != n["chain_hash"]:
                return {"valid": False, "broken_at": n["seq"], "reason": "chain_hash mismatch"}
            prev_hash, expected_seq = n["chain_hash"], expected_seq + 1
        return {"valid": True, "length": len(nodes), "head": prev_hash}

    def for_subject(self, subject_id: str) -> List[Dict[str, Any]]:
        return self.repo.many(subject_id=subject_id)

    def for_subjects(self, subject_ids: Sequence[str]) -> List[Dict[str, Any]]:
        """Everything recorded against any of these subjects, in chain order.

        A model's record is not held under one id. The model carries its
        registration, tiering, findings and warrants; each VERSION carries its
        creation, approval, validation episodes, test results, parameter sets
        and telemetry. Anything that asked only for the model's own id — as the
        document compiler did — saw the first list and none of the second, and
        the sections that matter most to a reader are built from the second.
        """
        seen, out = set(), []
        for subject_id in subject_ids:
            if not subject_id or subject_id in seen:
                continue
            seen.add(subject_id)
            out.extend(self.repo.many(subject_id=subject_id))
        return sorted(out, key=lambda n: n["seq"])

    # ------------------------------------------------------------ evaluate
    def evaluate(self, claim: str, derivations: Dict[str, Derivation], semiring: Semiring,
                 valuation: Callable[[str], Any]) -> EvaluationResult:
        """Memoised bottom-up evaluation of the derivation DAG."""
        memo: Dict[str, Any] = {}
        truncated = [False]

        def go(key: str, seen: frozenset) -> Any:
            if key in memo:
                return memo[key]
            if key in seen:                                  # a cycle contributes nothing
                return semiring.zero
            node = derivations.get(key)
            if node is None or node.is_leaf:
                return valuation(key)
            total = semiring.zero
            for alt in node.alternatives:
                term = semiring.one
                for dep in alt:
                    term = semiring.times(term, go(dep, seen | {key}))
                total = semiring.plus(total, term)
                if semiring is WHY and len(total) > MAX_TERMS:
                    truncated[0] = True
                    break
            memo[key] = total
            return total

        return EvaluationResult(go(claim, frozenset()), truncated[0])

    # Convenience valuations ------------------------------------------------
    def presence_valuation(self, subject_id: str) -> Callable[[str], bool]:
        kinds = {n["kind"] for n in self.for_subject(subject_id)}
        return lambda key: key in kinds

    def cited_valuation(self, cited: Set[str]) -> Callable[[str], bool]:
        """Law: a cited set supports a claim iff the derivation is true under it."""
        return lambda key: key in cited

    def why_valuation(self) -> Callable[[str], Set[frozenset]]:
        return lambda key: {frozenset({key})}

    def trust_valuation(self, subject_id: str) -> Callable[[str], float]:
        by_kind = {n["kind"]: n["trust"] for n in self.for_subject(subject_id)}
        return lambda key: by_kind.get(key, 0.0)
