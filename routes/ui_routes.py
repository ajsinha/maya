"""
MAYA — the authenticated interface.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The UI holds no governance logic: it renders decisions the services computed,
with their rationale. Every asset is vendored, so it renders air-gapped.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import Request
from fastapi.responses import HTMLResponse

from routes.base import Routes, login_required


class UIRoutes(Routes):
    def register(self) -> None:
        @self.app.get("/dashboard", response_class=HTMLResponse, tags=["ui"])
        def dashboard(request: Request):
            if (r := login_required(request)) is not None:
                return r
            models = self.ctx["authz"].visible(self.principal(request),
                                               self.ctx["registry"].list())
            by_tier: Dict[Any, int] = {}
            for m in models:
                by_tier[m["tier"]] = by_tier.get(m["tier"], 0) + 1
            who = self.principal(request)
            return self.page(
                request, "dashboard.html", models=models, by_tier=by_tier,
                chain=self.ctx["evidence"].verify_chain(),
                estate=self.ctx["estate"].of(models),
                work=self.ctx["worklist"].mine(who, self.ctx["authz"], models))

        @self.app.get("/model/{name:path}", response_class=HTMLResponse, tags=["ui"])
        def model_detail(request: Request, name: str):
            if (r := login_required(request)) is not None:
                return r
            registry, urn = self.ctx["registry"], f"maya://model/{name}"
            m = registry.get(urn)
            if not m:
                return self.page(request, "not_found.html", status=404, name=name)
            versions = registry.versions(urn)
            features, register = self.ctx["features"], self.ctx["findings"]
            docs = self.ctx["documents"]
            return self.page(
                request, "model.html", model=m, versions=versions,
                history=registry.alias_history(urn),
                warrants=self.ctx["warrants"].grants_for(urn),
                evidence=self.ctx["evidence"].for_subject(m["id"]),
                # A model's features are the view versions its contracts pin —
                # per model version, because that is the granularity a contract
                # binds at and the granularity serving reads at.
                contracts=[(v, features.contract_for(v["id"])) for v in versions],
                findings=register.open_for(m["id"]),
                finding_summary=register.summary(m["id"]),
                validations=self.ctx["validation"].for_model(urn),
                flow=self.ctx["lifecycle"].state(urn), now=time.time(),
                monitoring=self.ctx["monitoring"].status(m["id"]),
                documents=[{**d, "staleness": docs.staleness(d["id"])}
                           for d in docs.for_model(m["id"])],
                # Compiled documents and filed ones are different things and
                # are shown as different things: one MAYA wrote, one somebody did.
                # Fitting does not change the kernel; it inhabits P. So the page
                # shows the parameter sets a version may run at, per version.
                approvals={v["semver"]: self.ctx["approvals"].needed(urn, v["semver"])
                           for v in versions},
                parameters={v["semver"]: self.ctx["parameters"].status(urn, v["semver"])
                            for v in versions},
                parameter_sets=[p for v in versions
                                for p in self.ctx["parameters"].for_version(
                                    urn, v["semver"])],
                attachments=self.ctx["attachments"].for_model(m["id"]),
                attachment_status=self.ctx["attachments"].status(m["id"]),
                overlays=self.ctx["overlays"].status(m["id"]),
                regimes=self.ctx["regimes"].determine_all(
                    self.ctx["regimes"].core_state(docs.build_context(urn))))

        # ------------------------------------------------------- features
        @self.app.get("/features", response_class=HTMLResponse, tags=["ui"])
        def features_page(request: Request):
            """The catalogue: what is defined, what is derived, what is served."""
            if (r := login_required(request)) is not None:
                return r
            f = self.ctx["features"]
            catalogue = f.list_features()
            derived = {d["name"]: d for d in f.derived.list()} if f.derived else {}
            views = []
            for view in f.views.views.many():
                versions = f.views.versions_of(view["name"])
                views.append({**view, "versions": versions,
                              "latest": versions[-1] if versions else None})
            return self.page(
                request, "features.html", features=catalogue, derived=derived,
                views=views,
                language=__import__("core.features.expressions",
                                    fromlist=["describe"]).describe())

        @self.app.get("/feature-views/{name}", response_class=HTMLResponse,
                      tags=["ui"])
        def feature_view_page(request: Request, name: str):
            if (r := login_required(request)) is not None:
                return r
            f = self.ctx["features"]
            view = f.views.views.one(name=name)
            if not view:
                return self.page(request, "not_found.html", status=404, name=name)
            versions = f.views.versions_of(name)
            return self.page(request, "feature_view.html", view=view,
                             versions=[{**v, **f.views.restated(name, v["version"])}
                                       for v in versions])

        # ---------------------------------------------------- featuresets
        @self.app.get("/featuresets", response_class=HTMLResponse, tags=["ui"])
        def featuresets_page(request: Request):
            if (r := login_required(request)) is not None:
                return r
            f = self.ctx["features"]
            rows = []
            for row in f.sets.list():
                versions = f.sets.versions_of(row["name"])
                rows.append({**row, "versions": versions,
                             "latest": versions[-1] if versions else None})
            return self.page(request, "featuresets.html", featuresets=rows,
                             catalogue=f.list_features())

        @self.app.get("/featureset/{name}", response_class=HTMLResponse,
                      tags=["ui"])
        def featureset_page(request: Request, name: str):
            if (r := login_required(request)) is not None:
                return r
            f = self.ctx["features"]
            row = f.sets.get(name)
            if not row:
                return self.page(request, "not_found.html", status=404, name=name)
            versions = f.sets.versions_of(name)
            return self.page(
                request, "featureset.html", featureset=row, versions=versions,
                plans={v["version"]: f.featureset_plan(name, v["version"])
                       for v in versions},
                restatements={v["version"]: f.restatements(name, v["version"])
                              for v in versions},
                catalogue=f.list_features())

        # -------------------------------------------------------- new model
        @self.app.get("/models/new", response_class=HTMLResponse, tags=["ui"])
        def new_model_page(request: Request):
            """Create a model, or upload a version of one that already exists."""
            if (r := login_required(request)) is not None:
                return r
            from core.domain.algebra import FitProcedure, OutputKind, ParameterKind
            from core.execution.grammar import RUNTIME_ENTRY
            return self.page(
                request, "new_model.html",
                models=self.ctx["registry"].list(),
                parameter_kinds=[k.value for k in ParameterKind],
                fit_procedures=[p.value for p in FitProcedure],
                output_kinds=[k.value for k in OutputKind],
                runtimes=sorted(RUNTIME_ENTRY),
                runtime_entry={k: list(v) for k, v in RUNTIME_ENTRY.items()})

        @self.app.get("/document/{document_id}", response_class=HTMLResponse,
                      tags=["ui"])
        def document(request: Request, document_id: str):
            """A compiled document, rendered with the same markdown pipeline the
            help system uses. One renderer, so a document reads like the rest of
            the platform rather than like a report generator's output."""
            if (r := login_required(request)) is not None:
                return r
            docs = self.ctx["documents"]
            doc = docs.get(document_id)
            if not doc:
                return self.page(request, "not_found.html", status=404,
                                 name=f"document/{document_id}")
            html, headings = self.ctx["renderer"].render(docs.markdown(doc))
            model = self.ctx["registry"].catalogue.models.one(id=doc["model_id"])
            return self.page(request, "document.html", doc=doc, model=model,
                             body=html,
                             anchors=[h for h in headings if h["level"] == 2],
                             staleness=docs.staleness(document_id),
                             citations=docs.verify_citations(document_id))
