"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A permission a supervisor gave, with what it covers and when it lapses.

**A regulatory approval is not a tier and not a control.** Putting it in either
would lose what makes it different: it is somebody *else's* decision, about a
defined scope, and it can be taken away. IRB permission is granted for named
portfolios. An FRTB IMA desk approval is granted for a desk and withdrawn when
that desk fails its P&L attribution test for long enough. A register that
recorded *approved* as a flag on a model could not answer either of the two
questions that matter — **for what**, and **until when**.

**An approval does not lower a tier, and this refuses to let it.** The pull is
obvious and constant: the model has regulatory permission, so surely it needs
less internal scrutiny. It is exactly backwards. A model with IRB permission is
one whose numbers reach the capital calculation, which is what a tier is
measuring; and the supervisor's approval was granted on the strength of the
firm's own governance, so using it to reduce that governance is circular. The
approval is recorded *beside* the tier and never folded into it.

**Conditions are the supervisor's words.** Normalising them into a vocabulary
this platform invented would be paraphrasing a regulator, and a paraphrase is
what somebody will read in three years when the person who received the letter
has left.

**A null expiry means no stated end, not forever.** IRB permission is withdrawn
rather than lapsing; a desk approval runs to a date. Those are different facts
and a single `expires_at` that defaulted to a far date would flatten them into
the more comfortable one.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from core.log import get_logger
from core.risk.tiering import RiskError

logger = get_logger(__name__)

DAY = 86400.0

#: The permissions a bank actually holds, and what each is granted over. Closed,
#: because these are named instruments in named regimes — a free-text kind would
#: let *"model approved"* into a register that exists to stop exactly that.
KINDS: Dict[str, Dict[str, str]] = {
    "irb": {
        "granted_over": "named portfolios or exposure classes",
        "means": "permission to use internal ratings for regulatory capital. "
                 "Has no expiry date and is WITHDRAWN rather than lapsing, "
                 "which is why a null expiry here means no stated end",
    },
    "ima": {
        "granted_over": "a named trading desk",
        "means": "FRTB internal model approval, held desk by desk and lost "
                 "desk by desk when P&L attribution fails. The scope is the "
                 "desk and recording it against the firm would be useless",
    },
    "ama_or_equivalent": {
        "granted_over": "an operational risk category",
        "means": "an advanced measurement permission, where the regime still "
                 "offers one",
    },
    "internal_model_waiver": {
        "granted_over": "a named requirement",
        "means": "permission not to do something the rules otherwise require. "
                 "The one kind where the supervisor's CONDITIONS usually carry "
                 "more weight than the permission",
    },
    "no_objection": {
        "granted_over": "a specific change or use",
        "means": "a supervisor said they would not object. Weaker than a "
                 "permission and worth recording as its own thing rather than "
                 "as an approval, because a firm that treats the two alike "
                 "will one day cite the wrong one",
    },
}

STATES = ("in_force", "expired", "withdrawn")

#: How long before expiry an approval is worth raising. Ninety days: a
#: re-permission is a programme, not a form.
NOTICE_DAYS = 90.0


