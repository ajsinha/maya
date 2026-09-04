"""
MAYA — supervisory regimes.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Several supervisors at once, each in its own vocabulary. Every determination
carries the terms it read and the citation it rests on, because "why is this
model in scope for the AI Act" is the question that gets asked and "the system
said so" has never been an answer.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import Request

from routes.base import Routes


class RegimeRoutes(Routes):
    def register(self) -> None:
        regimes, registry = self.ctx["regimes"], self.ctx["registry"]
        documents = self.ctx["documents"]
        api = self.api

        @self.app.get(f"{api}/regimes", tags=["regimes"])
        def catalogue(request: Request):
            """Every encoded regime, its vocabulary, and whether it is active."""
            self.authorise(request, "regime:read")
            active = set(regimes.active())
            return {"regimes": [
                {"key": key, "title": r["title"], "authority": r["authority"],
                 "active": key in active,
                 "vocabulary": sorted(r["signature"].terms),
                 "obligations": [{"key": s.key, "text": s.text,
                                  "citation": s.citation} for s in r["sentences"]]}
                for key, r in sorted(regimes.library.items())]}

        @self.app.get(f"{api}/regimes/{{key}}/satisfaction", tags=["regimes"])
        def satisfaction(request: Request, key: str):
            """Does truth survive translation into this regime's vocabulary?"""
            self.authorise(request, "regime:read")
            return self.guard(lambda: regimes.check(key))

        @self.app.post(f"{api}/regimes/{{key}}/activate", tags=["regimes"])
        def activate(request: Request, key: str):
            """Turn a regime on. Refused if its encoding is inconsistent."""
            who = self.authorise(request, "regime:activate")
            return self.guard(lambda: regimes.activate(key, self.actor(who)))

        @self.app.get(f"{api}/regimes/determinations", tags=["regimes"])
        def determinations(request: Request, urn: str):
            """Every activated regime's verdict on one model, kept apart."""
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "regime:read", model=model)
            state = regimes.core_state(documents.build_context(urn))
            return {"model": urn, "core_state": state,
                    **regimes.determine_all(state)}
