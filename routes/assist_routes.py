"""
MAYA — machine assistance.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The platform's own AI, and the controls on it. Note what is missing: there is no
endpoint that makes a governance decision from a generation. A draft becomes
consequential only when a person attests it, and that is a separate call made by
somebody other than whoever asked for the draft.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException, Request
from pydantic import Field

from core.assist import TIER_MEANING, oracles
from core.assist import providers as assist_providers
from routes.base import Body, Routes


class CapabilityIn(Body):
    capability_key: str
    description: str
    tier: str
    base_model: str
    prompt_digest: str
    owner: str
    oracle_key: Optional[str] = None
    autonomy: str = "human_approved_automation"
    review_sample: float = 0.1


class DraftIn(Body):
    capability_key: str
    subject_type: str
    subject_id: str
    instruction: str = ""
    oracle_payload: Optional[dict] = None


class GenerateIn(Body):
    capability_key: str
    subject_type: str
    subject_id: str
    claims: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="each with text and the evidence ids it cites")
    known_evidence: List[str] = Field(default_factory=list)
    oracle_payload: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)


class BudgetIn(Body):
    tokens: Optional[float] = None
    cost: Optional[float] = None
    steps: Optional[float] = None
    window_days: Optional[float] = None


class AttestIn(Body):
    accept: bool = True
    final_text: str = ""
    note: str = ""


class AssistRoutes(Routes):
    def register(self) -> None:
        capabilities, generations = self.ctx["capabilities"], self.ctx["generations"]
        api = self.api

        @self.app.get(f"{api}/assist/tiers", tags=["assistance"])
        def tiers(request: Request):
            """The two registrable tiers, and the oracles Tier A can name."""
            self.principal(request)
            return {"tiers": [{"tier": t, "means": m} for t, m in TIER_MEANING.items()],
                    "oracles": oracles.describe(),
                    "note": ("Tier C — output that can be neither checked nor "
                             "grounded — is deliberately not registrable: that is "
                             "a person using a chat window, not a platform "
                             "capability.")}

        @self.app.get(f"{api}/assist/capabilities", tags=["assistance"])
        def list_capabilities(request: Request):
            self.authorise(request, "assist:read")
            return {"capabilities": capabilities.list()}

        @self.app.post(f"{api}/assist/capabilities", status_code=201,
                       tags=["assistance"])
        def register_capability(request: Request, body: CapabilityIn):
            who = self.authorise(request, "assist:register")
            return self.guard(lambda: capabilities.register(
                body.capability_key, body.description, body.tier, body.base_model,
                body.prompt_digest, body.owner, body.oracle_key, body.autonomy,
                body.review_sample, actor=self.actor(who)))

        @self.app.get(f"{api}/assist/canaries", tags=["assistance"])
        def canaries_estate(request: Request):
            """Whether the model under each capability's version string moved.

            A `base_model` string identifies nothing: a hosted model is
            re-trained, quantised and rolled forward while the string it answers
            to stays the same. Fixed trivial probes, digested at evaluation
            time, compared now.

            Read `without_a_baseline` as the absence of a clean bill of health
            rather than one, and `unfingerprintable` as an honest answer — a
            model that will not give the same probe the same answer twice cannot
            be fingerprinted, and a digest moving on every check is an alarm
            that consumes exactly the attention a real change would need.
            """
            self.authorise(request, "assist:read")
            return self.guard(
                lambda: self.ctx["canaries"].across_the_estate())

        @self.app.post(f"{api}/assist/canaries/{{capability_key}}",
                       status_code=201, tags=["assistance"])
        def take_canary(request: Request, capability_key: str):
            """Record what this capability's model answers today.

            Taken at evaluation — the moment the platform decides what it thinks
            of a capability, and therefore the moment worth being able to name
            the model it thought that about. Probes that disagree with
            themselves across repeats are excluded by name.
            """
            who = self.authorise(request, "assist:register")
            return self.guard(lambda: self.ctx["canaries"].take(
                capability_key, actor=self.actor(who)))

        @self.app.get(f"{api}/assist/canaries/{{capability_key}}",
                      tags=["assistance"])
        def check_canary(request: Request, capability_key: str):
            """Has it moved? A trigger, never a verdict.

            Temperature, a sampling seed or different hardware all move the
            output without the weights moving, so nothing is suspended. What
            changes on a hit is that the review sample goes back to 1.0: every
            accepted draft and every clean sample was measured against weights
            that have apparently moved, so that evidence is not wrong — it is
            about something else.
            """
            who = self.authorise(request, "assist:read")
            return self.guard(lambda: self.ctx["canaries"].check(
                capability_key, actor=self.actor(who)))

        @self.app.get(f"{api}/assist/injection", tags=["assistance"])
        def injection_sweep(request: Request):
            """Register rows carrying content shaped like an instruction.

            A **signal, never a gate**. This is a blocklist and the adversary
            can write anything — synonyms, another language, base64, a
            homoglyph — so a clean sweep means nothing was recognised, not that
            nothing is there. What holds is structural: register content is
            fenced behind a nonce generated when the prompt is assembled, which
            content written earlier cannot contain.

            Nothing is removed. The words are evidence that somebody wrote
            them, and a control whose only output is a quieter prompt is one
            nobody can audit.
            """
            self.authorise(request, "assist:read")
            from core.assist import injection
            return self.guard(lambda: injection.sweep(self.ctx["evidence"]))

        @self.app.get(f"{api}/assist/budgets", tags=["assistance"])
        def budgets_estate(request: Request):
            """Every capability, what it may spend and what it has spent.

            The column worth reading is `on_default`. A capability nobody set a
            budget for is not unbudgeted — it runs on a number this platform
            chose, and reporting that as though somebody decided it is how a
            default becomes permanent. The other is
            `calls_that_produced_nothing`: spend that bought nothing is the
            number that says a capability is not working rather than busy.
            """
            self.authorise(request, "assist:read")
            return self.guard(
                lambda: self.ctx["assist_budgets"].across_the_estate())

        @self.app.get(f"{api}/assist/budgets/{{capability_key}}",
                      tags=["assistance"])
        def budget_of(request: Request, capability_key: str):
            """What this capability may spend, and how much is left."""
            self.authorise(request, "assist:read")
            return self.guard(
                lambda: self.ctx["assist_budgets"].of(capability_key))

        @self.app.put(f"{api}/assist/budgets/{{capability_key}}",
                      tags=["assistance"])
        def set_budget(request: Request, capability_key: str, body: BudgetIn):
            """Declare what this capability may spend per rolling window.

            Three numbers, because they bound three different failures. Tokens
            bound a prompt that grew, cost bounds the invoice, and **steps bound
            a loop** — a runaway agent is a large number of small calls, and it
            passes a token budget and a cost budget for a long time before
            either notices.

            A window rather than a lifetime cap: a lifetime cap is reached once
            and then the capability is dead forever, which is how budgets end up
            raised to a number that means nothing.
            """
            who = self.authorise(request, "assist:register")
            return self.guard(lambda: self.ctx["assist_budgets"].set(
                capability_key, tokens=body.tokens, cost=body.cost,
                steps=body.steps, window_days=body.window_days,
                actor=self.actor(who)))

        @self.app.post(f"{api}/assist/generations", status_code=201,
                       tags=["assistance"])
        def generate(request: Request, body: GenerateIn):
            """Record a generation, gated. Ungrounded claims never reach the output."""
            who = self.authorise(
                request, "assist:generate",
                model=self.model_of_subject(body.subject_type, body.subject_id))
            return self.guard(lambda: generations.record(
                body.capability_key, body.subject_type, body.subject_id,
                body.claims, body.known_evidence, body.oracle_payload,
                body.output, actor=self.actor(who)))

        @self.app.get(f"{api}/assist/providers", tags=["assistance"])
        def list_providers(request: Request):
            """Which model this instance can ask, and why it cannot ask the rest."""
            self.principal(request)
            drafting = self.ctx.get("drafting")
            return {"providers": assist_providers.describe(),
                    "in_force": drafting.describe() if drafting else {
                        "provider": None, "usable": False,
                        "why_not": "no drafting service is configured"}}

        @self.app.post(f"{api}/assist/drafts", status_code=201,
                       tags=["assistance"])
        def draft(request: Request, body: DraftIn):
            """Ask the configured provider for a draft about this subject.

            What the model may cite is fixed from the register BEFORE it is
            asked, so a citation it invents has nowhere to land. The result runs
            through the same gate a hand-delivered generation does, and lands
            drafted -- never evidence -- until a person attests it.
            """
            who = self.authorise(
                request, "assist:generate",
                model=self.model_of_subject(body.subject_type, body.subject_id))
            drafting = self.ctx.get("drafting")
            if drafting is None:
                raise HTTPException(501, {
                    "error": "no_drafting_service",
                    "detail": "this instance has no assist provider configured, "
                              "so it can record a generation produced elsewhere "
                              "but cannot ask for one",
                    "remediation": "set assist.provider in configuration"})
            return self.guard(lambda: drafting.draft(
                body.capability_key, body.subject_type, body.subject_id,
                body.instruction, body.oracle_payload, actor=self.actor(who)))

        @self.app.get(f"{api}/assist/generations/{{generation_id}}",
                      tags=["assistance"])
        def read(request: Request, generation_id: str):
            self.authorise(request, "assist:read")
            return self.guard(lambda: generations.require(generation_id))

        @self.app.post(f"{api}/assist/generations/{{generation_id}}/attest",
                       tags=["assistance"])
        def attest(request: Request, generation_id: str, body: AttestIn):
            """A person takes responsibility for it. Never the requester."""
            generation = self.guard(lambda: generations.require(generation_id))
            who = self.authorise(
                request, "assist:attest",
                model=self.model_of_subject(generation["subject_type"],
                                            generation["subject_id"]))
            return self.guard(lambda: generations.attest(
                generation_id, self.actor(who), body.final_text, body.accept,
                body.note))

        @self.app.get(f"{api}/assist/reviewers/{{reviewer}}", tags=["assistance"])
        def reviewer(request: Request, reviewer: str):
            """Is this reviewer still reading? A falling edit distance says not."""
            self.authorise(request, "assist:read")
            return generations.automation_bias(reviewer)
