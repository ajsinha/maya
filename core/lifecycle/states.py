"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The model record's state machine.

Six states, and the whole design turns on one distinction: an **attested** record
is immutable, and a **mutable** record is one somebody has explicitly opened for
change and will have to attest again.

    draft ──submit──▶ submitted ──approve──▶ approved ──attest──▶ attested
      ▲                   │                                          │
      └──────return───────┘                                          │
                                                                     │
    amending ◀────────────────open amendment─────────────────────────┘
      │                                                              │
      └──submit──▶ submitted ─────────────────────────────▶ attested │
                                                                     │
                                            retired ◀──retire────────┘

Why immutability is a *state* rather than a flag: the question a supervisor asks
is not "is this record locked" but "what is in force, who said so, and when did
they say it". A state machine answers all three, and a flag answers none of them.

Transitions are data. "Who can move this model, from where, to where" is a
question that gets asked in every audit, and it should be readable rather than
reconstructed from conditionals scattered across a service.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

DRAFT = "draft"
# An existing model imported into the register. It is governed going forward and
# carries explicit debt for what it does not have (adversarial review, C-5). It
# is MUTABLE, because closing that debt is exactly what changing it means.
BASELINED = "baselined"
SUBMITTED = "submitted"
APPROVED = "approved"
ATTESTED = "attested"
AMENDING = "amending"
RETIRED = "retired"

STATES: Tuple[str, ...] = (DRAFT, BASELINED, SUBMITTED, APPROVED, ATTESTED,
                           AMENDING, RETIRED)

# The states in which the record may be changed at all. Everything else is
# frozen, including the addition of new versions: a new version IS a change to
# the model, and pretending otherwise is how an attested record quietly stops
# describing what runs.
MUTABLE: Tuple[str, ...] = (DRAFT, BASELINED, AMENDING)

# What each state means, in the words someone would use to explain it.
MEANING: Dict[str, str] = {
    DRAFT: "being written; open to change and not yet in force",
    BASELINED: ("imported from an existing estate; governed going forward, "
                "carrying explicit debt for the evidence it does not have"),
    SUBMITTED: "submitted for approval; frozen while it is being considered",
    APPROVED: "approved but not yet attested; not in force until it is",
    ATTESTED: "in force and immutable; open an amendment to change it",
    AMENDING: "an amendment is open; the record is changeable again",
    RETIRED: "withdrawn from use; kept for the record, never deleted",
}


@dataclass(frozen=True)
class Transition:
    """One legal move, and what it takes to make it."""
    name: str
    sources: Tuple[str, ...]
    target: str
    permission: str
    note: str


TRANSITIONS: Tuple[Transition, ...] = (
    Transition("submit", (DRAFT, BASELINED, AMENDING), SUBMITTED, "model:submit",
               "the owner puts the record forward for approval"),
    Transition("return", (SUBMITTED,), DRAFT, "model:approve",
               "the reviewer sends it back for more work, with a reason"),
    Transition("approve", (SUBMITTED,), APPROVED, "model:approve",
               "the second line approves the record; it is not yet in force"),
    Transition("attest", (APPROVED,), ATTESTED, "model:attest",
               "the required roles sign; the record becomes immutable and in force"),
    Transition("amend", (ATTESTED,), AMENDING, "model:amend",
               "an amendment is opened; the record becomes changeable again"),
    Transition("retire", (ATTESTED, APPROVED, DRAFT, BASELINED), RETIRED,
               "model:retire",
               "the model is withdrawn from use; nothing is deleted"),
)

BY_NAME: Dict[str, Transition] = {t.name: t for t in TRANSITIONS}


def is_mutable(state: str) -> bool:
    return state in MUTABLE


def transition(name: str) -> Optional[Transition]:
    return BY_NAME.get(name)


def allowed_from(state: str) -> List[Transition]:
    """Every legal move out of a state. Drives the interface as well as the checks."""
    return [t for t in TRANSITIONS if state in t.sources]


def describe() -> List[Dict[str, object]]:
    """The machine, for the interface and for an examiner."""
    return [{"name": t.name, "from": list(t.sources), "to": t.target,
             "permission": t.permission, "note": t.note} for t in TRANSITIONS]
