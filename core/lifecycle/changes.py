"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Whether a proposed change is material, decided from what actually changed.

Every institution has this rule and almost none of them can apply it
consistently, because "material" is asked of a person who is looking at a pull
request and who has an opinion about how much work revalidation is. The answer
drifts toward non-material over a career.

So this is computed from the two versions rather than asked. The inputs are
already in the register and already load-bearing elsewhere: the trainability
class, the input and output schemas, the contract, the runtime, the artifact.
The classifier's whole contribution is to say what each difference *means* for
revalidation, and to say it the same way twice.

**Three verdicts, not two.** Material and non-material are the requirement's
words, and there is a third the requirement does not have and needs:
`class_change`. A version whose parameter object changes kind — an estimated
scorecard replaced by a trained network at the same urn — is not a material
change to a model, it is a different model wearing the same name. Calling that
"material" would put it in the same queue as a widened bound, and the right
answer is not a heavier review but a separate registration.

**The override is recorded, never silent.** A rules-based classifier that
somebody may override is the correct design: the rules cannot see everything,
and a change that is technically non-material can be material because of what
it is for. But an override with no reason and no author is how the rule stops
existing, so it takes both and goes on the evidence chain beside the verdict it
replaced — *this was computed non-material and a person called it material* is
a much better sentence for a supervisor than a bare classification.

**Refinement is the interesting half.** `L-7` already decides whether one
contract may replace another: a replacement must accept everything its
predecessor accepted and promise everything it promised. A change that
*tightens* a bound is safe in the direction the algebra cares about and is still
material for revalidation — the model now refuses inputs it used to answer, and
somebody downstream is about to find out. A change that *loosens* one is both.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

MATERIAL = "material"
NON_MATERIAL = "non_material"
CLASS_CHANGE = "class_change"
VERDICTS: Tuple[str, ...] = (NON_MATERIAL, MATERIAL, CLASS_CHANGE)

VERDICT_MEANING: Dict[str, str] = {
    NON_MATERIAL: "nothing changed that alters what the model accepts, "
                  "promises or is. Revalidation is not triggered, and the "
                  "change is still versioned and approved like any other",
    MATERIAL: "something changed that a validator's previous conclusion no "
              "longer covers. Revalidation is triggered",
    CLASS_CHANGE: "the parameter object changed KIND, so this is not a "
                  "different version of the same model — it is a different "
                  "model at the same urn. The answer is a separate "
                  "registration rather than a heavier review",
}


def classify(current: Dict[str, Any],
             proposed: Dict[str, Any]) -> Dict[str, Any]:
    """What kind of change this is, and every reason it is that kind.

    Both arguments are version rows. The reasons are returned in full rather
    than reduced to the verdict, because the argument a person is about to have
    is never about the verdict — it is about which of the differences counts.
    """
    reasons: List[Dict[str, str]] = []

    def note(kind: str, what: str, why: str) -> None:
        reasons.append({"verdict": kind, "what": what, "why": why})

    was_class = current.get("trainability_class")
    now_class = proposed.get("trainability_class")
    if was_class and now_class and was_class != now_class:
        note(CLASS_CHANGE, f"trainability class {was_class} → {now_class}",
             "the parameter object is inhabited differently, so what may be "
             "asked of this model, what evidence it owes and which operations "
             "are admissible all change. That is a different model, not a "
             "later version of this one")

    was_in = _names(current.get("input_schema"))
    now_in = _names(proposed.get("input_schema"))
    if (added := sorted(now_in - was_in)):
        note(MATERIAL, f"inputs added: {', '.join(added)}",
             "adding a regressor is a model change and not a data change. "
             "Every conclusion a validator reached was reached about a model "
             "that did not read these")
    if (removed := sorted(was_in - now_in)):
        note(MATERIAL, f"inputs removed: {', '.join(removed)}",
             "input schemas are contravariant: a replacement must accept "
             "everything its predecessor accepted, so a caller sending one of "
             "these is about to be refused")

    was_out = _names(current.get("output_schema"))
    now_out = _names(proposed.get("output_schema"))
    if was_out != now_out:
        note(MATERIAL,
             f"outputs {', '.join(sorted(was_out))} → "
             f"{', '.join(sorted(now_out))}",
             "output schemas are covariant: a replacement must promise "
             "everything its predecessor promised, and anything consuming the "
             "old shape reads this as a breakage")

    if (was_runtime := current.get("runtime")) != (now_runtime := proposed.get("runtime")):
        if was_runtime and now_runtime:
            note(MATERIAL, f"runtime {was_runtime} → {now_runtime}",
                 "the runtime decides how the artifact is loaded and whether "
                 "that load path executes code, so a validator's conclusions "
                 "about how this model runs no longer describe how it runs")

    reasons.extend(_contract_reasons(current.get("contract") or {},
                                     proposed.get("contract") or {}))

    if _artifact_of(current) != _artifact_of(proposed) and _artifact_of(proposed):
        note(MATERIAL, "the artifact changed",
             "different bytes are a different model, whatever the kernel says. "
             "For a trained model the artifact IS the parameters, and no "
             "description distinguishes two graphs trained from the same code")

    verdict = (CLASS_CHANGE if any(r["verdict"] == CLASS_CHANGE for r in reasons)
               else MATERIAL if any(r["verdict"] == MATERIAL for r in reasons)
               else NON_MATERIAL)
    return {
        "verdict": verdict, "means": VERDICT_MEANING[verdict],
        "reasons": reasons,
        "triggers_revalidation": verdict == MATERIAL,
        "detail": _detail(verdict, reasons),
    }


