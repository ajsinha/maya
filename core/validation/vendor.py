"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Validating a model you did not build.

SR 26-2 VII and SS1/23 2.6 say the same thing, and it is the thing firms get
wrong: **you cannot validate what you cannot see, so what is validated is your
use of the model, not the model.** The commonest failure is not laziness — it is
a bank asking the vendor for a validation report, receiving a thorough one, and
filing it. That report describes the vendor's development on the vendor's data.
Filing it validates somebody else's work.

So three things are kept strictly apart.

**Due diligence** is what the firm found out. Questions the firm answered, each
with what discharges it.

**A vendor attestation is evidence that the vendor SAID something, and nothing
else.** It is recorded with its date and the version it covers, it goes stale,
and — the rule the whole module exists to enforce — **it cannot discharge an item
that only the firm's own outcomes can discharge**. Accepting a vendor's word for
its own discrimination is how a bank ends up unable to answer the one question
the supervisor asks, which is *how does it perform on your book*.

**Customisation** is what the firm changed. It matters because a customised
vendor model is neither the vendor's model nor the firm's, and both parties will
say so when it goes wrong — so *nothing was changed* is a recorded answer and a
different thing from nobody having said.

**And the version change is the failure this is really about.** A vendor upgrades
the model and the bank finds out from a release note, or does not. The vendor
version string identifies what the vendor calls it; the artifact digest
identifies what is running, and the two part company at every silent upgrade. An
assessment holds both, and a change in either reopens it — because an assessment
of a model that has since been replaced is an assessment of nothing.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from core.validation.common import ValidationError

DAY = 86400.0

#: What discharges an item — and the distinction that carries the module.
#: `firm` means the firm has to establish it; `vendor` means the vendor's
#: statement is the evidence, which is a weaker thing and is labelled as one.
FIRM, VENDOR = "firm", "vendor"

#: The due-diligence checklist. Closed, because a checklist somebody can add a
#: line to is one that quietly loses the line nobody wanted to answer — and each
#: item says who must establish it, which is where the design lives.
CHECKLIST: Dict[str, Dict[str, str]] = {
    "conceptual_basis": {
        "discharged_by": VENDOR,
        "asks": "what the model does and on what theory",
        "why": "the vendor is the only party who knows, and a firm that cannot "
               "state it in its own words does not understand what it is using",
    },
    "development_data": {
        "discharged_by": VENDOR,
        "asks": "what population it was developed on",
        "why": "this is what decides whether the firm's book resembles it at "
               "all, and it is the question a vendor is most often vague about",
    },
    "vendor_validation": {
        "discharged_by": VENDOR,
        "asks": "what independent validation the vendor has had",
        "why": "worth having and worth nothing on its own — it describes the "
               "vendor's development on the vendor's data",
    },
    "limitations": {
        "discharged_by": VENDOR,
        "asks": "what the vendor says it cannot do",
        "why": "a vendor that states no limitations has not been asked",
    },
    "own_outcomes": {
        "discharged_by": FIRM,
        "asks": "how it performs on this firm's own book",
        "why": "the item that actually validates the USE, and the one no "
               "vendor statement can discharge. It is also the question a "
               "supervisor asks first",
    },
    "own_population": {
        "discharged_by": FIRM,
        "asks": "how this firm's population differs from the development one",
        "why": "the gap between the two is where a vendor model fails, and only "
               "the firm can measure it",
    },
    "customisation": {
        "discharged_by": FIRM,
        "asks": "what this firm changed, or that it changed nothing",
        "why": "a customised vendor model is neither the vendor's model nor the "
               "firm's, and both parties will say so when it goes wrong",
    },
    "exit": {
        "discharged_by": FIRM,
        "asks": "what happens if the vendor withdraws it",
        "why": "concentration risk is the one thing about a vendor model that "
               "has nothing to do with the model",
    },
}

#: How long a vendor's statement stands before it is stale. A year: a statement
#: with no date is one nobody can tell is current, and one from four years ago
#: describes a product that has been through eight releases.
ATTESTATION_STANDS_DAYS = 365.0

CONCLUSIONS: Dict[str, str] = {
    "fit_for_use": "the firm may use it, having established its own outcomes",
    "fit_with_conditions": "the firm may use it on terms — see the approval "
                           "conditions, which are machine-enforced",
    "not_fit": "the firm should not use it, and the assessment says why",
}


