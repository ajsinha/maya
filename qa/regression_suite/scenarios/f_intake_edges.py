"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — intake, and the crossing from proposal to model.

A proposal is not a model and is not stored as one. The interesting boundary
is the crossing: what may cross, what may cross twice, and whether a reading
the platform produced can be mistaken for a determination a person made.
"""
from __future__ import annotations

from core.lifecycle.intake import BUILD, SOURCING
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

INTAKE = "/api/v1/intake"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _proposed(ctx: Ctx) -> str:
    ref = ctx.unique("PROP")
    ctx.api.post(INTAKE, json={
        "reference": ref, "title": "A QA proposal",
        "description": "a gradient boosted model scoring credit applications",
        "proposed_by": "owner", "business_area": "retail"})
    return ref


def _triage(ctx: Ctx, ref: str, **over):
    body = {"in_scope": True, "sourcing": BUILD, "generative": False,
            "rationale": "it decides on customers"}
    body.update(over)
    return ctx.api.post(f"{INTAKE}/{ref}/triage", json=body,
                        auth=ctx.people["risk"])


def _register(ctx: Ctx, ref: str, **over):
    name = ctx.unique("in")
    body = {"urn": f"maya://model/{name}", "name": name, "owner": "owner",
            **TIER}
    body.update(over)
    return ctx.api.post(f"{INTAKE}/{ref}/register", json=body)


@case("QA-GOV-018", "Register a proposal before it has been triaged")
def gov_018(ctx: Ctx) -> Result:
    """The three intake questions are the point of intake. Crossing without
    answering them puts a model in the register that nobody decided was one.
    """
    return refused_by_the_control(
        _register(ctx, _proposed(ctx)),
        "a proposal became a model without anybody triaging it")


@case("QA-GOV-019", "Triage out of scope, then try to register")
def gov_019(ctx: Ctx) -> Result:
    ref = _proposed(ctx)
    out = _triage(ctx, ref, in_scope=False,
                  rationale="a spreadsheet, not a model")
    if out.status_code >= 400:
        return BLOCKED, out.text[:170]
    return refused_by_the_control(
        _register(ctx, ref),
        "a proposal triaged OUT of scope was registered as a model anyway")


@case("QA-GOV-020", "Register the same proposal twice")
def gov_020(ctx: Ctx) -> Result:
    """Two models from one determination is one triage doing two jobs."""
    ref = _proposed(ctx)
    if _triage(ctx, ref).status_code >= 400:
        return BLOCKED, "could not triage"
    first = _register(ctx, ref)
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    return refused_by_the_control(
        _register(ctx, ref),
        "one proposal was registered twice, so two models rest on one triage")


@case("QA-GOV-021", "Re-triage a proposal already triaged")
def gov_021(ctx: Ctx) -> Result:
    """A determination that can be revised is right — people change their
    minds on evidence. What matters is whether the first one survives on the
    record, or is overwritten without trace."""
    ref = _proposed(ctx)
    if _triage(ctx, ref).status_code >= 400:
        return BLOCKED, "could not triage"
    again = _triage(ctx, ref, sourcing="buy",
                    rationale="we are buying it after all")
    if again.status_code >= 400:
        return PASS, f"a second determination is refused '{code_of(again)}'"
    read = ctx.api.get(f"{INTAKE}?reference={ref}")
    if read.status_code >= 400:
        return BLOCKED, read.text[:170]
    if (read.json() or {}).get("sourcing") != "buy":
        return FAIL, "the revised determination was not recorded"
    # The row holds the CURRENT determination and the previous one is not in
    # it — which is right, and is not the whole story. The trace lives on the
    # evidence chain, one `proposal_triaged` node per determination, and that
    # is the place a revision has to be visible from. Reading only the row
    # and calling the first determination lost would be a false finding.
    evidence = ctx.made.get("evidence")
    if evidence is None:
        return BLOCKED, "no evidence engine on this run"
    nodes = evidence.for_subject((read.json() or {}).get("id") or "")
    triages = [n for n in nodes
               if (n.get("payload") or {}).get("sourcing") is not None]
    if len(triages) < 2:
        return FAIL, ("the first determination was overwritten with no trace; "
                      "a triage that can be silently revised is a decision "
                      "nobody can audit")
    kept = [t["payload"]["sourcing"] for t in triages]
    if BUILD not in kept:
        return FAIL, f"the first determination is not on the chain: {kept}"
    return PASS, f"revised; the chain holds both determinations {kept}"


@case("QA-GOV-022", "Register a proposal onto a URN already in the register")
def gov_022(ctx: Ctx) -> Result:
    """The proposal must stay triaged rather than being consumed by a
    crossing that did not happen."""
    taken = ctx.unique("in")
    ctx.api.post(M, json={"urn": f"maya://model/{taken}", "name": taken,
                          "owner": "owner", **TIER})
    ref = _proposed(ctx)
    if _triage(ctx, ref).status_code >= 400:
        return BLOCKED, "could not triage"
    got = _register(ctx, ref, urn=f"maya://model/{taken}", name=taken)
    if got.status_code < 400:
        return FAIL, "a proposal was registered onto a URN already in use"
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    read = ctx.api.get(f"{INTAKE}?reference={ref}")
    if (read.json() or {}).get("state") != "triaged":
        return FAIL, ("the failed crossing consumed the proposal: it now "
                      f"reads '{(read.json() or {}).get('state')}' and can "
                      f"never be registered")
    return PASS, f"refused '{code_of(got)}', proposal still triaged"


@case("QA-GOV-013", "Set designations on an attested record")
def gov_013(ctx: Ctx) -> Result:
    """A designation says a model is in scope for SOX or for a regulation.
    Whether an attested record accepts one is a real question: the record is
    immutable, and a designation is a fact about it rather than a change to
    what it says.
    """
    name = ctx.unique("in")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    ctx.api.post(f"{M}/{name}/assess",
                 json={"exposure": 1e6, "purpose_class": "credit_decision",
                       "feature_count": 12, "interpretable": True,
                       "uses_alternative_data": False})
    ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    ctx.api.post(f"{M}/{name}/approve", json={"note": "qa"})
    for role, who in (("model_owner", "owner"), ("model_risk_manager", "risk")):
        ctx.api.post(f"{M}/{name}/attest",
                     json={"role": role, "decision": "attest",
                           "statement": "qa"}, auth=ctx.people[who])
    got = ctx.api.put(f"{M}/{name}/designations",
                      json={"designations": ["sox_relevant"]})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return PASS, ("accepted on an attested record — a designation is "
                      "treated as a fact ABOUT the record rather than a "
                      "change to what it says")
    return PASS, f"refused '{code_of(got)}' on an attested record"


@case("QA-GOV-017", "A model registered with no legal entity")
def gov_017(ctx: Ctx) -> Result:
    """Scope is enforced by legal entity. A model belonging to none is a
    model no entity-scoped principal can see, and an estate-wide report then
    counts something nobody is accountable for."""
    name = ctx.unique("in")
    got = ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                                "owner": "owner", "model_class": "logistic",
                                "domain": "credit", "legal_entity": "",
                                "purpose": "credit_decision"})
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    return FAIL, ("a model was registered belonging to no legal entity, so no "
                  "entity-scoped principal can reach it and nobody is "
                  "accountable for it")


@case("QA-GOV-1400", "The sourcing vocabulary is closed")
def gov_1400(ctx: Ctx) -> Result:
    """`undecided` is a member on purpose — recorded as undecided rather than
    defaulted to build — so the vocabulary has to be closed for that choice
    to mean anything."""
    ref = _proposed(ctx)
    got = _triage(ctx, ref, sourcing="rent")
    if got.status_code < 400:
        return FAIL, "a sourcing decision outside the vocabulary was recorded"
    if code_of(got) in ("forbidden", "unauthorised"):
        return BLOCKED, "the caller never reached the check"
    if not any(k in got.text for k in SOURCING):
        return FAIL, "the refusal does not name what the vocabulary is"
    return PASS, f"refused '{code_of(got)}', naming the {len(SOURCING)} members"


@case("QA-GOV-1401", "The assessment is a reading, never a determination")
def gov_1401(ctx: Ctx) -> Result:
    """A determination whose reasoning is invisible is one nobody can
    disagree with, and the whole value of triage is in the disagreements. So
    the reading has to say which words it turned on, and must not by itself
    move the proposal."""
    ref = _proposed(ctx)
    got = ctx.api.get(f"{INTAKE}/{ref}/assessment")
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json()
    if "suggests_in_scope" not in body:
        return FAIL, f"the assessment states no reading: {sorted(body)}"
    # `answers` maps each intake question to what it suggests, WHY it
    # matters, and `on_words` — the words in the description that turned it
    # on. That last one is the part a person disagrees with.
    answers = body.get("answers") or {}
    if not answers:
        return FAIL, "the reading answers none of the intake questions"
    mute = [q for q, a in answers.items() if "on_words" not in (a or {})]
    if mute:
        return FAIL, (f"{len(mute)} question(s) suggest an answer without "
                      f"saying which words turned them on: {sorted(mute)[:3]}")
    if any(not (a or {}).get("why_it_matters") for a in answers.values()):
        return FAIL, "a question is answered without saying why it matters"
    # `state`, not a substring of the body: the row always carries
    # `triaged_at` and `triaged_by` keys, so "triaged" is in the text of
    # every proposal ever returned, triaged or not.
    after = ctx.api.get(f"{INTAKE}?reference={ref}")
    if (after.json() or {}).get("state") != "proposed":
        return FAIL, (f"reading the assessment moved the proposal to "
                      f"'{(after.json() or {}).get('state')}'")
    return PASS, (f"{len(answers)} questions, each naming the words it "
                  f"turned on, and the proposal untouched")
