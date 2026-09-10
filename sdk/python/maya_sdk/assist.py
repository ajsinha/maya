"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Machine assistance: capabilities, generations, and who signed for them.

**Why this module exists at all.** Every other subsystem in this platform had a
client and this one did not, so the only way to register an AI capability from
Python was a raw `maya.call(...)` — including in the case study written to
demonstrate the AI framework. A governed path that is harder to reach than the
ungoverned one is a governed path people work around, and that is the whole
argument the assistance framework makes about itself.

**The three ideas the API is shaped by**, and they are not conveniences:

*   A capability is **registered like a model**, because it is one: `P` is a
    prompt and a configuration, `X` is the context it is given, `D(Y)` is a
    distribution over text.
*   **Tier C is not registrable.** A capability whose output can be neither
    mechanically checked nor grounded in evidence is advisory, and advisory AI
    is a person using a chat window. The refusal is the point.
*   **Nothing is evidence until a person attests it**, and never the person who
    asked for it. `attest()` is a different act from `generate()` and the
    platform refuses to let one principal do both.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class Assist:
    """The AI capability register, and the generations recorded against it."""

    def __init__(self, maya):
        self._maya = maya

    # ------------------------------------------------------------ vocabulary
    def tiers(self) -> Dict[str, Any]:
        """What A, B and C mean, from the code rather than from a copy here.

        Asked rather than carried for the same reason the warrant grammar is:
        a vocabulary duplicated into a client is a vocabulary that goes stale,
        and the copy that goes stale is the one the caller is reading.
        """
        return self._maya.call("GET", "/assist/tiers")

    def providers(self) -> Dict[str, Any]:
        """Which model providers this instance can actually reach."""
        return self._maya.call("GET", "/assist/providers")

    # ---------------------------------------------------------- capabilities
    def capabilities(self) -> Dict[str, Any]:
        return self._maya.call("GET", "/assist/capabilities")

    def register(self, *, capability_key: str, description: str, tier: str,
                 base_model: str, prompt_digest: str, owner: str,
                 oracle_key: Optional[str] = None,
                 autonomy: str = "human_approved_automation",
                 review_sample: float = 0.1) -> Dict[str, Any]:
        """Register a capability. Tier A needs an oracle; Tier C is refused.

        `prompt_digest` rather than the prompt: the prompt is the parameter
        object and may be long, and what governance needs is the ability to say
        *this generation came from that prompt* — which a digest answers and a
        copy of the text does not, because a copy can be edited.

        `review_sample` is the fraction pulled for independent review whatever
        it looks like. It defaults to a tenth and is deterministic on the
        capability's own draw count, so a drafter cannot infer the rate by
        watching a clock — and 1.0 genuinely means every generation.
        """
        return self._maya.call("POST", "/assist/capabilities", json={
            "capability_key": capability_key, "description": description,
            "tier": tier, "base_model": base_model,
            "prompt_digest": prompt_digest, "owner": owner,
            "oracle_key": oracle_key, "autonomy": autonomy,
            "review_sample": review_sample})

    # ----------------------------------------------------------- generations
    def record(self, *, capability_key: str, subject_type: str,
               subject_id: str, claims: Optional[List[Dict[str, Any]]] = None,
               known_evidence: Optional[List[str]] = None,
               oracle_payload: Optional[Dict[str, Any]] = None,
               output: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Record what a capability produced, with the claims it made.

        Each claim carries the evidence ids it cites. The grounding gate then
        **removes** the claims that cite nothing MAYA holds rather than flagging
        them — and keeps them, separately, for the reviewer. Flagging leaves the
        unsupported sentence in the document with a marker somebody has to
        notice; removal leaves a document whose remaining sentences are all
        supported, and a list of what was taken out.
        """
        return self._maya.call("POST", "/assist/generations", json={
            "capability_key": capability_key, "subject_type": subject_type,
            "subject_id": subject_id, "claims": claims or [],
            "known_evidence": known_evidence or [],
            "oracle_payload": oracle_payload or {}, "output": output or {}})

    def draft(self, *, capability_key: str, subject_type: str, subject_id: str,
              instruction: str = "",
              oracle_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Ask the configured provider to draft, and record the result.

        The one call here that reaches a model. It goes through the same
        recording path as `record()`, so a generation produced by a provider and
        one delivered by a caller are the same kind of object and are governed
        identically.
        """
        return self._maya.call("POST", "/assist/drafts", json={
            "capability_key": capability_key, "subject_type": subject_type,
            "subject_id": subject_id, "instruction": instruction,
            "oracle_payload": oracle_payload or {}})

    # -------------------------------------------------------------- injection
    def injection(self) -> Dict[str, Any]:
        """Register rows carrying content shaped like an instruction to a model.

        Read this as a signal and never as a gate. It is a blocklist, and the
        adversary can write anything — a clean sweep means nothing was
        recognised, not that nothing is there. What actually holds is
        structural: register content is fenced behind a nonce generated when
        the prompt is assembled, so content written at any earlier moment
        cannot contain it, and the grounding gate means even a fully successful
        injection can produce only a *candidate* fact.

        Nothing is stripped. The words are the evidence that somebody wrote
        them.
        """
        return self._maya.call("GET", "/assist/injection")

    # ---------------------------------------------------------------- budgets
    def budgets(self) -> Dict[str, Any]:
        """Every capability, what it may spend and what it has spent.

        Two columns repay reading. `on_default` names the capabilities running
        on a number this platform chose rather than one anybody decided — a
        default reported as a decision is how a default becomes permanent. And
        `calls_that_produced_nothing` is the spend that bought nothing: a draft
        the grounding gate refused leaves no generation at all, and it cost
        exactly as much to produce as one that survived.
        """
        return self._maya.call("GET", "/assist/budgets")

    def budget(self, capability_key: str) -> Dict[str, Any]:
        """What this capability may spend, and how much of it is left."""
        return self._maya.call("GET", f"/assist/budgets/{capability_key}")

    def set_budget(self, capability_key: str, *,
                   tokens: Optional[float] = None,
                   cost: Optional[float] = None,
                   steps: Optional[float] = None,
                   window_days: Optional[float] = None) -> Dict[str, Any]:
        """Declare what this capability may spend per rolling window.

        `steps` is the one worth setting deliberately. Tokens bound a prompt
        that grew and cost bounds the invoice, but a runaway agent is a large
        number of *small* calls — it passes both for a long time before either
        notices, and a step budget is the bound that matches its shape.

        The window is rolling rather than a lifetime cap, because a lifetime cap
        is reached once and then the capability is dead forever, which is how
        budgets end up raised to a number that means nothing.
        """
        return self._maya.call("PUT", f"/assist/budgets/{capability_key}",
                               json={"tokens": tokens, "cost": cost,
                                     "steps": steps,
                                     "window_days": window_days})

    def get(self, generation_id: str) -> Dict[str, Any]:
        return self._maya.call("GET", f"/assist/generations/{generation_id}")

    def attest(self, generation_id: str, *, accept: bool = True,
               final_text: str = "", note: str = "") -> Dict[str, Any]:
        """A person takes responsibility for it — and not the one who asked.

        This is the act that turns a generation into evidence. Refusing it is
        as meaningful as accepting: a rejected generation stays on the record
        with its reason, because a capability whose rejections are deleted has
        no measurable quality.
        """
        return self._maya.call(
            "POST", f"/assist/generations/{generation_id}/attest",
            json={"accept": accept, "final_text": final_text, "note": note})

    def reviewer(self, reviewer: str) -> Dict[str, Any]:
        """One reviewer's record: what they accepted, and how much they changed.

        Edit distance is the automation-bias detector. Somebody accepting
        everything unchanged and somebody reading carefully produce the same
        approval count and very different distributions, and only one of those
        two facts is visible without measuring it.
        """
        return self._maya.call("GET", f"/assist/reviewers/{reviewer}")


__all__ = ["Assist"]
