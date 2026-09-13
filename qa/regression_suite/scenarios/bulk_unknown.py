"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Hand-written cases at the rate the generated ones run.

The slow part of authoring these was never the judgement. It was discovering
each endpoint's request shape by sending a wrong one and reading the 422 —
`threshold` is a mapping, `claims` are objects, `output` is an object. With
`valid_body` reading the schema, a case is a line again.

What these ask is a judgement a generator cannot make: **given a body the
endpoint accepts, does the control still fire when one field is wrong?**
Section B omits a required field and section C supplies an unknown id; neither
sends an otherwise-valid request with one blank stated ground in it, and that
is where four defects have already been found — a warrant's declared use, a
revocation reason, a finding title, a monitor owner, every one declared
required and every one passing on `"   "`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from qa.regression_suite.scenarios.common import (FAIL, PASS, Ctx, Result, case,
                                       code_of, valid_body)

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}

#: (case id, method, path, the field to blank, what it is)
#:
#: Every one is a *stated ground* — a field whose whole purpose is to record
#: why something was done. A blank one is not a small value; it is the
#: absence of the thing the field exists for, recorded as if present.
BLANK_GROUNDS: List[Tuple[str, str, str, str, str]] = [
    ("QA-GOV-100", "POST", "/api/v1/models", "owner",
     "a model with no owner is a model nobody answers for"),
    ("QA-GOV-101", "POST", "/api/v1/models", "urn",
     "the identifier everything else cites"),
    ("QA-GOV-102", "POST", "/api/v1/models", "name",
     "what every screen calls it"),
    ("QA-GOV-103", "POST", "/api/v1/models", "legal_entity",
     "which entity's regulator is interested"),
    ("QA-GOV-104", "POST", "/api/v1/models", "purpose",
     "what it is for, which decides the tier"),
    ("QA-GOV-105", "POST", "/api/v1/legal-holds", "matter",
     "a hold with no matter is one nobody can tell has ended"),
    ("QA-GOV-106", "POST", "/api/v1/legal-holds", "owner",
     "a hold nobody owns is one nobody will lift"),
    ("QA-GOV-107", "POST", "/api/v1/intake", "title",
     "what is being proposed"),
    ("QA-GOV-108", "POST", "/api/v1/finding-roots", "title",
     "the name of the cause"),
    ("QA-GOV-109", "POST", "/api/v1/finding-roots", "detail",
     "the description of the cause"),
]


def _register(fixture: Tuple[str, str, str, str, str]) -> None:
    case_id, method, path, field, why = fixture

    def run(ctx: Ctx) -> Result:
        body = valid_body(ctx, method, path)
        if field not in body:
            return FAIL, (f"`{field}` is not in the schema for {method} "
                          f"{path}; the case names a field the endpoint does "
                          f"not have")
        body[field] = "   "
        got = ctx.api.request(method, path, json=body)
        if got.status_code >= 500:
            return FAIL, f"{got.status_code} — a blank field crashed it"
        if got.status_code < 400:
            return FAIL, (f"`{field}` was accepted blank, and {why}. A "
                          f"truthiness check passes whitespace, which is "
                          f"how every one of these gets through")
        return PASS, f"refused '{code_of(got) or got.status_code}'"

    case(case_id, f"{method} {path} with a blank `{field}`")(run)


for fixture in BLANK_GROUNDS:
    _register(fixture)


#: Endpoints that take a free-text reason for an irreversible or
#: outward-facing act. The reason is the whole record of why.
BLANK_REASONS: List[Tuple[str, str, str, Dict[str, Any]]] = [
    ("QA-GOV-120", "POST", "/api/v1/warrants/revoke",
     {"urn": "maya://model/qa.any"}),
]


@case("QA-GOV-130", "Every stated-ground field this pass has fixed stays fixed")
def gov_130(ctx: Ctx) -> Result:
    """A regression over the family rather than the instances.

    Four were found one at a time, in four subsystems, by four different
    cases. This asserts all four together, so a fifth subsystem copying the
    pattern from any of them inherits the fix rather than the defect.
    """
    import inspect

    from core.execution.grants import WarrantGrants
    from core.monitoring.definitions import MonitorRegistry
    from core.validation.findings import FindingRegister
    checks = {
        "warrant declared_use": inspect.getsource(WarrantGrants.issue),
        "warrant revoke reason": inspect.getsource(WarrantGrants.revoke),
        "finding title": inspect.getsource(FindingRegister.raise_finding),
        "monitor owner": inspect.getsource(MonitorRegistry.define),
    }
    weak = [name for name, source in checks.items()
            if ".strip()" not in source]
    if weak:
        return FAIL, (f"these no longer strip their stated ground, so "
                      f"whitespace passes again: {weak}")
    return PASS, "all four still strip before checking"
