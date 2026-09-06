"""
MAYA — warrant issuance, resolution and revocation.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

This is the boundary of the product. MAYA hands out a signed execution contract;
an execution engine acts on it. The captive engine is exposed here too, but only
as one CONSUMER of the same endpoints an external engine uses.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import Request
from pydantic import Field

from core.authz.common import AuthzError, same_person
from core.execution.urn import model_urn, parse_urn
from routes.base import Body, Routes


def strip_qualifier(urn: str) -> str:
    """The bare model urn, with any @semver or #alias removed."""
    return model_urn(parse_urn(urn)[0])


def _model_urn(urn: str) -> str:
    """The model a warrant urn names, with any alias or pinned version dropped.

    `maya://model/x#champion` and `maya://model/x@3.2.1` are the same model for
    the purpose of legal-entity scope, and a hand-rolled `split("#")` gets the
    second one wrong — which is how the scope check first landed here refusing
    a model that plainly exists.
    """
    return model_urn(parse_urn(urn)[0])


class FitIn(Body):
    urn: str
    environment: str = "lab"
    principal: str
    declared_use: str = "model_development"
    featureset: str
    featureset_version: int
    window: dict
    as_of: float


class IssueIn(Body):
    urn: str
    principal: str
    declared_use: str
    environment: str = "prod"
    flavour: str = "descriptor_only"


class ResolveIn(Body):
    urn: str
    principal: str
    declared_use: str
    environment: str = "prod"


class ExecuteIn(ResolveIn):
    inputs: Dict[str, Any] = Field(default_factory=dict)


class RevokeIn(Body):
    urn: str
    reason: str


class WarrantRoutes(Routes):
    def _must_be_self_or_delegated(self, who: Dict[str, Any],
                                   principal: str) -> None:
        """A credential is minted for the caller, or by somebody entitled to
        mint for others.

        `principal` arrives in the request body and used to be taken on trust,
        so any authenticated caller could obtain a signed descriptor naming any
        service account. Holding `warrant:issue` is what makes minting for a
        third party a deliberate, permissioned act rather than a request field.
        """
        if same_person(principal, who.get("username")):
            return
        if "warrant:issue" in self.ctx["authz"].permissions(who):
            return
        raise AuthzError(
            "principal_not_self",
            f"{who.get('username')} asked for a warrant naming '{principal}', "
            f"which is somebody else",
            "resolve a warrant for yourself, or hold warrant:issue to mint one "
            "on another principal's behalf")

    def register(self) -> None:
        warrants, engine = self.ctx["warrants"], self.ctx.get("engine")
        registry = self.ctx["registry"]

        @self.app.post(f"{self.api}/fit-warrants", status_code=201,
                       tags=["warrants"])
        def fit(request: Request, body: FitIn):
            """A signed descriptor to fit this version from that featureset.

            Law L-W10 is checked here: a featureset a warrant names must provide
            what the kernel declares it reads. Adding a regressor is a model
            change, not a data change, and this is where that is enforced rather
            than remembered.
            """
            self.authorise(request, "warrant:issue",
                           model=self.guard(lambda: registry.require(_model_urn(body.urn))))
            return self.guard(lambda: warrants.resolve_fit(
                body.urn, body.environment, body.principal, body.declared_use,
                body.featureset, body.featureset_version, body.window,
                body.as_of))

        @self.app.get(f"{self.api}/engine", tags=["warrants"])
        def engine_boundary(request: Request):
            """What the captive engine is, and what its isolation does not cover.

            Published rather than implied. An engine that runs artifacts owes its
            callers a statement of the boundary, and a name like "sandbox" left
            unexplained implies a guarantee the process model does not provide.
            """
            self.principal(request)
            if engine is None:
                return {"captive_engine": "not enabled",
                        "detail": "this instance issues warrants and runs nothing"}
            return {"captive_engine": "enabled", **engine.isolation()}

        @self.app.post(f"{self.api}/warrants", status_code=201, tags=["warrants"])
        def issue(request: Request, body: IssueIn):
            # The urn names the model, and issuing production authority over
            # a model in another legal entity was the sharpest of the unscoped
            # routes: it granted execution rights, not just a record.
            who = self.authorise(request, "warrant:issue",
                                 model=self.guard(lambda: registry.require(_model_urn(body.urn))))
            return self.guard(lambda: warrants.issue(
                body.urn, body.environment, body.principal, body.declared_use,
                body.flavour, actor=self.actor(who)))

        @self.app.post(f"{self.api}/resolve", tags=["warrants"])
        def resolve(request: Request, body: ResolveIn, verb: str = "score"):
            """The hot path. A signed descriptor, or a refusal with a reason.

            Two things had to change here. It authorised against `warrant:read`,
            which is in the read set and therefore held by every role including
            the auditor -- so anybody could obtain an execution credential. And
            it minted the descriptor for `body.principal` without ever checking
            that against the caller, so anybody could obtain one for anybody.
            Passing no `model=` meant scope was skipped as well, so it worked
            across legal entities.
            """
            # `get`, not `require`: an unknown model is a 404 here, and
            # `require` refuses with a conflict shaped for a different caller.
            model = self.guard(lambda: registry.get(strip_qualifier(body.urn)))
            if model is None:
                raise self.not_found(f"no model {body.urn}")
            who = self.authorise(request, "warrant:resolve", model=model)
            self._must_be_self_or_delegated(who, body.principal)
            return self.guard(lambda: warrants.resolve(
                body.urn, body.environment, body.principal, body.declared_use, verb))

        @self.app.post(f"{self.api}/warrants/revoke", tags=["warrants"])
        def revoke(request: Request, body: RevokeIn):
            who = self.authorise(request, "warrant:revoke",
                                 model=self.guard(lambda: registry.require(_model_urn(body.urn))))
            n = self.guard(lambda: warrants.revoke_model(body.urn, body.reason,
                                                         actor=self.actor(who)))
            return {"revoked": n, "urn": body.urn, "reason": body.reason,
                    "epoch": warrants.epoch}

        @self.app.post(f"{self.api}/execute", tags=["execution"])
        def execute(request: Request, body: ExecuteIn):
            model = self.guard(lambda: registry.get(strip_qualifier(body.urn)))
            if model is None:
                raise self.not_found(f"no model {body.urn}")
            who = self.authorise(request, "warrant:execute", model=model)
            self._must_be_self_or_delegated(who, body.principal)
            """Convenience only: the captive engine, reached through the same
            contract an external engine uses. Disable it and nothing else changes."""
            if engine is None:
                raise self.not_found("no captive engine is configured; resolve the warrant "
                                     "and run the model in your own execution engine")
            return self.guard(lambda: engine.execute(
                body.urn, body.environment, body.principal, body.declared_use,
                body.inputs).__dict__)
