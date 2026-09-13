"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — findings, and the acts that move one toward being closed.

A finding is the register saying something is wrong. Everything here is about
who may say it is no longer wrong, and on what evidence — which is the half of
model risk that is entirely about people rather than about mathematics.
"""
from __future__ import annotations

from tools.qa.scenarios.common import (BLOCKED, FAIL, PASS, Ctx, Result, case,
                                       code_of, expect_accepted,
                                       expect_refused)

#: A real root kind. `upstream_feed` is not one — the vocabulary is
#: control_gap, platform, population_shift and the rest, and inventing a
#: plausible-sounding value made four cases report `unknown_root_kind` and
#: look like defects.
ROOT_KIND = "platform"

TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}


def _model(ctx: Ctx, owner: str = "owner") -> str:
    name = ctx.unique("am")
    urn = f"maya://model/{name}"
    ctx.api.post("/api/v1/models",
                 json={"urn": urn, "name": name, "owner": owner, **TIER})
    return urn


def _raise(ctx: Ctx, urn: str, **over):
    body = {"urn": urn, "severity": "High", "title": "QA finding",
            "owner": "owner", "description": "raised by the QA pass",
            "category": "monitoring", "source": "self_identified"}
    body.update(over)
    return ctx.api.post("/api/v1/findings", json=body)


def _raised(ctx: Ctx, **over):
    """A finding, and its id."""
    got = _raise(ctx, _model(ctx), **over)
    if got.status_code >= 400:
        raise AssertionError(f"could not raise a finding: {got.text[:180]}")
    return got.json()["id"]


# --------------------------------------------------------------- raising one
@case("QA-AM-067", "A Critical finding blocks without anybody deciding")
def am_067(ctx: Ctx) -> Result:
    got = _raise(ctx, _model(ctx), severity="Critical")
    if got.status_code >= 400:
        return FAIL, got.text[:160]
    if not got.json().get("blocking"):
        return FAIL, ("a Critical finding is advisory unless somebody says "
                      "otherwise — the default is the whole control")
    return PASS, "blocking by default"


@case("QA-AM-068", "A Critical finding explicitly marked non-blocking")
def am_068(ctx: Ctx) -> Result:
    got = _raise(ctx, _model(ctx), severity="Critical", blocking=False)
    if got.status_code >= 400:
        return FAIL, got.text[:160]
    if got.json().get("blocking"):
        return FAIL, "an explicit blocking:false was ignored"
    return PASS, "accepted, and not blocking"


@case("QA-AM-071", "Raise with an unknown severity")
def am_071(ctx: Ctx) -> Result:
    return expect_refused(_raise(ctx, _model(ctx), severity="Catastrophic"),
                          "validation_refused", "validation_error",
                          "unknown_severity")


@case("QA-AM-072", "Raise against a model that does not exist")
def am_072(ctx: Ctx) -> Result:
    return expect_refused(_raise(ctx, "maya://model/qa.never"),
                          "registry_refused", "not_found")


@case("QA-AM-073", "Raise with no owner")
def am_073(ctx: Ctx) -> Result:
    return expect_refused(_raise(ctx, _model(ctx), owner=""),
                          "validation_error", "owner_required",
                          "validation_refused")


@case("QA-AM-074", "Raise with an empty title")
def am_074(ctx: Ctx) -> Result:
    got = _raise(ctx, _model(ctx), title="   ")
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    return FAIL, ("a finding with a blank title is a row in a worklist that "
                  "says nothing about what is wrong")


# ------------------------------------------------------------------ the acts
@case("QA-AM-080", "Acknowledge as somebody who does not own it")
def am_080(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post(f"/api/v1/findings/{_raised(ctx)}/acknowledge",
                     json={"days": 30, "plan": "fix it"},
                     auth=ctx.people["validator"]),
        "not_the_owner", "forbidden")


@case("QA-AM-081", "Acknowledge with no plan and none on record")
def am_081(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post(f"/api/v1/findings/{_raised(ctx)}/acknowledge",
                     json={"days": 30}, auth=ctx.people["owner"]),
        "plan_required")


@case("QA-AM-082", "Acknowledge with a plan")
def am_082(ctx: Ctx) -> Result:
    return expect_accepted(
        ctx.api.post(f"/api/v1/findings/{_raised(ctx)}/acknowledge",
                     json={"days": 30, "plan": "replace the feed"},
                     auth=ctx.people["owner"]))


@case("QA-AM-083", "Acknowledge with a date already in the past")
def am_083(ctx: Ctx) -> Result:
    """A commitment to have finished yesterday is not a commitment."""
    return expect_refused(
        ctx.api.post(f"/api/v1/findings/{_raised(ctx)}/acknowledge",
                     json={"committed_at": 1.0, "plan": "fix"},
                     auth=ctx.people["owner"]),
        "date_in_the_past", "committed_at_in_the_past", "validation_error",
        "past_due")


@case("QA-AM-084", "Acknowledging moves the finding out of open")
def am_084(ctx: Ctx) -> Result:
    fid = _raised(ctx)
    ctx.api.post(f"/api/v1/findings/{fid}/acknowledge",
                 json={"days": 30, "plan": "fix"}, auth=ctx.people["owner"])
    status = ctx.api.get(f"/api/v1/findings/{fid}").json().get("status")
    if status == "open":
        return FAIL, "acknowledging left the finding open"
    return PASS, f"status is now {status!r}"


@case("QA-AM-085", "Close with no evidence")
def am_085(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post(f"/api/v1/findings/{_raised(ctx)}/close",
                     json={"evidence": "   "}, auth=ctx.people["owner"]),
        "evidence_required", "validation_error", "validation_refused")


@case("QA-AM-086", "Close verified by the person who owns it")
def am_086(ctx: Ctx) -> Result:
    """Somebody marking their own work as verified is the finding closing
    itself with extra steps."""
    fid = _raised(ctx)
    ctx.api.post(f"/api/v1/findings/{fid}/acknowledge",
                 json={"days": 30, "plan": "fix"}, auth=ctx.people["owner"])
    got = ctx.api.post(f"/api/v1/findings/{fid}/close",
                       json={"evidence": "the feed was replaced",
                             "verified_by": "owner"},
                       auth=ctx.people["owner"])
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    return FAIL, ("the owner closed their own finding and verified it "
                  "themselves")


@case("QA-AM-087", "Extend with no reason")
def am_087(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post(f"/api/v1/findings/{_raised(ctx)}/extend",
                     json={"days": 30, "reason": "   "},
                     auth=ctx.people["risk"]),
        "reason_required", "validation_error", "not_the_owner")


@case("QA-AM-088", "Assign to nobody")
def am_088(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post(f"/api/v1/findings/{_raised(ctx)}/assign",
                     json={"to": "  ", "reason": "handover"}),
        "validation_error", "owner_required", "unknown_principal",
        "validation_refused")


@case("QA-AM-090", "Act on a finding that does not exist")
def am_090(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post("/api/v1/findings/qa-never/acknowledge",
                     json={"days": 30, "plan": "fix"}),
        "no_finding", "not_found")


# ------------------------------------------------------------------- roots
@case("QA-AM-130", "A root with no findings attached")
def am_130(ctx: Ctx) -> Result:
    return expect_accepted(
        ctx.api.post("/api/v1/finding-roots",
                     json={"kind": ROOT_KIND, "title": "QA root",
                           "detail": "the feed stopped"}), status=201)


@case("QA-AM-131", "A root with an empty detail")
def am_131(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post("/api/v1/finding-roots",
                     json={"kind": ROOT_KIND, "title": "QA root",
                           "detail": "   "}),
        "root_detail_required")


@case("QA-AM-132", "A root of an unknown kind")
def am_132(ctx: Ctx) -> Result:
    return expect_refused(
        ctx.api.post("/api/v1/finding-roots",
                     json={"kind": "made_up", "title": "QA root",
                           "detail": "d"}),
        "unknown_root_kind")


@case("QA-AM-135", "A root counts an acknowledged child as still owed")
def am_135(ctx: Ctx) -> Result:
    """The regression: the count read `status == "open"`, and acknowledging
    moves a finding to `in_remediation` — so a root read `open: 0` the moment
    every child was acknowledged, with nothing closed."""
    fid = _raised(ctx)
    root = ctx.api.post("/api/v1/finding-roots",
                        json={"kind": ROOT_KIND, "title": "QA root",
                              "detail": "the feed stopped",
                              "findings": [fid]})
    if root.status_code >= 400:
        return BLOCKED, root.text[:160]
    root_id = root.json()["id"]
    ctx.api.post(f"/api/v1/findings/{fid}/acknowledge",
                 json={"days": 30, "plan": "fix"}, auth=ctx.people["owner"])
    # `root_id` is a QUERY parameter on the collection, not a path segment —
    # there is no `GET /finding-roots/{id}`. Asking for one answered 404 and
    # the case reported BLOCKED against a route that was never there.
    got = ctx.api.get("/api/v1/finding-roots", params={"root_id": root_id})
    if got.status_code >= 400:
        return BLOCKED, got.text[:160]
    still = got.json().get("open")
    if still != 1:
        return FAIL, (f"the root reports {still} still owed after its only "
                      f"child was acknowledged — an all-clear produced by "
                      f"somebody agreeing to do the work")
    return PASS, "the acknowledged child is still counted"
