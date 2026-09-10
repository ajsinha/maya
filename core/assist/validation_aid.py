"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Help for a validator, and the three places it stops.

Effective challenge is a judgement made by a person who can be held to it. Every
control in this platform is arranged so that judgement stays with the second
line, and assistance that produced a *conclusion* would be the one place the
arrangement leaked. So there is no method here that concludes, no parameter that
takes an outcome, and a test that asserts both — because the absence is the
control, and an absence nothing checks is an absence somebody adds a method to.

What is offered is three pieces of work a validator would otherwise do by hand,
and each is deliberately constructed differently:

**Vendor documents against the checklist — retrieval, never summary.** For each
checklist item, which filed document mentions it and where. Not a paraphrase: a
summary of a vendor document is a second document, it says something the vendor
did not, and the validator who relies on it cannot cite it when the vendor
disagrees. What comes back is *this item is discussed on the page with these
terms in this attachment*, and the validator reads the attachment.

**Challenge questions — derived from findings, never invented.** Each question
carries the finding it came from and the model it was raised against. A
challenge question with no provenance is one a validator cannot defend when a
model owner pushes back, and "the tool suggested it" is not an answer. The
comparison set is models the register already says are comparable — same domain,
same trainability class — because *this failed on a model like yours* is a
question with force, and a generic checklist is not.

**Assumptions with nothing testing them — an exact derivation, no model at
all.** The assumption register records whether a monitor watches each one, so
this is arithmetic. Routing it through a language model would add a source of
error to an answer that had none, and it is worth saying which of these three
answers is exact: a validator reading a screen that mixes retrieval, derivation
and generation without distinguishing them will trust all three the same amount,
which is either too much or too little for two of them.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.assist.common import AssistError
from core.log import get_logger
from core.validation.vendor import CHECKLIST

logger = get_logger(__name__)

#: How each answer was arrived at. Published on every result, because a screen
#: that mixes them without saying so gets one level of trust applied to all.
EXACT, RETRIEVED, DERIVED = "exact", "retrieved", "derived"

#: What makes two models comparable enough that a finding on one is a question
#: about the other. Ordered: a match on more of these is a stronger question.
COMPARABLE_ON = ("trainability_class", "domain", "model_class")

#: Findings that make poor challenge questions. A remediation-SLA finding is
#: about a date being missed, which is a fact about a programme rather than a
#: question about a model, and a validator handed forty of them stops reading.
NOT_A_QUESTION = ("remediation_sla", "model_health")


