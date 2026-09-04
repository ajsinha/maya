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

from core.authz.common import same_person, AuthzError
from core.evidence import EvidenceEngine
from core.log import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Incompatibility:
    """An act, and the prior acts by the same person that forbid it.

    ``payload_key`` exists because an evidence node's subject is not always the
    thing an act is about. A finding is raised against the *model* — that is
    where a reader looks for it, and where a compiled document cites it — but
    the act being checked is about one finding. So the rule names the payload
    field carrying the identity, and the caller supplies it.

    Without this the check silently passed: it looked for evidence under the
    finding's own id, found none, and permitted everything.
    """
    act: str
    conflicting_kinds: Tuple[str, ...]
    reason: str
    remediation: str
    payload_key: Optional[str] = None


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
        "closure must be attested by someone other than the raiser",
        payload_key="finding_id"),
    Incompatibility(
        "finding:extend", ("finding_acknowledged",),
        "the person who accepted a finding may not move the date they accepted",
        "an extension is where somebody independent asks whether the date was "
        "ever realistic; route it to the second line",
        payload_key="finding_id"),
)

BY_ACT: Dict[str, Incompatibility] = {r.act: r for r in RULES}


class SegregationPolicy:
    """Checks an act against what the same actor already did to the same subject."""

    def __init__(self, evidence: EvidenceEngine,
                 rules: Tuple[Incompatibility, ...] = RULES):
        self.evidence = evidence
        self.rules = {r.act: r for r in rules}

    def conflict(self, actor: str, act: str, subject_id: str,
                 about: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """The prior act that forbids this one, or None.

        ``about`` narrows a subject that carries evidence for many things. A rule
        declaring a ``payload_key`` and given no ``about`` would match any node of
        that kind on the subject — so it refuses to guess and matches nothing,
        which is loud in the tests rather than silent in production.
        """
        rule = self.rules.get(act)
        if rule is None or not subject_id:
            return None
        for node in self.evidence.for_subject(subject_id):
            if node["kind"] not in rule.conflicting_kinds:
                continue
            # The one duties check that was still comparing identities with
            # `!=` while eleven others routed through same_person. It decides
            # every rule in this module, so an actor spelled two ways here
            # disables all of them at once.
            if not same_person(node.get("recorded_by"), actor):
                continue
            if rule.payload_key is not None:
                if about is None:
                    continue
                if (node.get("payload") or {}).get(rule.payload_key) != about:
                    continue
            return {"act": act, "actor": actor, "conflicting_kind": node["kind"],
                    "evidence_seq": node["seq"], "reason": rule.reason,
                    "remediation": rule.remediation,
                    "about": about}
        return None

    def check(self, actor: str, act: str, subject_id: str,
              about: Optional[str] = None) -> None:
        """Raise if the actor is disqualified from this act on this subject."""
        found = self.conflict(actor, act, subject_id, about)
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
                 "matched_by": r.payload_key,
                 "reason": r.reason, "remediation": r.remediation}
                for r in self.rules.values()]
