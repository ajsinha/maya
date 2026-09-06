"""
MAYA — the authenticated interface.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The UI holds no governance logic: it renders decisions the services computed,
with their rationale. Every asset is vendored, so it renders air-gapped.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from fastapi import Request
from fastapi.responses import HTMLResponse

from core.execution.urn import model_urn as urn
from core.notify import CHANNEL_MEANING
from core.parameters import PROVENANCE_MEANING
from core.policy import GATES, describe_facts
from core.policy.language import describe as describe_language
from core.features.common import SUGGESTED_DTYPES
from core.features.transfer import accept_attribute
from core.telemetry import STREAM_MEANING
from core.log import get_logger, swallowed
from routes.base import Routes, login_required
from core.registry.versions import latest_version

logger = get_logger(__name__)

# Worst first, and stated once. A list of findings sorted by when they were
# raised buries the Critical one under three Observations.
_SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3,
                   "Observation": 4}


def _rule_vocabulary() -> dict:
    """The operator list, from the code. A screen holding its own copy is a
    second vocabulary that drifts from the first."""
    from core.rules.common import OPERATOR_MEANING, OPERATORS, ORDERED_ONLY
    return {"operators": [{"op": op, "means": OPERATOR_MEANING[op],
                           "needs_ordered_field": op in ORDERED_ONLY}
                          for op in OPERATORS]}


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
                return self.page(request, "not_found.html", http_status=404, name=name)
            # Scope, by the same rule the API applies. Without this the page
            # served a model the API refuses -- versions, alias history, warrant
            # grants and the whole evidence chain.
            if not self.may_view(request, "model:read", m):
                return self.refused_page(request, f"The model {name}")
            versions = registry.versions(urn)
            features, register = self.ctx["features"], self.ctx["findings"]
            docs = self.ctx["documents"]
            return self.page(
                request, "model.html", model=m, versions=versions,
                # The definition the platform is organised around, assembled
                # once here rather than by a reader across four cards.
                kernel_type=_kernel_type(versions),
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
            # Resolved one at a time, and a refusal is shown rather than
            # thrown.
            #
            # This was an unguarded comprehension, so ONE feature the resolver
            # refuses — a composition whose parent has moved, say — took the
            # whole catalogue down with a 500 and twenty-one bytes of plain
            # text. Every feature in the estate became unreadable because of a
            # fault in one of them, which is the opposite of what a catalogue is
            # for; and the refusal that caused it was correct.
            #
            # `/dossier` already answers this shape per node. A row that cannot
            # be resolved is listed WITH its reason, because a catalogue that
            # silently omits what it could not read is a catalogue nobody can
            # tell is incomplete.
            catalogue, unresolved = [], []
            for row in f.list_features():
                try:
                    catalogue.append(f.catalogue.resolved(row["name"]))
                except Exception as exc:
                    swallowed(logger, exc, f"resolved feature '{row['name']}'",
                              detail="listed with the refusal instead, so the "
                                     "catalogue degrades by one row rather than "
                                     "entirely")
                    catalogue.append({**row, "unresolved": str(exc)})
                    unresolved.append(row["name"])
            derived = {d["name"]: d for d in f.derived.list()} if f.derived else {}
            views = []
            for view in f.views.views.many():
                versions = f.views.versions_of(view["name"])
                views.append({**view, "versions": versions,
                              "latest": versions[-1] if versions else None})
            return self.page(
                request, "features.html", unresolved=unresolved,
                # From the code. Two forms carried their own list and they
                # disagreed about `boolean`, so whether a feature could be one
                # depended on which screen you opened.
                dtypes=list(SUGGESTED_DTYPES), features=catalogue, derived=derived,
                views=views,
                language=__import__("core.features.expressions",
                                    fromlist=["describe"]).describe(),
                retrieval=__import__("core.features.preparation",
                                     fromlist=["describe"]).describe(),
                alignment=__import__("core.features.alignment",
                                     fromlist=["describe"]).describe(),
                composition=__import__("core.features.composition",
                                       fromlist=["describe"]).describe())

        @self.app.get("/feature-views/{name}", response_class=HTMLResponse,
                      tags=["ui"])
        def feature_view_page(request: Request, name: str):
            if (r := login_required(request)) is not None:
                return r
            f = self.ctx["features"]
            view = f.views.views.one(name=name)
            if not view:
                return self.page(request, "not_found.html", http_status=404, name=name)
            versions = f.views.versions_of(name)
            return self.page(request, "feature_view.html", view=view,
                             # From the code. The control offered four suffixes
                             # and the API reads six — including CSV, which is
                             # what every worked example in the product uploads.
                             upload_accepts=accept_attribute(),
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
                rows.append({**f.sets.resolved(row["name"]), "versions": versions,
                             "latest": versions[-1] if versions else None})
            return self.page(
                request, "featuresets.html", featuresets=rows,
                catalogue=f.list_features(),
                retrieval=__import__("core.features.preparation",
                                     fromlist=["describe"]).describe(),
                alignment=__import__("core.features.alignment",
                                     fromlist=["describe"]).describe())

        @self.app.get("/featureset/{name}", response_class=HTMLResponse,
                      tags=["ui"])
        def featureset_page(request: Request, name: str):
            if (r := login_required(request)) is not None:
                return r
            f = self.ctx["features"]
            if not f.sets.get(name):
                return self.page(request, "not_found.html", http_status=404, name=name)
            row = f.sets.resolved(name)
            versions = f.sets.versions_of(name)
            return self.page(
                request, "featureset.html", featureset=row, versions=versions,
                plans={v["version"]: f.featureset_plan(name, v["version"])
                       for v in versions},
                restatements={v["version"]: f.restatements(name, v["version"])
                              for v in versions},
                catalogue=f.list_features())

        # ------------------------------------------------------- rule sets
        @self.app.get("/rules/{name:path}/{semver}", response_class=HTMLResponse,
                      tags=["ui"])
        def ruleset_editor_page(request: Request, name: str, semver: str):
            """The T8 editor.

            One page per *version*, not per model: the rule set is the parameter
            object of a particular version, and its input schema is what the
            conditions are checked against. A model-level editor would have to
            pick a schema, and picking one silently is how a rule set comes to
            be validated against something other than what it runs on.
            """
            if (r := login_required(request)) is not None:
                return r
            from core.rules.common import ORDERED_DTYPES

            reg = self.ctx["registry"]
            urn = f"maya://model/{name}"
            model = reg.get(urn)
            version = reg.version(urn, semver) if model else None
            if model is None or version is None:
                return self.page(request, "not_found.html", http_status=404,
                                 name=f"{name} {semver}")
            if not self.may_view(request, "model:read"):
                return self.refused_page(request, "reading a model needs model:read")

            existing = [p for p in self.ctx["parameters"].for_version(urn, semver)
                        if p.get("kind") == "rule_set"]
            latest = existing[-1] if existing else None
            inputs = [{"name": f.get("name"), "dtype": f.get("dtype", "numeric"),
                       "ordered": f.get("dtype", "numeric") in ORDERED_DTYPES}
                      for f in (version.get("input_schema") or [])]
            return self.page(
                request, "ruleset_editor.html", model=model, model_version=version,
                inputs=inputs, outputs=version.get("output_schema") or [],
                existing=existing,
                document=(latest or {}).get("values_inline") or
                         {"rules": [], "otherwise": {}, "note": ""},
                vocabulary=_rule_vocabulary())

        @self.app.get("/rulesets/{parameter_set_id}", response_class=HTMLResponse,
                      tags=["ui"])
        def ruleset_page(request: Request, parameter_set_id: str):
            """A recorded rule set, read back in English."""
            if (r := login_required(request)) is not None:
                return r
            if not self.may_view(request, "model:read"):
                return self.refused_page(request, "reading a model needs model:read")
            from core.rules.common import RuleError
            try:
                explained = self.ctx["rules"].explain(parameter_set_id)
            except RuleError as exc:
                logger.info("rule set page refused: %s", exc.detail)
                return self.page(request, "not_found.html", http_status=404,
                                 name=parameter_set_id)
            return self.page(request, "ruleset.html", ruleset=explained,
                             row=self.ctx["parameters"].require(parameter_set_id))

        # ---------------------------------------------------------- policy
        @self.app.get("/policies", response_class=HTMLResponse, tags=["ui"])
        def policies_page(request: Request):
            """The four gates: what is in force, and how somebody changes one.

            The whole point of the policy engine is that a gate can be tightened
            by somebody who is not deploying code, and that person is not going
            to write the JSON by hand.
            """
            if (r := login_required(request)) is not None:
                return r
            from core.execution.profiles import SELECTABLE_FACTS
            who, policies = self.principal(request), self.ctx["policies"]
            history = {gate: policies.history(gate) for gate in GATES}
            # The gate object the registry actually consults, so the page
            # describes the thing doing the work rather than a second account
            # of it that could drift from it.
            return self.page(
                request, "policies.html",
                policy=self.ctx["registry"].policy.describe(),
                history=history,
                # Profiles sit beside the gates because the pair is the whole
                # answer to "how do warrants differ by kind of model": a profile
                # fills a hole, a gate refuses. Showing them apart invites
                # somebody to write an obligation as a default.
                profiles=self.ctx["warrant_profiles"].list(),
                profile_facts=sorted(SELECTABLE_FACTS),
                drafts=[row for rows in history.values() for row in rows
                        if row["state"] == "draft"],
                # Read off the evidence chain, not recomputed: the comparison
                # was made against the rule in force at the time, and that rule
                # may since have been superseded twice over.
                drift={row["id"]: policies.drift_of(row["id"])
                       for rows in history.values() for row in rows
                       if row["state"] != "draft"},
                facts={gate: describe_facts(gate) for gate in GATES},
                vocabulary={gate: [f["fact"] for f in describe_facts(gate)]
                            for gate in GATES},
                language=describe_language(),
                permissions=self.ctx["authz"].explain(who)["permissions"])

        # -------------------------------------------------------- findings
        @self.app.get("/findings", response_class=HTMLResponse, tags=["ui"])
        def findings_page(request: Request):
            """Every open finding across the estate, worst first.

            This screen did not exist, and neither did the query behind it. A
            model risk manager whose worklist read "nothing is outstanding for
            you" had an unacknowledged finding, six unmonitored models and a
            Tier 1 model with no validation in the same estate — and no route in
            the product could list them.
            """
            if (r := login_required(request)) is not None:
                return r
            who = self.page_principal(request)
            if who is None or not self.ctx["authz"].permits(who, "finding:read"):
                return self.refused_page(request, "finding:read")
            visible = self.ctx["authz"].visible(who, self.ctx["registry"].list())
            by_id = {m["id"]: m for m in visible}
            findings = self.ctx["findings"].open_across(list(by_id))
            now = time.time()
            rows = sorted(
                ({**f, "model": by_id[f["model_id"]],
                  "overdue": bool(f.get("due_at") and f["due_at"] < now)}
                 for f in findings),
                key=lambda f: (_SEVERITY_ORDER.get(f["severity"], 9),
                               f.get("due_at") or float("inf")))
            return self.page(
                request, "findings.html", findings=rows, now=now,
                models=len({f["model_id"] for f in findings}),
                estate=len(visible),
                overdue=sum(1 for f in rows if f["overdue"]),
                blocking=sum(1 for f in rows if f.get("blocking")),
                permissions=self.ctx["authz"].explain(who)["permissions"])

        # --------------------------------------------------- notifications
        @self.app.get("/notifications", response_class=HTMLResponse, tags=["ui"])
        def notifications_page(request: Request):
            """Which channels work, what has reached anybody, and what you
            yourself would be sent."""
            if (r := login_required(request)) is not None:
                return r
            who = self.principal(request)
            notifications = self.ctx["notifications"]
            return self.page(
                request, "notifications.html",
                # Not "status": Routes.page takes that as the HTTP status code,
                # and a context key of the same name is silently swallowed.
                notify=notifications.status(), meanings=CHANNEL_MEANING,
                # The same derivation the dashboard reads and the same one a
                # run would send, so the preview is the message rather than a
                # rehearsal of it.
                preview=notifications.digest_for(who),
                deliveries=notifications.history(None, 100), now=time.time(),
                permissions=self.ctx["authz"].explain(who)["permissions"])

        # ------------------------------------------------------- telemetry
        @self.app.get("/telemetry", response_class=HTMLResponse, tags=["ui"])
        def telemetry_page(request: Request):
            """Every version's telemetry, the ones that have stopped sending
            first — the collector decides that order, not this page."""
            if (r := login_required(request)) is not None:
                return r
            who = self.principal(request)
            models = self.ctx["authz"].visible(who, self.ctx["registry"].list())
            # Which version each alias points at, so the table can mark the one
            # in force. The screen's whole argument is that *the silence is the
            # finding*, and it could not tell a reader that the silent version
            # was the one serving production.
            in_force: Dict[str, list] = {}
            for m in models:
                for environment in ("prod", "uat", "dev"):
                    for name in ("champion", "challenger"):
                        pinned = self.ctx["registry"].resolve_alias(
                            m["urn"], environment, name)
                        if pinned and pinned.get("semver"):
                            in_force.setdefault(
                                f"{m['urn']}@{pinned['semver']}", []
                            ).append(f"{environment}/{name}")
            return self.page(request, "telemetry.html",
                             in_force=in_force,
                             estate=self.ctx["telemetry"].estate(models),
                             streams=STREAM_MEANING)

        # The version comes before the model on both of the routes below. The
        # model segment is a greedy `:path` converter — a URN carries dots and
        # slashes — and a greedy segment in front of a semver would swallow it.
        @self.app.get("/telemetry/{semver}/{name:path}",
                      response_class=HTMLResponse, tags=["ui"])
        def telemetry_version_page(request: Request, semver: str, name: str):
            """One version: what arrived, and the cohort a monitor would judge."""
            if (r := login_required(request)) is not None:
                return r
            model, version = self._version_or_none(name, semver)
            if version is None:
                return self.page(request, "not_found.html", http_status=404,
                                 name=f"telemetry/{semver}/{name}")
            if not self.may_view(request, "monitor:read", model):
                return self.refused_page(request, f"Telemetry for {name}")
            telemetry, urn = self.ctx["telemetry"], model["urn"]
            cohort = telemetry.cohort(urn, semver)
            return self.page(
                request, "telemetry_version.html", model=model, model_version=version,
                summary=telemetry.status(urn, semver), streams=STREAM_MEANING,
                rows=len(cohort), shown=cohort[:200], now=time.time(),
                labelled=sum(1 for row in cohort if "label" in row))

        # ------------------------------------------------------ parameters
        @self.app.get("/parameters/{semver}/{name:path}",
                      response_class=HTMLResponse, tags=["ui"])
        def parameters_page(request: Request, semver: str, name: str):
            """What one version may run on: the values, and what stands behind
            them."""
            if (r := login_required(request)) is not None:
                return r
            who = self.principal(request)
            model, version = self._version_or_none(name, semver)
            if version is None:
                return self.page(request, "not_found.html", http_status=404,
                                 name=f"parameters/{semver}/{name}")
            if not self.may_view(request, "model:read", model):
                return self.refused_page(request, f"Parameters for {name}")
            parameters, urn = self.ctx["parameters"], model["urn"]
            sets = parameters.for_version(urn, semver)
            return self.page(
                request, "parameters.html", model=model, model_version=version,
                readiness=parameters.status(urn, semver), parameter_sets=sets,
                provenance=PROVENANCE_MEANING,
                # A fitted set names the featureset version it was fitted from;
                # the row holds its id, and an id is not something a reviewer
                # can read.
                featuresets=self._featureset_labels(sets),
                permissions=self.ctx["authz"].explain(who)["permissions"])

        @self.app.get("/dossier/{name:path}", response_class=HTMLResponse,
                      tags=["ui"])
        def dossier_page(request: Request, name: str):
            """Everything documented about a model, following the pins."""
            if (r := login_required(request)) is not None:
                return r
            model = self.ctx["registry"].get(urn(name))
            if not model:
                return self.page(request, "not_found.html", http_status=404,
                                 what=f"model {name}")
            if not self.may_view(request, "document:read", model):
                return self.refused_page(
                    request, "reading this model's documentation needs "
                             "document:read within its scope")
            return self.page(request, "dossier.html",
                             dossier=self.ctx["dossier"].of(model["urn"]))

        @self.app.get("/board-pack", response_class=HTMLResponse, tags=["ui"])
        def board_pack_page(request: Request):
            """What a committee would be shown, before it is recorded."""
            if (r := login_required(request)) is not None:
                return r
            if not self.may_view(request, "report:read"):
                return self.refused_page(
                    request, "reading the portfolio report needs report:read")
            packs = self.ctx["board_packs"]
            pack = packs.build()
            return self.page(
                request, "board_pack.html",
                pack=pack,
                breaches=[e for e in pack["exceptions"] if e["status"] == "breach"],
                ambers=[e for e in pack["exceptions"] if e["status"] == "amber"],
                appetite=self.ctx["appetite"].in_force(),
                packs=packs.history(limit=12),
                # Whether to offer the button is the platform's decision, not the
                # template's: a page that hides a control it cannot explain is
                # better than one that offers an action the caller may not take.
                may_cut=self.may_view(request, "report:cut"))

        # -------------------------------------------------------- new model
        @self.app.get("/models/new", response_class=HTMLResponse, tags=["ui"])
        def new_model_page(request: Request):
            """Create a model, or upload a version of one that already exists."""
            if (r := login_required(request)) is not None:
                return r
            from core.artifacts import EXECUTES_ON_LOAD, FORMAT_MEANING, FORMATS
            from core.attachments import KINDS as ATTACHMENT_KINDS
            from core.domain.algebra import FitProcedure, OutputKind, ParameterKind
            from core.execution.grammar import RUNTIME_ENTRY
            who = self.page_principal(request)
            return self.page(
                request, "new_model.html",
                # Filtered, not listed. This page showed every model in the
                # estate to anybody signed in, which made the inventory
                # discoverable to a principal the API refuses it to.
                models=self.ctx["authz"].visible(who, self.ctx["registry"].list()),
                parameter_kinds=[k.value for k in ParameterKind],
                fit_procedures=[p.value for p in FitProcedure],
                # From the code, so the form cannot offer a kind the register
                # refuses. A page holding its own copy of a closed vocabulary is
                # a second vocabulary.
                attachment_kinds=list(ATTACHMENT_KINDS),
                # Whether the signed-in person may actually do either of these.
                # Both forms rendered in full for a model developer, who holds
                # neither, and the refusal that followed said "ask an
                # administrator for a role that carries this permission" when
                # the right answer is "ask the model owner". A form offered to
                # somebody who cannot submit it is a form that teaches them the
                # product is broken.
                may_register=self.may_view(request, "model:register"),
                may_version=self.may_view(request, "version:create"),
                output_kinds=[k.value for k in OutputKind],
                runtimes=sorted(RUNTIME_ENTRY),
                runtime_entry={k: list(v) for k, v in RUNTIME_ENTRY.items()},
                # Which formats run code when they load travels to the page, so
                # the warning is attached to the choice rather than left in a
                # document somebody read once.
                artifact_formats=[{"format": f, "means": FORMAT_MEANING[f],
                                   "executes_on_load": f in EXECUTES_ON_LOAD}
                                  for f in FORMATS])

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
                return self.page(request, "not_found.html", http_status=404,
                                 name=f"document/{document_id}")
            # A compiled document carries the model's whole record in prose --
            # tier, findings, validation outcomes, evidence. It is the LAST
            # thing that should be readable outside its model's scope.
            subject = self.ctx["registry"].by_id(doc["model_id"])
            if subject is not None and not self.may_view(request, "document:read",
                                                          subject):
                return self.refused_page(request, "That document")
            html, headings = self.ctx["renderer"].render(docs.markdown(doc))
            model = self.ctx["registry"].catalogue.models.one(id=doc["model_id"])
            return self.page(request, "document.html", doc=doc, model=model,
                             body=html,
                             anchors=[h for h in headings if h["level"] == 2],
                             staleness=docs.staleness(document_id),
                             citations=docs.verify_citations(document_id))

    # ------------------------------------------------------------- lookups
    def _version_or_none(self, name: str, semver: str) -> tuple:
        """The model and the named version of it, or (model, None).

        Both telemetry and parameters are per model *version*, and a page that
        rendered an empty shell for a version that does not exist would look
        like a version with nothing recorded against it.
        """
        registry, urn = self.ctx["registry"], f"maya://model/{name}"
        model = registry.get(urn)
        if model is None:
            return None, None
        return model, registry.version(urn, semver)

    def _featureset_labels(self, parameter_sets) -> Dict[str, str]:
        """featureset version id -> 'name@vN', for the sets that name one."""
        sets = self.ctx["features"].sets
        labels: Dict[str, str] = {}
        for row in parameter_sets:
            identifier = row.get("featureset_version_id")
            if not identifier or identifier in labels:
                continue
            version = sets.versions.one(id=identifier)
            if version is None:
                continue
            featureset = sets.sets.one(id=version["featureset_id"])
            if featureset is None:
                continue
            labels[identifier] = f"{featureset['name']}@v{version['version']}"
        return labels


def _kernel_type(versions) -> Optional[Dict[str, Any]]:
    """`f : P ⊗ X → D(Y)` for the version a reader is looking at.

    Derived, never declared: the trainability class falls out of how the
    parameter object is inhabited, and showing it beside the two facts it comes
    from is the difference between a label and an explanation.
    """
    if not versions:
        return None
    version = latest_version(versions)
    kernel = ((version.get("manifest") or {}).get("kernel") or {})

    def fields(schema):
        out = []
        for field in schema or []:
            low, high = field.get("minimum"), field.get("maximum")
            span = (f"[{low}, {high}]" if low is not None and high is not None
                    else f"≥ {low}" if low is not None
                    else f"≤ {high}" if high is not None else "")
            out.append({"name": field.get("name"), "dtype": field.get("dtype"),
                        "range": span})
        return out

    return {
        "semver": version.get("semver"),
        "trainability_class": version.get("trainability_class"),
        "parameter_kind": version.get("parameter_kind"),
        "fit_procedure": version.get("fit_procedure"),
        "runtime": kernel.get("runtime") or "descriptor_only",
        "output_kind": kernel.get("output_kind") or "point_estimate",
        "parameters": PARAMETER_MEANING.get(version.get("parameter_kind"), ""),
        "inputs": fields(version.get("input_schema")),
        "outputs": fields(version.get("output_schema")),
    }


#: What each way of inhabiting `P` actually is, in a reader's words. Short on
#: purpose: the page is showing a type, not teaching the taxonomy.
PARAMETER_MEANING = {
    "none": "empty — there is nothing to fit",
    "calibration_set": "solved against market instruments, repeatedly",
    "estimated_coefficients": "estimated from a historical sample",
    "learned_weights": "learned by a training run; held as an artifact",
    "llm_configuration": "a configuration around somebody else's model",
    "rule_set": "rules somebody wrote down",
    "elicited_weights": "decided by people, in a room",
    "opaque": "exists, and cannot be reached from here",
}