class VendorAssessments:
    """Runs the due diligence, tracks what the vendor said, and watches the version."""

    def __init__(self, assessments, items, registry, evidence,
                 validation=None):
        self.assessments, self.items = assessments, items
        self.registry, self.evidence = registry, evidence
        self.validation = validation

    # ---------------------------------------------------------- vocabulary
    @staticmethod
    def checklist() -> Dict[str, Any]:
        """The items, and who must establish each."""
        rows = [{"item": k, **v} for k, v in CHECKLIST.items()]
        firm = [r["item"] for r in rows if r["discharged_by"] == FIRM]
        return {
            "items": rows, "must_be_established_by_the_firm": firm,
            "conclusions": CONCLUSIONS,
            "detail": (
                f"{len(firm)} of {len(rows)} items cannot be discharged by "
                f"anything the vendor says. That is the whole of SR 26-2 VII: "
                f"you cannot validate what you cannot see, so what is validated "
                f"is your USE of the model. A vendor's validation report "
                f"describes the vendor's development on the vendor's data, and "
                f"filing it validates somebody else's work"),
        }

    # -------------------------------------------------------------- opening
    def open(self, urn: str, *, vendor: str, product: str, version: str,
             artifact_digest: Optional[str] = None, kind: str = "vendor",
             actor: str = "system") -> Dict[str, Any]:
        """Start a due-diligence assessment, with every item outstanding."""
        model = self.registry.require(urn)
        for name, value in (("vendor", vendor), ("product", product),
                            ("version", version)):
            if not (value or "").strip():
                raise ValidationError(
                    f"a vendor assessment needs the {name}: an assessment that "
                    f"cannot say what it assessed cannot be repeated when the "
                    f"vendor ships the next release")
        open_already = [a for a in self.assessments.many(model_id=model["id"])
                        if a["state"] == "open"]
        if open_already:
            raise ValidationError(
                f"{open_already[0]['reference']} is already open on this model")

        rows = self.assessments.many()
        row = {
            "model_id": model["id"],
            "reference": f"VEN-{len(rows) + 1:04d}", "vendor": vendor.strip(),
            "product": product.strip(), "vendor_version": version.strip(),
            "artifact_digest": artifact_digest, "kind": kind, "state": "open",
            "customisation": "", "opened_by": actor, "opened_at": time.time(),
            "concluded_at": None, "concluded_by": None, "conclusion": None,
            "conclusion_note": "",
        }
        with self.evidence.recording():
            stored = self.assessments.add(row)
            for item, spec in CHECKLIST.items():
                self.items.add({
                    "assessment_id": stored["id"], "item": item,
                    "kind": spec["discharged_by"], "answer": "",
                    "evidence": [], "answered_by": None, "answered_at": None,
                    "stated_at": None, "covers_version": None,
                    "state": "outstanding"})
            self.evidence.append(
                "vendor_assessment_opened", "model", model["id"],
                {"reference": row["reference"], "vendor": vendor,
                 "product": product, "version": version}, actor=actor)
        return stored

    # --------------------------------------------------------------- answer
    def answer(self, reference: str, item: str, answer: str, *,
               evidence: Optional[List[str]] = None,
               stated_at: Optional[float] = None,
               covers_version: Optional[str] = None,
               actor: str = "system") -> Dict[str, Any]:
        """Record what was found out, or what the vendor said."""
        assessment = self.require(reference)
        row = self.items.one(assessment_id=assessment["id"], item=item)
        if not row:
            raise ValidationError(
                f"'{item}' is not on the checklist. It is closed, because a "
                f"checklist somebody can add a line to is one that quietly "
                f"loses the line nobody wanted to answer. The items are: "
                + ", ".join(CHECKLIST))
        if not (answer or "").strip():
            raise ValidationError(
                f"'{item}' answered with nothing records that somebody opened "
                f"the form. If the answer is that nothing was changed, say so — "
                f"that is a real answer and a different one from silence")
        if row["kind"] == VENDOR and stated_at is None:
            raise ValidationError(
                f"'{item}' is discharged by what the vendor says, and a vendor "
                f"statement with no date is one nobody can tell is current. "
                f"Give the date the vendor stated it")

        fields = {"answer": answer.strip(), "evidence": list(evidence or ()),
                  "answered_by": actor, "answered_at": time.time(),
                  "state": "answered", "stated_at": stated_at,
                  "covers_version": covers_version}
        self.items.set(fields, id=row["id"])
        if item == "customisation":
            self.assessments.set({"customisation": answer.strip()},
                                 id=assessment["id"])
        return self.items.one(id=row["id"])

    # ---------------------------------------------------------------- state
    def status(self, reference: str,
               now: Optional[float] = None) -> Dict[str, Any]:
        """Where this assessment stands, and what only the firm can close."""
        assessment = self.require(reference)
        moment = now if now is not None else time.time()
        rows = self.items.many(assessment_id=assessment["id"])

        outstanding, stale, answered = [], [], []
        for row in rows:
            spec = CHECKLIST.get(row["item"], {})
            entry = {"item": row["item"], "kind": row["kind"],
                     "asks": spec.get("asks", ""), "why": spec.get("why", ""),
                     "answer": row["answer"]}
            if row["state"] != "answered":
                outstanding.append(entry)
            elif (row["kind"] == VENDOR
                  and row.get("stated_at") is not None
                  and moment - row["stated_at"] > ATTESTATION_STANDS_DAYS * DAY):
                stale.append({**entry, "stated_at": row["stated_at"],
                              "why_stale": (
                                  f"the vendor stated this "
                                  f"{(moment - row['stated_at']) / DAY:.0f} days "
                                  f"ago, and a statement older than "
                                  f"{ATTESTATION_STANDS_DAYS:.0f} days "
                                  f"describes a product that has been through "
                                  f"releases since")})
            elif (row["kind"] == VENDOR and row.get("covers_version")
                  and row["covers_version"] != assessment["vendor_version"]):
                stale.append({**entry,
                              "covers_version": row["covers_version"],
                              "why_stale": (
                                  f"the vendor stated this about "
                                  f"{row['covers_version']} and the installed "
                                  f"version is {assessment['vendor_version']}")})
            else:
                answered.append(entry)

        firm_outstanding = [e for e in outstanding if e["kind"] == FIRM]
        return {
            "reference": reference, "vendor": assessment["vendor"],
            "product": assessment["product"],
            "vendor_version": assessment["vendor_version"],
            "state": assessment["state"], "items": len(rows),
            "answered": len(answered), "outstanding": outstanding,
            "stale_attestations": stale,
            "firm_must_still_establish": firm_outstanding,
            "complete": not outstanding,
            "detail": self._detail(assessment, outstanding, firm_outstanding,
                                   stale),
        }

    @staticmethod
    def _detail(assessment, outstanding, firm_outstanding, stale) -> str:
        if not outstanding and not stale:
            return (f"every item on the checklist is answered for "
                    f"{assessment['vendor']} {assessment['product']} "
                    f"{assessment['vendor_version']}")
        out = f"{len(outstanding)} item(s) outstanding"
        if firm_outstanding:
            out += (f", {len(firm_outstanding)} of which no vendor statement "
                    f"can discharge — "
                    + ", ".join(e["item"] for e in firm_outstanding)
                    + ". Those are the ones that validate the USE rather than "
                      "the model")
        if stale:
            out += (f". {len(stale)} vendor statement(s) no longer describe "
                    f"what is installed, which is the failure this exists for: "
                    f"a vendor upgrades and the firm finds out from a release "
                    f"note, or does not")
        return out

    # ------------------------------------------------------- version change
    def observe_version(self, reference: str, *, version: str,
                        artifact_digest: Optional[str] = None,
                        actor: str = "system") -> Dict[str, Any]:
        """What is installed now, against what was assessed.

        The failure this module is really about. A vendor version string
        identifies what the vendor calls it; the digest identifies what is
        running, and the two part company at every silent upgrade — so a change
        in **either** reopens the assessment. An assessment of a model that has
        since been replaced is an assessment of nothing.
        """
        assessment = self.require(reference)
        moved_version = version.strip() != assessment["vendor_version"]
        moved_digest = (artifact_digest is not None
                        and assessment.get("artifact_digest") is not None
                        and artifact_digest != assessment["artifact_digest"])
        if not (moved_version or moved_digest):
            return {"reference": reference, "changed": False,
                    "detail": (f"what is installed is still "
                               f"{assessment['vendor_version']}, which is what "
                               f"was assessed")}

        with self.evidence.recording():
            self.assessments.set(
                {"vendor_version": version.strip(),
                 "artifact_digest": artifact_digest, "state": "open",
                 "concluded_at": None, "concluded_by": None,
                 "conclusion": None}, id=assessment["id"])
            # Every vendor statement is now about a version that is not the one
            # installed. Reopened rather than deleted: what the vendor said
            # about the old release is the record of what they said.
            for row in self.items.many(assessment_id=assessment["id"]):
                if row["kind"] == VENDOR and row["state"] == "answered":
                    self.items.set({"state": "outstanding"}, id=row["id"])
            self.evidence.append(
                "vendor_version_changed", "model", assessment["model_id"],
                {"reference": reference,
                 "was": assessment["vendor_version"], "now": version,
                 "digest_moved": moved_digest}, actor=actor)
        return {
            "reference": reference, "changed": True,
            "was": assessment["vendor_version"], "now": version.strip(),
            "digest_moved": moved_digest,
            "detail": (
                f"the installed version moved from "
                f"{assessment['vendor_version']} to {version.strip()}"
                + (" and the artifact digest moved with it" if moved_digest
                   else "")
                + ". The assessment is reopened and every vendor statement is "
                  "outstanding again: they were made about a release that is "
                  "no longer installed, and an assessment of a model that has "
                  "since been replaced is an assessment of nothing"),
        }

    # -------------------------------------------------------------- conclude
    def conclude(self, reference: str, conclusion: str, note: str,
                 actor: str = "system") -> Dict[str, Any]:
        """End the assessment. Refused while the firm's own items are open."""
        assessment = self.require(reference)
        if assessment["state"] != "open":
            raise ValidationError(f"{reference} is already concluded")
        if conclusion not in CONCLUSIONS:
            raise ValidationError(
                f"'{conclusion}' is not a conclusion; one of "
                + ", ".join(f"{k} ({v})" for k, v in CONCLUSIONS.items()))
        if not (note or "").strip():
            raise ValidationError(
                "a conclusion with no note records a verdict and not the "
                "reasoning, and the reasoning is what somebody will be asked "
                "about")
        status = self.status(reference)
        firm_open = status["firm_must_still_establish"]
        if conclusion != "not_fit" and firm_open:
            raise ValidationError(
                f"{', '.join(e['item'] for e in firm_open)} cannot be "
                f"discharged by anything the vendor says, and concluding "
                f"'{conclusion}' without them would be validating the vendor's "
                f"work rather than your use of it — which is the failure SR "
                f"26-2 VII is about. 'not_fit' needs no such evidence, because "
                f"deciding not to use something requires less than deciding to")
        with self.evidence.recording():
            self.assessments.set(
                {"state": "concluded", "concluded_at": time.time(),
                 "concluded_by": actor, "conclusion": conclusion,
                 "conclusion_note": note.strip()}, id=assessment["id"])
            self.evidence.append(
                "vendor_assessment_concluded", "model",
                assessment["model_id"],
                {"reference": reference, "conclusion": conclusion,
                 "note": note}, actor=actor)
        return self.require(reference)

    # ------------------------------------------------------------------ read
    def require(self, reference: str) -> Dict[str, Any]:
        row = self.assessments.one(reference=reference)
        if not row:
            raise ValidationError(f"no vendor assessment '{reference}'")
        return row

    def for_model(self, urn: str) -> List[Dict[str, Any]]:
        model = self.registry.require(urn)
        return self.assessments.many(model_id=model["id"])

    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        moment = now if now is not None else time.time()
        rows = []
        for assessment in self.assessments.many():
            model = self.registry.by_id(assessment["model_id"]) or {}
            status = self.status(assessment["reference"], now=moment)
            rows.append({
                "reference": assessment["reference"], "urn": model.get("urn"),
                "vendor": assessment["vendor"],
                "product": assessment["product"],
                "vendor_version": assessment["vendor_version"],
                "state": assessment["state"],
                "conclusion": assessment.get("conclusion"),
                "outstanding": len(status["outstanding"]),
                "firm_outstanding": len(status["firm_must_still_establish"]),
                "stale_attestations": len(status["stale_attestations"]),
                "customised": bool(assessment.get("customisation")),
            })
        rows.sort(key=lambda r: (-r["firm_outstanding"], -r["stale_attestations"]))
        firm = [r for r in rows if r["firm_outstanding"]]
        stale = [r for r in rows if r["stale_attestations"]]
        return {
            "assessments": rows, "count": len(rows),
            "with_firm_items_outstanding": len(firm),
            "with_stale_attestations": len(stale),
            "detail": (
                f"{len(rows)} vendor assessment(s)"
                + (f", {len(firm)} with items only the firm can establish still "
                   f"open — those are the ones that validate the USE rather "
                   f"than the model" if firm else "")
                + (f"; {len(stale)} carry a vendor statement that no longer "
                   f"describes what is installed" if stale else "")
                if rows else
                "no model on this estate is recorded as somebody else's"),
        }
