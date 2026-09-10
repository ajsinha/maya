"""
MAYA — compiled documentation.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Documents are compiled from the register and the evidence graph, so the useful
endpoints are not "upload" and "download" but **compile**, **check the citations**
and **ask whether it has gone stale**.
"""
from __future__ import annotations


from typing import Any, Dict, Optional

from fastapi import Request
from pydantic import Field
from fastapi.responses import PlainTextResponse

from core.docs import KINDS, TITLES
from core.docs.review import DocumentReview
from core.features.request_time import RequestTimeInputs
from core.execution.urn import model_urn as urn
from core.docs.common import PURPOSE
from routes.base import Body, Routes


class CommentIn(Body):
    """A remark on one section. Deliberately not an edit.

    `asks_for` comes from a closed list, because *please look at this* and
    *this is factually wrong* are different obligations and a free-text field
    makes them the same one.
    """
    section: str
    body: str
    asks_for: str = "comment"
    quote: str = ""


class ResolveCommentIn(Body):
    """What was done. `evidence_id` where the fix was to the record."""
    resolution: str
    evidence_id: str = ""


class RequestPayloadIn(Body):
    urn: str
    semver: str
    payload: Dict[str, Any] = Field(default_factory=dict)


class DocumentRoutes(Routes):
    def register(self) -> None:
        docs, registry = self.ctx["documents"], self.ctx["registry"]
        api = self.api

        @self.app.get(f"{api}/document-search", tags=["documentation"])
        def document_search(request: Request, q: str, urn: str = "",
                            kind: str = "", limit: int = 25):
            """Every filed document containing these terms, best match first.

            Retrieval is **exact rather than semantic**, and that is a decision.
            The question a supervisor asks is *show me where you wrote that*,
            and an approximate answer to it is worse than none because the
            reader cannot tell a miss from an absence. The semantic half is
            named in `/document-search/coverage` with what it would take, rather
            than left as an absence somebody has to discover.

            Read `could_not_be_read` before an empty result. A PDF filed and
            never extracted is invisible to a search, and invisible is exactly
            how it looks to somebody who searched and found nothing.
            """
            who = self.authorise(request, "document:read")
            return self.guard(
                lambda: self.ctx["document_search"].search(
                    q, principal=who, urn=urn, kind=kind, limit=limit))

        @self.app.get(f"{api}/document-search/coverage",
                      tags=["documentation"])
        def document_coverage(request: Request):
            """How much of the corpus a search can actually see.

            The figure to read before any result: a search over a corpus that is
            forty percent unextracted is a search whose empty answers mean
            nothing.
            """
            who = self.authorise(request, "document:read")
            return self.guard(
                lambda: self.ctx["document_search"].coverage(principal=who))

        @self.app.get(f"{api}/document-kinds", tags=["documents"])
        def kinds(request: Request):
            self.principal(request)
            return {"kinds": [{"kind": k, "title": TITLES[k], "purpose": PURPOSE[k]}
                              for k in KINDS]}

        @self.app.get(f"{api}/documents", tags=["documents"])
        def list_documents(request: Request, urn: str):
            model = self.guard(lambda: registry.require(urn))
            self.authorise(request, "document:read", model=model)
            return {"model": urn, "documents": [
                {**d, "staleness": docs.staleness(d["id"])}
                for d in docs.for_model(model["id"])]}

        @self.app.post(f"{api}/documents", status_code=201, tags=["documents"])
        def compile_document(request: Request, urn: str, kind: str):
            model = self.guard(lambda: registry.require(urn))
            who = self.authorise(request, "document:compile", model=model)
            return self.guard(lambda: docs.compile(kind, urn, self.actor(who)))

        @self.app.get(f"{api}/documents/{{document_id}}", tags=["documents"])
        def get_document(request: Request, document_id: str):
            self.authorise(request, "document:read")
            doc = self.guard(lambda: docs.require(document_id))
            return {**doc, "staleness": docs.staleness(document_id),
                    "citations_verified": docs.verify_citations(document_id)}

        @self.app.get(f"{api}/documents/{{document_id}}/markdown",
                      response_class=PlainTextResponse, tags=["documents"])
        def markdown(request: Request, document_id: str):
            """The document as markdown — what a person reads, or exports."""
            self.authorise(request, "document:read")
            return docs.markdown(self.guard(lambda: docs.require(document_id)))

        # ------------------------------------------------- the documentation graph
        @self.app.get(f"{self.api}/document-subjects", tags=["documents"])
        def subjects(request: Request):
            """What a document can be about, and which subjects are pinned."""
            self.principal(request)
            from core.docs.subjects import describe
            return describe()

        @self.app.get(f"{self.api}/dossiers/{{name:path}}", tags=["documents"])
        def dossier(request: Request, name: str):
            """Everything documented about a model, following the pins.

            A graph rather than a list: the training record for a parameter set
            hangs under the version that produced it, and the featureset
            documentation hangs under the featureset VERSION it was fitted from
            — not the set, which has since moved.
            """
            model = self.ctx["registry"].get(urn(name))
            if not model:
                raise self.not_found(f"no model {name}")
            self.authorise(request, "document:read", model=model)
            return self.guard(lambda: self.ctx["dossier"].of(model["urn"]))

        @self.app.post(f"{self.api}/training-records/{{parameter_set_id}}",
                       status_code=201, tags=["documents"])
        def training_record(request: Request, parameter_set_id: str):
            """Compile the record of one fit.

            Every other document is about a model or a version. This one is
            about a parameter set, which is the moment that had no document at
            all — two hundred and fifty calibrations a year, each a governed act
            with a warrant behind it and none of them readable.
            """
            who = self.authorise(
                request, "document:compile",
                model=self.model_behind(
                    self.ctx["parameters"].get(parameter_set_id)))
            return self.guard(lambda: self.ctx["training_records"].compile(
                parameter_set_id, actor=self.actor(who)))

        @self.app.get(f"{self.api}/training-records/{{parameter_set_id}}/preview",
                      tags=["documents"])
        def preview_training_record(request: Request, parameter_set_id: str):
            """What it would say, without authoring it."""
            self.authorise(request, "document:read")
            return self.guard(lambda: self.ctx["training_records"].render(
                parameter_set_id))

        # -------------------------------------------------- document review
        @self.app.get(f"{api}/document-review/asks", tags=["documents"])
        def review_asks(request: Request):
            """What a comment may ask for, and why a document is not editable."""
            self.authorise(request, "document:read")
            return DocumentReview.asks()

        @self.app.get(f"{api}/document-review", tags=["documents"])
        def review(request: Request, document_id: str = "",
                   now: Optional[float] = None):
            """A document's review state, or every document under review."""
            self.authorise(request, "document:read",
                           estate_wide="reading every document under review")
            engine = self.ctx["document_review"]
            if not document_id:
                return self.guard(lambda: engine.across_the_estate(now=now))
            return self.guard(lambda: engine.read(document_id, now=now))

        @self.app.post(f"{api}/document-review", status_code=201,
                       tags=["documents"])
        def comment(request: Request, document_id: str, body: CommentIn):
            """Say which section is wrong and what about it.

            A compiled document cannot be edited: every sentence cites a node,
            and editing the prose would break the citation without changing the
            record it cites. The fix for a wrong sentence is a fix to the
            record, and a recompilation.
            """
            who = self.authorise(request, "document:review",
                                 estate_wide="commenting on a compiled document")
            return self.guard(lambda: self.ctx["document_review"].comment(
                document_id, section=body.section, body=body.body,
                asks_for=body.asks_for, quote=body.quote,
                actor=self.actor(who)))

        @self.app.post(f"{api}/document-review/{{comment_id}}/resolve",
                       tags=["documents"])
        def resolve_comment(request: Request, comment_id: str,
                            body: ResolveCommentIn):
            """Close a comment, saying what was done — and which node if any."""
            who = self.authorise(request, "document:review",
                                 estate_wide="resolving a document comment")
            return self.guard(lambda: self.ctx["document_review"].resolve(
                comment_id, body.resolution, evidence_id=body.evidence_id,
                actor=self.actor(who)))

        @self.app.post(f"{api}/document-review/{{comment_id}}/withdraw",
                       tags=["documents"])
        def withdraw_comment(request: Request, comment_id: str,
                             reason: str = ""):
            """Take a comment back. Recorded as what it is, never deleted."""
            who = self.authorise(request, "document:read",
                                 estate_wide="withdrawing a document comment")
            return self.guard(lambda: self.ctx["document_review"].withdraw(
                comment_id, reason, actor=self.actor(who)))

        # ------------------------------------------------ request-time inputs
        @self.app.get(f"{api}/request-time/guarantees", tags=["features"])
        def request_time_guarantees(request: Request):
            """What the platform promises about a stored value, and not a sent one."""
            self.authorise(request, "feature:read")
            return RequestTimeInputs.guarantees()

        @self.app.get(f"{api}/request-time", tags=["features"])
        def request_time(request: Request, urn: str = "", semver: str = "",
                         now: Optional[float] = None):
            """What arrives in the request, and what cannot be promised about it."""
            engine = self.ctx["request_time"]
            if not urn:
                self.authorise(request, "feature:read",
                               estate_wide="reading every caller-supplied input")
                return self.guard(lambda: engine.across_the_estate(now=now))
            model = self.guard(lambda: self.ctx["registry"].require(urn))
            self.authorise(request, "feature:read", model=model)
            return self.guard(lambda: engine.posture(urn, semver))

        @self.app.post(f"{api}/request-time/check", tags=["features"])
        def check_request_time(request: Request, body: RequestPayloadIn):
            """Judge one request's caller-supplied values against the contract.

            Every violation is reported rather than the first: a caller told
            about one bad field fixes it, retries, and is told about the next.
            """
            model = self.guard(lambda: self.ctx["registry"].require(body.urn))
            self.authorise(request, "feature:read", model=model)
            return self.guard(lambda: self.ctx["request_time"].check(
                body.urn, body.semver, body.payload))
