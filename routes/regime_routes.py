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


from fastapi import Request

from routes.base import Body, Routes


class EncodingIn(Body):
    """Regulatory prose, and a name to argue about it under.

    Deliberately no field for a predicate, an expression or a rule. A proposal
    carries a form name and term names; the sentence is built by MAYA's own
    constructors, and anything else a caller sends is discarded and listed.
    """
    name: str
    text: str
    citation: str = ""


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

        # ------------------------------------------- proposing an encoding
        @self.app.get(f"{api}/regime-encoding", tags=["regimes"])
        def encoding_forms(request: Request):
            """The forms, the modal cues and the boundary — published first.

            A proposal names a form and some terms; MAYA builds the sentence
            from its own constructors, so no predicate ever crosses the
            boundary.
            """
            self.authorise(request, "regime:read")
            return self.ctx["regime_encoding"].describe()

        @self.app.post(f"{api}/regime-encoding", tags=["regimes"])
        def propose_encoding(request: Request, body: EncodingIn):
            """Read obligations out of regulatory prose and propose an encoding.

            **Nothing here is activated.** The output is a candidate somebody
            reads, argues with and writes into the library themselves — a regime
            that entered force because a machine proposed it and a check passed
            would mean the institution's obligations were set by something with
            no standing to set them.
            """
            self.authorise(request, "regime:activate",
                           estate_wide="proposing an encoding of a regime that "
                                       "would bind the whole estate")
            return self.guard(lambda: self.ctx["regime_encoding"].propose(
                body.name, body.text, citation=body.citation))
