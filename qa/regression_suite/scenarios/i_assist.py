"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — machine assistance, which the register treats as a suspect.

"Attestation is a person taking responsibility for machine output; it must be
somebody other than whoever asked for it." Until a generation is attested it
carries no weight anywhere in the platform, so the cases here are about that
transition and about the grounding gate that decides what reaches it.
"""
from __future__ import annotations

from core.assist.common import TIER_A, TIER_B, TIERS
from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of)

A = "/api/v1/assist"
#: A claim cites its support under `citations`. Under any other key the
#: claim cites NOTHING, is rejected as ungrounded, and every case in this
#: module then meets `nothing_grounded` instead of the thing it was asking.


def _capability(ctx: Ctx, tier: str = TIER_B, **over):
    key = ctx.unique("cap")
    body = {"capability_key": key, "description": "a QA capability",
            "tier": tier, "base_model": "qa-model-1",
            "prompt_digest": "a" * 64, "owner": "owner",
            "autonomy": "human_approved_automation", "review_sample": 0.1}
    body.update(over)
    made = ctx.api.post(f"{A}/capabilities", json=body, auth=ctx.people["risk"])
    return key if made.status_code < 400 else ""


def _generate(ctx: Ctx, key: str, claims, evidence, who="developer", **over):
    body = {"capability_key": key, "subject_type": "model",
            "subject_id": "qa-subject", "claims": list(claims),
            "known_evidence": list(evidence), "oracle_payload": {},
            "output": {}}
    body.update(over)
    return ctx.api.post(f"{A}/generations", json=body, auth=ctx.people[who])


def _reached(got) -> bool:
    return code_of(got) not in DENIAL + ("not_found",)


@case("QA-PLT-188", "A Tier B generation whose grounding rejects every claim")
def plt_188(ctx: Ctx) -> Result:
    """A Tier B capability's output IS its grounded claims. With none kept
    there is nothing left to record, and recording the ungrounded prose would
    put machine assertion into the register wearing the shape of evidence."""
    key = _capability(ctx)
    if not key:
        return BLOCKED, "the capability could not be declared"
    got = _generate(ctx, key,
                    [{"text": "the model is fine", "citations": ["ev-nope"]}],
                    [])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if not _reached(got):
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code < 400:
        return FAIL, ("a generation with no grounded claim was recorded; the "
                      "ungrounded prose is now in the register")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-192", "A fabricated citation on the drafting path")
def plt_192(ctx: Ctx) -> Result:
    """The claim citing evidence that does not exist is DROPPED rather than
    the whole draft refused — a model that invents one citation among ten
    should not cost the nine."""
    key = _capability(ctx)
    if not key:
        return BLOCKED, "the capability could not be declared"
    got = _generate(
        ctx, key,
        [{"text": "grounded", "citations": ["ev-real"]},
         {"text": "invented", "citations": ["ev-fabricated"]}],
        ["ev-real"])
    if got.status_code >= 400:
        return BLOCKED, got.text[:170]
    body = got.json() or {}
    rejected = body.get("rejected_claims") or []
    kept = body.get("claims") or []
    if not rejected:
        return FAIL, ("a claim citing evidence that does not exist was kept, "
                      "so an invented citation is indistinguishable from a "
                      "real one")
    if not kept:
        return FAIL, "the grounded claim was dropped along with the invented one"
    if "invented" in str(kept):
        return FAIL, "the fabricated claim is among the kept ones"
    return PASS, f"{len(kept)} kept, {len(rejected)} rejected"


@case("QA-PLT-200", "Zero claims versus every claim rejected")
def plt_200(ctx: Ctx) -> Result:
    """Two different facts. A generation that asserted nothing and one whose
    every assertion was unsupported must not print the same, or a model that
    hallucinated wholesale reads as one that was cautious."""
    key = _capability(ctx)
    if not key:
        return BLOCKED, "the capability could not be declared"
    silent = _generate(ctx, key, [], [])
    rejected = _generate(
        ctx, key, [{"text": "invented", "citations": ["ev-nope"]}], [])
    if silent.status_code >= 500 or rejected.status_code >= 500:
        return FAIL, f"{silent.status_code}/{rejected.status_code}"
    if silent.status_code < 400 and rejected.status_code < 400:
        if silent.text == rejected.text:
            return FAIL, ("asserting nothing and asserting only unsupported "
                          "things produce an identical record")
        return PASS, "the two are distinguishable"
    if code_of(silent) == code_of(rejected) and silent.status_code == \
            rejected.status_code:
        return FAIL, (f"both refuse '{code_of(silent)}', so a cautious "
                      f"generation and a wholly unsupported one are one fact")
    return PASS, (f"no claims -> '{code_of(silent) or silent.status_code}', "
                  f"none grounded -> "
                  f"'{code_of(rejected) or rejected.status_code}'")


@case("QA-PLT-194", "Attest your own generation")
def plt_194(ctx: Ctx) -> Result:
    """It must be somebody other than whoever asked for it."""
    key = _capability(ctx)
    if not key:
        return BLOCKED, "the capability could not be declared"
    # The requester has to be somebody who COULD attest, or the refusal is
    # the permission gate rather than the self-attestation check. `validator`
    # holds both `assist:generate` and `assist:attest`; the developer holds
    # only the first.
    made = _generate(ctx, key,
                     [{"text": "grounded", "citations": ["ev-real"]}],
                     ["ev-real"], who="validator")
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    gid = (made.json() or {}).get("id")
    got = ctx.api.post(f"{A}/generations/{gid}/attest",
                       json={"accept": True, "final_text": "", "note": "mine"},
                       auth=ctx.people["validator"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("the person who asked for a generation attested it, so "
                      "nobody took responsibility who had not already")
    if code_of(got) in DENIAL:
        return BLOCKED, "the caller never reached the check"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-195", "A generation created by `system`, attested by `system`")
def plt_195(ctx: Ctx) -> Result:
    """The self-attestation check reads
    `same_person(actor, created_by) and created_by != "system"`. The carve-out
    is defensible for a HUMAN attesting a scheduled job's output — there was
    no requester to be other than. It also lets `system` attest `system`,
    which is machine output taking responsibility for itself.
    """
    generations = ctx.ui.app.state.ctx.get("generations")
    if generations is None:
        return BLOCKED, "no generation register reachable from this run"
    key = _capability(ctx)
    if not key:
        return BLOCKED, "the capability could not be declared"
    made = generations.record(
        key, "model", "qa-subject",
        [{"text": "grounded", "citations": ["ev-real"]}], ["ev-real"],
        actor="system")
    from core.assist.common import AssistError
    try:
        generations.attest(made["id"], accept=True, final_text="",
                           actor="system")
    except AssistError as exc:
        if exc.code != "self_attestation":
            return FAIL, f"refused '{exc.code}', not self_attestation"
        return PASS, "`system` cannot attest its own generation"
    return FAIL, (
        "a generation created by `system` was attested by `system`. "
        "Attestation is a person taking responsibility for machine output, "
        "and the `created_by` is-not-system carve-out — which exists so a "
        "human can attest a scheduled job's output — also lets the machine "
        "sign for itself")


@case("QA-PLT-196", "Attest the same generation twice")
def plt_196(ctx: Ctx) -> Result:
    """Attestation is the only transition that gives a generation weight, so
    a second one would be a second answer about the same text."""
    key = _capability(ctx)
    if not key:
        return BLOCKED, "the capability could not be declared"
    made = _generate(ctx, key,
                     [{"text": "grounded", "citations": ["ev-real"]}],
                     ["ev-real"])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    gid = (made.json() or {}).get("id")
    first = ctx.api.post(f"{A}/generations/{gid}/attest",
                         json={"accept": True, "final_text": "", "note": "ok"},
                         auth=ctx.people["risk"])
    if first.status_code >= 400:
        return BLOCKED, first.text[:170]
    again = ctx.api.post(f"{A}/generations/{gid}/attest",
                         json={"accept": False, "final_text": "",
                               "note": "changed my mind"},
                         auth=ctx.people["validator"])
    if again.status_code >= 500:
        return FAIL, f"{again.status_code}"
    if again.status_code < 400:
        return FAIL, "an attested generation was attested again"
    return PASS, f"refused '{code_of(again)}'"


@case("QA-PLT-197", "The raw ungrounded prose survives in the record")
def plt_197(ctx: Ctx) -> Result:
    """What the machine actually said has to be recoverable, or nobody can
    later ask what the grounding gate removed."""
    key = _capability(ctx)
    if not key:
        return BLOCKED, "the capability could not be declared"
    made = _generate(
        ctx, key,
        [{"text": "grounded", "citations": ["ev-real"]},
         {"text": "invented", "citations": ["ev-nope"]}],
        ["ev-real"])
    if made.status_code >= 400:
        return BLOCKED, made.text[:170]
    if "invented" not in made.text:
        return FAIL, ("the rejected claim is nowhere in the record, so what "
                      "the machine said before the gate cannot be recovered")
    return PASS, "the rejected claim is kept beside the kept ones"


@case("QA-PLT-185", "Use a suspended capability")
def plt_185(ctx: Ctx) -> Result:
    key = _capability(ctx)
    if not key:
        return BLOCKED, "the capability could not be declared"
    stopped = ctx.api.post(f"{A}/capabilities/{key}/suspend",
                           json={"reason": "qa"}, auth=ctx.people["risk"])
    if stopped.status_code >= 400:
        return BLOCKED, f"could not suspend: {stopped.text[:140]}"
    got = _generate(ctx, key,
                    [{"text": "grounded", "citations": ["ev-real"]}],
                    ["ev-real"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, ("a suspended capability went on generating, so "
                      "suspension is a label")
    return PASS, f"refused '{code_of(got)}'"


@case("QA-PLT-201", "Set a budget of zero")
def plt_201(ctx: Ctx) -> Result:
    """A budget of zero is not a budget; it is a capability nobody may use,
    which is what suspension is for."""
    key = _capability(ctx)
    if not key:
        return BLOCKED, "the capability could not be declared"
    accepted = []
    for field in ("tokens", "cost", "steps"):
        got = ctx.api.put(f"{A}/budgets/{key}",
                          json={field: 0, "window_days": 30},
                          auth=ctx.people["risk"])
        if got.status_code >= 500:
            return FAIL, f"{field}: {got.status_code}"
        if got.status_code < 400:
            accepted.append(field)
    if accepted:
        return FAIL, f"a zero budget was accepted for: {accepted}"
    return PASS, "zero refused on tokens, cost and steps"


@case("QA-PLT-3600", "A capability of a tier that is not one")
def plt_3600(ctx: Ctx) -> Result:
    """The tier decides which control applies — an oracle or a human. A third
    value is a capability with neither."""
    made = ctx.api.post(f"{A}/capabilities",
                        json={"capability_key": ctx.unique("cap"),
                              "description": "a QA capability", "tier": "C",
                              "base_model": "qa-model-1",
                              "prompt_digest": "a" * 64, "owner": "owner"},
                        auth=ctx.people["risk"])
    if made.status_code >= 500:
        return FAIL, f"{made.status_code}"
    if made.status_code < 400:
        return FAIL, "a capability was declared at a tier with no control"
    if not any(t in made.text for t in TIERS):
        return FAIL, "the refusal does not name the tiers"
    return PASS, f"refused '{code_of(made)}', naming tiers {', '.join(TIERS)}"


@case("QA-PLT-3601", "A Tier A capability with no oracle")
def plt_3601(ctx: Ctx) -> Result:
    """"A formal property checks the output; the check is the control." A
    Tier A capability with no oracle named is a control that cannot run."""
    got = ctx.api.post(f"{A}/capabilities",
                       json={"capability_key": ctx.unique("cap"),
                             "description": "a QA capability", "tier": TIER_A,
                             "base_model": "qa-model-1",
                             "prompt_digest": "a" * 64, "owner": "owner",
                             "oracle_key": None},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code}"
    if got.status_code < 400:
        return FAIL, (f"a Tier {TIER_A} capability was declared with no "
                      f"oracle, so the control it rests on cannot run")
    return PASS, f"refused '{code_of(got)}'"
