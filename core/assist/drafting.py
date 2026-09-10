"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Asking a model, and refusing to believe the answer.

The generation log could always take delivery of a draft, check it against an
oracle, drop the claims it could not ground and hold the rest until somebody
signed. Nothing ever *asked*. This joins the two, and the order it does it in is
the design:

  1. **The evidence is gathered first, from the register.** Not from the model,
     and not from the prompt. What the model may cite is fixed before it is
     asked, so a citation it invents has nowhere to land.
  2. **The prompt is assembled from that evidence** and its digest recorded, so
     "what was it asked" has an answer that survives the model moving on.
  3. **The provider drafts.** Anything it returns is a candidate.
  4. **The existing gate runs unchanged** -- oracle for Tier A, grounding for
     Tier B -- and the generation lands `drafted`, never evidence, until a
     person attests it.

The important property is that step 1 bounds step 4. A provider cannot introduce
a fact, only a candidate fact, and a candidate that cites nothing the platform
holds is dropped before a reader sees it. That is what makes it safe to point
this at a model nobody has audited, and it is why the mock provider is a real
test of the path rather than a stand-in for one.

**What this does not do.** It does not decide whether the prose is any good. It
measures whether the reviewer changed it, and samples a fraction of accepted
drafts for independent review regardless of how good they looked -- because a
reviewer who has approved forty correct drafts is not reviewing the forty-first.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from core.assist import injection
from core.assist.common import AssistError
from core.assist.providers import build as build_provider
from core.log import get_logger
from db.database import digest as canonical_digest

logger = get_logger(__name__)

# How many evidence nodes a single draft may be grounded in. A prompt that
# carried the whole chain would be a prompt nobody could review, and a claim
# citing one of four thousand nodes is not a citation anybody can check.
MAX_EVIDENCE = 40


