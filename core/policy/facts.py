"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The facts each gate publishes.

A policy may read these and nothing else. That is what keeps a rule reviewable:
the reader can see the entire universe the rule is defined over, in one place, in
the order somebody would ask about it.

It is also what makes a rule *refusable at the moment it is written*. A name that
is not a fact here is caught when the policy is authored, rather than at the
moment of a governance decision — which would be the worst possible time for a
gate to fail.

Adding a fact is a deliberate act: it widens what every policy on that gate may
consider, and a fact nobody can explain is a fact somebody will write a rule
against anyway.
"""
from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

FACTS: Dict[str, Dict[str, str]] = {
    "version:approve": {
        "tier": "the model's risk tier, 1 (most material) to 4, or None if "
                "unassessed",
        "status": "the version's current status",
        "blocking_findings": "how many open findings block this model",
        "open_findings": "the severities of every open finding, as a list",
        "has_artifact_digest": "whether the version pins the bytes that will run",
        "has_contract": "whether the version states its operating assumptions",
        "validated": "whether a validation episode has concluded for it",
        "validation_outcome": "the conclusion of the most recent episode, or None",
        "documents": "how many documents are on file against this model",
        "accepted_documents": "how many of those a second person accepted",
        "quorum_signatures": "signatures gathered on the open approval, if any",
        "actor_roles": "the roles held by whoever is asking",
    },
    "alias:move": {
        "tier": "the model's risk tier",
        "environment": "which environment the alias lives in",
        "alias": "which alias is being moved",
        "record_status": "the model record's own lifecycle state",
        "to_status": "the status of the version being pointed at",
        "blocking_findings": "how many open findings block this model",
        "refinement_holds": "whether the new contract refines the incumbent's",
        "variance_ok": "whether the schemas satisfy the variance rule",
        "attested": "whether the model record is currently attested",
        "actor_roles": "the roles held by whoever is asking",
    },
    "model:mutate": {
        "tier": "the model's risk tier",
        "lifecycle_state": "the record's state: draft, baselined, attested, …",
        "attested": "whether the record is currently attested",
        "amending": "whether an amendment is open",
        "actor_roles": "the roles held by whoever is asking",
    },
    "warrant:resolve": {
        "tier": "the model's risk tier",
        "environment": "which environment the warrant is for",
        "declared_use": "what the caller says it is for",
        "blocking_findings": "how many open findings block this model",
        "attested": "whether the model record is currently attested",
        # The RECORD's state, as against the version's. Every gate here spoke
        # only about the version, so a model whose own record had never been
        # submitted — never approved, never attested, nothing asserted about it
        # by anybody — passed all four and was handed a signed descriptor.
        "record_status": "the model record's own lifecycle state: draft, "
                         "baselined, submitted, approved, attested, amending, "
                         "retired",
        "version_status": "the status of the version that would run",
        "has_approved_parameters": "whether an approved parameter set exists",
        "principal": "who is asking",
    },
}


def vocabulary(gate: str) -> List[str]:
    """The names a policy on this gate may use."""
    return sorted(FACTS.get(gate, {}))


def describe(gate: str) -> List[Dict[str, str]]:
    return [{"fact": name, "means": meaning}
            for name, meaning in sorted(FACTS.get(gate, {}).items())]


def complete(gate: str, facts: Dict[str, Any]) -> Dict[str, Any]:
    """Every fact the gate publishes, defaulted where the caller gave none.

    A gate that supplied only some of its facts would make a rule's behaviour
    depend on which call site evaluated it, which is the kind of difference
    nobody finds until it matters.
    """
    known = FACTS.get(gate, {})
    return {name: facts.get(name, _DEFAULTS.get(name)) for name in known}


_DEFAULTS: Dict[str, Any] = {
    "tier": None, "status": "draft", "blocking_findings": 0,
    "open_findings": [], "has_artifact_digest": False, "has_contract": False,
    "validated": False, "validation_outcome": None, "documents": 0,
    "accepted_documents": 0, "quorum_signatures": 0, "actor_roles": [],
    "environment": "", "alias": "", "to_status": "draft",
    "refinement_holds": False, "variance_ok": False, "attested": False,
    "lifecycle_state": "draft", "amending": False,
    "record_status": "draft",
    "declared_use": "", "version_status": "draft",
    "has_approved_parameters": False, "principal": "",
}


# The rules the platform enforces today, expressed in the language, so that
# adopting the policy engine changes nothing until somebody changes a policy.
# They are the DEFAULT, not a suggestion: an instance that publishes nothing
# runs exactly what it ran before.
BUILT_IN: Dict[str, Tuple[str, str]] = {
    "version:approve": (
        "blocking_findings == 0 and tier is not None",
        "a version is not approved over an open blocking finding, and not "
        "before the model has a tier — the tier decides how many signatures "
        "the approval needs"),
    "alias:move": (
        "to_status == 'approved' and blocking_findings == 0 "
        "and refinement_holds and variance_ok",
        "an alias points only at an approved version whose contract refines "
        "the incumbent's and whose schemas satisfy the variance rule, and never "
        "over a blocking finding"),
    "model:mutate": (
        "not attested or amending",
        "an attested record is immutable; the way to change one is to open an "
        "amendment, which will have to be attested again"),
    "warrant:resolve": (
        "version_status == 'approved' "
        "and record_status not in ('draft', 'retired')",
        "a warrant resolves only against an approved version of a model whose "
        "own record has been put through the register — a record still in "
        "'draft' has been asserted by nobody, and a 'retired' one has been "
        "withdrawn. Open blocking findings are refused separately and earlier, "
        "at `_check_not_blocked`, which is the control that actually reads them"),
}
