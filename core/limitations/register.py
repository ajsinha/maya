"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a model cannot do, stated where it can be counted.

The operating **contract** already carries what a machine can check: `dscr`
between -5 and 20, and an execution refused outside it. What a contract cannot
carry is most of what a model risk manager actually writes — *calibrated on
2019–2024 and never through a rate shock above 400bp*, *assumes the sector mix
is stable*, *LGD is a flat haircut and not modelled*. Those go in a document,
and a document is prose: it cannot be counted, cannot be compared between two
versions, and cannot answer the question a supervisor actually asks.

That question is **which of a model's limitations are enforced and which are
only written down**, and it is a query. So each limitation here names the
contract clause that enforces it, or names none — and *none* is the value worth
having, because it counts what the platform is trusting a person to remember.

Two things this deliberately does not do. It does not parse the statement; a
limitation is prose and pretending otherwise would produce a check that passes
on nonsense. And it does not refuse a version for having unenforced limitations
— most limitations genuinely cannot be bounds, and a control that refused them
would be a control people route around by not writing any down, which is
strictly worse than the document nobody queries.

Limitations attach to a **version**, because that is the immutable thing they
are about. A limitation on "the model" would survive a version that fixed it.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from core.evidence import EvidenceEngine
from core.registry.common import RegistryError

#: The four kinds, which are the four places a limitation comes from. Closed,
#: because an open list becomes a free-text field with extra steps.
KINDS: tuple = ("data", "methodology", "scope", "implementation")

KIND_MEANING: Dict[str, str] = {
    "data": "what the model was fitted on, and what it therefore has not seen "
            "— a period, a population, a regime",
    "methodology": "a choice in how the model works that bounds what it can "
                   "answer — a flat haircut, a linear link, an assumed "
                   "independence",
    "scope": "where the model may be used, as opposed to where it happens to "
             "run — a book, a product, a jurisdiction",
    "implementation": "something true of this build rather than of the model — "
                      "a library version, a precision, a tolerance",
}


class LimitationRegister:
    """Records, withdraws and counts what a version cannot do."""

    def __init__(self, repo, registry, evidence: EvidenceEngine):
        self.repo, self.registry, self.evidence = repo, registry, evidence

    # ------------------------------------------------------------------ write
    def record(self, urn: str, semver: str, kind: str, statement: str,
               *, basis: str = "", bound_key: Optional[str] = None,
               actor: str = "system") -> Dict[str, Any]:
        """State a limitation against one version.

        `bound_key` is checked against the version's own contract rather than
        accepted: a limitation claiming to be enforced by a clause that does not
        exist is the worst of the three states, because it reads as the safe
        one.
        """
        if kind not in KINDS:
            raise RegistryError(
                f"'{kind}' is not a kind of limitation; the four are "
                f"{', '.join(KINDS)} — which are the four places one comes "
                f"from, and the list is closed because an open one becomes a "
                f"free-text field with extra steps")
        if not (statement or "").strip():
            raise RegistryError(
                "a limitation with no statement records that something is "
                "wrong and not what")

        model = self.registry.require(urn)
        version = self.registry.version_service.require(urn, semver)

        if bound_key:
            contract = version.get("contract") or {}
            keys = {str(b["key"]) for section in ("assumptions", "guarantees")
                    for b in (contract.get(section) or [])
                    if isinstance(b, dict) and b.get("key")}
            if bound_key not in keys:
                raise RegistryError(
                    f"this limitation says it is enforced by the contract "
                    f"clause '{bound_key}', and version {semver}'s contract has "
                    f"no such clause. A limitation claiming an enforcement that "
                    f"does not exist is worse than one claiming none, because "
                    f"it reads as the safe case"
                    + (f"; the clauses are {', '.join(sorted(keys))}" if keys
                       else "; the contract declares no clauses at all"))

        existing = self.repo.many(model_version_id=version["id"])
        row = {"model_id": model["id"], "model_version_id": version["id"],
               "reference": f"LIM-{len(existing) + 1:04d}",
               "kind": kind, "statement": statement.strip(),
               "bound_key": bound_key, "basis": basis,
               "raised_by": actor, "created_at": time.time()}
        stored = self.repo.add(row)
        self.evidence.append("limitation_recorded", "model_version",
                             version["id"],
                             {"reference": row["reference"], "kind": kind,
                              "enforced": int(bool(bound_key)),
                              "statement": statement.strip()},
                             actor=actor)
        return stored

    def withdraw(self, limitation_id: str, reason: str,
                 actor: str = "system") -> Dict[str, Any]:
        """A limitation that no longer holds is withdrawn, never deleted.

        The version it describes is immutable, so the limitation's history is
        part of what that version was understood to be — and 'we used to think
        this model could not do X' is exactly the sentence a review needs.
        """
        row = self.require(limitation_id)
        if row.get("withdrawn_at"):
            raise RegistryError(
                f"{row['reference']} was already withdrawn; withdrawing it "
                f"again would record a second decision nobody made")
        if not (reason or "").strip():
            raise RegistryError(
                "withdrawing a limitation needs a reason: the statement was "
                "made about an immutable version, so removing it without one "
                "leaves the register saying less than it did with no record of "
                "why")
        self.repo.set({"withdrawn_at": time.time(), "withdrawn_by": actor,
                       "withdrawal_reason": reason.strip()}, id=limitation_id)
        self.evidence.append("limitation_withdrawn", "model_version",
                             row["model_version_id"],
                             {"reference": row["reference"], "reason": reason},
                             actor=actor)
        return self.require(limitation_id)

    # ------------------------------------------------------------------- read
    def require(self, limitation_id: str) -> Dict[str, Any]:
        row = self.repo.one(id=limitation_id)
        if not row:
            raise RegistryError(f"no limitation '{limitation_id}'")
        return row

    def for_version(self, urn: str, semver: str) -> Dict[str, Any]:
        """Every limitation on one version, and the count that matters."""
        version = self.registry.version_service.require(urn, semver)
        rows = [r for r in self.repo.many(model_version_id=version["id"])]
        standing = [r for r in rows if not r.get("withdrawn_at")]
        enforced = [r for r in standing if r.get("bound_key")]
        stated = [r for r in standing if not r.get("bound_key")]
        return {
            "urn": urn, "semver": semver,
            "limitations": rows,
            "standing": len(standing),
            "enforced": len(enforced),
            "stated_only": len(stated),
            "by_kind": {k: sum(1 for r in standing if r["kind"] == k)
                        for k in KINDS if any(r["kind"] == k for r in standing)},
            "detail": self._detail(len(standing), len(enforced), len(stated)),
        }

    @staticmethod
    def _detail(standing: int, enforced: int, stated: int) -> str:
        if not standing:
            return ("no limitations recorded — which is a claim about the "
                    "model, not an absence of one")
        return (f"{standing} standing: {enforced} enforced by a contract "
                f"clause, {stated} stated and relied on a person to remember")
