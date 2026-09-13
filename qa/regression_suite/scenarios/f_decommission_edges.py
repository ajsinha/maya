"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — the edges of a decommissioning.

The module's own claim is that everything is validated BEFORE the transition,
so a refusal leaves the model in service rather than half-retired with no
record of why. These cases test that promise from both ends: a state the
retirement cannot legally reach, a replacement that names the model itself, a
replacement spelled with a capital N, and the estate view that exists to make
the gap between *retired* and *decommissioned* into a backlog somebody can
work.

The consumer gate is covered next door in `f_decommission`, where the case
that finds it can read the mechanism.
"""
from __future__ import annotations

from core.lifecycle.decommission import NOTHING
from core.retention import CLASSES
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)
from qa.regression_suite.scenarios.f_decommission import (CONSUMES, PRODUCES,
                                                          _attested, _record)

D = "/api/v1/decommission"
M = "/api/v1/models"


def _urn(name: str) -> str:
    return f"maya://model/{name}"


def _relate(ctx: Ctx, upstream: str, downstream: str):
    return ctx.api.post("/api/v1/model-relations",
                        json={"from_urn": _urn(upstream),
                              "to_urn": _urn(downstream),
                              "kind": "input_to"})


def _record_of(ctx: Ctx, name: str) -> dict:
    """The record, or an empty dict when there is none.

    `GET /decommission?urn=` answers a TRUTHY dict either way — a model with
    no record gets `{decommissioned: False, detail: "this model is in
    service"}` — so the flag is what says whether a record exists. Reading
    the dict's truthiness instead reports every model as decommissioned.
    """
    got = ctx.api.get(f"{D}?urn={_urn(name)}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return {}
    body = got.json() or {}
    return body if body.get("decommissioned") else {}


def _gate_is_live(ctx: Ctx, upstream: str, downstream: str) -> bool:
    """Whether the consumer reading can see the edge at all.

    QA-GOV-4605: `consumers()` reads `radius.get("reached")` and
    `blast_radius` answers `reaches`, so the live list is always empty and
    the `consumers_not_notified` refusal can never fire. Every case about
    passing THROUGH that gate would otherwise pass without the gate existing.
    """
    got = ctx.api.get(f"{D}/consumers?urn={_urn(upstream)}",
                      auth=ctx.people["risk"])
    if got.status_code >= 400:
        return False
    return _urn(downstream) in ((got.json() or {}).get("live") or [])


@case("QA-GOV-275", "Decommission a `submitted` model")
def gov_275(ctx: Ctx) -> Result:
    """The recorded defect this module was rewritten around: the record used
    to land, the transition then raised, and the register held a
    decommissioning for a model still in service. Retirement is not reachable
    from `submitted`, so the refusal has to come first and leave nothing
    behind."""
    name = ctx.unique("dc")
    ctx.api.post(M, json={"urn": _urn(name), "name": name, "owner": "owner",
                          "model_class": "logistic", "domain": "credit",
                          "legal_entity": "LE-US-01",
                          "purpose": "credit_decision"})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": "1.0.0"},
                 auth=ctx.people["developer"])
    ctx.api.post(f"{M}/{name}/assess",
                 json={"exposure": 1_000.0, "purpose_class": "commercial",
                       "feature_count": 3, "interpretable": True,
                       "uses_alternative_data": False})
    moved = ctx.api.post(f"{M}/{name}/submit", json={"note": "qa"})
    if moved.status_code >= 400:
        return BLOCKED, f"the model could not be submitted: {moved.text[:140]}"
    got = _record(ctx, name)
    outcome = refused_by_the_control(
        got, "a model in 'submitted' was decommissioned")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "illegal_transition":
        return FAIL, (f"refused '{code_of(got)}' rather than naming the "
                      f"transition")
    if _record_of(ctx, name):
        return FAIL, ("the transition was refused and a decommissioning "
                      "record was written anyway — the register now holds a "
                      "decommissioning for a model still in service")
    return PASS, "refused 'illegal_transition', and nothing was written"


@case("QA-GOV-277", "Decommission twice")
def gov_277(ctx: Ctx) -> Result:
    """A second record would make *why was this taken out* a question with
    two answers, which is worse than the one answer being wrong."""
    name = _attested(ctx)
    first = _record(ctx, name)
    if first.status_code >= 400:
        return BLOCKED, f"the first decommission failed: {first.text[:140]}"
    got = _record(ctx, name, rationale="a different reason entirely, at length")
    outcome = refused_by_the_control(got, "a model was decommissioned twice")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "already_decommissioned":
        return FAIL, f"refused '{code_of(got)}'"
    held = _record_of(ctx, name)
    if "different reason" in (held.get("rationale") or ""):
        return FAIL, "the refused second record overwrote the first rationale"
    return PASS, "refused 'already_decommissioned', first rationale intact"


@case("QA-GOV-278", "Rationale of exactly ten characters")
def gov_278(ctx: Ctx) -> Result:
    """Ten characters is a low bar and it is there to stop `n/a`. The bound
    is `< 10`, so ten is in — and a boundary nobody tested is a boundary that
    moves when the comparison is rewritten."""
    name = _attested(ctx)
    got = _record(ctx, name, rationale="0123456789")
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' at exactly ten characters; "
                      f"the bar is documented as ten, not eleven")
    return PASS, "ten characters accepted"


@case("QA-GOV-279", "Rationale of nine characters")
def gov_279(ctx: Ctx) -> Result:
    """The other side of the same boundary."""
    name = _attested(ctx)
    got = _record(ctx, name, rationale="012345678")
    outcome = refused_by_the_control(
        got, "a nine-character rationale was accepted")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "rationale_required":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'rationale_required' at nine"


@case("QA-GOV-280", "Replacement naming the model's own URN")
def gov_280(ctx: Ctx) -> Result:
    """A model replaced by itself. The URN is registered, so
    `_require_registered` passes, and the record then says the job is done by
    a model that has just been retired — which is the one answer that is
    worse than `none`, because it reads as a live successor."""
    name = _attested(ctx)
    got = _record(ctx, name, replacement=_urn(name))
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    held = _record_of(ctx, name)
    if held.get("replacement") == _urn(name):
        return FAIL, ("a model was recorded as its own replacement: the "
                      "replacement check asks only whether the URN is "
                      "registered, and the model being retired always is, so "
                      "the record names a retired model as the thing doing "
                      "the job now")
    return PASS, f"accepted, and the replacement reads '{held.get('replacement')}'"


@case("QA-GOV-281", "Replacement naming an unregistered URN")
def gov_281(ctx: Ctx) -> Result:
    """*Replaced by the new scorecard* is a sentence, not a link."""
    name = _attested(ctx)
    got = _record(ctx, name, replacement="maya://model/never-registered")
    outcome = refused_by_the_control(
        got, "a replacement named a model that does not exist")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "replacement_not_registered":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, "refused 'replacement_not_registered'"


@case("QA-GOV-282", "Replacement naming a model that is itself retired")
def gov_282(ctx: Ctx) -> Result:
    """EXPLORATORY. The replacement is registered, so the check passes — and
    the record then points at something that is not in service either. Two
    retirements in sequence leave a chain of successors that all stop."""
    successor = _attested(ctx)
    if _record(ctx, successor).status_code >= 400:
        return BLOCKED, "the successor could not be retired first"
    name = _attested(ctx)
    got = _record(ctx, name, replacement=_urn(successor))
    if got.status_code >= 400:
        return PASS, (f"refused '{code_of(got)}' — a retired model cannot be "
                      f"named as what does the job now")
    return FAIL, (f"'{_urn(successor)}' is retired and was accepted as the "
                  f"replacement: the check asks whether the URN is registered "
                  f"and never whether it is in service, so the successor "
                  f"chain points at another retirement")


@case("QA-GOV-283", "Replacement recorded as the literal `none`")
def gov_283(ctx: Ctx) -> Result:
    """A model withdrawn with nothing taking its place is a fact somebody
    will want to have been told deliberately — which is why blank is refused
    and the explicit word is not."""
    name = _attested(ctx)
    got = _record(ctx, name, replacement=NOTHING)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — the explicit 'none' is the "
                      f"documented way to say nothing replaces it")
    body = got.json() or {}
    detail = (body.get("detail") or "").lower()
    if "nothing" not in detail and "no replacement" not in detail:
        return FAIL, (f"accepted, and the detail does not say nothing takes "
                      f"its place: {detail[:120]}")
    return PASS, f"accepted, detail says: {detail[:80]}"


@case("QA-GOV-284", "Replacement recorded as `None` with a capital N")
def gov_284(ctx: Ctx) -> Result:
    """EXPLORATORY, and the answer is the one that keeps the register
    honest: `none` is a sentinel, not a word, so a capital N is a URN nobody
    registered rather than a second way of saying nothing."""
    name = _attested(ctx)
    got = _record(ctx, name, replacement="None")
    if got.status_code < 400:
        held = _record_of(ctx, name)
        return FAIL, (f"'None' was accepted and stored as "
                      f"'{held.get('replacement')}': the sentinel is matched "
                      f"case-sensitively in one place and not another, so the "
                      f"register holds two spellings of nothing")
    if code_of(got) != "replacement_not_registered":
        return FAIL, f"refused '{code_of(got)}'"
    return PASS, ("refused 'replacement_not_registered' — the sentinel is "
                  "exact, so 'None' is read as a URN")


@case("QA-GOV-285", "Unknown retention class")
def gov_285(ctx: Ctx) -> Result:
    """A free-text class would be a retention schedule nobody can act on.
    The refusal has to name the classes, because the reason they differ is
    that the obligations do."""
    name = _attested(ctx)
    got = _record(ctx, name, retention_class="keep_it_a_while")
    outcome = refused_by_the_control(
        got, "a retention class the platform does not have was accepted")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "unknown_retention_class":
        return FAIL, f"refused '{code_of(got)}'"
    missing = [c for c in CLASSES if c not in got.text]
    if missing:
        return FAIL, (f"the refusal does not name every class it will take: "
                      f"missing {missing}")
    return PASS, f"refused, naming all {len(CLASSES)} classes"


@case("QA-GOV-287", "Live consumers, all listed in `notified`")
def gov_287(ctx: Ctx) -> Result:
    """The legitimate route through the consumer gate. It has to work, or
    the gate is a wall."""
    upstream, downstream = _attested(ctx, PRODUCES), _attested(ctx, CONSUMES)
    if _relate(ctx, upstream, downstream).status_code >= 400:
        return BLOCKED, "the two models could not be related"
    if not _gate_is_live(ctx, upstream, downstream):
        return BLOCKED, ("the consumer reading does not see the edge, so "
                         "passing through the gate proves nothing about it "
                         "— see QA-GOV-4605")
    got = _record(ctx, upstream, notified=[_urn(downstream)])
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' with the only live consumer "
                      f"listed as notified")
    held = _record_of(ctx, upstream)
    if _urn(downstream) not in (held.get("notified") or []):
        return FAIL, "accepted and the notified list was not kept"
    if held.get("unnotified"):
        return FAIL, (f"the consumer was notified and still appears as "
                      f"unnotified: {held.get('unnotified')}")
    return PASS, "accepted, the consumer recorded as notified"


@case("QA-GOV-289", "Only *retired* models downstream")
def gov_289(ctx: Ctx) -> Result:
    """A retired consumer is not somebody to tell. The gate is about LIVE
    models, and counting retired ones would make every long-lived feeder
    impossible to withdraw."""
    upstream, downstream = _attested(ctx, PRODUCES), _attested(ctx, CONSUMES)
    if _relate(ctx, upstream, downstream).status_code >= 400:
        return BLOCKED, "the two models could not be related"
    if not _gate_is_live(ctx, upstream, downstream):
        return BLOCKED, ("the consumer reading does not see the edge while "
                         "the downstream model is still live, so retiring it "
                         "changes nothing observable — see QA-GOV-4605")
    if _record(ctx, downstream).status_code >= 400:
        return BLOCKED, "the downstream model could not be retired first"
    got = _record(ctx, upstream)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' with nothing live "
                      f"downstream; a retired consumer is not somebody to tell")
    held = _record_of(ctx, upstream)
    if held.get("unnotified"):
        return FAIL, (f"a retired consumer is recorded as unnotified: "
                      f"{held.get('unnotified')}")
    return PASS, "accepted, and the retired consumer is not counted"


@case("QA-GOV-291", "Decommission a model that was already retired the old way")
def gov_291(ctx: Ctx) -> Result:
    """The backlog this feature exists to clear. Models retired before the
    record existed must be able to acquire one, and the transition must not
    be attempted a second time."""
    name = _attested(ctx)
    gone = ctx.api.post(f"{M}/{name}/retire",
                        json={"reason": "retired the old way, before records"},
                        auth=ctx.people["risk"])
    if gone.status_code >= 400:
        return BLOCKED, f"the bare retirement failed: {gone.text[:140]}"
    got = _record(ctx, name)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — a model retired before the "
                      f"record existed can never acquire one, so the backlog "
                      f"cannot be worked")
    if (got.json() or {}).get("status") != "retired":
        return FAIL, f"the model reads '{(got.json() or {}).get('status')}'"
    return PASS, "a bare retirement acquired its record"


@case("QA-GOV-292",
      "Estate view after one proper and one bare retirement")
def gov_292(ctx: Ctx) -> Result:
    """*Retired* and *decommissioned* are two different populations, and the
    gap between them is a backlog somebody can work — which means the view
    has to name the bare one, not just count it."""
    proper, bare = _attested(ctx), _attested(ctx)
    if _record(ctx, proper).status_code >= 400:
        return BLOCKED, "the proper decommission failed"
    gone = ctx.api.post(f"{M}/{bare}/retire",
                        json={"reason": "retired without a record"},
                        auth=ctx.people["risk"])
    if gone.status_code >= 400:
        return BLOCKED, f"the bare retirement failed: {gone.text[:140]}"
    got = ctx.api.get(f"{D}/estate", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return BLOCKED, f"the estate view answered {got.status_code}"
    body = got.json() or {}
    named = f"{body.get('without_a_record')}"
    if _urn(bare) not in named:
        return FAIL, (f"the bare retirement is not named in "
                      f"`without_a_record`, so the backlog is a count nobody "
                      f"can work: {named[:130]}")
    if _urn(proper) in named:
        return FAIL, "the properly decommissioned model is in the backlog too"
    return PASS, "the bare retirement is named and the proper one is not"
