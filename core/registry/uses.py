"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a model is used for, as a thing rather than as a string.

`declared_use` on a warrant grant is a string, checked at resolution against the
grant that carries it. That is exactly enough to authorise a call and not enough
for anything else. A string has no owner, no dates, no product and no legal
entity — so risk cannot attach to a use, and *which models fed the Q2
provision* has no answer.

The distinction that makes this worth a table: **the same model used for two
purposes is two risk propositions.** A PD model used at origination and used for
provisioning carries different materiality, different regulatory expectations
and different consequences of being wrong. A register holding one row for the
model holds one answer for both, and the second answer is the one that turns out
to be wrong.

**Effective dates are the other half, and the more useful one.** SR 26-2 asks
about models being "misapplied or misused", and the commonest form of that is
not a use nobody approved — those get refused. It is a use somebody *did*
approve, for a period that has ended, which nobody switched off. That is
invisible to every control in this platform: the grant still exists, the warrant
still resolves, every call is authorised. Only a use with an end date can catch
it, and only if something reads the date.

**Two things this deliberately does not do.** It does not close the vocabulary
for product, channel, segment or geography — those are the institution's own
words, and a closed list here would be this platform having an opinion about how
a bank divides itself up. And it does not make a use change the model's tier
automatically. It reports where a model's tier looks low against what its uses
say, because materiality is a judgement and re-tiering behind somebody's back
produces a register whose tiers nobody can account for.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.registry.common import RegistryError

DAY = 86400.0

STATUSES = ("active", "retired")

#: The dimensions the requirement names. Kept as a list because several answers
#: below are "group the estate by one of these", and the list is the thing that
#: makes those answers uniform rather than eight near-identical methods.
DIMENSIONS = ("product", "legal_entity", "geography", "channel", "segment")