def _contract_reasons(was: Dict[str, Any],
                      now: Dict[str, Any]) -> List[Dict[str, str]]:
    """What moved in the operating contract, and which direction it moved.

    Both directions are material and they are material for opposite reasons,
    which is why they are reported as two things rather than as "the contract
    changed".
    """
    out: List[Dict[str, str]] = []
    for section in ("assumptions", "guarantees"):
        # Keyed by `str(...)` so a clause with no key sorts rather than
        # raising: a malformed contract is a thing to report on, not a thing
        # to crash the classifier that would have reported it.
        before = {str(b.get("key")): b for b in (was.get(section) or [])
                  if isinstance(b, dict)}
        after = {str(b.get("key")): b for b in (now.get(section) or [])
                 if isinstance(b, dict)}
        for key in sorted(set(before) | set(after)):
            old, new = before.get(key), after.get(key)
            if old == new:
                continue
            if old is None:
                out.append({
                    "verdict": MATERIAL, "what": f"{section}: {key} added",
                    "why": "a bound that did not exist now refuses calls that "
                           "used to be answered"})
            elif new is None:
                out.append({
                    "verdict": MATERIAL, "what": f"{section}: {key} removed",
                    "why": "the model now answers outside a boundary somebody "
                           "put there, and the guarantee that held inside it "
                           "was the reason it was safe to"})
            else:
                out.append({
                    "verdict": MATERIAL,
                    "what": f"{section}: {key} moved from "
                            f"[{old.get('minimum')}, {old.get('maximum')}] to "
                            f"[{new.get('minimum')}, {new.get('maximum')}]",
                    "why": ("widening lets the model answer where nobody "
                            "validated it; narrowing refuses calls somebody "
                            "downstream is still making. Both are material "
                            "and for opposite reasons")})
    return out


def _names(schema) -> set:
    return {str(f.get("name")) for f in (schema or [])
            if isinstance(f, dict) and f.get("name")}


def _artifact_of(version: Dict[str, Any]) -> Optional[str]:
    return version.get("artifact_digest")


def _detail(verdict: str, reasons: List[Dict[str, str]]) -> str:
    if verdict == NON_MATERIAL:
        return ("nothing changed that alters what this model accepts, promises "
                "or is — so a validator's previous conclusion still covers it")
    counted = sum(1 for r in reasons if r["verdict"] == verdict)
    if verdict == CLASS_CHANGE:
        return (f"{counted} change(s) alter what kind of model this is. Register "
                f"it separately: a heavier review of the wrong thing is still a "
                f"review of the wrong thing")
    return (f"{counted} material change(s); revalidation is triggered. The "
            f"argument worth having is which of them counts, which is why they "
            f"are listed rather than summed")


class ChangeClassifier:
    """Classifies a proposed change, and records an override as an override."""

    def __init__(self, registry, evidence, validation=None):
        self.registry, self.evidence = registry, evidence
        self.validation = validation

    def classify(self, urn: str, current_semver: str,
                 proposed_semver: str) -> Dict[str, Any]:
        current = self.registry.version_service.require(urn, current_semver)
        proposed = self.registry.version_service.require(urn, proposed_semver)
        return {"urn": urn, "from": current_semver, "to": proposed_semver,
                **classify(current, proposed)}

    def override(self, urn: str, current_semver: str, proposed_semver: str,
                 verdict: str, reason: str, actor: str = "system"
                 ) -> Dict[str, Any]:
        """A person's answer, recorded beside the computed one.

        Both are kept. A rules-based classifier somebody may override is the
        right design — the rules cannot see what a change is FOR — but an
        override with no reason and no author is how the rule stops existing.
        """
        from core.registry.common import RegistryError

        if verdict not in VERDICTS:
            raise RegistryError(
                f"'{verdict}' is not a verdict; the three are "
                f"{', '.join(VERDICTS)}")
        if not (reason or "").strip():
            raise RegistryError(
                "overriding the classifier needs a reason. The rules cannot "
                "see what a change is for, which is exactly why an override "
                "with no reasoning is indistinguishable from somebody who did "
                "not want to revalidate")
        computed = self.classify(urn, current_semver, proposed_semver)
        model = self.registry.require(urn)
        with self.evidence.recording():
            self.evidence.append(
                "change_classified", "model", model["id"],
                {"from": current_semver, "to": proposed_semver,
                 "computed": computed["verdict"], "recorded": verdict,
                 "overridden": verdict != computed["verdict"],
                 "reason": reason}, actor=actor)
        return {**computed, "computed_verdict": computed["verdict"],
                "verdict": verdict, "overridden": verdict != computed["verdict"],
                "override_reason": reason, "overridden_by": actor,
                "triggers_revalidation": verdict == MATERIAL}
