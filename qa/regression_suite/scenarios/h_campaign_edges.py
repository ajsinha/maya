"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the edges of a recertification round.

`h_campaigns.py` covers opening, answering and closing. These are the cases
where the round exists and something about it cannot be cited, read or
answered: a round nobody can refer to, a state that is not one, a reassignment
to nobody, a population that moved after launch, and a reference that does not
exist at all.

The thread running through them is that a campaign is evidence somebody asked.
Every one of these failures produces a round that looks answered from the
outside and cannot be shown to anybody.
"""
from __future__ import annotations

from core.lifecycle.campaigns import ITEM_STATES, KINDS
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of,
                                                  refused_by_the_control)

C = "/api/v1/campaigns"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx) -> str:
    name = ctx.unique("ce")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    return urn


def _open(ctx: Ctx, **over):
    body = {"reference": ctx.unique("CERT"), "kind": sorted(KINDS)[0],
            "title": "A QA round", "where": [], "instruction": "confirm"}
    body.update(over)
    return ctx.api.post(C, json=body, auth=ctx.people["risk"])


@case("QA-AM-801", "A campaign with no reference")
def am_801(ctx: Ctx) -> Result:
    """The reference is how a round is cited afterwards — in a board paper, in
    a regulator's request, in the sentence *we recertified the estate in Q2*.
    A round with none is one nobody can point at, and the evidence it produced
    belongs to no identifiable exercise."""
    return refused_by_the_control(
        _open(ctx, reference="   "),
        "a recertification round opened with nothing to cite it by, so what "
        "it produced belongs to no identifiable exercise")


@case("QA-AM-804", "Respond with a state that is not one")
def am_804(ctx: Ctx) -> Result:
    """The vocabulary is closed for the reason every vocabulary here is: the
    completion figure counts states, and a state nobody declared is counted by
    nothing and reported as neither done nor outstanding."""
    urn = _model(ctx)
    opened = _open(ctx)
    if opened.status_code >= 400:
        return BLOCKED, f"the round would not open: {opened.text[:120]}"
    reference = (opened.json() or {}).get("reference") or ""
    got = ctx.api.post(f"{C}/{reference}/respond",
                       json={"urn": urn, "state": "probably_fine",
                             "response": "seems ok"},
                       auth=ctx.people["owner"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, (f"an item was answered 'probably_fine', which is not one "
                      f"of {sorted(ITEM_STATES)}, so the completion figure counts "
                      f"it as neither done nor outstanding")
    if not any(s in got.text for s in ITEM_STATES):
        return FAIL, (f"refused '{code_of(got)}' without naming the states "
                      f"that are allowed")
    return PASS, f"refused '{code_of(got)}', naming {len(ITEM_STATES)} state(s)"


@case("QA-AM-806", "Reassign a campaign item to nobody")
def am_806(ctx: Ctx) -> Result:
    """Reassignment exists because reviewers leave, go on secondment, and turn
    out to be in the population they were asked to review. To NOBODY is the
    one destination that helps none of those: the item stays outstanding and
    the record says somebody dealt with it."""
    urn = _model(ctx)
    opened = _open(ctx)
    if opened.status_code >= 400:
        return BLOCKED, f"the round would not open: {opened.text[:120]}"
    reference = (opened.json() or {}).get("reference") or ""
    return refused_by_the_control(
        ctx.api.post(f"{C}/{reference}/reassign",
                     json={"urn": urn, "to": "   ",
                           "reason": "the reviewer has left"},
                     auth=ctx.people["owner"]),
        "an item was reassigned to nobody, so it is outstanding and the "
        "record says it was dealt with")


@case("QA-AM-807", "A campaign's population is frozen at launch")
def am_807(ctx: Ctx) -> Result:
    """The property the whole design rests on. If a model registered after
    launch joined the round, completion would fall as the estate grew and a
    round could never finish; if one could leave, a model could be removed
    from a review by being retired mid-round and the round would still report
    100%.
    """
    before = _model(ctx)
    opened = _open(ctx)
    if opened.status_code >= 400:
        return BLOCKED, f"the round would not open: {opened.text[:120]}"
    reference = (opened.json() or {}).get("reference") or ""
    first = ctx.api.get(f"{C}?reference={reference}", auth=ctx.people["risk"])
    if first.status_code >= 400:
        return BLOCKED, f"the round could not be read: {first.status_code}"

    def population(response) -> int:
        body = response.json() or {}
        for key in ("population", "items", "total", "count"):
            value = body.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, list):
                return len(value)
        return -1

    started = population(first)
    if started < 0:
        return BLOCKED, f"the round does not report its population: {first.text[:130]}"
    _model(ctx)                       # registered AFTER the round opened
    again = ctx.api.get(f"{C}?reference={reference}", auth=ctx.people["risk"])
    now = population(again)
    if now != started:
        return FAIL, (f"the population moved from {started} to {now} when a "
                      f"model was registered after launch, so completion falls "
                      f"as the estate grows and the round can never finish")
    del before
    return PASS, (f"the population stayed at {started} across a registration "
                  f"made after launch")


@case("QA-AM-808", "The kinds a campaign may be for are published")
def am_808(ctx: Ctx) -> Result:
    """A closed vocabulary nobody can read is a closed vocabulary somebody
    discovers by being refused. And each kind has to say how completion is
    MEASURED, because 'attestation' and 'recertification' count different
    things and a round reported at 84% means nothing without which."""
    got = ctx.api.get(f"{C}/kinds", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the kinds answered {got.status_code}"
    body = got.json() or {}
    rows = body.get("kinds") if isinstance(body, dict) else body
    if isinstance(rows, dict):
        rows = [{"kind": k, **(v if isinstance(v, dict) else {"means": v})}
                for k, v in rows.items()]
    if not rows:
        return FAIL, "no campaign kind is published, so the vocabulary is closed and invisible"
    named = {r.get("kind") or r.get("key") for r in rows}
    absent = sorted(set(KINDS) - named)
    if absent:
        return FAIL, f"these kinds are accepted and not published: {absent}"
    silent = [r.get("kind") for r in rows
              if not str(r.get("asks") or r.get("means")
                         or r.get("description") or "").strip()]
    if silent:
        return FAIL, (f"{len(silent)} kind(s) are published without saying "
                      f"what they ask: {silent}")
    # Completion is measured the same way for every kind — against the frozen
    # population — so it is stated once rather than per row. A first draft of
    # this case demanded it per kind and reported all six as silent.
    said = str(body.get("detail") or "") if isinstance(body, dict) else ""
    if "completion" not in said.lower():
        return FAIL, (f"{len(rows)} kind(s) say what they ask and nothing says "
                      f"how completion is measured, so a round reported at 84% "
                      f"does not say 84% of what")
    if "frozen" not in said.lower():
        return FAIL, ("completion is described without saying it is measured "
                      "against the population frozen at launch, which is the "
                      "whole difference between 84% and a figure that improves "
                      "on its own")
    return PASS, (f"{len(rows)} kind(s), each saying what it asks, and "
                  f"completion measured against the frozen population")


@case("QA-AM-809", "Read a campaign that does not exist")
def am_809(ctx: Ctx) -> Result:
    """The listing and the single read answer the same endpoint, so a
    reference nobody opened could come back as the empty round — which is the
    same answer as a round where nobody has responded yet."""
    got = ctx.api.get(f"{C}?reference={ctx.unique('NO-SUCH')}",
                      auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' ({got.status_code})"
    return FAIL, (f"a reference nobody opened answered {got.status_code} with "
                  f"{got.text[:110]}, which reads as a round where nobody has "
                  f"responded yet")
