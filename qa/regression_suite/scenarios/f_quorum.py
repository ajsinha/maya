"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section F — the version approval quorum.

A tier is not a label on a model; it is the size of the quorum every version
of it has to pass. Tiers 1 and 2 need a model risk manager AND a validator,
tiers 3 and 4 need one authorised person, and the interesting cases are all
about the ways a quorum of two can turn out to be a quorum of one: the same
human under two hats, a signature raced against itself, the person who built
the version, or a tier raised after the fact so that an approval already given
no longer meets the bar.
"""
from __future__ import annotations

from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

A = "/api/v1/version-approvals"
M = "/api/v1/models"
SHAPE = {"model_class": "logistic", "domain": "credit",
         "legal_entity": "LE-US-01", "purpose": "credit_decision"}
#: A tier is a monotone map of exposure against purpose. 500m of credit
#: decisioning is tier 2 and needs the quorum; 1m of the same is tier 3 and
#: needs one signature. Both are used below, and which one a case wants is
#: the whole difference between `no_quorum_required` and a real quorum.
TIER_2 = {"exposure": 500_000_000.0, "purpose_class": "credit_decision",
          "feature_count": 12, "interpretable": True,
          "uses_alternative_data": False}
TIER_3 = {**TIER_2, "exposure": 1_000_000.0}


def _model(ctx: Ctx, facts=None, *, semver: str = "1.0.0",
           builder: str = "developer") -> tuple:
    name = ctx.unique("qm")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **SHAPE})
    ctx.api.post(f"{M}/{name}/versions", json={"semver": semver},
                 auth=ctx.people.get(builder, builder))
    ctx.api.post(f"{M}/{name}/assess", json=dict(facts or TIER_2))
    return name, urn


def _principal(ctx: Ctx, roles, entities=None) -> tuple:
    """A principal minted for one case. `principal:manage` needs an
    unrestricted scope, so this is the administrator's act and not a role's."""
    who = ctx.unique("qp")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": list(roles),
                              "password": f"{who}-password",
                              "legal_entities": list(entities or []),
                              "domains": []},
                        auth=ADMIN)
    return (who, f"{who}-password") if made.status_code < 400 else None


def _open(ctx: Ctx, urn: str, semver: str = "1.0.0", who: str = "risk"):
    return ctx.api.post(A, json={"urn": urn, "semver": semver,
                                 "statement": "qa"},
                        auth=ctx.people.get(who, who))


def _sign(ctx: Ctx, aid: str, role: str, who, decision: str = "approve"):
    return ctx.api.post(f"{A}/{aid}/sign",
                        json={"role": role, "decision": decision,
                              "statement": "qa"},
                        auth=ctx.people.get(who, who))


def _status(ctx: Ctx, name: str, semver: str = "1.0.0") -> str:
    """There is no `GET /models/{name}/versions/{semver}` — the name segment
    is a greedy `:path` converter and would swallow any suffix registered
    after it, so every version travels inside the model reading."""
    got = ctx.api.get(f"{M}/{name}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return ""
    for row in (got.json() or {}).get("versions") or []:
        if row.get("semver") == semver:
            return row.get("status") or ""
    return ""


def _approval(ctx: Ctx, facts=None) -> tuple:
    name, urn = _model(ctx, facts)
    made = _open(ctx, urn)
    return (made.json()["id"] if made.status_code < 400 else ""), name, urn


@case("QA-GOV-099", "Open a quorum for a tier 3 version")
def gov_099(ctx: Ctx) -> Result:
    """A tier 3 version is approved by one authorised person. Opening a
    quorum for it would invent a control the tier does not ask for, and every
    later reader would see a two-signature approval and infer a tier."""
    _name, urn = _model(ctx, TIER_3)
    got = _open(ctx, urn)
    outcome = refused_by_the_control(
        got, "a quorum was opened for a tier that requires no quorum")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "no_quorum_required":
        return FAIL, f"refused '{code_of(got)}' rather than naming the tier"
    return PASS, "refused 'no_quorum_required'"


@case("QA-GOV-100", "Open two quorums for one version")
def gov_100(ctx: Ctx) -> Result:
    """Two open approvals on one version is two places a signature can land,
    and whichever completes first decides — so the second is a way of asking
    the question again until the answer is the one you wanted."""
    aid, _name, urn = _approval(ctx)
    if not aid:
        return BLOCKED, "the first approval could not be opened"
    got = _open(ctx, urn)
    outcome = refused_by_the_control(
        got, "a second approval was opened on a version that already had one")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "approval_open":
        return FAIL, f"refused '{code_of(got)}' rather than 'approval_open'"
    return PASS, "refused 'approval_open'"


@case("QA-GOV-101", "Open a quorum for a version already approved")
def gov_101(ctx: Ctx) -> Result:
    """The approval already happened. A second one would either change the
    record of an immutable version or sit open for ever."""
    name, urn = _model(ctx, TIER_3)
    done = ctx.api.post(f"{M}/{name}/versions/1.0.0/approve", json={},
                        auth=ctx.people["risk"])
    if done.status_code >= 400:
        return BLOCKED, f"the version could not be approved: {done.text[:140]}"
    # Raised to tier 2 AFTER the approval, so the quorum now applies to a
    # version that already has a status — which is the state this refuses on.
    ctx.api.post(f"{M}/{name}/assess", json=dict(TIER_2))
    got = _open(ctx, urn)
    outcome = refused_by_the_control(
        got, "a quorum was opened for a version that is already approved")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "already_approved":
        return FAIL, f"refused '{code_of(got)}' rather than 'already_approved'"
    return PASS, "refused 'already_approved'"


@case("QA-GOV-103", "Complete a two-role quorum with two distinct people")
def gov_103(ctx: Ctx) -> Result:
    """The case every refusal below is measured against. If two people cannot
    approve a tier 2 version, none of the refusals mean anything."""
    aid, name, _urn = _approval(ctx)
    if not aid:
        return BLOCKED, "the approval could not be opened"
    first = _sign(ctx, aid, "model_risk_manager", "risk")
    if first.status_code >= 400:
        return BLOCKED, f"the first signature failed: {first.text[:150]}"
    body = first.json() or {}
    if (body.get("status") or body.get("approval", {}).get("status")) == \
            "approved":
        return FAIL, "one signature completed a two-role quorum"
    second = _sign(ctx, aid, "validator", "validator")
    if second.status_code >= 400:
        return FAIL, (f"the second signature was refused "
                      f"'{code_of(second)}': a legitimate quorum cannot be "
                      f"completed")
    status = _status(ctx, name)
    if status != "approved":
        return FAIL, (f"both roles signed and the version reads '{status}'; "
                      f"the quorum completed and approved nothing")
    return PASS, "two people, two roles, and the version is approved"


@case("QA-GOV-104", "One person holding both quorum roles signs twice")
def gov_104(ctx: Ctx) -> Result:
    """A quorum is a number of people, not a number of hats. A dual-hatted
    principal signing both halves is one person approving their own model,
    with the record showing two roles."""
    dual = _principal(ctx, ["model_risk_manager", "validator"])
    if dual is None:
        return BLOCKED, "the dual-hatted principal could not be created"
    aid, _name, _urn = _approval(ctx)
    if not aid:
        return BLOCKED, "the approval could not be opened"
    first = _sign(ctx, aid, "model_risk_manager", dual)
    if first.status_code >= 400:
        return BLOCKED, f"the first signature failed: {first.text[:150]}"
    got = _sign(ctx, aid, "validator", dual)
    outcome = refused_by_the_control(
        got, "one person signed both halves of a two-role quorum")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "already_signed_personally":
        return FAIL, (f"refused '{code_of(got)}' — if this is 'already_signed' "
                      f"the refusal is about the ROLE, and a second person "
                      f"holding that role would be refused too")
    return PASS, "refused 'already_signed_personally'"


@case("QA-GOV-105", "Race two signatures from one dual-hatted principal")
def gov_105(ctx: Ctx) -> Result:
    """The read-then-write the refusal above depends on. Two requests that
    both pass the check and both write leave one person's two signatures on
    the record, and the approval completes."""
    import threading
    dual = _principal(ctx, ["model_risk_manager", "validator"])
    if dual is None:
        return BLOCKED, "the dual-hatted principal could not be created"
    aid, _name, _urn = _approval(ctx)
    if not aid:
        return BLOCKED, "the approval could not be opened"
    out = {}

    def go(role):
        out[role] = _sign(ctx, aid, role, dual)

    threads = [threading.Thread(target=go, args=(r,))
               for r in ("model_risk_manager", "validator")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if len(out) != 2:
        return BLOCKED, "one of the racing signatures did not return"
    won = [r for r, got in out.items() if got.status_code < 400]
    if len(won) == 2:
        return FAIL, ("both halves of a two-role quorum were signed by one "
                      "person under a race: the check reads and then writes, "
                      "so two requests that interleave both pass it")
    lost = [got for r, got in out.items() if got.status_code >= 400]
    if code_of(lost[0]) not in ("already_signed_personally", "already_signed"):
        return FAIL, (f"the loser refused '{code_of(lost[0])}', which is not "
                      f"the duties check")
    return PASS, f"one signature stood, the other refused '{code_of(lost[0])}'"


@case("QA-GOV-106", "The version's creator signs the quorum")
def gov_106(ctx: Ctx) -> Result:
    """Effective challenge requires a validator independent of the build, and
    the evidence chain is where that is checked — the segregation rule reads
    `version_created` against the version the approval names."""
    who = ctx.unique("qp")
    pair = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": ["model_developer", "validator"],
                              "password": f"{who}-password",
                              "legal_entities": [], "domains": []},
                        auth=ADMIN)
    if pair.status_code < 400:
        return FAIL, ("one principal now holds `version:create` and "
                      "`version:sign`, so the builder can sign the challenge "
                      "of what they built and the outer control is not there")
    if code_of(pair) in ("unauthenticated", "forbidden"):
        return BLOCKED, "the administrator never reached the role store"
    # The state this case describes cannot be reached through the API at all:
    # `version:create` is a FIRST-LINE act and `version:sign` a second-line
    # one, and the role store refuses the pair before anybody gets as far as
    # an approval. The signature-time segregation check behind it stays worth
    # having — it reads `version_created` off the chain, so it also catches
    # the version built before the roles were separated.
    return PASS, (f"the pairing is refused at the role store "
                  f"('{code_of(pair)}'), before any version exists to sign")


@case("QA-GOV-107", "Decline one signature of a two-role quorum")
def gov_107(ctx: Ctx) -> Result:
    """One decline closes it. A quorum that could be re-tried after a refusal
    until somebody said yes would not be a quorum."""
    aid, name, _urn = _approval(ctx)
    if not aid:
        return BLOCKED, "the approval could not be opened"
    got = _sign(ctx, aid, "validator", "validator", decision="decline")
    if got.status_code >= 400:
        return FAIL, (f"a decline was refused '{code_of(got)}'; a validator "
                      f"who cannot say no is not a control")
    progress = ctx.api.get(f"{A}/{aid}", auth=ctx.people["risk"])
    status = ((progress.json() or {}).get("approval") or
              progress.json() or {}).get("status")
    if status != "declined":
        return FAIL, f"one decline left the approval '{status}'"
    if _status(ctx, name) == "approved":
        return FAIL, "the version is approved after a declined quorum"
    return PASS, "declined, and the version is not approved"


@case("QA-GOV-108", "Sign after a decline closed the approval")
def gov_108(ctx: Ctx) -> Result:
    """The second role arriving after the refusal must not be able to
    overturn it by signing into a closed approval."""
    aid, _name, _urn = _approval(ctx)
    if not aid:
        return BLOCKED, "the approval could not be opened"
    if _sign(ctx, aid, "validator", "validator",
             decision="decline").status_code >= 400:
        return BLOCKED, "the decline failed"
    got = _sign(ctx, aid, "model_risk_manager", "risk")
    outcome = refused_by_the_control(
        got, "a signature landed on an approval a decline had closed")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "approval_closed":
        return FAIL, f"refused '{code_of(got)}' rather than 'approval_closed'"
    return PASS, "refused 'approval_closed'"


@case("QA-GOV-109", "Open a new quorum after one was declined")
def gov_109(ctx: Ctx) -> Result:
    """A decline is not a permanent bar — the model gets fixed and comes
    back. What matters is that the new approval is a new record and the
    decline stays on the chain."""
    aid, _name, urn = _approval(ctx)
    if not aid:
        return BLOCKED, "the approval could not be opened"
    if _sign(ctx, aid, "validator", "validator",
             decision="decline").status_code >= 400:
        return BLOCKED, "the decline failed"
    got = _open(ctx, urn)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' — a declined version can "
                      f"never be approved, whatever is done to it")
    if (got.json() or {}).get("id") == aid:
        return FAIL, "the declined approval was reopened rather than replaced"
    return PASS, "a second approval, distinct from the declined one"


@case("QA-GOV-110", "Withdraw an open approval, then open another")
def gov_110(ctx: Ctx) -> Result:
    """Withdrawal is the legitimate way out of an approval opened by mistake,
    and it has to actually clear the way for the next one."""
    aid, _name, urn = _approval(ctx)
    if not aid:
        return BLOCKED, "the approval could not be opened"
    gone = ctx.api.post(f"{A}/{aid}/withdraw", json={},
                        auth=ctx.people["risk"])
    if gone.status_code >= 400:
        return FAIL, f"the withdrawal was refused '{code_of(gone)}'"
    got = _open(ctx, urn)
    if got.status_code >= 400:
        return FAIL, (f"refused '{code_of(got)}' after a withdrawal, so a "
                      f"version can be locked out by an approval nobody wants")
    return PASS, "withdrawn, and a fresh approval opens"


@case("QA-GOV-111", "Withdraw an approval that is already withdrawn")
def gov_111(ctx: Ctx) -> Result:
    """The second withdrawal would rewrite the moment the first one closed."""
    aid, _name, _urn = _approval(ctx)
    if not aid:
        return BLOCKED, "the approval could not be opened"
    if ctx.api.post(f"{A}/{aid}/withdraw", json={},
                    auth=ctx.people["risk"]).status_code >= 400:
        return BLOCKED, "the first withdrawal failed"
    got = ctx.api.post(f"{A}/{aid}/withdraw", json={},
                       auth=ctx.people["risk"])
    outcome = refused_by_the_control(got, "an approval was withdrawn twice")
    if outcome[0] is not PASS:
        return outcome
    if code_of(got) != "approval_closed":
        return FAIL, f"refused '{code_of(got)}' rather than 'approval_closed'"
    return PASS, "refused 'approval_closed'"


@case("QA-GOV-112", "A UK-scoped validator signs half a US model's tier 2 quorum")
def gov_112(ctx: Ctx) -> Result:
    """The recorded defect. The sign route resolved the approval and the
    version but not the MODEL, so the legal-entity scope was never applied —
    and because `decision: decline` on the same endpoint closes the approval,
    it was a cross-entity veto as well as a cross-entity signature."""
    abroad = _principal(ctx, ["validator"], ["LE-UK-01"])
    if abroad is None:
        return BLOCKED, "the UK-scoped validator could not be created"
    aid, _name, _urn = _approval(ctx)
    if not aid:
        return BLOCKED, "the approval could not be opened"
    got = _sign(ctx, aid, "validator", abroad)
    if got.status_code < 400:
        return FAIL, ("a validator scoped to LE-UK-01 signed half the quorum "
                      "of an LE-US-01 model; the same endpoint accepts a "
                      "decline, so this is a cross-entity veto too")
    if code_of(got) in ("unauthenticated", "csrf_token_invalid"):
        return BLOCKED, f"the caller never reached the scope check: {code_of(got)}"
    return PASS, f"refused '{code_of(got)}'"


@case("QA-GOV-113",
      "Raise the tier after a version was approved on one signature")
def gov_113(ctx: Ctx) -> Result:
    """The recorded defect, and the sharpest one in this group: a tier 3
    model approved on one signature and then reassessed to tier 2 went on
    serving while the platform reported `quorum_required: true`. The record
    said the control applied and the version had never been through it."""
    name, _urn = _model(ctx, TIER_3)
    done = ctx.api.post(f"{M}/{name}/versions/1.0.0/approve", json={},
                        auth=ctx.people["risk"])
    if done.status_code >= 400:
        return BLOCKED, f"the version could not be approved: {done.text[:140]}"
    got = ctx.api.post(f"{M}/{name}/assess", json=dict(TIER_2))
    if got.status_code >= 400:
        return BLOCKED, f"the reassessment failed: {got.text[:140]}"
    body = got.json() or {}
    if "approvals_below_quorum" not in body:
        return FAIL, ("the reassessment reports no `approvals_below_quorum`, "
                      "so nothing looked at the versions already approved")
    if body["approvals_below_quorum"] != ["1.0.0"]:
        return FAIL, (f"the version approved under tier 3 is not reported as "
                      f"below quorum: {body['approvals_below_quorum']}")
    found = ctx.api.get(f"/api/v1/findings?urn=maya://model/{name}",
                        auth=ctx.people["risk"])
    stale = [f for f in ((found.json() or {}).get("open") or [])
             if "tier raised" in (f.get("title") or "")]
    if not stale:
        return FAIL, ("reported below quorum and no finding was raised, so "
                      "the number is on one response and nowhere else")
    if not stale[0].get("blocking"):
        return FAIL, ("the finding is not blocking, so it does not stop the "
                      "alias move that keeps the model serving")
    return PASS, (f"reported ['1.0.0'] and raised a blocking "
                  f"{stale[0].get('severity')} finding")


@case("QA-GOV-114", "Lower the tier after a quorum-approved version")
def gov_114(ctx: Ctx) -> Result:
    """The other direction raises nothing. A version approved by two people
    still satisfies a tier that asks for one, and a finding here would be
    noise on every model whose exposure fell."""
    aid, name, _urn = _approval(ctx)
    if not aid:
        return BLOCKED, "the approval could not be opened"
    _sign(ctx, aid, "model_risk_manager", "risk")
    if _sign(ctx, aid, "validator", "validator").status_code >= 400:
        return BLOCKED, "the quorum could not be completed"
    got = ctx.api.post(f"{M}/{name}/assess", json=dict(TIER_3))
    if got.status_code >= 400:
        return BLOCKED, f"the reassessment failed: {got.text[:140]}"
    if (got.json() or {}).get("approvals_below_quorum"):
        return FAIL, (f"lowering the tier reported "
                      f"{got.json()['approvals_below_quorum']} below quorum")
    found = ctx.api.get(f"/api/v1/findings?urn=maya://model/{name}",
                        auth=ctx.people["risk"])
    stale = [f for f in ((found.json() or {}).get("open") or [])
             if "tier raised" in (f.get("title") or "")]
    if stale:
        return FAIL, "lowering the tier raised a finding about the quorum"
    return PASS, "tier 2 to tier 3, nothing below quorum and no finding"


@case("QA-GOV-115", "Raise the tier twice in a row")
def gov_115(ctx: Ctx) -> Result:
    """EXPLORATORY. Tier 3 to 2 to 1: the version is still below quorum the
    second time, and the question is whether that is a second finding or the
    same one said twice. The extension escalation next door answers this by
    checking whether the title is already open."""
    name, _urn = _model(ctx, TIER_3)
    if ctx.api.post(f"{M}/{name}/versions/1.0.0/approve", json={},
                    auth=ctx.people["risk"]).status_code >= 400:
        return BLOCKED, "the version could not be approved"
    ctx.api.post(f"{M}/{name}/assess", json=dict(TIER_2))
    ctx.api.post(f"{M}/{name}/assess",
                 json={**TIER_2, "exposure": 5_000_000_000.0,
                       "purpose_class": "policy_decision"})
    found = ctx.api.get(f"/api/v1/findings?urn=maya://model/{name}",
                        auth=ctx.people["risk"])
    stale = [f for f in ((found.json() or {}).get("open") or [])
             if "tier raised" in (f.get("title") or "")]
    if not stale:
        return FAIL, "two tier rises over an under-quorum version raised nothing"
    if len(stale) == 1:
        return PASS, ("one finding for two rises — the same fact, said once, "
                      "like the repeated-extension escalation")
    titles = sorted(f["title"] for f in stale)
    if len(set(titles)) != len(titles):
        return FAIL, (f"{len(stale)} findings and {len(set(titles))} distinct "
                      f"titles: the same sentence is on the register twice")
    return PASS, (f"{len(stale)} findings, one per rise, each naming its own "
                  f"tier: {titles}")