class DraftingService:
    """Asks a provider for a draft, and records it through the ordinary gate."""

    def __init__(self, generations, capabilities, evidence, provider=None,
                 budgets=None):
        self.generations, self.capabilities = generations, capabilities
        self.evidence = evidence
        self.provider = provider or build_provider("mock")
        # The gateway's budget check. Optional so an instance can run
        # without one, and when it is absent nothing is claimed: no budget
        # is enforced and the estate view says which capabilities that is
        # true of, rather than reporting them as within budget.
        self.budgets = budgets

    # ------------------------------------------------------------------ draft
    def draft(self, capability_key: str, subject_type: str, subject_id: str,
              instruction: str = "", oracle_payload: Optional[Dict[str, Any]] = None,
              actor: str = "system") -> Dict[str, Any]:
        """Ask for a draft about this subject, grounded in what the register holds."""
        capability = self.capabilities.require(capability_key)
        # Before the provider is asked, which is the only position from which a
        # budget is a control rather than a report. Everything else about a
        # generation is recorded afterwards, and a spend figure computed the
        # same way tells you what happened without stopping it happening.
        if self.budgets is not None:
            self.budgets.check(capability_key)
        if why := self.provider.available():
            raise AssistError(
                "provider_unavailable",
                f"the '{self.provider.key}' provider cannot draft: {why}",
                "set assist.provider to 'mock' to exercise the governed path, or "
                "wire a provider your institution has approved")

        nodes = self._evidence_for(subject_id)
        if not nodes:
            raise AssistError(
                "nothing_to_ground",
                f"there is no evidence recorded against {subject_type} "
                f"{subject_id}, so nothing a model drafted about it could be "
                f"grounded",
                "a subject with no record is one nobody should be drafting about")
        evidence_ids = tuple(n["id"] for n in nodes)
        # Every payload below was written by somebody. Scanned for the shapes an
        # injection takes and NOT stripped of them: removing the words would
        # destroy the evidence that somebody wrote them, and the structural
        # separation in `_prompt` is what actually holds. This is the signal.
        found = injection.scan_nodes(nodes)
        found += injection.scan(instruction, where="caller_instruction")
        injected = injection.report(found)
        if found:
            logger.warning(
                "drafting for capability %s about %s %s over content carrying "
                "%d injection-shaped span(s): %s", capability_key, subject_type,
                subject_id, len(found), sorted(injected["by_pattern"]))
        prompt = self._prompt(capability, subject_type, subject_id, instruction,
                              nodes)

        drafted = self.provider.draft(
            prompt, base_model=capability.get("base_model") or "",
            evidence_ids=evidence_ids,
            context={"subject": f"{subject_type} {subject_id}",
                     "instruction": instruction})

        # The gate is the existing one, unchanged. Nothing here decides whether a
        # claim is admissible; that judgement stays in one place.
        #
        # The `try` is not defensive. `GenerationLog.record` REFUSES a draft
        # that grounds nothing and writes no row — the provider was still
        # called, and the tokens were still spent. Letting the refusal through
        # without charging for it would mean a capability whose output never
        # grounds has no measurable cost at all, which is exactly backwards:
        # the one failing most often is the one burning the most.
        try:
            generation = self.generations.record(
                capability_key, subject_type, subject_id,
                claims=drafted.claims, known_evidence=evidence_ids,
                oracle_payload=oracle_payload,
                output={"provider": drafted.provider, "model": drafted.model,
                        "usage": drafted.usage,
                        "prompt_digest": canonical_digest({"prompt": prompt}),
                        # Recorded next to the generation, because the useful
                        # output is not "the prompt contained something" but
                        # "this row in your register does".
                        "injection": injected,
                        # The provider's own prose, kept for the record and NOT
                        # shown as the answer: what a reader sees is assembled
                        # from the claims that survived grounding.
                        "as_drafted": drafted.text},
                actor=actor)
        except AssistError as refused:
            logger.warning("capability %s was called and produced nothing (%s); "
                           "the call is charged to its budget anyway",
                           capability_key, refused.code)
            self._charge(capability_key, drafted, outcome=refused.code,
                         actor=actor)
            raise
        self._charge(capability_key, drafted, generation_id=generation["id"],
                     actor=actor)
        return generation

    def _charge(self, capability_key, drafted, generation_id=None,
                outcome: str = "recorded", actor: str = "system") -> None:
        """One provider call, one row on the spend ledger."""
        if self.budgets is None:
            return
        usage = drafted.usage or {}
        self.budgets.charge(
            capability_key, tokens=usage.get("tokens") or 0,
            cost=usage.get("cost") or 0.0, steps=usage.get("steps") or 1,
            generation_id=generation_id, outcome=outcome, actor=actor)

    # ------------------------------------------------------------------ parts
    def _evidence_for(self, subject_id: str) -> List[Dict[str, Any]]:
        """What the model is allowed to cite, fixed before it is asked."""
        nodes = list(self.evidence.for_subject(subject_id) or [])
        if len(nodes) > MAX_EVIDENCE:
            logger.info("grounding a draft in the %d most recent of %d evidence "
                        "nodes for %s", MAX_EVIDENCE, len(nodes), subject_id)
            nodes = nodes[-MAX_EVIDENCE:]
        return nodes

    @staticmethod
    def _prompt(capability: Dict[str, Any], subject_type: str, subject_id: str,
                instruction: str, nodes: Sequence[Dict[str, Any]]) -> str:
        """The prompt, in three regions ordered by provenance.

        Every line about the subject comes from an evidence node and is labelled
        with that node's id, so a claim citing one can be checked and a claim
        citing anything else cannot.

        The regions are separated by a **per-prompt nonce**, and that is the
        whole of the structural control: a fixed marker is a string the register
        content can simply print, and a delimiter the writer can forge is not a
        delimiter. The boundary the regions draw is *governed against
        ungoverned* rather than instruction against data — the capability's
        description was registered by somebody holding `assist:register`, and
        the caller's free text was not.
        """
        governed = [
            f"Capability: {capability.get('capability_key')} "
            f"(tier {capability.get('tier')}, {capability.get('autonomy')}).",
            f"Subject: {subject_type} {subject_id}.",
            capability.get("description") or "Draft a summary.",
            "",
            "You may cite ONLY the evidence in the data region below, by its "
            "id. A claim citing anything else will be discarded before anybody "
            "reads it.",
        ]
        data = [f"[{node['id']}] {node.get('kind')} — "
                f"{node.get('subject_type')} {node.get('subject_id')} "
                f"— {node.get('payload')}"
                for node in nodes]
        return injection.envelope(governed=governed,
                                  caller_instruction=instruction,
                                  data=data, marker=injection.fence())

    def describe(self) -> Dict[str, Any]:
        """Which provider is in force, and whether it can actually be used."""
        why = self.provider.available()
        return {"provider": self.provider.key, "usable": why is None,
                "why_not": why or "",
                "max_evidence_per_draft": MAX_EVIDENCE}
