"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — registration, the record lifecycle, and the state machine.

Mostly the same shape: a short sequence, and an assertion about what the last
step does. Written as data rather than as one function each, so the case is
visible and the boilerplate is not.

Each case that needs a subject registers **its own**. Sharing one model across
cases is how a case comes to pass because of what the previous one left
behind, which has already happened once in this run.
"""
from __future__ import annotations

from tools.qa.scenarios.common import Ctx, sequence

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}

#: A complete assessment.
#:
#: Every fact, because a partial one is refused `fact_not_supplied` — "this
#: assessment lands on a different tier depending on feature_count,
#: interpretable, uses_alternative_data, and the request did not say". The
#: platform will not guess a tier, which is the right answer and made half
#: this file's setups fail until they said everything.
ASSESSMENT = {"exposure": 1_000_000.0, "purpose_class": "credit_decision",
              "feature_count": 12, "interpretable": True,
              "uses_alternative_data": False}


def fresh(ctx: Ctx) -> dict:
    """Register a model and bind `{name}` and `{urn}` for the steps.

    The URN is `maya://model/<name>` and not `maya://model/qa.<name>`.
    Every `/models/{name}/...` route derives the URN from the name, so a
    record whose URN does not match its name is invisible to its own
    endpoints — and the first version of this file registered fourteen models
    the routes could not then find, which read as fourteen defects.
    """
    name = ctx.unique("gov")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": "admin", **TIER})
    return {"name": name, "urn": urn}


def unregistered(ctx: Ctx) -> dict:
    """A name and URN that have NOT been registered."""
    name = ctx.unique("gov")
    return {"name": name, "urn": f"maya://model/{name}"}


def submitted(ctx: Ctx) -> dict:
    """A model in `submitted` — registered, versioned, tiered, submitted.

    Written out because the state a case is about is usually several acts
    away from a fresh record, and a case that asserts on `submitted` while
    its subject is still a draft asserts on the wrong thing. QA-GOV-034
    ("retire a submitted record") passed a draft to the retirement route,
    which legitimately accepted it, and the case reported a defect.
    """
    bound = fresh(ctx)
    name = bound["name"]
    ctx.api.post(f"/api/v1/models/{name}/versions", json={"semver": "1.0.0"})
    ctx.api.post(f"/api/v1/models/{name}/assess", json=ASSESSMENT)
    ctx.api.post(f"/api/v1/models/{name}/submit", json={"note": "qa"})
    return bound


M = "/api/v1/models"

# --------------------------------------------------------------- registration
sequence("QA-GOV-001", "Register the same URN twice",
         [("POST", M, {"urn": "{urn}", "name": "{name}", "owner": "admin", **TIER}),
          ("POST", M, {"urn": "{urn}", "name": "{name}", "owner": "admin", **TIER})],
         ("refused", "registry_refused"), setup=unregistered)

sequence("QA-GOV-002", "Two URNs differing only in letter case",
         [("POST", M, {"urn": "maya://model/qa.{name}", "name": "{name}",
                       "owner": "admin", **TIER}),
          ("POST", M, {"urn": "maya://model/QA.{name}", "name": "{name}-upper",
                       "owner": "admin", **TIER})],
         ("explore",), setup=unregistered)

sequence("QA-GOV-003", "A URN that is a strict prefix of an existing one",
         [("POST", M, {"urn": "{urn}.smallbiz", "name": "{name}-smallbiz",
                       "owner": "admin", **TIER})],
         ("accepted",), setup=fresh)

sequence("QA-GOV-004", "Submit with no version and no tier",
         [("POST", M + "/{name}/submit", {})],
         ("refused", "nothing_to_approve", "not_tiered", "illegal_transition",
          "no_version"),
         setup=fresh)

sequence("QA-GOV-007", "PATCH an editable field on a draft",
         [("PATCH", M + "/{name}", {"fields": {"owner": "someone-else"}})],
         ("accepted",), setup=fresh)

sequence("QA-GOV-008", "PATCH the urn on a draft",
         [("PATCH", M + "/{name}", {"fields": {"urn": "maya://model/stolen"}})],
         ("refused", "registry_refused", "validation_error"), setup=fresh)

sequence("QA-GOV-009", "PATCH status directly, bypassing the state machine",
         [("PATCH", M + "/{name}", {"fields": {"status": "attested"}})],
         ("refused", "registry_refused", "validation_error"), setup=fresh)

sequence("QA-GOV-010", "PATCH tier directly",
         [("PATCH", M + "/{name}", {"fields": {"tier": 4}})],
         ("refused", "registry_refused", "validation_error"), setup=fresh)

sequence("QA-GOV-011", "PATCH with an empty body",
         [("PATCH", M + "/{name}", {"fields": {}})], ("accepted",), setup=fresh)

sequence("QA-GOV-012", "PATCH the same field to the same value twice",
         [("PATCH", M + "/{name}", {"fields": {"owner": "x"}}),
          ("PATCH", M + "/{name}", {"fields": {"owner": "x"}})],
         ("accepted",), setup=fresh)

sequence("QA-GOV-015", "Designations back to empty after being populated",
         [("PUT", M + "/{name}/designations", {"designations": ["sox_relevant"]}),
          ("PUT", M + "/{name}/designations", {"designations": []})],
         ("accepted",), setup=fresh)

sequence("QA-GOV-016", "Designations containing the same value twice",
         [("PUT", M + "/{name}/designations",
           {"designations": ["sox_relevant", "sox_relevant"]})],
         ("accepted",), setup=fresh)

# ------------------------------------------------------------------ lifecycle
sequence("QA-GOV-030", "Approve a draft record",
         [("POST", M + "/{name}/approve", {})],
         ("refused", "illegal_transition"), setup=fresh)

sequence("QA-GOV-031", "Attest a submitted record",
         [("POST", M + "/{name}/attest", {"role": "model_owner"})],
         ("refused", "illegal_transition", "no_attestation_open",
          "validation_error"), setup=fresh)

sequence("QA-GOV-032", "Return a draft record",
         [("POST", M + "/{name}/return", {"reason": "not ready"})],
         ("refused", "illegal_transition"), setup=fresh)

sequence("QA-GOV-033", "Return with a whitespace-only reason",
         [("POST", M + "/{name}/return", {"reason": "   "})],
         ("refused", "illegal_transition", "reason_required",
          "validation_error"), setup=fresh)

sequence("QA-GOV-034", "Retire a submitted record",
         [("POST", M + "/{name}/retire", {"reason": "qa"})],
         ("refused", "illegal_transition"), setup=submitted)

sequence("QA-GOV-029", "Submit twice",
         [("POST", M + "/{name}/submit", {"note": "again"})],
         ("refused", "illegal_transition"), setup=submitted)

sequence("QA-GOV-005", "Submit with a version but no assessment",
         [("POST", M + "/{name}/versions", {"semver": "1.0.0"}),
          ("POST", M + "/{name}/submit", {"note": "qa"})],
         ("refused", "not_tiered", "nothing_to_approve"), setup=fresh)

sequence("QA-GOV-006", "The full ordered path: register, version, assess, submit",
         [("POST", M + "/{name}/versions", {"semver": "1.0.0"}),
          ("POST", M + "/{name}/assess", ASSESSMENT),
          ("POST", M + "/{name}/submit", {"note": "qa"})],
         ("accepted",), setup=fresh)

sequence("QA-GOV-063", "Approve a submitted record",
         [("POST", M + "/{name}/approve", {"note": "qa"})],
         ("accepted",), setup=submitted)

sequence("QA-GOV-036", "Retire twice",
         [("POST", M + "/{name}/retire", {"reason": "qa"}),
          ("POST", M + "/{name}/retire", {"reason": "qa"})],
         ("refused", "illegal_transition"), setup=fresh)

sequence("QA-GOV-037", "Add a version to a retired record",
         [("POST", M + "/{name}/retire", {"reason": "qa"}),
          ("POST", M + "/{name}/versions", {"semver": "1.0.0"})],
         ("refused", "registry_refused", "illegal_transition"), setup=fresh)

sequence("QA-GOV-038", "PATCH a retired record",
         [("POST", M + "/{name}/retire", {"reason": "qa"}),
          ("PATCH", M + "/{name}", {"fields": {"owner": "x"}})],
         ("refused", "registry_refused"), setup=fresh)

sequence("QA-GOV-041", "Sign an attestation before approval",
         [("POST", M + "/{name}/attest", {"role": "model_owner",
                                          "decision": "sign"})],
         ("refused", "no_attestation_open", "illegal_transition",
          "validation_error"), setup=fresh)

# ---------------------------------------------------------------- unknown ids
sequence("QA-GOV-060", "Submit a model that does not exist",
         [("POST", M + "/{name}/submit", {})],
         ("refused", "registry_refused", "not_found"), setup=unregistered)

sequence("QA-GOV-061", "Retire a model that does not exist",
         [("POST", M + "/{name}/retire", {"reason": "qa"})],
         ("refused", "registry_refused", "not_found"), setup=unregistered)

sequence("QA-GOV-062", "Assess a model that does not exist",
         [("POST", M + "/{name}/assess", ASSESSMENT)],
         ("refused", "registry_refused", "not_found", "validation_error"),
         setup=unregistered)

# --------------------------------------------------------------------- intake
sequence("QA-GOV-023", "Triage with an empty rationale",
         [("POST", "/api/v1/intake", {"title": "QA proposal",
                                      "sponsor": "admin",
                                      "description": "a QA proposal"}),
          ("POST", "/api/v1/intake/QA-1/triage", {"in_scope": True,
                                                  "rationale": "   "})],
         ("refused", "rationale_required", "not_found", "validation_error"))
