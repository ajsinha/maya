"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — decommission: taking a model out, with the facts needed later.

`retire` is a state transition; decommission is the record of what a
retirement WAS. The case that matters most is the last one: a model something
else reads cannot vanish quietly, and the two ways a firm can proceed anyway —
telling the consumers, or recording that somebody looked and decided regardless
— are deliberately different facts.
"""
from __future__ import annotations

from core.lifecycle.decommission import CLASSES, NOTHING, REQUIRED
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

M = "/api/v1/models"
D = "/api/v1/decommission"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
ASSESSMENT = {"exposure": 1_000.0, "purpose_class": "commercial",
              "feature_count": 3, "interpretable": True,
              "uses_alternative_data": False}


#: A kernel producing a score and one consuming it, so an `input_to` edge
#: between them composes. Without matching schemas the relation is refused
#: "it produces nothing", and every consumer case blocks on the fixture.
PRODUCES = {"parameter_kind": "estimated_coefficients",
            "fit_procedure": "estimate", "runtime": "estimator",
            "input_schema": [{"name": "x", "dtype": "float"}],
            "output_schema": [{"name": "score", "dtype": "float"}]}
CONSUMES = {"parameter_kind": "estimated_coefficients",
            "fit_procedure": "estimate", "runtime": "estimator",
            "input_schema": [{"name": "score", "dtype": "float"}],
            "output_schema": [{"name": "decision", "dtype": "float"}]}


def _attested(ctx: Ctx, kernel=None) -> str:
    """A model in a state a decommission can be recorded against."""
    name = ctx.unique("dc")
    api = ctx.api
    api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                      "owner": "owner", **TIER})
    api.post(f"{M}/{name}/versions",
             json={"semver": "1.0.0", "kernel": kernel} if kernel
             else {"semver": "1.0.0"},
             auth=ctx.people["developer"])
    api.post(f"{M}/{name}/assess", json=ASSESSMENT)
    api.post(f"{M}/{name}/submit", json={"note": "qa"})
    api.post(f"{M}/{name}/approve", json={"note": "qa"})
    for role, who in (("model_owner", "owner"),
                      ("model_risk_manager", "risk")):
        api.post(f"{M}/{name}/attest",
                 json={"role": role, "decision": "attest", "statement": "qa"},
                 auth=ctx.people[who])
    return name


def _record(ctx: Ctx, name: str, **over):
    body = {"rationale": "superseded by a newer scorecard this quarter",
            "replacement": NOTHING, "retention_class": sorted(CLASSES)[0],
            "notified": [], "acknowledged": False}
    body.update(over)
    # `POST /decommission?urn=...` — the model is a query parameter, not a
    # path segment. Posting to /models/{name}/decommission answers 405,
    # which is a refusal, and therefore scored as a pass.
    return ctx.api.post(f"{D}?urn=maya://model/{name}", json=body)


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-GOV-4600", "A decommission with a one-word rationale")
def gov_4600(ctx: Ctx) -> Result:
    """"Why it is being taken out, in more than a word." `retire` already
    records that it happened; this records why, and a single word records
    neither."""
    got = _record(ctx, _attested(ctx), rationale="old")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, "a decommission was recorded with a one-word reason"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-4601", "A decommission with a blank replacement")
def gov_4601(ctx: Ctx) -> Result:
    """"Blank is indistinguishable from nobody having filled it in." Saying
    nothing replaces it is a fact; saying nothing at all is not."""
    got = _record(ctx, _attested(ctx), replacement="")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a decommission was recorded with a blank replacement, "
                      "which reads the same as nobody having answered")
    if NOTHING not in got.text:
        return FAIL, (f"the refusal does not offer '{NOTHING}' as the way to "
                      f"say nothing replaces it: {got.text[:120]}")
    return PASS, f"refused '{code_of(got)}', naming '{NOTHING}'"


@case("QA-GOV-4602", "A replacement that is not registered")
def gov_4602(ctx: Ctx) -> Result:
    """Naming a successor nobody registered is a hand-off to nothing, and it
    is the field somebody reads a year later to find where the work went."""
    got = _record(ctx, _attested(ctx),
                  replacement="maya://model/qa.never.existed")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a decommission names a successor that does not exist"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-4603", "A retention class that is not one")
def gov_4603(ctx: Ctx) -> Result:
    """The class decides how long the record is kept and under which rule. A
    value outside the set is a retention nobody can apply."""
    got = _record(ctx, _attested(ctx), retention_class="a while")
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, "a decommission was recorded under an unknown retention"
    if not any(c in got.text for c in CLASSES):
        return FAIL, "the refusal does not name the retention classes"
    return PASS, f"refused '{code_of(got)}', naming {len(CLASSES)} classes"


@case("QA-GOV-4604", "A decommission recorded twice")
def gov_4604(ctx: Ctx) -> Result:
    """A model is taken out of service once. Two records are two accounts of
    the same event, and neither is the one somebody reads."""
    name = _attested(ctx)
    first = _record(ctx, name)
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    again = _record(ctx, name, rationale="taken out again for other reasons")
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code < 400:
        return FAIL, "a model was decommissioned twice"
    return PASS, f"refused '{code_of(again)}'"


@case("QA-GOV-4605", "A model something else reads")
def gov_4605(ctx: Ctx) -> Result:
    """The one that matters. A feeder model disappearing quietly breaks
    whatever reads it, months later, with no trace of the decision."""
    upstream = _attested(ctx, PRODUCES)
    downstream = _attested(ctx, CONSUMES)
    edge = ctx.api.post("/api/v1/model-relations",
                        json={"from_urn": f"maya://model/{upstream}",
                              "to_urn": f"maya://model/{downstream}",
                              "kind": "input_to"})
    if edge.status_code >= 400:
        return BLOCKED, f"could not relate the two: {edge.text[:140]}"
    got = _record(ctx, upstream)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        if downstream not in got.text:
            return FAIL, (f"the refusal does not name the consumer: "
                          f"{got.text[:130]}")
        return PASS, f"refused '{code_of(got)}', naming the consumer"
    # Establish the mechanism rather than the symptom.
    composition = ctx.ui.app.state.ctx.get("composition")
    why = ""
    if composition is not None:
        radius = composition.blast_radius(f"maya://model/{upstream}")
        if radius.get("reaches") and not radius.get("reached"):
            why = (" — `blast_radius` answers `reaches` and `consumers()` "
                   "reads `reached`, so the list is always empty and the "
                   "`consumers_not_notified` refusal can never fire")
    return FAIL, (
        "a model another one reads was decommissioned with its consumers "
        "neither notified nor acknowledged" + why)


@case("QA-GOV-4606", "Notified and acknowledged are different facts")
def gov_4606(ctx: Ctx) -> Result:
    """"Somebody looked at this list and decided anyway is a different fact
    from nobody having looked, and both are better than a feeder model
    disappearing quietly." Both must work, and be distinguishable."""
    results = {}
    for label in ("notified", "acknowledged"):
        upstream = _attested(ctx, PRODUCES)
        downstream = _attested(ctx, CONSUMES)
        if ctx.api.post("/api/v1/model-relations",
                        json={"from_urn": f"maya://model/{upstream}",
                              "to_urn": f"maya://model/{downstream}",
                              "kind": "input_to"}).status_code >= 400:
            return BLOCKED, "could not relate the two"
        over = ({"notified": [f"maya://model/{downstream}"]}
                if label == "notified" else {"acknowledged": True})
        results[label] = _record(ctx, upstream, **over)
    for label, got in results.items():
        if got.status_code >= 400:
            return FAIL, (f"'{label}' did not let the decommission proceed: "
                          f"{got.text[:120]}")
    bodies = {label: got.json() or {} for label, got in results.items()}
    if bodies["notified"].get("acknowledged") == \
            bodies["acknowledged"].get("acknowledged") and \
            bodies["notified"].get("notified") == \
            bodies["acknowledged"].get("notified"):
        return FAIL, ("telling the consumers and recording that somebody "
                      "decided anyway produce an identical record")
    # Both proceeded — but with the consumer list empty (QA-GOV-4605) they
    # would proceed regardless, so say which was actually demonstrated.
    composition = ctx.ui.app.state.ctx.get("composition")
    enforced = bool(composition is None or
                    (composition.blast_radius(f"maya://model/{upstream}")
                     .get("reached")))
    return PASS, ("both proceed and the record distinguishes them"
                  + ("" if enforced else
                     "; note the consumer list is empty either way, so this "
                     "shows the fields are recorded rather than that the gate "
                     "was passed"))


