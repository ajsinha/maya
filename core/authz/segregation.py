"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Segregation of duties, enforced from the evidence chain.

The usual way to build this is a separate table of who-did-what, consulted when
someone attempts a conflicting act. That table is a second source of truth about
history, and the moment it disagrees with the record, the control is worthless.

MAYA already has an append-only, hash-chained record of every governance act
with its actor and its subject. So segregation is checked **against the evidence
chain itself**: the same artifact that proves what happened decides who may act
next. There is nothing to keep in step, and tampering to clear a conflict breaks
the chain.

The rules are data. "Who could have approved this version?" is a question an
examiner will ask, and the answer should be readable rather than reconstructed
from conditionals.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from core.authz.common import AuthzError
from core.evidence import EvidenceEngine
from core.log import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Incompatibility:
    """An act, and the prior acts by the same person that forbid it."""
    act: str
    conflicting_kinds: Tuple[str, ...]
    reason: str
    remediation: str


RULES: Tuple[Incompatibility, ...] = (
    Incompatibility(
        "version:approve", ("version_created",),
        "the person who created a version may not approve it",
        "route the approval to someone in the second line who did not build it"),
    Incompatibility(
        "alias:move", ("version_created",),
        "the person who created a version may not promote it into an environment",
        "route the promotion to a model risk manager who did not build the version"),
    Incompatibility(
        "validation:conclude", ("version_created",),
        "the person who created a version may not conclude its validation",
        "effective challenge requires a validator independent of the build"),
    Incompatibility(
        "finding:close", ("finding_raised",),
        "the person who raised a finding may not close it",
        "closure must be attested by someone other than the raiser"),
)

BY_ACT: Dict[str, Incompatibility] = {r.act: r for r in RULES}


class SegregationPolicy:
    """Checks an act against what the same actor already did to the same subject."""

    def __init__(self, evidence: EvidenceEngine,
                 rules: Tuple[Incompatibility, ...] = RULES):
        self.evidence = evidence
        self.rules = {r.act: r for r in rules}

    def conflict(self, actor: str, act: str, subject_id: str) -> Optional[Dict[str, Any]]:
        """The prior act that forbids this one, or None."""
        rule = self.rules.get(act)
        if rule is None or not subject_id:
            return None
        for node in self.evidence.for_subject(subject_id):
            if node["kind"] in rule.conflicting_kinds and node["recorded_by"] == actor:
                return {"act": act, "actor": actor, "conflicting_kind": node["kind"],
                        "evidence_seq": node["seq"], "reason": rule.reason,
                        "remediation": rule.remediation}
        return None

    def check(self, actor: str, act: str, subject_id: str) -> None:
        """Raise if the actor is disqualified from this act on this subject."""
        found = self.conflict(actor, act, subject_id)
        if found is None:
            return
        logger.warning("segregation refused %s for %s on %s (evidence #%s)",
                       act, actor, subject_id, found["evidence_seq"])
        raise AuthzError(
            "segregation_of_duties",
            f"{found['reason']} — {actor} recorded '{found['conflicting_kind']}' "
            f"against this subject at evidence #{found['evidence_seq']}",
            found["remediation"])

    def describe(self) -> List[Dict[str, Any]]:
        """The rule table, for the interface and for an examiner."""
        return [{"act": r.act, "conflicts_with": list(r.conflicting_kinds),
                 "reason": r.reason, "remediation": r.remediation}
                for r in self.rules.values()]
