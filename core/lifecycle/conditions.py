"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Approving something on terms, where the terms are checked by something.

SR 26-2 V permits a model to be used before it is validated **with compensating
controls**. Every institution already does this; what varies is whether the
controls are enforced or promised. A conditional approval recorded as a sentence
in a committee minute is a promise, and the register cannot tell the difference
between one that is being honoured and one that everybody has forgotten.

**A condition nothing can check is not a condition.** The vocabulary is closed to
kinds this platform can actually do something about, and free text is refused
naming them — because *the model will only be used for low-value cases* is not a
control, it is a hope with a date on it.

**The distinction that carries the design is `enforced` against `attested`.**
Enforced means something here refuses when the condition is broken: a
usage cap becomes a grant quota, an environment restriction becomes a refusal at
resolution, an expiry lapses the approval. Attested means MAYA **cannot see** the
thing the condition is about — it does not know the exposure behind a call, or
whether a human read the output — so the control is that a named person
periodically confirms it still holds, and an unconfirmed one goes stale and
raises a finding.

Recording which is which, at the moment the condition is imposed, is the whole
point. **A firm that believes its exposure cap is machine-enforced is worse off
than one that knows it is a diary entry**, because the first has stopped
checking. Selling an attested condition as an enforced one would be the single
most damaging thing this module could do.

**An expiry is mandatory and cannot be waived.** A conditional approval with no
end date is an unconditional approval that has not noticed yet, which is exactly
how a temporary state becomes the permanent one — the same failure the waiver
register exists to prevent, arriving through a different door.

**The conditions bite at use, not at approval.** Approval is a moment and use is
continuous, so every condition is evaluated when the model is resolved rather
than when somebody signed.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.lifecycle.common import LifecycleError
from core.log import get_logger

logger = get_logger(__name__)

DAY = 86400.0

ENFORCED, ATTESTED = "enforced", "attested"

#: The condition kinds, what each one requires, and — the column that matters —
#: whether this platform can actually check it or only remind somebody to.
KINDS: Dict[str, Dict[str, Any]] = {
    "expires": {
        "enforcement": ENFORCED,
        "requires": (),
        "means": "the approval lapses on the date below and the model stops "
                 "resolving. Mandatory on every conditional approval",
        "how": "checked at resolution against the clock",
    },
    "environments": {
        "enforcement": ENFORCED,
        "requires": ("environments",),
        "means": "the model may be resolved only in the environments named",
        "how": "refused at resolution, by comparing the environment asked for "
               "against the list",
    },
    "usage_cap": {
        "enforcement": ENFORCED,
        "requires": ("calls", "window_hours"),
        "means": "at most this many calls in the window",
        "how": "imposed as a quota on every grant for this model, and refused "
               "by the same code that refuses any other quota",
    },
    "validated_by": {
        "enforcement": ENFORCED,
        "requires": (),
        "means": "a completed validation must exist by the expiry, or the "
                 "approval lapses. This is the condition SR 26-2 V is actually "
                 "about",
        "how": "checked against the validation register at resolution",
    },
    "exposure_cap": {
        "enforcement": ATTESTED,
        "requires": ("amount", "currency"),
        "means": "the portfolio this model decides on may not exceed the "
                 "amount below",
        "how": "MAYA does not see the exposure behind a call and cannot check "
               "this. A named person confirms it periodically, and an "
               "unconfirmed one goes stale — which is a real control and is "
               "not the same thing as an enforced one",
    },
    "human_review": {
        "enforcement": ATTESTED,
        "requires": ("share",),
        "means": "this share of decisions must be reviewed by a person before "
                 "they take effect",
        "how": "MAYA does not see what happens to an output after it is "
               "returned. A named person confirms the review is happening, and "
               "a firm told this was machine-enforced would have stopped "
               "checking",
    },
}

#: How long an attested condition's confirmation stands before it is stale.
DEFAULT_CONFIRM_DAYS = 30.0

#: The longest a conditional approval may run before somebody has to decide
#: again. Six months: long enough to finish a validation, short enough that
#: nobody plans around it.
MAX_DAYS = 183.0


