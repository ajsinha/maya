"""
MAYA — model, version, alias and risk endpoints.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import HTTPException, Query, Request
from pydantic import Field

from core.execution.urn import urn_of
from core.domain import paging
from routes.base import Body, Routes
from core.features.rendering import to_latex, to_python
from core.limitations import KIND_MEANING, KINDS
from core.registry.versions import latest_version


class RelateIn(Body):
    """One model's standing to another. `from` is a Python keyword, so the
    field is `from_urn` and the shape says so rather than being clever."""
    from_urn: str
    to_urn: str
    kind: str
    note: str = ""


class UnrelateIn(Body):
    from_urn: str
    to_urn: str
    kind: str
    reason: str


class ModelIn(Body):
    urn: str
    name: str
    model_class: str
    domain: str
    owner: str
    legal_entity: str
    purpose: str
    description: str = ""
    origin: str = "internal"


class VersionIn(Body):
    semver: str
    kernel: Dict[str, Any] = Field(default_factory=dict)
    contract: Dict[str, Any] = Field(default_factory=dict)
    artifact_digest: Optional[str] = None
    artifact_uri: Optional[str] = None


class AliasIn(Body):
    semver: str
    environment: str = "prod"
    alias: str = "champion"
    justification: str = ""


class LimitationIn(Body):
    urn: str
    semver: str
    kind: str
    statement: str
    basis: str = ""
    #: The contract clause that enforces this, if one does. Checked against the
    #: version's own contract rather than accepted — a limitation claiming an
    #: enforcement that does not exist reads as the safe case and is not.
    bound_key: Optional[str] = None


class WithdrawLimitationIn(Body):
    reason: str


class AssessIn(Body):
    # No defaults on these two. Exposure and purpose are the whole materiality
    # axis, and a default of "nothing, commercial" tiers an unassessed model at
    # the bottom of the lattice on nobody's word.
    exposure: float
    purpose_class: str
    # These three keep their defaults, but the route refuses the request when a
    # default is load-bearing — see `TieringEngine.load_bearing`.
    feature_count: int = 0
    uses_alternative_data: bool = False
    interpretable: bool = True


class ModelRoutes(Routes):
    """The inventory API.

    Every endpoint authorises before it acts, and every act is attributed to the
    principal who made it rather than to "system". That attribution is what the
    segregation policy reads back: a version approved by the person who created
    it is refused because the evidence chain says who created it.
    """

    def register(self) -> None:
        reg, ev = self.ctx["registry"], self.ctx["evidence"]
        composition = self.ctx["composition"]
        tiering, risk_repo = self.ctx["tiering"], self.ctx["risk_repo"]
        # Accepts a bare name or the full urn MAYA prints everywhere; see
        # `core.execution.urn.urn_of` for why the second was a 404.
        urn = urn_of

        @self.app.get(f"{self.api}/models", tags=["models"])
        def list_models(request: Request, domain: Optional[str] = None,
                        tier: Optional[int] = None, q: Optional[str] = None,
                        limit: Optional[int] = None,
                        offset: Optional[int] = None):
            who = self.authorise(request, "model:read")
            # Filtered at the listing, not only at the detail page: a model out
            # of scope must not be discoverable by a count that does not add up.
            #
            # And filtered BEFORE the page is cut, for the same reason: page two
            # of a filtered list must not be page two of the unfiltered one with
            # holes in it.
            visible = self.ctx["authz"].visible(who, reg.list(domain, tier))
            if q:
                needle = q.strip().lower()
                visible = [m for m in visible
                           if needle in f"{m.get('name','')} {m.get('urn','')} "
                                        f"{m.get('owner','')} "
                                        f"{m.get('model_class','')}".lower()]
            return paging.page(visible, limit, offset).as_dict("models")

        # ------------------------------------------------------ composition
        @self.app.get(f"{self.api}/model-relations", tags=["models"])
        def relations(request: Request):
            """The relations one model may have to another, and what each means."""
            self.principal(request)
            from core.registry import ModelComposition
            return ModelComposition.describe()

        @self.app.post(f"{self.api}/model-relations", status_code=201,
                       tags=["models"])
        def relate(request: Request, body: RelateIn):
            """Record that one model stands to another in this way.

            Two relations do different work. `input_to` propagates -- change the
            source and this model's answer changes -- and `derives_from` does
            not: a model built from another has its own versions and its own
            approvals. Conflating them makes a challenger look like a
            dependency and inflates every blast radius it appears in.
            """
            target = self.guard(lambda: reg.require(body.to_urn))
            who = self.authorise(request, "model:amend", model=target)
            return self.guard(lambda: composition.relate(
                body.from_urn, body.to_urn, body.kind, body.note,
                actor=self.actor(who)))

        # A POST rather than a DELETE because it carries a body: removing a
        # relation requires a reason, and a reason does not belong in a query
        # string where it will be truncated and logged.
        @self.app.post(f"{self.api}/model-relations/remove", tags=["models"])
        def unrelate(request: Request, body: UnrelateIn):
            """Remove a relation, with a reason. An edge that disappears without
            one is a dependency somebody stopped believing in and nobody can ask
            about."""
            target = self.guard(lambda: reg.require(body.to_urn))
            who = self.authorise(request, "model:amend", model=target)
            return self.guard(lambda: composition.unrelate(
                body.from_urn, body.to_urn, body.kind, body.reason,
                actor=self.actor(who)))

        @self.app.get(f"{self.api}/models/{{name:path}}/relations", tags=["models"])
        def model_relations(request: Request, name: str):
            """Everything attached to this model, in both directions."""
            model = self.guard(lambda: reg.require(urn(name)))
            self.authorise(request, "model:read", model=model)
            return self.guard(lambda: composition.edges_of(model["urn"]))

        @self.app.post(f"{self.api}/blast-radius", tags=["models"])
        def blast_radius(request: Request, body: Dict[str, Any]):
            """What a change here reaches, and how far away each one is.

            Only propagating relations are followed, so a challenger is not
            downstream of the model it argues with.
            """
            model = self.guard(lambda: reg.require(body["urn"]))
            self.authorise(request, "model:read", model=model)
            return self.guard(lambda: composition.blast_radius(model["urn"]))

        @self.app.post(f"{self.api}/shared-dependencies", tags=["models"])
        def shared(request: Request, body: Dict[str, Any]):
            """What two or more of these models both depend on.

            The obstruction, made computable: a network that COPIES a dependency
            is not the same as one that duplicates it, and that difference is
            why an aggregate risk assignment cannot simply add up. Supervisors
            ask about common dependencies in prose; this answers it.
            """
            self.authorise(request, "model:read")
            return self.guard(lambda: composition.shared_dependencies(
                body.get("urns") or []))

        @self.app.post(f"{self.api}/models", status_code=201, tags=["models"])
        def create_model(request: Request, body: ModelIn):
            who = self.authorise(request, "model:register",
                                 model={"legal_entity": body.legal_entity,
                                        "domain": body.domain})
            return self.guard(lambda: reg.register(
                body.urn, body.name, body.model_class, body.domain, body.owner,
                body.legal_entity, body.purpose, body.description, body.origin,
                actor=self.actor(who)))

        @self.app.get(f"{self.api}/models/{{name:path}}", tags=["models"])
        def get_model(request: Request, name: str):
            m = reg.get(urn(name))
            if not m:
                raise self.not_found(f"no model {name}")
            self.authorise(request, "model:read", model=m)
            # The lifecycle state travels with the model rather than living at
            # /models/{name}/state: the name segment is a greedy `:path`
            # converter and would swallow any suffix registered after it.
            return {"model": m, "versions": reg.versions(m["urn"]),
                    "alias_history": reg.alias_history(m["urn"]),
                    "lifecycle": self.ctx["lifecycle"].state(m["urn"]),
                    "evidence": ev.for_subject(m["id"])}

        @self.app.post(f"{self.api}/models/{{name:path}}/versions", status_code=201,
                       tags=["versions"])
        def create_version(request: Request, name: str, body: VersionIn):
            who = self.authorise(request, "version:create",
                                 model=self.guard(lambda: reg.require(urn(name))))
            return self.guard(lambda: reg.create_version(
                urn(name), body.semver, body.kernel, body.contract,
                body.artifact_digest, body.artifact_uri, actor=self.actor(who)))

        # ------------------------------------------------------- limitations
        @self.app.get(f"{self.api}/limitation-kinds", tags=["models"])
        def limitation_kinds(request: Request):
            """The four kinds, and what each is for. Closed on purpose."""
            self.principal(request)
            return {"kinds": [{"kind": k, "means": KIND_MEANING[k]}
                              for k in KINDS],
                    "detail": "a limitation names the contract clause that "
                              "enforces it, or names none — and none is the "
                              "value worth counting"}

        # A model name is a QUERY parameter here rather than a path segment,
        # which is this API's rule wherever a name is not the last thing in the
        # path: `{name:path}` is greedy, so `/models/x/versions/1.0.0/limitations`
        # resolves `name` to `x/versions/1.0.0/limitations` and answers 404
        # naming a model nobody asked for. Written down in `14 §Addressing`;
        # discovered again here, which is what the rule is for.
        @self.app.get(f"{self.api}/limitations", tags=["models"])
        def limitations(request: Request, urn_: str = Query(..., alias="urn"),
                        semver: str = Query(...)):
            """What this version cannot do, and how much of it is enforced."""
            m = self.guard(lambda: reg.require(urn_of(urn_)))
            self.authorise(request, "limitation:read", model=m)
            return self.guard(
                lambda: self.ctx["limitations"].for_version(urn_of(urn_), semver))

        @self.app.post(f"{self.api}/limitations", status_code=201,
                       tags=["models"])
        def record_limitation(request: Request, body: LimitationIn):
            """State a limitation against one version."""
            m = self.guard(lambda: reg.require(urn_of(body.urn)))
            who = self.authorise(request, "limitation:record", model=m)
            return self.guard(lambda: self.ctx["limitations"].record(
                urn_of(body.urn), body.semver, body.kind, body.statement,
                basis=body.basis, bound_key=body.bound_key,
                actor=self.actor(who)))

        @self.app.post(f"{self.api}/limitations/{{limitation_id}}/withdraw",
                       tags=["models"])
        def withdraw_limitation(request: Request, limitation_id: str,
                                body: WithdrawLimitationIn):
            """Withdraw one. Never deleted: the version is immutable, so what it
            was understood to be is part of the record."""
            row = self.guard(
                lambda: self.ctx["limitations"].require(limitation_id))
            who = self.authorise(request, "limitation:withdraw",
                                 model=self.model_of(row["model_id"]))
            return self.guard(lambda: self.ctx["limitations"].withdraw(
                limitation_id, body.reason, actor=self.actor(who)))

        @self.app.get(f"{self.api}/mathematics", tags=["models"])
        def mathematics(request: Request, name: str = Query(..., alias="urn"),
                        semver: str = Query(...)):
            """The version's kernel as mathematics and as code, both derived.

            Neither is stored. A `latex` field beside the expression, filled in
            by whoever wrote it, is a second description of one model — and two
            descriptions drift, with the one nobody executes drifting first. So
            this renders the syntax tree the platform evaluates, which means a
            disagreement between the equation, the code and the answer is not
            possible rather than merely unlikely.

            Only a `formula` kernel has an expression to render. Every other
            runtime names an artifact MAYA does not read, and inventing an
            equation for one would be exactly the invented description this
            exists to avoid — so it says so instead.
            """
            m = self.guard(lambda: reg.require(urn_of(name)))
            self.authorise(request, "model:read", model=m)
            version = self.guard(
                lambda: reg.version_service.require(urn_of(name), semver))
            kernel = (version.get("manifest") or {}).get("kernel") or {}
            entry = kernel.get("entry") or {}
            expression = entry.get("expression")
            if kernel.get("runtime") != "formula" or not expression:
                raise HTTPException(409, {
                    "error": "not_derivable",
                    "detail": f"version {semver} runs on "
                              f"'{kernel.get('runtime') or 'no runtime'}', which "
                              f"names an artifact rather than carrying its own "
                              f"expression — so there is nothing here to derive "
                              f"an equation from",
                    "remediation": "only a 'formula' kernel is renderable; for "
                                   "everything else the mathematics belongs in "
                                   "an attached document, where a person signs "
                                   "for it"})
            symbols = {f["name"]: f["symbol"]
                       for f in (version.get("input_schema") or [])
                       if isinstance(f, dict) and f.get("symbol")}
            reads = sorted({f["name"] for f in (version.get("input_schema") or [])
                            if isinstance(f, dict) and f.get("name")})
            return {
                "urn": urn_of(name), "semver": semver,
                "expression": expression,
                "target": entry.get("target") or "value",
                "latex": to_latex(expression, symbols),
                "python": to_python(expression, name="predict", inputs=reads),
                "symbols": symbols,
                "detail": "both are derived from the expression at request "
                          "time and neither is stored, so they cannot disagree "
                          "with what runs",
            }

        @self.app.post(f"{self.api}/models/{{name:path}}/versions/{{semver}}/approve",
                       tags=["versions"])
        def approve(request: Request, name: str, semver: str):
            model = self.guard(lambda: reg.require(urn(name)))
            version = reg.version(urn(name), semver)
            if not version:
                raise self.not_found(f"no version {semver} for {name}")
            # The subject is the VERSION, because that is what the evidence chain
            # recorded `version_created` against.
            who = self.authorise(request, "version:approve", model=model,
                                 subject_id=version["id"])
            return self.guard(lambda: reg.approve_version(urn(name), semver,
                                                          actor=self.actor(who)))

        @self.app.put(f"{self.api}/models/{{name:path}}/aliases", tags=["aliases"])
        def move_alias(request: Request, name: str, body: AliasIn):
            model = self.guard(lambda: reg.require(urn(name)))
            version = reg.version(urn(name), body.semver)
            who = self.authorise(request, "alias:move", model=model,
                                 subject_id=version["id"] if version else None)
            return self.guard(lambda: reg.move_alias(
                urn(name), body.environment, body.alias, body.semver,
                actor=self.actor(who), justification=body.justification))

        @self.app.post(f"{self.api}/models/{{name:path}}/assess", tags=["risk"])
        def assess(request: Request, name: str, body: AssessIn):
            m = self.guard(lambda: reg.require(urn(name)))
            who = self.authorise(request, "risk:assess", model=m)
            versions = reg.versions(urn(name))
            facts = {**body.model_dump(),
                     "trainability_class": (latest_version(versions) or {})
                                           .get("trainability_class", "T0")}
            missing = tiering.load_bearing(facts,
                                           body.model_dump(exclude_unset=True))
            if missing:
                raise HTTPException(422, {
                    "error": "fact_not_supplied",
                    "detail": "this assessment lands on a different tier "
                              "depending on " + ", ".join(sorted(missing))
                              + ", and the request did not say",
                    "remediation": "send " + ", ".join(sorted(missing))
                              + "; the schema's defaults are the low-risk "
                                "reading, and defaulting to it silently is "
                                "choosing your own tier"})
            a = tiering.assess(facts)
            tiering.persist(risk_repo, m["id"], a)
            reg.set_tier(m["id"], a.tier)
            ev.append("tier_assigned", "model", m["id"],
                      {"tier": a.tier, "rationale": a.rationale},
                      actor=self.actor(who))
            return {"tier": a.tier, "materiality": a.materiality, "complexity": a.complexity,
                    "required_controls": list(a.required_controls), "rationale": a.rationale,
                    "ruleset_version": a.ruleset_version}

        @self.app.get(f"{self.api}/evidence/chain", tags=["evidence"])
        def chain(request: Request):
            self.authorise(request, "evidence:read")
            return ev.verify_chain()
