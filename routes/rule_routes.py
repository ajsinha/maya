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
from pydantic import BaseModel, Field

from core.rules.common import OPERATOR_MEANING, OPERATORS, ORDERED_DTYPES, ORDERED_ONLY
from routes.base import Body, Routes


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