class ValidationAssistant:
    """Three pieces of a validator's work. None of them is a conclusion."""

    def __init__(self, registry, findings=None, assumptions=None,
                 vendor=None, search=None, monitoring=None):
        self.registry, self.findings = registry, findings
        self.assumptions, self.vendor = assumptions, vendor
        self.search, self.monitoring = search, monitoring

    # ------------------------------------------------- vendor documentation
    def vendor_coverage(self, urn: str,
                        principal: Optional[Dict[str, Any]] = None
                        ) -> Dict[str, Any]:
        """Which checklist item each filed document appears to speak to.

        Retrieval, and it says so. A summary of a vendor document is a second
        document that says something the vendor did not, and a validator cannot
        cite it back to the vendor.
        """
        if self.search is None:
            raise AssistError(
                "no_document_search",
                "this assistant was built without document search, so it "
                "cannot say which filed document speaks to which checklist item",
                "wire the document index")
        model = self.registry.require(urn)
        assessment = self._assessment(urn)
        answered = self._answered(assessment)
        items = []
        for item, spec in CHECKLIST.items():
            hits = self.search.search(_terms_for(item, spec), principal=principal,
                                      urn=urn, limit=3)
            items.append({
                "item": item, "asks": spec["asks"],
                "discharged_by": spec["discharged_by"],
                "answered": item in answered,
                "documents": [{"attachment_id": h["attachment_id"],
                               "title": h["title"], "terms": h.get("matched"),
                               "score": h["score"]}
                              for h in hits["results"]],
                "unreadable": len(hits["could_not_be_read"]),
            })
        silent = [i["item"] for i in items if not i["documents"]]
        unanswered = [i["item"] for i in items if not i["answered"]]
        return {
            "urn": urn, "model": model.get("name"),
            "assessment": (assessment or {}).get("reference"),
            "basis": RETRIEVED,
            "items": items,
            "no_document_mentions": silent,
            "unanswered": unanswered,
            "detail": self._vendor_detail(items, silent, unanswered, assessment),
        }

    @staticmethod
    def _vendor_detail(items, silent, unanswered, assessment) -> str:
        out = (f"{len(items)} checklist item(s) searched against the documents "
               f"filed for this model. What comes back is which attachment "
               f"mentions an item and on what terms — never a paraphrase, "
               f"because a summary of a vendor document is a second document "
               f"that says something the vendor did not")
        if silent:
            out += (f". {len(silent)} item(s) are mentioned by no filed "
                    f"document at all: {', '.join(silent[:4])}"
                    + (f" and {len(silent) - 4} more" if len(silent) > 4 else ""))
        if not assessment:
            out += (". No vendor assessment has been opened for this model, so "
                    "there is nothing to check the documents against yet")
        elif unanswered:
            out += (f". {len(unanswered)} item(s) remain unanswered in the "
                    f"assessment itself, which is a different fact from no "
                    f"document mentioning them")
        return out

    def _assessment(self, urn: str) -> Optional[Dict[str, Any]]:
        if self.vendor is None:
            return None
        rows = self.vendor.for_model(urn)
        return rows[-1] if rows else None

    def _answered(self, assessment: Optional[Dict[str, Any]]) -> set:
        if not assessment or self.vendor is None:
            return set()
        return {row["item"] for row
                in self.vendor.items.many(assessment_id=assessment["id"])
                if (row.get("answer") or "").strip()}

    # ---------------------------------------------------- challenge questions
    def challenge_questions(self, urn: str, limit: int = 20) -> Dict[str, Any]:
        """What went wrong on comparable models, phrased as a question.

        Every question carries the finding it came from. A challenge question
        with no provenance is one a validator cannot defend when the owner
        pushes back, and "the tool suggested it" is not an answer.
        """
        if self.findings is None:
            raise AssistError(
                "no_findings",
                "this assistant was built without the finding register, and "
                "every question it asks comes from one",
                "wire the finding register")
        model = self.registry.require(urn)
        peers = self._comparable(model)
        questions: List[Dict[str, Any]] = []
        for peer, shared in peers:
            for finding in self._closed_and_open(peer):
                if finding.get("category") in NOT_A_QUESTION:
                    continue
                questions.append({
                    "question": _as_question(finding, peer),
                    "because": finding["title"],
                    "severity": finding["severity"],
                    "from_finding": finding["id"],
                    "from_model": peer["urn"],
                    "comparable_on": shared,
                    "strength": len(shared),
                })
        questions.sort(key=lambda q: (-q["strength"],
                                      _rank(q["severity"]), q["question"]))
        return {
            "urn": urn, "basis": DERIVED,
            "questions": questions[:limit],
            "available": len(questions),
            "comparable_models": [p["urn"] for p, _ in peers],
            "detail": self._questions_detail(questions, peers, model),
        }

    @staticmethod
    def _questions_detail(questions, peers, model) -> str:
        if not peers:
            return ("nothing in the register is comparable to this model on "
                    "trainability class, domain or model class, so there are no "
                    "questions to derive. That is an empty answer and not a "
                    "clean one: a model with no peers is one whose failure "
                    "modes nobody else has met yet")
        if not questions:
            return (f"{len(peers)} comparable model(s) and no finding has ever "
                    f"been raised against any of them. Worth reading as a fact "
                    f"about the challenge those models received rather than "
                    f"about how well they were built")
        return (f"{len(questions)} question(s) from findings raised against "
                f"{len(peers)} comparable model(s), strongest first — strength "
                f"is how much the two models have in common, because *this "
                f"failed on a model like yours* is a question with force and a "
                f"generic checklist is not. Every one carries the finding it "
                f"came from: a challenge nobody can source is one the owner "
                f"can dismiss")

    def _comparable(self, model: Dict[str, Any]) -> List:
        """Models the register already says resemble this one."""
        mine = self._facets(model)
        out = []
        for other in self.registry.list():
            if other["urn"] == model["urn"]:
                continue
            theirs = self._facets(other)
            shared = sorted(k for k in COMPARABLE_ON
                            if mine.get(k) and mine[k] == theirs.get(k))
            if shared:
                out.append((other, shared))
        out.sort(key=lambda pair: -len(pair[1]))
        return out

    def _facets(self, model: Dict[str, Any]) -> Dict[str, Any]:
        versions = self.registry.versions(model["urn"])
        return {"domain": model.get("domain"),
                "model_class": model.get("model_class"),
                "trainability_class": (versions[-1].get("trainability_class")
                                       if versions else None)}

    def _closed_and_open(self, model: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Both, and the closed ones especially.

        A closed finding is the *better* question: somebody found it, agreed it
        was real and fixed it, so it is a failure mode this institution has
        confirmed rather than one it merely suspected.
        """
        return list(self.findings.findings.many(model_id=model["id"]))

    # ------------------------------------------------- untested assumptions
    def untested_assumptions(self, urn: str = "") -> Dict[str, Any]:
        """Assumptions with nothing watching them. Arithmetic, not assistance.

        The register already records whether a monitor watches each assumption,
        so this is a filter. It is here because a validator wants it beside the
        other two — and it is labelled `exact` because a screen that mixed a
        derivation with a generation without saying so would get one level of
        trust applied to both.
        """
        if self.assumptions is None:
            raise AssistError(
                "no_assumptions",
                "this assistant was built without the assumption register",
                "wire the assumption register")
        estate = self.assumptions.across_the_estate()
        versions = estate["versions"]
        if urn:
            self.registry.require(urn)
            versions = [v for v in versions if v.get("urn") == urn]
        rows = []
        for version in versions:
            for assumption in version["assumptions"]:
                if assumption.get("monitor_id"):
                    continue
                rows.append({
                    "urn": version.get("urn"), "semver": version.get("semver"),
                    "assumption": assumption["id"],
                    "reference": assumption.get("reference"),
                    "kind": assumption["kind"],
                    "statement": assumption["statement"],
                    "materiality": assumption.get("materiality"),
                    "mitigated": bool((assumption.get("mitigation") or "").strip()),
                })
        rows.sort(key=lambda r: (r["materiality"] not in ("critical", "material"),
                                 r["mitigated"], r["urn"] or ""))
        grave = [r for r in rows
                 if r["materiality"] in ("critical", "material")
                 and not r["mitigated"]]
        return {
            "urn": urn, "basis": EXACT,
            "assumptions": rows, "count": len(rows),
            "material_and_unmitigated": len(grave),
            "detail": (
                f"{len(rows)} standing assumption(s) have no monitor watching "
                f"them, {len(grave)} of them material or worse with no "
                f"mitigation recorded. This is a filter over the assumption "
                f"register rather than an inference: it is exact, and it is "
                f"labelled exact because a page that mixed it with a generated "
                f"answer would get one level of trust applied to both"
                if rows else
                "every standing assumption has a monitor against it, which is "
                "rarer than it sounds and worth checking rather than "
                "celebrating: an assumption pointed at a monitor that does not "
                "test it reads here exactly like one that does"),
        }

    # ----------------------------------------------------------------- what
    def describe(self) -> Dict[str, Any]:
        """The three offerings, and the one thing none of them does."""
        return {
            "offers": [
                {"what": "vendor_coverage", "basis": RETRIEVED,
                 "means": "which filed document mentions which checklist item, "
                          "and where — never a paraphrase"},
                {"what": "challenge_questions", "basis": DERIVED,
                 "means": "questions from findings raised against comparable "
                          "models, each carrying the finding it came from"},
                {"what": "untested_assumptions", "basis": EXACT,
                 "means": "a filter over the assumption register; no inference "
                          "and no model involved"},
            ],
            "never": "concludes",
            "detail": ("effective challenge is a judgement made by a person who "
                       "can be held to it. There is no method here that "
                       "concludes a validation, no parameter that takes an "
                       "outcome, and a test that asserts both — the absence is "
                       "the control, and an absence nothing checks is one "
                       "somebody adds a method to"),
        }


def _terms_for(item: str, spec: Dict[str, str]) -> str:
    """Search terms for a checklist item, from its own name and question."""
    words = item.replace("_", " ") + " " + spec["asks"]
    return words


def _as_question(finding: Dict[str, Any], peer: Dict[str, Any]) -> str:
    return (f"{finding['title']} was raised against {peer['urn']}, which is "
            f"comparable to this model. What establishes that the same is not "
            f"true here?")


def _rank(severity: str) -> int:
    order = ("Critical", "High", "Medium", "Low", "Observation")
    return order.index(severity) if severity in order else len(order)
