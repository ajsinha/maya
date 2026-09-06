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
