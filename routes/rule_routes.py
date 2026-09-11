"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The rule-set editor's API.

Four verbs and one vocabulary, and the split between them is the whole design:
`check` and `trial` are **free** — they carry no authority, record nothing and
can be called on every keystroke — while `publish` is the ordinary
`parameter:record` act with the ordinary consequences. An author iterates
without touching the register, and the moment their draft becomes a governed
object is one act they had to choose.
"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import Request
from pydantic import Field

from core.rules.common import OPERATOR_MEANING, OPERATORS, ORDERED_DTYPES, ORDERED_ONLY
from routes.base import Body, Routes



class ExtensionIn(Body):
    axis: str
    name: str
    owner: str
    does: str

class RuleImportIn(Body):
    """A rulebook as the bank already holds it.

    `document` is text — a CSV decision table or a DMN file — rather than a
    parsed object, because the whole point is to read what the source system
    exported without anybody retyping it in between.
    """
    format: str
    document: str
    note: str = ""
    urn: str = ""
    semver: str = ""


class RuleSetIn(Body):
    urn: str
    semver: str
    document: Dict[str, Any]


class RuleTrialIn(RuleSetIn):
    rows: List[Dict[str, Any]] = Field(default_factory=list)


class RulePublishIn(RuleSetIn):
    name: str
    note: str = ""


class RuleRoutes(Routes):
    def register(self) -> None:
        api = self.api

        @self.app.get(f"{api}/extension-points", tags=["policy"])
        def extension_points(request: Request, axis: str = ""):
            """Which parts of this platform a deployment may extend.

            **The dividing line is whether the extension changes a governance
            answer.** A notification channel changes how somebody is told; a
            runtime adapter changes what may execute. The four closed axes are
            each a place where a plugin would be a *removal* rather than an
            extension — an open format axis is a `pickle` loader arriving by
            pull request — so a closed axis here is not a missing feature, it is
            the feature.

            Every closed axis names what the closure protects and a route to
            what the caller actually wanted, because a refusal that names no
            route is a wall.
            """
            self.principal(request)
            return self.guard(
                lambda: self.ctx["extensions"].registered(axis))

        @self.app.post(f"{api}/extension-points", status_code=201,
                       tags=["policy"])
        def register_extension(request: Request, body: ExtensionIn):
            """Add something on an open axis. A governance act, not an import.

            A name is never silently replaced: doing so would change what a
            recorded result *means* without changing its name, and every
            measurement taken under the old one would still say it was taken
            under this.
            """
            who = self.authorise(request, "policy:publish")
            return self.guard(lambda: self.ctx["extensions"].register(
                body.axis, body.name, owner=body.owner, does=body.does,
                actor=self.actor(who)))

        @self.app.get(f"{api}/rulesets/vocabulary", tags=["rules"])
        def vocabulary(request: Request):
            """Everything an editor needs to offer, from the code rather than
            from a copy of it. A screen holding its own operator list is a
            second vocabulary that drifts from the first."""
            self.principal(request)
            return {
                "operators": [{"op": op, "means": OPERATOR_MEANING[op],
                               "needs_ordered_field": op in ORDERED_ONLY}
                              for op in OPERATORS],
                "combinators": ["all", "any", "not"],
                "ordered_dtypes": sorted(ORDERED_DTYPES),
                "outcome": "an object; its fields must be declared in the "
                           "version's output schema",
            }

        @self.app.post(f"{api}/rulesets/check", tags=["rules"])
        def check(request: Request, body: RuleSetIn):
            """Validate a draft against the version's schemas.

            Reads rather than writes, so `model:read` and not
            `parameter:record`: checking a draft changes nothing, and requiring
            the recording permission to *look* at whether a document is valid
            would push authors to skip the step.
            """
            model = self.guard(lambda: self.ctx["registry"].require(body.urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(lambda: self.ctx["rules"].check(
                body.urn, body.semver, body.document))

        @self.app.post(f"{api}/rulesets/trial", tags=["rules"])
        def trial(request: Request, body: RuleTrialIn):
            """Run a draft against sample rows. Records nothing, decides nothing.

            Deliberately not `/execute`: there is no warrant and no entitlement,
            because nothing is being scored — an author is reading their own
            draft back. The response also reports which rules fired on no row,
            which is the question worth asking before approval.
            """
            model = self.guard(lambda: self.ctx["registry"].require(body.urn))
            self.authorise(request, "model:read", model=model)
            return self.guard(lambda: self.ctx["rules"].trial(
                body.urn, body.semver, body.document, body.rows))

        @self.app.post(f"{api}/rulesets", status_code=201, tags=["rules"])
        def publish(request: Request, body: RulePublishIn):
            """Record the rule set as a parameter set, validated first.

            No new authority: this is `POST /parameters` reached through a door
            that checks the document. The set lands `proposed`, and somebody
            other than its author approves it — exactly as a fitted coefficient
            set does.
            """
            model = self.guard(lambda: self.ctx["registry"].require(body.urn))
            who = self.authorise(request, "parameter:record", model=model)
            return self.guard(lambda: self.ctx["rules"].publish(
                body.urn, body.semver, body.name, body.document, body.note,
                self.actor(who)))

        @self.app.get(f"{api}/rulesets/{{parameter_set_id}}", tags=["rules"])
        def explain(request: Request, parameter_set_id: str):
            """An approved rule set in English.

            One rendering, so the model card, the committee paper and the export
            pack quote the same sentences rather than each writing their own —
            and the differences between three renderings are exactly where a
            misreading survives.
            """
            self.authorise(request, "model:read")
            return self.guard(lambda: self.ctx["rules"].explain(parameter_set_id))


        # ----------------------------------------------- importing a rulebook
        @self.app.get(f"{api}/rule-import/formats", tags=["rules"])
        def import_formats(request: Request):
            """What can be read, what cannot, and what to do instead.

            The refused list is the useful half. A stored procedure is not
            translated and will not be: SQL is a general language, a
            translator would be a compiler, and a wrong compiler produces a
            rule set that loads, validates and decides differently from the
            procedure it claims to be — which nobody finds by reading it.
            """
            self.principal(request)
            from core.rules.importing import RuleSetImport
            return RuleSetImport.formats()

        @self.app.post(f"{api}/rule-import", tags=["rules"])
        def import_rulebook(request: Request, body: RuleImportIn):
            """Read a decision table or a DMN file into a rule set **candidate**.

            Nothing is written. What comes back is a document for the same
            `check`, `trial` and `publish` path a hand-written rule set takes,
            including the second-person approval — because an importer that
            wrote into the register would be authoring a parameter set on
            somebody else's behalf, which is the one thing the rules editor
            was careful not to do.

            Rows that could not be translated are named with the cell that
            stopped them, and a document with any of them is refused **as a
            whole**. A parser finds the judgement calls hard, and the
            judgement calls are what a rulebook exists for.

            Pass `urn` and `semver` to have the result validated against that
            version's schemas as well as parsed. Parsing says the document was
            readable; validation says whether it is usable, and only the
            second is the question somebody importing a rulebook has.
            """
            self.authorise(request, "model:read")
            engine = self.ctx["rule_import"]
            if body.urn and body.semver:
                model = self.guard(
                    lambda: self.ctx["registry"].require(body.urn))
                self.authorise(request, "model:read", model=model)
                return self.guard(lambda: engine.check(
                    body.urn, body.semver, body.format, body.document,
                    note=body.note))
            return self.guard(
                lambda: engine.read(body.format, body.document,
                                    note=body.note))
