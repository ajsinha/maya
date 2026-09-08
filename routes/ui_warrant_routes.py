"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The screens for the warrant lifecycle and for taking a model package.

Split out of `ui_routes.py` rather than added to it. That file holds the pages
that *read* the register; these author into it, and the two have different
failure modes — a read page that breaks shows nothing, an authoring page that
breaks writes something wrong.

**These screens decide nothing.** Every refusal a user sees here is the API's,
rendered; nothing about whether an act is permitted is computed in the browser
or in this module. A page that made a governance decision locally would be a
second implementation of a rule, and a second implementation disagrees with the
first eventually, in the direction of permitting more — because that is the
direction in which nobody files a bug.

So the pages render, and post to the endpoints an external engine already uses.
Two things are served rather than rendered, and both for the same reason: a
browser can only take delivery of a zip from a response whose headers say so,
and the named gaps a pack records are written *inside* that zip by the packer
and exist nowhere else — so the preview reads them back out of a pack it built
and threw away, rather than assembling a second opinion about what is missing.
"""
from __future__ import annotations

import inspect
import io
import re
import time
import zipfile
from typing import Any, Callable, Dict, List, Optional

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from core.attachments.common import KIND_MEANING
from core.docs import KINDS
from core.execution.grammar import (SECTIONS, VERB_MEANING, VERBS,
                                    admissible_verbs, rules)
from core.execution.profiles import (AUTHORITY_KEYS, DEFAULTABLE,
                                     SELECTABLE_FACTS)
from core.execution.urn import model_urn
from core.export import CONTENTS, DEFAULT_DOCUMENTS, MANIFEST, PACK_VERSION
# `GAPS` is the gaps file's name and is not re-exported by the package, so it
# comes from the module that owns it rather than being retyped here.
from core.export.common import GAPS
from core.log import get_logger
from core.parameters import PROVENANCE_MEANING
from routes.base import Routes, login_required
from core.registry.versions import latest_version

logger = get_logger(__name__)

#: How each act is performed without a browser. Carried to the page because the
#: audience for these screens is people who will shortly be writing the curl —
#: a screen that hides the call it makes teaches nothing about the platform.
CURL = {
    "grant": "POST /api/v1/warrants",
    "score": "POST /api/v1/resolve?verb=score",
    "fit": "POST /api/v1/fit-warrants",
    "record": "POST /api/v1/parameters",
    "review": "POST /api/v1/parameter-sets/{id}/review",
    "revoke": "POST /api/v1/warrants/revoke",
    "check": "POST /api/v1/grammar/validate",
    "profile": "POST /api/v1/warrant-profiles",
    "preview": "POST /api/v1/warrant-profiles/preview",
    "execute": "POST /api/v1/execute",
    "pack": "POST /api/v1/export-packs/{name}",
}


def _first_paragraph(fn: Callable) -> str:
    """The opening paragraph of a check's docstring, as one line, with its own
    law number taken off the front.

    Quoted from the implementation rather than retyped. A screen holding its own
    account of a law is a second account of it, and the second one is the one
    that goes stale — silently, because a law nobody re-reads still renders.
    """
    doc = inspect.getdoc(fn) or ""
    text = " ".join(doc.split("\n\n")[0].split())
    return re.sub(r"^(Law\s+)?L-W\d+\.\s*", "", text)


#: Where a law is enforced, and therefore where a developer meets it.
#: `/grammar/validate` reports every problem in a document at once; a refusal at
#: resolution reports the same laws but arrives one HTTP call at a time.
BY_GRAMMAR = "the grammar validator, and again when a warrant is resolved"
AT_RESOLUTION = "warrant resolution only"

_CHECKED_BY = [
    ("L-W1", rules.check_verb_against_class,
     "check_verb_against_class, check_trainability_class"),
    ("L-W2", rules.check_generative, "check_generative"),
    ("L-W3", rules.check_training_bindings, "check_training_bindings"),
    ("L-W4", rules.check_fit_output, "check_fit_output"),
    ("L-W5", rules.check_determinism, "check_determinism"),
    ("L-W6", rules.check_descriptor_only, "check_descriptor_only"),
    ("L-W7", rules.check_outcomes, "check_outcomes"),
    ("L-W8", rules.check_parameter_source, "check_parameter_source"),
    ("L-W9", rules.check_featureset_bounds, "check_featureset_bounds"),
    ("L-W11", rules.check_calibration_as_of, "check_calibration_as_of"),
    ("L-W12", rules.check_artifact_digest, "check_artifact_digest"),
    ("L-W13", rules.check_generative_pin, "check_generative_pin"),
]

#: The two laws with no single function to quote.
#:
#: `L-W0` is the shape pass, which raises the same law from six places in
#: `GrammarValidator._shape` — a missing section, an unknown verb, an unknown
#: runtime, a runtime whose entry block is short of a key, an unknown binding
#: and an unknown sink. `L-W10` is not in the grammar at all: whether a
#: featureset provides what a kernel reads cannot be answered by reading the
#: warrant, only by looking both objects up, so it is enforced in the warrant
#: service and refuses `schema_not_satisfied`.
#:
#: Written out here because there is nothing to quote, and both say where they
#: are enforced so that nobody looks for them in `rules.py` and concludes the
#: grammar has twelve laws.
_WRITTEN_OUT = {
    "L-W0": ("Every warrant carries all ten sections, and every vocabulary "
             "value in it — the verb, the runtime, each data binding, each "
             "output sink — is one the grammar knows. An absent section is not "
             "an empty one.",
             "grammar/validator.py — GrammarValidator._shape",
             BY_GRAMMAR),
    "L-W10": ("A featureset a warrant names must provide what the kernel "
              "declares it reads — contravariance in inputs, the same variance "
              "rule that gates alias promotion, applied one level out. Adding "
              "a regressor is a model change, not a data change.",
              "execution/warrants.py — WarrantService._check_schema",
              AT_RESOLUTION),
}


def _laws() -> List[Dict[str, str]]:
    """The fourteen admissibility laws, in order, each with what it says.

    In order and complete, because the point of showing them is that a
    developer can read the list once instead of meeting them one 422 at a time.
    """
    quoted = {law: (_first_paragraph(fn), f"grammar/rules.py — {where}",
                    BY_GRAMMAR)
              for law, fn, where in _CHECKED_BY}
    quoted.update(_WRITTEN_OUT)
    return [{"law": law, "says": quoted[law][0], "enforced_by": quoted[law][1],
             "reported_by": quoted[law][2]}
            for law in sorted(quoted, key=lambda name: int(name[3:]))]


class WarrantAuthoringRoutes(Routes):
    def register(self) -> None:
        registry, warrants = self.ctx["registry"], self.ctx["warrants"]

        # ------------------------------------------------------- warrants
        @self.app.get("/warrants/estate", response_class=HTMLResponse,
                      tags=["ui"])
        def warrants_estate(request: Request):
            """Who currently holds authority to run what, and until when.

            The question a day-to-day administrator asks most often, and it
            had no answer anywhere: `/warrants` requires a model to be chosen
            first, `GET /api/v1/warrants` answered 405 because the path is a
            POST, and the dashboard has no warrant tile.

            This screen is a client of `GET /api/v1/warrants`, which now
            exists, and both read `every_grant()` — so a script and a browser
            answer the same question the same way.

            Scoped like everything else — a grant says who may run a model, so
            somebody the API refuses that model to does not see its grants.
            """
            if (r := self.page_gate(request, "warrant:read")) is not None:
                return r
            who = self.page_principal(request)
            readable = {m["urn"] for m in
                        self.ctx["authz"].visible(who, registry.list())}
            grants = [g for g in warrants.every_grant()
                      if g.get("model_urn") in readable]
            now = time.time()
            for grant in grants:
                expires = grant.get("expires_at")
                grant["lapses_in_days"] = (
                    round((expires - now) / 86400.0, 1)
                    if expires else None)
                grant["lapsed"] = bool(expires and expires <= now)
            return self.page(request, "warrants_estate.html", grants=grants,
                             live=[g for g in grants
                                   if not g.get("revoked") and not g["lapsed"]],
                             now=now)

        @self.app.get("/warrants", response_class=HTMLResponse, tags=["ui"])
        def warrant_authoring(request: Request, model: str = "",
                              environment: str = "prod"):
            """The whole warrant lifecycle on one page.

            One page rather than six, because the six are one act split by time:
            nothing resolves without a standing grant, a fit warrant goes out
            and the parameters it produced come back, and a revocation ends all
            of it. The refusal that says a grant is missing (`no_entitlement`)
            is the single most common surprise on this platform, and putting the
            grant beside the resolution is the only arrangement in which the
            reason for that is obvious.
            """
            if (r := login_required(request)) is not None:
                return r
            who = self.page_principal(request)
            visible = self.ctx["authz"].visible(who, registry.list())
            chosen = registry.get(model_urn(model)) if model else None
            if model and chosen is None:
                return self.page(request, "not_found.html", http_status=404,
                                 name=model)
            # Scope, by the rule the API applies. A model's grants say who is
            # entitled to run it and for what, which is not a thing to hand to
            # somebody the API refuses the model to.
            if chosen is not None and not self.may_view(request, "model:read",
                                                        chosen):
                return self.refused_page(request, f"Warrants for {model}")
            versions = registry.versions(chosen["urn"]) if chosen else []
            engine = self.ctx.get("engine")
            return self.page(
                request, "warrant_author.html", models=visible, model=chosen,
                versions=versions, environment=environment,
                # Whether this person may actually issue one. The page rendered
                # the whole form for a model developer, who holds neither
                # `warrant:issue` nor `warrant:revoke`, and the refusal then
                # pointed at an administrator when the answer is the model
                # owner. Naming the right person is most of what a remediation
                # is for.
                may_issue=self.may_view(request, "warrant:issue", chosen),
                may_revoke=self.may_view(request, "warrant:revoke", chosen),
                grants=warrants.grants_for(chosen["urn"]) if chosen else [],
                # Every verb, with what it means. Which verbs a class can
                # meaningfully be asked for is the grammar's answer, not this
                # page's — `admissible_verbs` is imported rather than
                # reimplemented, and the form still offers all ten so that a
                # developer meets the refusal rather than a greyed-out option.
                verbs=[{"verb": v, "means": VERB_MEANING[v]} for v in VERBS],
                admits=admissible_verbs(
                    (latest_version(versions) or {}).get("trainability_class", "T0"))
                       if versions else list(VERBS),
                sections=SECTIONS, laws=_laws(), curl=CURL,
                featuresets=self._featuresets(),
                # The configured maps, not the defaults in the code: an
                # instance may have been tuned, and a page showing the shipped
                # numbers would be describing a different platform. Reached
                # through the grant register because there is no accessor.
                ttl_by_tier=warrants.grants.ttl,
                grace_by_tier=warrants.grants.grace, epoch=warrants.epoch,
                # The other half of the round trip: a fit warrant goes out, an
                # engine trains, and the numbers come back here.
                parameters=self._parameter_state(chosen, versions),
                provenance=PROVENANCE_MEANING,
                # Request defaults, and the three constraints that stop a
                # profile becoming a taxonomy.
                profiles=self.ctx["warrant_profiles"].list(),
                profile_facts=SELECTABLE_FACTS,
                profile_defaultable=DEFAULTABLE,
                profile_authority=list(AUTHORITY_KEYS),
                # The operating boundary travels in the warrant, and only an
                # engine can report a violation of it. Whether this instance
                # has one to demonstrate with is the platform's answer, not the
                # page's guess.
                engine=engine.isolation() if engine is not None else None,
                permissions=self.ctx["authz"].explain(who)["permissions"]
                            if who else [])

        # ------------------------------------------------------- packages
        @self.app.get("/packages", response_class=HTMLResponse, tags=["ui"])
        def packages_index(request: Request):
            """Which models a pack can be cut for. Filtered, not listed: an
            inventory of model names is itself sensitive."""
            if (r := login_required(request)) is not None:
                return r
            who = self.page_principal(request)
            return self.page(
                request, "packages.html",
                models=self.ctx["authz"].visible(who, registry.list()),
                contents=CONTENTS, pack_version=PACK_VERSION,
                documents=list(DEFAULT_DOCUMENTS))

        # Before the page route below it: `{name:path}` is greedy and would
        # otherwise swallow `/preview` as part of a model name.
        @self.app.get("/packages/{name:path}/preview", tags=["ui"])
        def preview_package(request: Request, name: str, documents: str = "",
                            attachments: int = 1):
            """The manifest and the named gaps, without handing over the bytes.

            The gaps are read back out of a pack that was built and discarded,
            rather than assembled here. A page that worked out for itself what
            was missing would be a second opinion about the completeness of an
            export, and the two would disagree in exactly the direction that
            makes a thin pack look complete.

            Nothing is recorded, because nothing left the platform. The evidence
            of an export is evidence of a *copy being taken*, and a reader who
            looked at what one would contain has not taken one.
            """
            model = registry.get(model_urn(name))
            if model is None:
                raise self.not_found(f"no model {name}")
            who = self.authorise(request, "document:read", model=model)
            pack = self.guard(lambda: self.ctx["export"].build(
                model["urn"], documents=self._kinds(documents),
                include_attachments=bool(attachments), actor=self.actor(who)))
            return {**pack["manifest"], "pack_digest": pack["digest"],
                    "filename": pack["filename"], "detail": pack["detail"],
                    "gaps_markdown": self._member(pack["bytes"], GAPS),
                    "bytes": len(pack["bytes"])}

        @self.app.get("/packages/{name:path}", response_class=HTMLResponse,
                      tags=["ui"])
        def package_page(request: Request, name: str):
            """Everything about one model, and what an export of it would hold.

            The inventory below is counted from the context the PACKER builds
            from — `documents.build_context`, the same gatherer — so the page
            cannot promise a pack something the pack will not contain. Two
            gatherers would be two answers to "what is true about this model",
            and the second drifts from the first in the places nobody looks.
            """
            if (r := login_required(request)) is not None:
                return r
            model = registry.get(model_urn(name))
            if model is None:
                return self.page(request, "not_found.html", http_status=404,
                                 name=name)
            # A pack is the most complete thing this platform produces about a
            # model, so an export of one the caller may not read would be the
            # largest scope leak available — the same check the API makes.
            if not self.may_view(request, "document:read", model):
                return self.refused_page(request, f"A pack for {name}")
            context = self.ctx["documents"].build_context(model["urn"])
            dossier = self.ctx["dossier"].of(model["urn"])
            return self.page(
                request, "package.html", model=model, name=name,
                contents=CONTENTS, pack_version=PACK_VERSION, curl=CURL,
                documents=list(DEFAULT_DOCUMENTS), document_kinds=list(KINDS),
                inventory=self._inventory(context, dossier),
                context=context, dossier=dossier,
                versions=context.get("versions") or [],
                chain=context.get("chain") or {},
                attachments=context.get("attachments") or [],
                attachment_kinds=KIND_MEANING,
                # Not in the pack as a member of its own, and said so rather
                # than left for a reader to discover: they travel inside the
                # dossier, which follows each fit to the featureset version it
                # read. See the note on the page.
                parameters=self._parameter_state(
                    model, context.get("versions") or []),
                manifest_name=MANIFEST, gaps_name=GAPS)

        @self.app.post("/packages/{name:path}", tags=["ui"])
        def cut_package(request: Request, name: str, documents: str = "",
                        attachments: int = 1):
            """Cut a pack and hand it over as a file.

            A POST, and the page reaches it with a form rather than with script:
            taking a complete record of a model away is an act that is recorded,
            and an act that is recorded should not be reachable by following a
            link — a GET is something a crawler, a preview fetcher or a mistyped
            URL performs on somebody's behalf.

            `attachments` is 0 or 1 rather than a boolean, here as everywhere.
            """
            model = registry.get(model_urn(name))
            if model is None:
                raise self.not_found(f"no model {name}")
            who = self.authorise(request, "document:read", model=model)
            kinds = self._kinds(documents)
            pack = self.guard(lambda: self.ctx["export"].build(
                model["urn"], documents=kinds,
                include_attachments=bool(attachments), actor=self.actor(who)))
            # Recorded for the same reason the API's own export records it:
            # handing a complete record of a model to somebody outside is a
            # governance act, and who took a copy is what an auditor asks about
            # later. Against the PACK, whose identity is its content digest, and
            # never against the model — recorded against the model it would land
            # inside the next pack and make every pack differ from the last for
            # no reason but that somebody had taken one.
            self.ctx["evidence"].append(
                "export_pack_cut", "export_pack",
                pack["manifest"]["content_digest"],
                {"urn": model["urn"], "model_id": model["id"],
                 "pack_digest": pack["digest"],
                 "files": len(pack["manifest"]["files"]),
                 "gaps": pack["manifest"]["gaps"], "documents": kinds,
                 "taken_from": "the model package screen"},
                actor=self.actor(who))
            return Response(
                pack["bytes"], media_type="application/zip",
                headers={"Content-Disposition":
                         f'attachment; filename="{pack["filename"]}"',
                         "X-Pack-Digest": pack["digest"],
                         "X-Pack-Content-Digest":
                             pack["manifest"]["content_digest"]})

    # ------------------------------------------------------------- lookups
    @staticmethod
    def _kinds(documents: str) -> List[str]:
        """Which documents to render, or all four. A caller narrowing the list
        is narrowing their own pack, never the register."""
        return ([k.strip() for k in documents.split(",") if k.strip()]
                or list(DEFAULT_DOCUMENTS))

    @staticmethod
    def _member(archive: bytes, name: str) -> str:
        """One text member of a pack, as text.

        The packer's own words for what it could not gather. Read from the zip
        rather than recomputed, so the page and the file agree by construction.
        """
        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            return zf.read(name).decode("utf-8", "replace")

    def _featuresets(self) -> List[Dict[str, Any]]:
        """Every featureset and the versions it has, for the fit form.

        Empty rather than absent when no featureset register is wired: a fit
        warrant then cannot be issued at all, and the page says so where the
        form would have been rather than offering a control that refuses.
        """
        sets = getattr(self.ctx.get("features"), "sets", None)
        if sets is None:
            return []
        return [{"name": row["name"],
                 "versions": [v["version"] for v in sets.versions_of(row["name"])]}
                for row in sets.list()]

    def _parameter_state(self, model: Optional[Dict[str, Any]],
                         versions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Per version: whether it may run, and every point of P recorded for it.

        This is the far end of the round trip. A fit warrant goes out, an engine
        trains, and what comes back lands here as `proposed` — which is not a
        formality: until somebody other than whoever recorded them approves a
        set, no warrant will name it and the version cannot run.
        """
        if model is None:
            return []
        register = self.ctx["parameters"]
        labels = self._featureset_labels()
        out = []
        for version in versions:
            semver = version["semver"]
            sets = [{**row, "featureset":
                     labels.get(row.get("featureset_version_id"))}
                    for row in register.for_version(model["urn"], semver)]
            out.append({
                "semver": semver, "status": version.get("status"),
                "trainability_class": version.get("trainability_class"),
                "readiness": register.status(model["urn"], semver),
                # What this version's contract pins, which is what serving must
                # read. Absent is normal: a version with no feature contract is
                # one whose inputs arrive on the request.
                "contract": self._feature_contract(version["id"]),
                "sets": sets,
            })
        return out

    def _featureset_labels(self) -> Dict[str, str]:
        """featureset version id -> 'name@vN'.

        A fitted set names the featureset VERSION it came from and the row holds
        its id — and an id is not a thing a reviewer can read. This is the pin
        that answers "what was this trained on" rather than "what does that
        featureset look like today".
        """
        sets = getattr(self.ctx.get("features"), "sets", None)
        if sets is None:
            return {}
        labels: Dict[str, str] = {}
        for row in sets.list():
            for version in sets.versions_of(row["name"]):
                labels[version["id"]] = f"{row['name']}@v{version['version']}"
        return labels

    def _feature_contract(self, version_id: str):
        """The feature views a version pins, or None.

        Not a member of the pack in its own right: it reaches a reader through
        the dossier, which follows each fit to the featureset version it read.
        Shown here because a model manager asking "what does this read" should
        not have to open a zip to find out.
        """
        features = self.ctx.get("features")
        if features is None:
            return None
        return features.contract_for(version_id)

    def _inventory(self, context: Dict[str, Any],
                   dossier: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Each member of a pack, what it answers, and what it holds today.

        Counted from the context the packer builds from, so this cannot promise
        a member something the pack will not carry. What it cannot count is the
        gaps file: a gap is discovered while gathering, so its contents are only
        known once a pack has been built — which is what the preview is for.
        """
        evidence = context.get("evidence") or []
        chain = context.get("chain") or {}
        validations = context.get("validations") or []
        results = context.get("results_by_validation") or {}
        held = {
            "model.json": f"1 record, {len(context.get('alias_history') or [])} "
                          f"alias move(s)",
            "versions.json": f"{len(context.get('versions') or [])} version(s)",
            "documents/": f"{len(DEFAULT_DOCUMENTS)} kind(s), rendered at the "
                          f"moment the pack is cut",
            "attachments/": f"{len(context.get('attachments') or [])} filed "
                            f"document(s)",
            "evidence/chain.json": f"{len(evidence)} node(s); the chain verified "
                                   f"{chain.get('valid')}",
            "validations.json": f"{len(validations)} episode(s), "
                                f"{sum(len(r) for r in results.values())} result(s)",
            "findings.json": f"{len(context.get('findings') or [])} open",
            # `monitors` and `overlays` are counts, not lists — these services
            # summarise rather than return rows, and calling len() on the
            # summary would have been a TypeError on the first tiered model.
            "monitoring.json": f"{(context.get('monitoring') or {}).get('monitors', 0)} "
                               f"monitor(s), "
                               f"{(context.get('monitoring') or {}).get('open_breaches', 0)} "
                               f"open breach(es)",
            "overlays.json": f"{(context.get('overlays') or {}).get('overlays', 0)} "
                             f"overlay(s), "
                             f"{(context.get('overlays') or {}).get('active', 0)} active",
            "warrants.json": f"{len(context.get('warrants') or [])} standing grant(s)",
            "documentation/dossier.json": dossier.get("detail", ""),
            MANIFEST: "written last, and excluded from the content digest",
            GAPS: "written after gathering — preview the pack to read it",
        }
        return [{"member": member, "answers": answers,
                 "holds": held.get(member, "")}
                for member, answers in CONTENTS.items()]
