"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The classification lattice, and its refusal type.
"""
from __future__ import annotations

from typing import Dict, Tuple

#: The classes, in order. A **total order**, which makes the join a maximum —
#: the simplest lattice there is, and the right one: a firm that needs
#: incomparable classes needs categories, and categories are what `pii` is for.
LEVELS: Tuple[str, ...] = ("public", "internal", "confidential", "restricted")

RANK: Dict[str, int] = {level: i for i, level in enumerate(LEVELS)}

#: The bottom of the lattice, and therefore the identity of the join. A model
#: reading nothing is `public`, which is correct rather than convenient: the
#: join of an empty set is the identity, and defaulting it to `internal`
#: instead would mean a model with no inputs was classified higher than one
#: reading public data.
BOTTOM = LEVELS[0]

#: The default for a feature whose class nobody stated. Deliberately NOT the
#: bottom: an unstated class is unknown, and treating unknown as public is the
#: assumption that makes a classification scheme worthless.
DEFAULT = "internal"

MEANING: Dict[str, str] = {
    "public": "already outside the firm, or fit to be",
    "internal": "ordinary business information. The default for anything "
                "nobody classified, because an unstated class is unknown and "
                "treating unknown as public is the assumption that makes a "
                "classification scheme worthless",
    "confidential": "would harm the firm or a counterparty if it left",
    "restricted": "regulated, contractually fenced, or personal in a way that "
                  "carries a statutory duty",
}


class ClassificationError(RuntimeError):
    """A classification act was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


def join(*levels: str) -> str:
    """The least class no lower than any of them.

    The whole of propagation. A total order makes this a maximum, and a maximum
    is the only rule that cannot be argued with: a thing built out of parts
    cannot be less sensitive than its most sensitive part.
    """
    ranks = [RANK[level] for level in levels if level in RANK]
    return LEVELS[max(ranks)] if ranks else BOTTOM


def at_least(declared: str, derived: str) -> bool:
    """Whether a declared class is no lower than what the parts force."""
    return RANK.get(declared, -1) >= RANK.get(derived, 0)


def normalise(value: str) -> str:
    """A stated class, or a refusal naming the ones that exist.

    The vocabulary has to be closed before a join means anything. Two features
    marked `Confidential`, `confidential` and `CONF` are three classes to a
    computer and one to a person, and a lattice over free text is a lattice over
    nothing.
    """
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return DEFAULT
    if cleaned not in RANK:
        raise ClassificationError(
            "unknown_classification",
            f"'{value}' is not a classification. The vocabulary is closed "
            f"because a join over free text means nothing: 'Confidential', "
            f"'confidential' and 'CONF' are three classes to a computer and "
            f"one to a person",
            "one of " + ", ".join(f"{k} ({v})" for k, v in MEANING.items()))
    return cleaned