class RegulatoryApprovals:
    """Records what a supervisor permitted, over what, and until when."""

    def __init__(self, repo, registry, evidence):
        self.repo, self.registry, self.evidence = repo, registry, evidence

    # ----------------------------------------------------------- vocabulary
    @staticmethod
    def kinds() -> Dict[str, Any]:
        return {
            "kinds": [{"kind": k, **v} for k, v in KINDS.items()],
            "detail": (
                "closed, because these are named instruments in named regimes. "
                "A free-text kind would let *model approved* into a register "
                "that exists to stop exactly that — and an approval is not a "
                "tier and not a control: it is somebody else's decision, about "
                "a defined scope, that can be taken away"),
        }

    # -------------------------------------------------------------- record
    def record(self, kind: str, *, regulator: str, scope: str,
               granted_at: float, urn: Optional[str] = None,
               conditions: str = "", expires_at: Optional[float] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Record a permission somebody gave."""
        if kind not in KINDS:
            raise RiskError(
                "unknown_approval_kind",
                f"'{kind}' is not a regulatory approval this register knows",
                "one of " + "; ".join(f"{k} — {v['means'][:60]}…"
                                      for k, v in KINDS.items()))
        # Two raise sites with two literal codes rather than one assembled
        # from the field's name. A code built with an f-string is a code nobody
        # can grep for — and the discipline test that reconciles this taxonomy
        # against the route layer's status map cannot see one either, so the
        # mapping would silently degrade to a bare 400.
        if not (regulator or "").strip():
            raise RiskError(
                "regulator_required",
                "an approval with no regulator recorded cannot answer the "
                "question it exists to answer — *who said so*",
                "record it as it was granted")
        if not (scope or "").strip():
            raise RiskError(
                "scope_required",
                "an approval with no scope recorded cannot answer the "
                "question it exists to answer — *for what*",
                "record it as it was granted")
        model_id = None
        if urn:
            model_id = self.registry.require(urn)["id"]

        rows = self.repo.many()
        row = {
            "reference": f"REG-{len(rows) + 1:04d}", "model_id": model_id,
            "kind": kind, "regulator": regulator.strip(),
            "scope": scope.strip(), "conditions": conditions.strip(),
            "granted_at": granted_at, "expires_at": expires_at,
            "state": "in_force", "withdrawn_at": None, "withdrawn_by": None,
            "withdrawal_reason": "", "recorded_by": actor,
            "recorded_at": time.time(),
        }
        with self.evidence.recording():
            stored = self.repo.add(row)
            self.evidence.append(
                "regulatory_approval_recorded",
                "model" if model_id else "firm", model_id or "firm",
                {"reference": row["reference"], "kind": kind,
                 "regulator": regulator, "scope": scope,
                 "expires_at": expires_at}, actor=actor)
        logger.info("regulatory approval %s (%s from %s) recorded by %s",
                    row["reference"], kind, regulator, actor)
        return stored

    def withdraw(self, reference: str, reason: str,
                 actor: str = "system") -> Dict[str, Any]:
        """Record that it was taken away.

        Withdrawn, never deleted. *We used to hold IRB permission for this
        portfolio and it was withdrawn in March* is the single most important
        sentence in a supervisory conversation, and a register that removed the
        row could not say it.
        """
        row = self.require(reference)
        if row["state"] != "in_force":
            raise RiskError("not_in_force", f"{reference} is {row['state']}",
                            "an approval is withdrawn once")
        if not (reason or "").strip():
            raise RiskError(
                "reason_required",
                "an approval withdrawn with no reason recorded loses the one "
                "thing anybody will ask about it afterwards",
                "record what the supervisor said")
        with self.evidence.recording():
            self.repo.set({"state": "withdrawn", "withdrawn_at": time.time(),
                           "withdrawn_by": actor,
                           "withdrawal_reason": reason.strip()}, id=row["id"])
            self.evidence.append(
                "regulatory_approval_withdrawn",
                "model" if row["model_id"] else "firm",
                row["model_id"] or "firm",
                {"reference": reference, "reason": reason}, actor=actor)
        return self.require(reference)

    # ------------------------------------------------------------------ read
    def require(self, reference: str) -> Dict[str, Any]:
        row = self.repo.one(reference=reference)
        if not row:
            raise RiskError("no_approval",
                            f"no regulatory approval '{reference}'",
                            "references look like REG-0001")
        return row

    def for_model(self, urn: str,
                  now: Optional[float] = None) -> Dict[str, Any]:
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        rows = [self._annotate(r, moment)
                for r in self.repo.many(model_id=model["id"])]
        in_force = [r for r in rows if r["effectively_in_force"]]
        return {
            "urn": urn, "approvals": rows, "count": len(rows),
            "in_force": len(in_force),
            # Stated on every read, because the pull to use it the other way is
            # constant and this is where somebody would look.
            "does_not_lower_the_tier": (
                "a regulatory approval is recorded beside the tier and never "
                "folded into it. A model with IRB permission is one whose "
                "numbers reach the capital calculation, which is what a tier "
                "measures — and the permission was granted on the strength of "
                "the firm's own governance, so using it to reduce that "
                "governance is circular"),
            "detail": self._detail(rows, in_force, moment),
        }

    @staticmethod
    def _annotate(row: Dict[str, Any], moment: float) -> Dict[str, Any]:
        expires = row.get("expires_at")
        lapsed = expires is not None and expires <= moment
        return {
            **row,
            "effectively_in_force": row["state"] == "in_force" and not lapsed,
            "lapsed": lapsed and row["state"] == "in_force",
            "days_left": (round((expires - moment) / DAY, 1)
                          if expires is not None else None),
            "no_stated_end": expires is None,
        }

    @staticmethod
    def _detail(rows, in_force, moment) -> str:
        if not rows:
            return ("no regulatory approval is recorded against this model, "
                    "which is the ordinary case — most models are not held "
                    "under one")
        lapsed = [r for r in rows if r["lapsed"]]
        near = [r for r in in_force
                if r["days_left"] is not None and r["days_left"] <= NOTICE_DAYS]
        out = f"{len(in_force)} of {len(rows)} approval(s) in force"
        if lapsed:
            out += (f"; {len(lapsed)} passed its expiry and nothing has marked "
                    f"it expired, so every screen still reads as permitted")
        if near:
            out += (f"; {len(near)} expire(s) within {NOTICE_DAYS:.0f} days, "
                    f"and a re-permission is a programme rather than a form")
        return out

    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        moment = now if now is not None else time.time()
        rows = [self._annotate(r, moment) for r in self.repo.many()]
        for row in rows:
            model = (self.registry.by_id(row["model_id"])
                     if row.get("model_id") else None)
            row["urn"] = (model or {}).get("urn")
        rows.sort(key=lambda r: (r["state"] != "in_force",
                                 r["days_left"] if r["days_left"] is not None
                                 else 1e9))
        lapsed = [r for r in rows if r["lapsed"]]
        near = [r for r in rows if r["effectively_in_force"]
                and r["days_left"] is not None
                and r["days_left"] <= NOTICE_DAYS]
        return {
            "approvals": rows, "count": len(rows),
            "in_force": sum(1 for r in rows if r["effectively_in_force"]),
            "lapsed": len(lapsed), "expiring": len(near),
            "kinds": KINDS,
            "detail": (
                f"{len(rows)} recorded permission(s)"
                + (f", {len(lapsed)} past their expiry and still reading as in "
                   f"force" if lapsed else "")
                + (f", {len(near)} expiring within {NOTICE_DAYS:.0f} days"
                   if near else "")
                if rows else
                "no regulatory approval is recorded. An approval is somebody "
                "else's decision about a defined scope that can be taken away, "
                "and a register with none is a firm that holds none — a "
                "different fact from one that has not written them down"),
        }

    def expire_due(self, now: Optional[float] = None,
                   actor: str = "scheduler") -> Dict[str, Any]:
        """Mark what has lapsed.

        The same reasoning as every other expiry here: an approval past its date
        that nothing has marked expired reads on every screen exactly like one
        still in force, and the date was always there.
        """
        moment = now if now is not None else time.time()
        expired = []
        for row in self.repo.many(state="in_force"):
            if row.get("expires_at") is None or row["expires_at"] > moment:
                continue
            with self.evidence.recording():
                self.repo.set({"state": "expired"}, id=row["id"])
                self.evidence.append(
                    "regulatory_approval_expired",
                    "model" if row["model_id"] else "firm",
                    row["model_id"] or "firm",
                    {"reference": row["reference"], "kind": row["kind"]},
                    actor=actor)
            expired.append(row["reference"])
        return {"expired": expired, "count": len(expired),
                "detail": (f"{len(expired)} approval(s) reached their expiry"
                           if expired else
                           "no approval reached its expiry")}
