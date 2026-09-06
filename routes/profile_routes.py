"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Warrant profiles over HTTP.

The endpoint people will actually use is the preview: "given this model and this
environment, what would a profile fill in, and which profile said so". A default
whose origin cannot be named is a value nobody can argue with later, so the
answer carries the derivation rather than the result.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Request
from pydantic import BaseModel, Field

from core.execution.profiles import (AUTHORITY_KEYS, DEFAULTABLE,
                                     SELECTABLE_FACTS, facts_for)
from core.execution.urn import model_urn as urn
from routes.base import Routes
from core.registry.versions import latest_version


class ProfileIn(BaseModel):
    name: str
    when: Dict[str, Any] = Field(default_factory=dict)
    defaults: Dict[str, Any] = Field(default_factory=dict)
    note: str = ""


class PreviewIn(BaseModel):
    urn: str
    semver: Optional[str] = None
    environment: str = "prod"
    request: Dict[str, Any] = Field(default_factory=dict)


class ProfileRoutes(Routes):
    def register(self) -> None:
        api = self.api
        profiles = self.ctx["warrant_profiles"]
        registry = self.ctx["registry"]

        @self.app.get(f"{api}/warrant-profile-vocabulary", tags=["warrants"])
        def vocabulary(request: Request):
            """What a profile may select on, and what it may fill in.

            Published rather than documented, because the two lists ARE the
            design: a profile selects on facts the platform derives and fills in
            what a caller could have typed, and everything else is refused.
            """
            self.principal(request)
            return {"selectable_facts": SELECTABLE_FACTS,
                    "defaultable": DEFAULTABLE,
                    "never_defaultable": list(AUTHORITY_KEYS),
                    "detail": "a profile fills holes in a request; it never "
                              "overrides a caller and never widens authority"}

        @self.app.get(f"{api}/warrant-profiles", tags=["warrants"])
        def listing(request: Request):
            """The live profiles, least specific first — the order they fold in."""
            self.principal(request)
            return {"profiles": profiles.list()}

        @self.app.post(f"{api}/warrant-profiles", status_code=201, tags=["warrants"])
        def create(request: Request, body: ProfileIn):
            who = self.authorise(request, "warrant:issue")
            return self.guard(lambda: profiles.create(
                body.name, body.when, body.defaults, body.note,
                actor=self.actor(who)))

        @self.app.post(f"{api}/warrant-profiles/{{name}}/retire", tags=["warrants"])
        def retire(request: Request, name: str):
            who = self.authorise(request, "warrant:issue")
            return self.guard(lambda: profiles.retire(name, actor=self.actor(who)))

        @self.app.post(f"{api}/warrant-profiles/preview", tags=["warrants"])
        def preview(request: Request, body: PreviewIn):
            """What would apply to this model, and where each value came from.

            Read before issuing rather than discovered afterwards: the same fold
            the issuer runs, reported instead of applied.
            """
            self.principal(request)
            model = self.guard(lambda: registry.require(urn(body.urn)))
            version = (registry.version(model["urn"], body.semver) if body.semver
                       else self._latest(model))
            if version is None:
                raise self.not_found(
                    f"{model['urn']} has no version to profile against")
            facts = facts_for(model, version, body.environment)
            out = profiles.apply(facts, body.request)
            out["facts"] = facts
            return out

    def _latest(self, model: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        versions = self.ctx["registry"].versions(model["urn"])
        return latest_version(versions)
