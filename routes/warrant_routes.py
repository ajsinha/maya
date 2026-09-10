"""
MAYA — warrant issuance, resolution and revocation.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

This is the boundary of the product. MAYA hands out a signed execution contract;
an execution engine acts on it. The captive engine is exposed here too, but only
as one CONSUMER of the same endpoints an external engine uses.
"""
from __future__ import annotations

import time

from typing import Any, Dict, Optional

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


class ZoneAttestIn(Body):
    warrant_id: str
    ran_in: str
    authorised: str


class LimitsIn(Body):
    rate: Optional[int] = None
    quota: Optional[int] = None
    cost: Optional[float] = None
    window_hours: Optional[float] = None


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

        @self.app.get(f"{self.api}/compute-zones", tags=["warrants"])
        def compute_zones(request: Request):
            """Where a fit on sensitive data is allowed to happen.

            Enforced at **warrant issue**, because MAYA does not run the
            training and cannot observe which machine read the rows — a
            platform claiming to enforce residency by watching would be
            claiming something it has no way to check. What it can do is
            decline to authorise the run.

            An unlisted zone handles no more than the weakest class, so a
            restricted fit into an unconfigured estate is refused rather than
            allowed by omission.
            """
            self.authorise(request, "warrant:read")
            return self.guard(lambda: self.ctx["compute_zones"].describe())

        @self.app.post(f"{self.api}/compute-zones/attest", tags=["warrants"])
        def attest_zone(request: Request, body: ZoneAttestIn):
            """The executor states where it actually ran.

            An **attestation, not an observation**. A mismatch is a finding
            rather than a refusal: by the time it is known the run has already
            happened, and refusing here would be theatre.
            """
            # The model is looked up from the warrant rather than taken from
            # the caller: `warrant:execute` is a permission about one model, and
            # a legal-entity scope that is not applied is not a scope.
            grant = self.ctx["warrants"].grants.repo.one(id=body.warrant_id)
            model = (self.ctx["registry"].by_id(grant["model_id"])
                     if grant else None)
            who = self.authorise(request, "warrant:execute", model=model)
            return self.guard(lambda: self.ctx["compute_zones"].attest(
                body.warrant_id, ran_in=body.ran_in,
                authorised=body.authorised, actor=self.actor(who)))

        @self.app.get(f"{self.api}/grant-limits", tags=["warrants"])
        def grant_limits(request: Request):
            """Every live grant, and how close it is to its limits.

            Read `unlimited` first: a grant with no limit of any kind is a
            decision nobody has taken rather than one they have, and this
            reports it rather than treating it as the normal state.
            """
            self.authorise(request, "warrant:read")
            return self.guard(
                lambda: self.ctx["grant_quotas"].across_the_estate())

        @self.app.get(f"{self.api}/grant-limits/{{warrant_id}}",
                      tags=["warrants"])
        def grant_limit(request: Request, warrant_id: str):
            """One grant's limits, what it has spent, and what is left."""
            self.authorise(request, "warrant:read")
            return self.guard(lambda: self.ctx["grant_quotas"].of(warrant_id))

        @self.app.put(f"{self.api}/grant-limits/{{warrant_id}}",
                      tags=["warrants"])
        def set_grant_limit(request: Request, warrant_id: str,
                            body: LimitsIn):
            """Declare what this grant may spend.

            Three limits, and they are not three sizes of the same thing. The
            **rate** protects the downstream system from a loop; the **quota**
            protects the authorisation from being used more than anybody
            intended, which no rate limit would notice because none of it is
            fast; the **cost** budget is the only one whose unit is not calls,
            and is therefore the one that matters for a token-metered model
            where ten calls can cost more than ten thousand.

            On the grant rather than the principal: a service account holding
            four grants should not have one runaway use exhaust the other three.

            `warrant:issue`, because setting terms on a grant is the same
            authority as issuing one: somebody who may create a grant with no
            limits at all can hardly be refused the ability to put limits on it.
            And that permission is about one model, so the model is loaded and
            named — a legal-entity scope that is not applied is not a scope.
            """
            quotas = self.ctx["grant_quotas"]
            grant = self.guard(lambda: quotas.of(warrant_id))
            model = self.ctx["registry"].by_id(grant["model_id"])
            who = self.authorise(request, "warrant:issue", model=model)
            return self.guard(lambda: quotas.set(
                warrant_id, rate=body.rate, quota=body.quota, cost=body.cost,
                window_hours=body.window_hours, actor=self.actor(who)))

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

        @self.app.get(f"{self.api}/warrants", tags=["warrants"])
        def standing(request: Request, model: str = "", environment: str = "",
                     principal: str = "", live: bool = False):
            """Who currently holds authority to run what, and until when.

            This existed as a screen and not as an endpoint, which is the wrong
            way round on a platform whose stated rule is that a screen is a
            client of the same API. `POST /api/v1/warrants` issues one, and a
            `GET` on the same path answered **405** — so the estate-wide
            question a day-to-day administrator asks most often could be seen
            in a browser and not read by a script, and nothing that watches
            this platform could tell you what was about to lapse.

            Ordered soonest-to-lapse rather than by model, because the reason
            to read this list is to find what is about to stop working, or what
            should have stopped and has not. Revoked grants sort last and are
            still listed: a withdrawn authority is part of the record of who
            could once do what, and dropping it from the default view would
            make the list answer a narrower question than it appears to.

            Scoped like every other listing. A grant says who may run a model,
            so somebody the API refuses that model to does not see its grants —
            filtered by `visible()` rather than by a check on each row, which
            is how a listing and a detail page come to disagree.
            """
            who = self.principal(request)
            self.ctx["authz"].authorise(who, "warrant:read")
            readable = {m["urn"] for m in
                        self.ctx["authz"].visible(who, registry.list())}
            now = time.time()
            rows = []
            for grant in warrants.every_grant():
                if grant.get("model_urn") not in readable:
                    continue
                if model and grant.get("model_urn") != model \
                        and grant.get("model_name") != model:
                    continue
                if environment and grant.get("environment") != environment:
                    continue
                if principal and grant.get("principal") != principal:
                    continue
                expires = grant.get("expires_at")
                grant["lapsed"] = bool(expires and expires <= now)
                grant["lapses_in_days"] = (round((expires - now) / 86400.0, 1)
                                           if expires else None)
                if live and (grant["lapsed"] or grant.get("revoked")):
                    continue
                rows.append(grant)
            return {"warrants": rows, "count": len(rows),
                    # The number the caller most often wants next, said once
                    # here rather than derived differently by each of them.
                    "live": sum(1 for r in rows
                                if not r["lapsed"] and not r.get("revoked")),
                    "epoch": warrants.epoch, "as_at": now}

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

        @self.app.get(f"{self.api}/warrant-catalogue", tags=["execution"])
        def warrant_catalogue(request: Request):
            """Every standing grant, and whether anybody uses it.

            The first three columns — what exists, who holds it, what it points
            at — were always answerable per model and never across the estate.
            The last three could not be answered at all until invocations were
            recorded, and the one that matters is the third: a grant nobody has
            exercised is an authorisation the estate is carrying for no reason.
            """
            self.authorise(request, "warrant:read",
                           estate_wide="reading every standing grant and how "
                                       "much each one is used")
            return self.guard(lambda: self.ctx["invocations"].catalogue())

        @self.app.get(f"{self.api}/invocations", tags=["execution"])
        def invocations(request: Request, urn: str):
            """How much this model is actually used, and how it goes."""
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "warrant:read", model=model)
            return {"model": urn,
                    **self.guard(lambda: self.ctx["invocations"].for_model(
                        model["id"]))}

        @self.app.get(f"{self.api}/use-reconciliation", tags=["execution"])
        def use_reconciliation(request: Request, urn: str):
            """What this model was approved for, against what it is used for.

            Every individual call is already legitimate: a declared use is
            checked at resolution against the grant that carries it. Off-label
            use is not a bad call — it is a pattern of good ones, and this is
            the only thing that looks at the pattern.
            """
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "warrant:read", model=model)
            return self.guard(
                lambda: self.ctx["use_reconciliation"].for_model(urn))

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