class ModelUses:
    """Registers what a model is used for, and answers questions about it."""

    def __init__(self, repo, registry, evidence, warrants=None):
        self.repo, self.registry, self.evidence = repo, registry, evidence
        # The warrant service, to say which declared uses have a grant and
        # which grants name a use nobody registered. Optional: without it the
        # register still holds uses and simply does not compare them.
        self.warrants = warrants

    # -------------------------------------------------------------- declare
    def declare(self, urn: str, *, declared_use: str, name: str,
                owner: str, purpose: str = "", product: str = "",
                legal_entity: str = "", geography: str = "", channel: str = "",
                segment: str = "", decision_authority: str = "",
                effective_from: Optional[float] = None,
                effective_to: Optional[float] = None,
                actor: str = "system") -> Dict[str, Any]:
        """Record a use of this model."""
        model = self.registry.require(urn)
        if not (declared_use or "").strip():
            raise RegistryError(
                "a use needs the `declared_use` string a warrant grant carries, "
                "or nothing can match a call to it")
        if not (name or "").strip():
            raise RegistryError("a use with no name is a row nobody will read")
        if not (owner or "").strip():
            raise RegistryError(
                "a use with no owner is a use nobody is accountable for — and "
                "the owner of a use is routinely not the owner of the model, "
                "which is the reason this field is here rather than inherited")
        start = effective_from if effective_from is not None else time.time()
        if effective_to is not None and effective_to <= start:
            raise RegistryError(
                f"this use ends at {effective_to} and begins at {start}, so it "
                f"is never in force")

        existing = self.repo.many(model_id=model["id"])
        row = {"model_id": model["id"],
               "reference": f"USE-{len(existing) + 1:04d}",
               "declared_use": declared_use.strip(), "name": name.strip(),
               "purpose": purpose, "product": product,
               "legal_entity": legal_entity, "geography": geography,
               "channel": channel, "segment": segment,
               "decision_authority": decision_authority, "owner": owner,
               "status": "active", "effective_from": start,
               "effective_to": effective_to, "created_at": time.time(),
               "created_by": actor, "retired_at": None, "retired_by": None,
               "retire_reason": None}
        with self.evidence.recording():
            stored = self.repo.add(row)
            self.evidence.append(
                "model_use_declared", "model", model["id"],
                {"reference": row["reference"], "declared_use": declared_use,
                 "name": name, "product": product,
                 "legal_entity": legal_entity,
                 "effective_from": start, "effective_to": effective_to},
                actor=actor)
        return stored

    def retire(self, use_id: str, reason: str,
               actor: str = "system") -> Dict[str, Any]:
        """End a use. Never deleted: what a model was used for, and when, is
        the history a supervisor asks about."""
        row = self.require(use_id)
        if row["status"] == "retired":
            raise RegistryError(f"{row['reference']} is already retired")
        if not (reason or "").strip():
            raise RegistryError(
                "retiring a use needs a reason: whether the product was "
                "withdrawn or the model was replaced for it are different "
                "facts, and only one of them means the model is now unused")
        with self.evidence.recording():
            self.repo.set({"status": "retired", "retired_at": time.time(),
                           "retired_by": actor,
                           "retire_reason": reason.strip()}, id=use_id)
            self.evidence.append("model_use_retired", "model", row["model_id"],
                                 {"reference": row["reference"],
                                  "reason": reason}, actor=actor)
        return self.require(use_id)

    # ------------------------------------------------------------------ read
    def require(self, use_id: str) -> Dict[str, Any]:
        row = self.repo.one(id=use_id)
        if not row:
            raise RegistryError(f"no model use '{use_id}'")
        return row

    def for_model(self, urn: str,
                  now: Optional[float] = None) -> Dict[str, Any]:
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        rows = [self._annotate(r, moment)
                for r in self.repo.many(model_id=model["id"])]
        granted = set()
        ungranted: List[str] = []
        if self.warrants is not None:
            granted = {g.get("declared_use")
                       for g in self.warrants.grants_for(urn)}
            declared = {r["declared_use"] for r in rows}
            ungranted = sorted(u for u in granted - declared if u)
        for row in rows:
            row["has_grant"] = row["declared_use"] in granted
        return {
            "urn": urn, "uses": rows, **self._counts(rows),
            # A grant for a use nobody registered: the call is authorised and
            # nothing describes what it is for.
            "granted_but_undeclared": ungranted,
            "detail": self._detail(rows, ungranted),
        }

    def across_the_estate(self, *, product: Optional[str] = None,
                          legal_entity: Optional[str] = None,
                          at: Optional[float] = None) -> Dict[str, Any]:
        """Every model used for something, filtered by what and when.

        This is the *which models fed the Q2 provision* query, and the `at`
        parameter is the half that makes it worth asking: a use in force today
        and a use in force in June are different sets, and the second is the
        one an examiner wants.
        """
        moment = at if at is not None else time.time()
        out = []
        for row in self.repo.many():
            if product and row.get("product") != product:
                continue
            if legal_entity and row.get("legal_entity") != legal_entity:
                continue
            annotated = self._annotate(row, moment)
            if not annotated["in_force_at"]:
                continue
            model = self.registry.by_id(row["model_id"]) or {}
            out.append({**annotated, "urn": model.get("urn"),
                        "model_name": model.get("name"),
                        "tier": model.get("tier")})
        out.sort(key=lambda r: (r.get("tier") or 99, r.get("urn") or ""))
        return {
            "at": moment, "product": product, "legal_entity": legal_entity,
            "uses": out, "count": len(out),
            "models": len({r["urn"] for r in out}),
            "detail": (f"{len({r['urn'] for r in out})} model(s) were in use "
                       f"for this at that moment"
                       if out else
                       "no model was in use for this at that moment — which "
                       "is an answer, and a different one from *we cannot "
                       "tell*"),
        }

    def lapsed(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Uses whose window has ended and which nobody has retired.

        The one this register exists for. A use nobody approved gets refused;
        a use somebody approved, for a period that ended, is invisible to every
        control here — the grant still exists, the warrant still resolves, and
        every call is authorised.
        """
        moment = now if now is not None else time.time()
        out = []
        for row in self.repo.many(status="active"):
            end = row.get("effective_to")
            if end is None or end > moment:
                continue
            model = self.registry.by_id(row["model_id"]) or {}
            out.append({"reference": row["reference"], "urn": model.get("urn"),
                        "name": row["name"], "owner": row["owner"],
                        "declared_use": row["declared_use"],
                        "ended": end,
                        "days_over": round((moment - end) / DAY, 1)})
        out.sort(key=lambda r: -r["days_over"])
        return {
            "lapsed": out, "count": len(out),
            "detail": (f"{len(out)} use(s) ended and were never retired. The "
                       f"grant still exists and every call under it is still "
                       f"authorised, which is why nothing else here can see "
                       f"this"
                       if out else
                       "every use in force is one whose window has not ended"),
        }

    # --------------------------------------------------------------- shaping
    @staticmethod
    def _annotate(row: Dict[str, Any], moment: float) -> Dict[str, Any]:
        end = row.get("effective_to")
        started = (row.get("effective_from") or 0) <= moment
        ended = end is not None and end <= moment
        return {**row,
                "in_force_at": started and not ended and row["status"] == "active",
                "lapsed": ended and row["status"] == "active"}

    @staticmethod
    def _counts(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "total": len(rows),
            "in_force": sum(1 for r in rows if r["in_force_at"]),
            "lapsed": sum(1 for r in rows if r["lapsed"]),
            "retired": sum(1 for r in rows if r["status"] == "retired"),
            "by_dimension": {
                d: sorted({r[d] for r in rows if r.get(d)})
                for d in DIMENSIONS
                if any(r.get(d) for r in rows)},
        }

    @staticmethod
    def _detail(rows: List[Dict[str, Any]], ungranted: List[str]) -> str:
        if not rows:
            return ("no use is declared for this model, so what it is FOR is "
                    "whatever string somebody put on a grant")
        in_force = sum(1 for r in rows if r["in_force_at"])
        lapsed = sum(1 for r in rows if r["lapsed"])
        out = f"{len(rows)} declared use(s), {in_force} in force"
        if lapsed:
            out += (f"; {lapsed} ended and were never retired, and every call "
                    f"under those is still being authorised")
        if ungranted:
            out += (f"; {len(ungranted)} grant(s) name a use nobody declared "
                    f"({', '.join(ungranted)}) — the calls are authorised and "
                    f"nothing describes what they are for")
        return out