class ApprovalConditions:
    """Imposes conditions on an approval, and evaluates them at use."""

    def __init__(self, repo, registry, evidence, validation=None,
                 quotas=None, warrants=None):
        self.repo, self.registry, self.evidence = repo, registry, evidence
        self.validation, self.quotas, self.warrants = validation, quotas, warrants

    # -------------------------------------------------------------- vocabulary
    @staticmethod
    def vocabulary() -> Dict[str, Any]:
        """The kinds, and which of them this platform actually enforces."""
        rows = [{"kind": kind, **spec} for kind, spec in KINDS.items()]
        enforced = [r["kind"] for r in rows if r["enforcement"] == ENFORCED]
        attested = [r["kind"] for r in rows if r["enforcement"] == ATTESTED]
        return {
            "kinds": rows, "enforced": enforced, "attested": attested,
            "detail": (
                f"{len(enforced)} kind(s) are enforced — something here refuses "
                f"when they are broken — and {len(attested)} are attested, "
                f"because MAYA cannot see the thing they are about. Which is "
                f"which is recorded on every condition, because a firm that "
                f"believes its exposure cap is machine-enforced is worse off "
                f"than one that knows it is a diary entry: the first has "
                f"stopped checking"),
        }

    # ---------------------------------------------------------------- impose
    def impose(self, urn: str, kind: str, *, rationale: str, days: float,
               parameters: Optional[Dict[str, Any]] = None,
               semver: Optional[str] = None,
               confirm_every_days: float = DEFAULT_CONFIRM_DAYS,
               actor: str = "system") -> Dict[str, Any]:
        """Put a condition on this model's approval."""
        model = self.registry.require(urn)
        spec = KINDS.get(kind)
        if spec is None:
            raise LifecycleError(
                "unknown_condition",
                f"'{kind}' is not a condition this platform can check. A "
                f"condition nothing checks is not a condition — it is a hope "
                f"with a date on it",
                "one of " + "; ".join(
                    f"{k} ({v['enforcement']}) — {v['means']}"
                    for k, v in KINDS.items()))
        if not (rationale or "").strip():
            raise LifecycleError(
                "rationale_required",
                "a condition with no rationale is one nobody can decide to "
                "lift, because nothing records what it was for",
                "say what risk this condition is standing in for")
        if days <= 0 or days > MAX_DAYS:
            raise LifecycleError(
                "window_out_of_range",
                f"a conditional approval runs for {days} days, and the bound is "
                f"1 to {MAX_DAYS:.0f}. With no end date it is an unconditional "
                f"approval that has not noticed yet",
                f"choose a window inside {MAX_DAYS:.0f} days; a longer "
                f"exception is renewed, which is a decision somebody takes "
                f"again rather than one that lapses into permanence")
        supplied = parameters or {}
        if missing := [k for k in spec["requires"] if k not in supplied]:
            raise LifecycleError(
                "condition_incomplete",
                f"a {kind} condition needs {', '.join(missing)}, and without "
                f"{'them' if len(missing) > 1 else 'it'} there is nothing to "
                f"check against",
                f"supply {', '.join(spec['requires'])}")

        now = time.time()
        existing = self.repo.many(model_id=model["id"])
        row = {
            "model_id": model["id"],
            "model_version_id": self._version_id(urn, semver),
            "reference": f"COND-{len(existing) + 1:04d}", "kind": kind,
            "enforcement": spec["enforcement"], "parameters": supplied,
            "rationale": rationale.strip(), "imposed_by": actor,
            "imposed_at": now, "expires_at": now + days * DAY,
            "confirmed_by": None, "confirmed_at": None,
            "confirm_every_days": confirm_every_days,
            "state": "active", "discharged_at": None, "discharged_by": None,
            "discharge_reason": "",
        }
        with self.evidence.recording():
            stored = self.repo.add(row)
            self.evidence.append(
                "approval_condition_imposed", "model", model["id"],
                {"reference": row["reference"], "kind": kind,
                 "enforcement": spec["enforcement"], "parameters": supplied,
                 "expires_at": row["expires_at"], "rationale": rationale},
                actor=actor)
        # An enforced usage cap is not a note; it becomes the quota that
        # refuses. Imposed here rather than left for somebody to remember,
        # because a condition that has to be applied by hand is a promise.
        if kind == "usage_cap":
            self._apply_usage_cap(model, supplied, actor)
        logger.info("condition %s (%s, %s) imposed on %s by %s",
                    row["reference"], kind, spec["enforcement"], urn, actor)
        return stored

    def _apply_usage_cap(self, model: Dict[str, Any],
                         parameters: Dict[str, Any], actor: str) -> None:
        if self.quotas is None or self.warrants is None:
            logger.warning(
                "a usage cap was imposed on %s and no quota register is wired "
                "into this instance, so it is recorded and NOT enforced",
                model.get("urn"))
            return
        for grant in self.warrants.grants.repo.many(model_id=model["id"]):
            if grant.get("revoked"):
                continue
            self.quotas.set(grant["id"], quota=int(parameters["calls"]),
                            window_hours=float(parameters["window_hours"]),
                            actor=actor)

    def _version_id(self, urn: str, semver: Optional[str]) -> Optional[str]:
        """Which version this condition is about, if it is about one.

        Null is a real answer and the common one: a condition on *the model*
        outlives its versions, which is what a use-before-validation approval
        usually means. Naming a version would silently lift the condition on
        the next one.
        """
        if not semver:
            return None
        found = self.registry.version(urn, semver)
        if not found:
            raise LifecycleError(
                "no_version", f"{urn} has no version {semver}",
                "name a version that exists, or none — a condition on the "
                "model outlives its versions")
        return found["id"]

    # -------------------------------------------------------------- evaluate
    def evaluate(self, urn: str, environment: str = "prod",
                 now: Optional[float] = None) -> Dict[str, Any]:
        """Whether this model's conditions hold, at the moment of use.

        Approval is a moment and use is continuous, which is why this is
        evaluated at resolution rather than when somebody signed.
        """
        model = self.registry.require(urn)
        moment = now if now is not None else time.time()
        rows = [r for r in self.repo.many(model_id=model["id"])
                if r["state"] == "active"]

        broken: List[Dict[str, Any]] = []
        stale: List[Dict[str, Any]] = []
        holding: List[Dict[str, Any]] = []
        for row in rows:
            verdict = self._verdict(urn, row, environment, moment)
            (broken if verdict["broken"]
             else stale if verdict["stale"] else holding).append(verdict)
        return {
            "urn": urn, "environment": environment,
            "conditions": len(rows), "holds": not broken,
            "broken": broken, "stale": stale, "holding": holding,
            "detail": self._detail(rows, broken, stale),
        }

    def _verdict(self, urn: str, row: Dict[str, Any], environment: str,
                 moment: float) -> Dict[str, Any]:
        kind, parameters = row["kind"], row.get("parameters") or {}
        base = {"reference": row["reference"], "kind": kind,
                "enforcement": row["enforcement"],
                "rationale": row["rationale"], "broken": False,
                "stale": False, "why": ""}

        if row["expires_at"] <= moment:
            return {**base, "broken": True,
                    "why": ("this conditional approval has expired. It is not "
                            "an approval any more — a conditional approval "
                            "that outlives its conditions is an unconditional "
                            "one nobody granted")}

        if row["enforcement"] == ATTESTED:
            last = row.get("confirmed_at")
            due = (row.get("confirm_every_days") or DEFAULT_CONFIRM_DAYS) * DAY
            if last is None:
                return {**base, "stale": True,
                        "why": ("nobody has confirmed this condition holds. "
                                "MAYA cannot check it, so an unconfirmed one "
                                "is a control nothing is exercising")}
            if moment - last > due:
                return {**base, "stale": True,
                        "why": (f"last confirmed "
                                f"{(moment - last) / DAY:.0f} days ago, "
                                f"against a cadence of {due / DAY:.0f}")}
            return {**base, "why": "confirmed recently and standing"}

        if kind == "environments":
            allowed = parameters.get("environments") or []
            if environment not in allowed:
                return {**base, "broken": True,
                        "why": (f"this model is approved for "
                                f"{', '.join(allowed)} only, and this is "
                                f"{environment}")}
            return {**base, "why": f"{environment} is one of the approved ones"}

        if kind == "validated_by":
            if self._validated(urn):
                return {**base, "why": "a completed validation exists"}
            return {**base,
                    "why": (f"no completed validation yet, and this approval "
                            f"lapses in "
                            f"{(row['expires_at'] - moment) / DAY:.0f} days")}

        if kind == "usage_cap":
            return {**base,
                    "why": ("imposed as a quota on every grant for this model, "
                            "and refused by the same code that refuses any "
                            "other quota")}
        return {**base, "why": "in force"}

    def _validated(self, urn: str) -> bool:
        if self.validation is None:
            return False
        return any(e.get("completed_at")
                   for e in self.validation.for_model(urn))

    @staticmethod
    def _detail(rows, broken, stale) -> str:
        if not rows:
            return ("this model's approval carries no conditions, so it is "
                    "approved outright")
        if broken:
            return (f"{len(broken)} of {len(rows)} condition(s) are broken: "
                    + "; ".join(f"{b['reference']} — {b['why']}"
                                for b in broken))
        out = f"all {len(rows)} condition(s) hold"
        if stale:
            out += (f", though {len(stale)} attested one(s) have not been "
                    f"confirmed recently — and an attested condition nobody "
                    f"confirms is a control nothing is exercising")
        return out

    # --------------------------------------------------------------- confirm
    def confirm(self, reference: str, actor: str,
                note: str = "") -> Dict[str, Any]:
        """Somebody states that an attested condition still holds."""
        row = self.require(reference)
        if row["enforcement"] != ATTESTED:
            raise LifecycleError(
                "not_attested",
                f"{reference} is enforced, so confirming it would record an "
                f"opinion about something the platform already checks",
                "enforced conditions need nothing from you; the attested ones "
                "are the ones that do")
        if row["state"] != "active":
            raise LifecycleError("not_active", f"{reference} is {row['state']}",
                                 "a discharged condition needs no confirmation")
        with self.evidence.recording():
            self.repo.set({"confirmed_by": actor, "confirmed_at": time.time()},
                          id=row["id"])
            self.evidence.append(
                "approval_condition_confirmed", "model", row["model_id"],
                {"reference": reference, "note": note}, actor=actor)
        return self.require(reference)

    def discharge(self, reference: str, reason: str,
                  actor: str = "system") -> Dict[str, Any]:
        """Lift a condition, because what it stood in for has been done."""
        row = self.require(reference)
        if row["state"] != "active":
            raise LifecycleError("not_active", f"{reference} is {row['state']}",
                                 "a condition is discharged once")
        if not (reason or "").strip():
            raise LifecycleError(
                "reason_required",
                "lifting a condition with no reason removes a control and "
                "records nothing about why it was safe to",
                "say what discharged it — usually the validation it was "
                "waiting for")
        with self.evidence.recording():
            self.repo.set({"state": "discharged", "discharged_at": time.time(),
                           "discharged_by": actor,
                           "discharge_reason": reason.strip()}, id=row["id"])
            self.evidence.append(
                "approval_condition_discharged", "model", row["model_id"],
                {"reference": reference, "reason": reason}, actor=actor)
        return self.require(reference)

    # ------------------------------------------------------------------ read
    def require(self, reference: str) -> Dict[str, Any]:
        row = self.repo.one(reference=reference)
        if not row:
            raise LifecycleError("no_condition",
                                 f"no approval condition '{reference}'",
                                 "references look like COND-0001")
        return row

    def for_model(self, urn: str) -> Dict[str, Any]:
        model = self.registry.require(urn)
        rows = self.repo.many(model_id=model["id"])
        return {"urn": urn, "conditions": rows, "count": len(rows),
                "active": sum(1 for r in rows if r["state"] == "active"),
                **self.evaluate(urn)}

    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every conditionally approved model, and whether its terms hold."""
        moment = now if now is not None else time.time()
        out = []
        for model in self.registry.list():
            rows = [r for r in self.repo.many(model_id=model["id"])
                    if r["state"] == "active"]
            if not rows:
                continue
            verdict = self.evaluate(model["urn"], now=moment)
            out.append({"urn": model["urn"], "tier": model.get("tier"),
                        "owner": model.get("owner"),
                        "conditions": len(rows),
                        "attested": sum(1 for r in rows
                                        if r["enforcement"] == ATTESTED),
                        "holds": verdict["holds"],
                        "broken": len(verdict["broken"]),
                        "stale": len(verdict["stale"]),
                        "soonest_expiry": min(r["expires_at"] for r in rows)})
        out.sort(key=lambda r: (r["holds"], r["soonest_expiry"]))
        broken = [r for r in out if not r["holds"]]
        stale = [r for r in out if r["stale"]]
        return {
            "models": out, "count": len(out),
            "broken": len(broken), "with_stale_attestations": len(stale),
            "detail": (
                f"{len(out)} model(s) are approved on conditions, "
                f"{len(broken)} of them on conditions that no longer hold"
                + (f"; {len(stale)} carry an attested condition nobody has "
                   f"confirmed recently, which is a control nothing is "
                   f"exercising" if stale else "")
                if out else
                "no model on this estate is approved conditionally"),
        }
