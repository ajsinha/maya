"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What arrives before a model, and the answer that matters most.

Somebody wants to build something. Before it is a model it is a proposal — a
paragraph, a business case, a vendor demo — and the question a model risk
function has to answer is not *how do we govern this* but three prior ones:

  1. **Is it a model at all?** SR 26-2 and SS1/23 both define the term, and both
     definitions catch things people do not call models and miss things they do.
  2. **Build or buy?** The two produce different obligations, and the choice is
     usually made before anybody in the second line hears about it.
  3. **Is it generative?** Which is not a question about the technology but
     about whether the output is *drawn from a distribution over text* — and it
     changes what can be validated at all.

**A proposal is not a model, and is not stored as one.** It has no version, no
artifact, nothing that could resolve, and putting it in the model table would be
the fastest way to turn a register into an inventory of ideas. The two objects
are separate and the crossing between them is an explicit act.

**The most valuable answer triage gives is "this is not a model".** A register
that admits everything is one nobody can read, and the pressure runs entirely
the other way: nobody is ever criticised for registering something. So the
out-of-scope determination is recorded with its reasons and **kept** — a proposal
declined and forgotten comes back next year as a fresh idea, and the second
triage has to start over without knowing the first one happened.

**Scope is proposed from what was written and decided by a person.** The
platform reads the description for the things the definitions turn on — does it
apply a quantitative method, does it produce an estimate, does an output reach a
decision — and shows which words it turned on. A determination whose reasoning
is invisible is one nobody can disagree with, and the whole value of triage is
in the disagreements.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from core.log import get_logger
from core.lifecycle.common import LifecycleError

logger = get_logger(__name__)

PROPOSED, TRIAGED, REGISTERED, DECLINED = (
    "proposed", "triaged", "registered", "declined")
STATES = (PROPOSED, TRIAGED, REGISTERED, DECLINED)

BUILD, BUY, REUSE, UNDECIDED = "build", "buy", "reuse", "undecided"
SOURCING: Dict[str, str] = {
    BUILD: "developed here, so the firm owns the development record and owes "
           "every part of it",
    BUY: "bought or licensed, so the firm cannot validate the model and must "
         "instead validate its own USE of it — a different and often larger "
         "piece of work than people expect",
    REUSE: "an existing registered model applied to a new purpose, which is a "
           "new risk proposition rather than a reuse of an old one",
    UNDECIDED: "not yet decided. Recorded as such rather than defaulted to "
               "build, because the choice is usually made before the second "
               "line hears about it and defaulting hides that",
}

#: What the definitions turn on. Each is a question with a published cue list,
#: so a determination can be argued with rather than merely received.
QUESTIONS: Dict[str, Dict[str, Any]] = {
    "quantitative_method": {
        "asks": "does it apply a statistical, economic, financial or "
                "mathematical method to produce a result",
        "cues": ("model", "regression", "forecast", "estimate", "score",
                 "predict", "statistical", "machine learning", "neural",
                 "gradient", "monte carlo", "simulation", "calibrat",
                 "optimis", "optimiz", "algorithm"),
        "why": "SR 26-2 §II turns on this phrase, and it is the reason a "
               "spreadsheet with a discount curve in it is a model"},
    "produces_estimate": {
        "asks": "does it produce an estimate, a projection or a decision "
                "rather than a lookup",
        "cues": ("estimate", "forecast", "projection", "probability", "score",
                 "rank", "recommend", "decide", "classify", "valuation",
                 "price"),
        "why": "a system that returns a stored value is a database; one that "
               "produces a number nobody stored is a model"},
    "reaches_a_decision": {
        "asks": "does its output reach a decision about a person, a price or a "
                "capital figure",
        "cues": ("approve", "decline", "limit", "pricing", "provision",
                 "capital", "customer", "applicant", "borrower", "eligibility",
                 "underwrit"),
        "why": "an output nobody acts on is a study; the tier lattice and the "
               "AI Act both turn on who is affected"},
    "generative": {
        "asks": "is the output drawn from a distribution over text, image or "
                "code",
        "cues": ("llm", "large language", "gpt", "generative", "chatbot",
                 "summaris", "summariz", "draft", "prompt", "rag",
                 "retrieval-augmented", "foundation model", "diffusion"),
        "why": "not a question about technology but about what can be "
               "validated: a generative output has no ground truth to test "
               "against, so the whole validation apparatus changes shape"},
    "vendor_supplied": {
        "asks": "was it built by somebody other than this firm",
        "cues": ("vendor", "third party", "third-party", "licensed", "bureau",
                 "supplier", "off the shelf", "off-the-shelf", "saas",
                 "purchased", "procure"),
        "why": "you cannot validate what you cannot see, so a bought model "
               "means validating the firm's USE of it instead"},
}