@case("QA-GOV-4607", "Every required field says why it is required")
def gov_4607(ctx: Ctx) -> Result:
    """The decommission record is read a year later by somebody who was not
    there. A field with no stated purpose is one they will fill in badly."""
    mute = [field for field, why in REQUIRED if not (why or "").strip()]
    if mute:
        return FAIL, f"required with no reason: {mute}"
    got = ctx.api.get(D, auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    for field, _ in REQUIRED:
        if field not in got.text:
            return FAIL, f"'{field}' is required and not published"
    return PASS, f"{len(REQUIRED)} required fields, each published with a reason"


@case("QA-GOV-4608", "The consumer reading is available before deciding")
def gov_4608(ctx: Ctx) -> Result:
    """Somebody should be able to see who reads a model BEFORE they try to
    take it out, rather than discovering it in a refusal."""
    upstream = _attested(ctx, PRODUCES)
    downstream = _attested(ctx, CONSUMES)
    if ctx.api.post("/api/v1/model-relations",
                    json={"from_urn": f"maya://model/{upstream}",
                          "to_urn": f"maya://model/{downstream}",
                          "kind": "input_to"}).status_code >= 400:
        return BLOCKED, "could not relate the two"
    got = ctx.api.get(f"{D}/consumers?urn=maya://model/{upstream}",
                      auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    if downstream not in got.text:
        composition = ctx.ui.app.state.ctx.get("composition")
        why = ""
        if composition is not None:
            radius = composition.blast_radius(f"maya://model/{upstream}")
            if radius.get("reaches"):
                why = (f" — the graph reaches {len(radius['reaches'])} model(s) "
                       f"under the key `reaches`, and `consumers()` reads "
                       f"`reached`")
        return FAIL, ("the consumer reading reports nothing downstream for a "
                      "model that is read by another" + why)
    return PASS, "the consumers are readable before the decision"