class Intake:
    """Proposals, and the three questions asked before anything is registered."""

    def __init__(self, proposals, registry, evidence, tiering=None):
        self.proposals, self.registry = proposals, registry
        self.evidence, self.tiering = evidence, tiering

    # -------------------------------------------------------------- propose
    def propose(self, reference: str, *, title: str, description: str,
                proposed_by: str, business_area: str = "",
                now: Optional[float] = None,
                actor: str = "system") -> Dict[str, Any]:
        """Record a proposal. It is not a model and is not stored as one."""
        if not (title or "").strip() or not (description or "").strip():
            raise LifecycleError(
                "description_required",
                "a proposal needs a description triage can read — a title alone "
                "is a name for something nobody has described",
                "say what it will do and what it will decide")
        if self.proposals.one(reference=reference):
            raise LifecycleError(
                "proposal_already_recorded",
                f"proposal '{reference}' already exists",
                "give this one its own reference")
        moment = now if now is not None else time.time()
        row = {"reference": reference, "title": title.strip(),
               "description": description.strip(), "proposed_by": proposed_by,
               "business_area": business_area, "proposed_at": moment,
               "in_scope": None, "sourcing": None, "generative": None,
               "rationale": {}, "state": PROPOSED, "triaged_by": None,
               "triaged_at": None, "registered_urn": None}
        with self.evidence.recording():
            self.proposals.add(row)
            self.evidence.append(
                "proposal_recorded", "intake_proposal", row["id"],
                {"reference": reference, "title": title.strip(),
                 "proposed_by": proposed_by, "business_area": business_area},
                actor=actor)
        logger.info("proposal %s recorded by %s", reference, proposed_by)
        return self.read(reference)

    # ---------------------------------------------------------------- assess
    def assess(self, reference: str) -> Dict[str, Any]:
        """What the description suggests, with the words it turned on.

        A proposal, never a determination. A reading whose reasoning is
        invisible is one nobody can disagree with, and the whole value of triage
        is in the disagreements.
        """
        proposal = self.require(reference)
        text = f"{proposal['title']} {proposal['description']}".lower()
        answers = {}
        for key, question in QUESTIONS.items():
            hit = sorted({cue for cue in question["cues"] if cue in text})
            answers[key] = {
                "question": question["asks"], "suggests": bool(hit),
                "on_words": hit, "why_it_matters": question["why"]}
        in_scope = (answers["quantitative_method"]["suggests"]
                    and answers["produces_estimate"]["suggests"])
        return {
            "reference": reference, "answers": answers,
            "suggests_in_scope": in_scope,
            "suggests_sourcing": (BUY if answers["vendor_supplied"]["suggests"]
                                  else UNDECIDED),
            "suggests_generative": answers["generative"]["suggests"],
            "decided": False,
            "detail": self._assessment_detail(answers, in_scope),
        }

    @staticmethod
    def _assessment_detail(answers, in_scope) -> str:
        fired = [k for k, v in answers.items() if v["suggests"]]
        out = ("this reads as in scope: it applies a quantitative method and "
               "produces an estimate" if in_scope else
               "this does not read as in scope on the two tests that define a "
               "model — a quantitative method AND an estimate. That is the "
               "most valuable answer triage gives, and the pressure runs "
               "entirely the other way, because nobody is ever criticised for "
               "registering something")
        if fired:
            out += (". Read on: " + ", ".join(
                f"{k} on '{', '.join(answers[k]['on_words'][:3])}'"
                for k in fired))
        out += (". This is a reading of the words somebody wrote and not a "
                "determination. A person decides, and the words it turned on "
                "are shown so they can disagree with something specific")
        return out

    # ---------------------------------------------------------------- triage
    def triage(self, reference: str, *, in_scope: bool, sourcing: str,
               generative: bool, rationale: str, actor: str = "system",
               now: Optional[float] = None) -> Dict[str, Any]:
        """Record the determination a person made, beside what was suggested."""
        proposal = self.require(reference)
        if proposal["state"] in (REGISTERED, DECLINED):
            raise LifecycleError(
                "already_triaged",
                f"proposal '{reference}' is {proposal['state']}",
                "record a new proposal if the thing has changed")
        if sourcing not in SOURCING:
            raise LifecycleError(
                "unknown_sourcing", f"'{sourcing}' is not a sourcing decision",
                f"the four are {', '.join(SOURCING)}")
        if not (rationale or "").strip():
            raise LifecycleError(
                "rationale_required",
                "a triage determination needs a reason. An out-of-scope "
                "decision with no reason is one that gets re-litigated every "
                "year by somebody who was not there",
                "say what it turned on")
        moment = now if now is not None else time.time()
        suggested = self.assess(reference)
        record = {
            "rationale": rationale.strip(),
            "suggested_in_scope": suggested["suggests_in_scope"],
            "suggested_sourcing": suggested["suggests_sourcing"],
            "suggested_generative": suggested["suggests_generative"],
            "answers": {k: v["on_words"] for k, v in
                        suggested["answers"].items()},
            "disagreed_with_the_reading": (
                suggested["suggests_in_scope"] != in_scope
                or suggested["suggests_generative"] != generative),
        }
        with self.evidence.recording():
            self.proposals.set(
                {"in_scope": in_scope, "sourcing": sourcing,
                 "generative": generative, "rationale": record,
                 "state": TRIAGED if in_scope else DECLINED,
                 "triaged_by": actor, "triaged_at": moment},
                id=proposal["id"])
            self.evidence.append(
                "proposal_triaged", "intake_proposal", proposal["id"],
                {"reference": reference, "in_scope": in_scope,
                 "sourcing": sourcing, "generative": generative,
                 "rationale": rationale.strip(),
                 "suggested_in_scope": record["suggested_in_scope"],
                 "disagreed_with_the_reading":
                     record["disagreed_with_the_reading"]},
                actor=actor)
        logger.info("proposal %s triaged by %s: in_scope=%s sourcing=%s "
                    "generative=%s", reference, actor, in_scope, sourcing,
                    generative)
        return self.read(reference)

    # -------------------------------------------------------------- register
    def register(self, reference: str, *, urn: str, name: str,
                 model_class: str, domain: str, owner: str,
                 legal_entity: str, purpose: str,
                 actor: str = "system") -> Dict[str, Any]:
        """Cross from proposal to model. An explicit act, and refused before triage."""
        proposal = self.require(reference)
        if proposal["state"] == DECLINED:
            raise LifecycleError(
                "proposal_declined",
                f"'{reference}' was triaged out of scope: "
                f"{(proposal.get('rationale') or {}).get('rationale', '')}",
                "if the proposal has changed, record a new one — reopening this "
                "would lose the determination somebody made and the reasons "
                "they gave")
        if proposal["state"] != TRIAGED:
            raise LifecycleError(
                "not_triaged",
                f"'{reference}' has not been triaged, and registering it now "
                f"would skip the only three questions asked before a model "
                f"exists",
                "triage it first")
        if proposal["state"] == REGISTERED:
            raise LifecycleError("already_registered",
                                f"'{reference}' is already registered as "
                                f"{proposal['registered_urn']}", "")
        model = self.registry.register(urn, name, model_class, domain, owner,
                                       legal_entity, purpose, actor=actor)
        with self.evidence.recording():
            self.proposals.set({"state": REGISTERED, "registered_urn": urn},
                               id=proposal["id"])
            self.evidence.append(
                "proposal_registered", "model", model["id"],
                {"proposal": reference, "urn": urn,
                 "sourcing": proposal["sourcing"],
                 "generative": proposal["generative"],
                 # The triage travels with the model as its first evidence: the
                 # build-versus-buy decision is the one that decides what the
                 # firm owes, and it is otherwise made in a meeting nobody
                 # minuted.
                 "triage_rationale": (proposal.get("rationale") or {}).get(
                     "rationale", "")}, actor=actor)
        logger.info("proposal %s registered as %s by %s", reference, urn, actor)
        return self.read(reference)

    # ------------------------------------------------------------------ read
    def read(self, reference: str) -> Dict[str, Any]:
        proposal = self.require(reference)
        return {**proposal,
                "sourcing_means": SOURCING.get(proposal.get("sourcing") or "",
                                               ""),
                "detail": self._detail(proposal)}

    @staticmethod
    def _detail(proposal: Dict[str, Any]) -> str:
        state = proposal["state"]
        if state == PROPOSED:
            return ("recorded and not yet triaged. It is not a model: it has no "
                    "version, no artifact and nothing that could resolve, and "
                    "it is kept apart from the register so that the register "
                    "does not become an inventory of ideas")
        record = proposal.get("rationale") or {}
        if state == DECLINED:
            return (f"triaged out of scope: {record.get('rationale', '')}. Kept "
                    f"rather than deleted — a proposal declined and forgotten "
                    f"comes back next year as a fresh idea, and the second "
                    f"triage starts over without knowing the first happened"
                    + (". A person disagreed with the platform's reading, which "
                       "is where the value of triage is"
                       if record.get("disagreed_with_the_reading") else ""))
        out = (f"in scope, {proposal['sourcing']}, "
               f"{'generative' if proposal['generative'] else 'not generative'}: "
               f"{record.get('rationale', '')}")
        if record.get("disagreed_with_the_reading"):
            out += (". A person disagreed with the platform's reading of the "
                    "description, and both are on the record")
        if state == REGISTERED:
            out += f". Registered as {proposal['registered_urn']}"
        return out

    def require(self, reference: str) -> Dict[str, Any]:
        row = self.proposals.one(reference=reference)
        if not row:
            raise LifecycleError("unknown_proposal",
                                f"no proposal '{reference}'", "list proposals")
        return row

    # ----------------------------------------------------------------- estate
    def across_the_estate(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Every proposal, untriaged first."""
        moment = now if now is not None else time.time()
        rows = [self.read(p["reference"]) for p in self.proposals.many()]
        rows.sort(key=lambda r: (r["state"] != PROPOSED,
                                 r.get("proposed_at") or 0.0))
        untriaged = [r for r in rows if r["state"] == PROPOSED]
        declined = [r for r in rows if r["state"] == DECLINED]
        by_sourcing: Dict[str, int] = {}
        for row in rows:
            if row.get("sourcing"):
                by_sourcing[row["sourcing"]] = by_sourcing.get(
                    row["sourcing"], 0) + 1
        oldest = min((r["proposed_at"] for r in untriaged), default=None)
        return {
            "proposals": rows, "count": len(rows),
            "untriaged": len(untriaged), "declined": len(declined),
            "registered": sum(1 for r in rows if r["state"] == REGISTERED),
            "by_sourcing": by_sourcing,
            "oldest_untriaged_days": (round((moment - oldest) / 86400.0, 1)
                                      if oldest else None),
            "disagreements": [r["reference"] for r in rows
                              if (r.get("rationale") or {}).get(
                                  "disagreed_with_the_reading")],
            "detail": self._estate_detail(rows, untriaged, declined,
                                          by_sourcing, oldest, moment),
        }

    @staticmethod
    def _estate_detail(rows, untriaged, declined, by_sourcing, oldest,
                       moment) -> str:
        if not rows:
            return ("no proposal is recorded. In most firms this means intake "
                    "is happening somewhere else, not that nothing is being "
                    "proposed")
        out = f"{len(rows)} proposal(s)"
        if by_sourcing:
            out += ": " + ", ".join(f"{n} {k}" for k, n in
                                    sorted(by_sourcing.items()))
        if untriaged:
            out += (f". {len(untriaged)} untriaged, the oldest "
                    f"{(moment - oldest) / 86400.0:.0f} days old — an intake "
                    f"queue nobody works is how a model gets built before "
                    f"anybody asked whether it was one")
        if declined:
            out += (f". {len(declined)} were triaged out of scope and are kept, "
                    f"which is what stops the same idea arriving again next "
                    f"year as a fresh one")
        return out

    @staticmethod
    def questions() -> Dict[str, Any]:
        """The three questions, the cues and the sourcing vocabulary."""
        return {
            "questions": [{"key": k, **{x: (list(v[x]) if x == "cues" else v[x])
                                        for x in ("asks", "cues", "why")}}
                          for k, v in QUESTIONS.items()],
            "sourcing": [{"sourcing": k, "means": v}
                         for k, v in SOURCING.items()],
            "states": list(STATES),
            "detail": ("the platform reads the description for what the "
                       "definitions turn on and shows the words it turned on. "
                       "A person decides. A determination whose reasoning is "
                       "invisible is one nobody can disagree with, and the "
                       "whole value of triage is in the disagreements"),
        }
