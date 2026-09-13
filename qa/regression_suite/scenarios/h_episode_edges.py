"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — the edges of a validation episode.

The cases the conclusion rules do not obviously cover: a result with no
threshold, a result that could not be computed, a blocking finding raised
against a sibling version, and three fields written at open that may never be
read again. The last group is the recurring shape in this platform — something
stored, documented, and never evaluated — so each of those cases ends by
looking for the reader rather than by watching the write succeed.
"""
from __future__ import annotations

import time

from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of,
                                                  refused_by_the_control)

V = "/api/v1/validations"
M = "/api/v1/models"
F = "/api/v1/findings"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
SAME = [float(n) for n in range(50)]


def _model(ctx: Ctx, *semvers: str) -> tuple:
    name = ctx.unique("ee")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    for semver in (semvers or ("1.0.0",)):
        ctx.api.post(f"{M}/{name}/versions", json={"semver": semver},
                     auth=ctx.people["developer"])
    return name, f"maya://model/{name}"


def _open(ctx: Ctx, urn: str, semver: str = "1.0.0", **over):
    body = {"urn": urn, "semver": semver, "kind": "initial",
            "validators": ["person/validator"]}
    body.update(over)
    return ctx.api.post(V, json=body, auth=ctx.people["risk"])


def _episode(ctx: Ctx, urn: str, semver: str = "1.0.0", **over) -> str:
    made = _open(ctx, urn, semver, **over)
    return made.json()["id"] if made.status_code < 400 else ""


def _record(ctx: Ctx, vid: str, who: str = "validator", **over):
    body = {"test_key": "stability.psi", "left": SAME, "right": list(SAME)}
    body.update(over)
    return ctx.api.post(f"{V}/{vid}/results", json=body,
                        auth=ctx.people[who])


def _conclude(ctx: Ctx, vid: str, who: str = "validator", **over):
    body = {"outcome": "approved", "tier_verdict": "remains_appropriate",
            "tier_note": "", "conditions": []}
    body.update(over)
    return ctx.api.post(f"{V}/{vid}/conclude", json=body,
                        auth=ctx.people[who])


def _summary(ctx: Ctx, vid: str) -> dict:
    got = ctx.api.get(f"{V}/{vid}", auth=ctx.people["risk"])
    return got.json() if got.status_code < 400 else {}


def _raise(ctx: Ctx, urn: str, *, blocking: bool = True,
           title: str = "A QA blocker") -> str:
    """A finding is raised against a MODEL. There is no `semver` on the body,
    and that is the whole point of QA-AM-020: a blocking finding says the
    model is unfit to serve, and a new version does not answer it by
    existing."""
    made = ctx.api.post(F, json={"urn": urn, "severity": "High",
                                 "title": title, "owner": "person/owner",
                                 "description": "qa", "category": "general",
                                 "source": "validation", "blocking": blocking},
                        auth=ctx.people["risk"])
    return made.json().get("id", "") if made.status_code < 400 else ""


@case("QA-AM-006",
      "Validator deactivated *after* the episode opened, then the episode is "
      "concluded")
def am_006(ctx: Ctx) -> Result:
    """Validators are resolved at open and never again. The question is not
    whether the conclusion should be refused — the person concluding is
    authenticated separately — but whether the pack still asserts
    `independent: true` on the strength of somebody who has since been
    suspended, and says nothing about it."""
    _name, urn = _model(ctx)
    # TWO validators, and the episode is concluded by the one still standing.
    # Concluding as the suspended validator refuses at the door — which proves
    # the session was revoked, not that the episode re-resolved its list.
    vid = _episode(ctx, urn,
                   validators=["person/validator", "person/risk"])
    if not vid:
        return BLOCKED, "the episode could not be opened"
    # `principal:manage` requires an unrestricted scope and no QA role holds
    # it — whoever may decide who can act on the register may act on all of it.
    gone = ctx.api.post("/api/v1/principals/validator/suspend", auth=ADMIN)
    if gone.status_code >= 400:
        return BLOCKED, f"the validator could not be suspended: {gone.text[:140]}"
    _record(ctx, vid, who="risk")
    done = _conclude(ctx, vid, outcome="rejected", who="risk")
    ctx.api.post("/api/v1/principals/validator/reinstate", auth=ADMIN)
    if code_of(done) in ("unauthenticated", "forbidden"):
        return BLOCKED, ("the conclusion was refused at the door, which says "
                         "nothing about whether the validator list is "
                         "re-resolved")
    if done.status_code >= 400:
        return PASS, (f"refused '{code_of(done)}' — the validator list is "
                      f"re-resolved at conclusion after all")
    body = _summary(ctx, vid)
    blob = f"{body}"
    if "suspend" in blob or "no longer" in blob or "inactive" in blob:
        return PASS, "concluded, and the reading says the validator is gone"
    return FAIL, ("the episode concluded and its reading still reports "
                  "`independent` on the strength of a validator suspended "
                  "before the conclusion; nothing in the record says so, so a "
                  "supervisor reading the pack cannot tell")


@case("QA-AM-008",
      "Two episodes open on one version at once, concluded to opposite "
      "outcomes")
def am_008(ctx: Ctx) -> Result:
    """Nothing refuses a second concurrent episode, which is defensible — a
    supervisory review runs alongside an internal one. What is not defensible
    is a model page that can show one and hide the other."""
    name, urn = _model(ctx)
    first = _episode(ctx, urn)
    second = _episode(ctx, urn)
    if not (first and second):
        return PASS, ("a second concurrent episode is refused, so the "
                      "contradiction cannot arise")
    if first == second:
        return FAIL, "the second open returned the first episode"
    _record(ctx, first)
    _record(ctx, second)
    a = _conclude(ctx, first, outcome="rejected")
    b = _conclude(ctx, second, outcome="approved")
    if a.status_code >= 400 or b.status_code >= 400:
        return PASS, (f"the second conclusion is refused "
                      f"('{code_of(b) or code_of(a)}'), so one version cannot "
                      f"hold two verdicts")
    # The model page is `/model/{name}`, singular. `/models/...` is the
    # registration screen and answers 404 for a name.
    page = ctx.ui.get(f"/model/{name}", auth=ctx.people["risk"])
    if page.status_code >= 400:
        return BLOCKED, f"the model page answered {page.status_code}"
    # The validation card renders kind/validators/status/outcome, never the
    # episode id — so the outcomes are what a reader can actually see, and
    # they are what has to be checked.
    shown = page.text
    approved = 'evidence-ok">approved' in shown
    rejected = 'evidence-bad">rejected' in shown
    if not (approved and rejected):
        return FAIL, (f"one version carries an 'approved' and a 'rejected' "
                      f"episode and the model page shows "
                      f"{'only the approval' if approved else 'only the rejection'}"
                      f"; the reader sees a verdict without its contradiction")
    return PASS, "both outcomes are rendered on the model page, side by side"


@case("QA-AM-015",
      "Conclude `approved` over one recorded result that declared no threshold")
def am_015(ctx: Ctx) -> Result:
    """No threshold means no verdict to fail, and that is deliberate — an
    exploratory number should not have to invent a limit. But the approval
    then rests on it, and the pack has to be able to tell it from a test that
    met a limit."""
    _name, urn = _model(ctx)
    vid = _episode(ctx, urn)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _record(ctx, vid, test_key="discrimination.gini",
                  left=[1, 0] * 25, right=[float(n) for n in range(50)])
    if got.status_code >= 400:
        return BLOCKED, f"the result could not be recorded: {got.text[:140]}"
    done = _conclude(ctx, vid)
    if done.status_code >= 400:
        return FAIL, (f"refused '{code_of(done)}' — an unthresholded "
                      f"measurement cannot be approved over, which makes "
                      f"recording an exploratory number impossible")
    body = _summary(ctx, vid)
    blob = f"{body}".lower()
    if "no threshold" in blob or "unthresholded" in blob:
        return PASS, "approved, and the reading says the test declared no limit"
    return FAIL, ("approved over a test that declared no threshold, and the "
                  "reading reports `tests_run: 1, tests_failed: 0` — exactly "
                  "what a test that met a limit reports; the pack cannot tell "
                  "an exploratory number from a passed one")


@case("QA-AM-016", "Conclude `approved` over a single *not computable* result")
def am_016(ctx: Ctx) -> Result:
    """A `None` must never count as a pass. Absent evidence is not evidence
    of compliance, and AUC over a sample with one class present is absent
    evidence."""
    _name, urn = _model(ctx)
    vid = _episode(ctx, urn)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    got = _record(ctx, vid, test_key="discrimination.auc",
                  left=[1] * 40, right=[float(n) for n in range(40)],
                  threshold={"min": 0.6})
    if got.status_code >= 400:
        return PASS, (f"refused at record time ('{code_of(got)}') — a test "
                      f"that cannot be computed never enters the episode")
    if (got.json() or {}).get("passed"):
        return FAIL, ("a result that could not be computed was recorded as "
                      "passed, so absent evidence counts as compliance")
    return refused_by_the_control(
        _conclude(ctx, vid),
        "a model was approved over a test that could not be computed")


@case("QA-AM-020",
      "Blocking finding open against a *different version* of the same model "
      "blocks approval of this one")
def am_020(ctx: Ctx) -> Result:
    """`blocking_for` is per model, not per version, and that is the intent:
    a blocking finding is about the model being unfit to serve, and a new
    version does not answer it by existing. The refusal has to say which
    finding, or the validator looks for it on the version they are holding."""
    _name, urn = _model(ctx, "1.0.0", "2.0.0")
    older = _raise(ctx, urn, title="Found against 1.0.0")
    if not older:
        return BLOCKED, "the blocking finding could not be raised"
    vid = _episode(ctx, urn, semver="2.0.0")
    if not vid:
        return BLOCKED, "the episode on 2.0.0 could not be opened"
    _record(ctx, vid)
    got = _conclude(ctx, vid)
    outcome = refused_by_the_control(
        got, "a version was approved with a blocking finding open on its "
             "sibling")
    if outcome[0] is not PASS:
        return outcome
    if "Found against 1.0.0" not in got.text:
        return FAIL, ("refused without naming the finding, so the validator "
                      "has no way to know it is on another version")
    return PASS, "refused, naming the finding raised against 1.0.0"


@case("QA-AM-021",
      "Close the blocking finding, then re-attempt the same conclusion")
def am_021(ctx: Ctx) -> Result:
    """The legitimate route out has to actually work, not just be named in
    the refusal."""
    _name, urn = _model(ctx, "1.0.0", "2.0.0")
    fid = _raise(ctx, urn, title="Found against 1.0.0")
    vid = _episode(ctx, urn, semver="2.0.0")
    if not (fid and vid):
        return BLOCKED, "the fixture could not be built"
    _record(ctx, vid)
    if _conclude(ctx, vid).status_code < 400:
        return FAIL, "the first conclusion was not refused, so there is no "\
                     "route out to test"
    closed = ctx.api.post(
        f"{F}/{fid}/close",
        json={"evidence": {"note": "repointed and re-measured"}},
        auth=ctx.people["validator"])
    if closed.status_code >= 400:
        return BLOCKED, f"the finding could not be closed: {closed.text[:140]}"
    again = _conclude(ctx, vid)
    if again.status_code >= 400:
        return FAIL, (f"still refused after the blocker closed: "
                      f"'{code_of(again)}' — the route the refusal names does "
                      f"not lead anywhere")
    return PASS, "refused while open, approved once the finding closed"


@case("QA-AM-024",
      "Open with `snapshot_id` naming a snapshot that does not exist")
def am_024(ctx: Ctx) -> Result:
    """A pin nobody validates is a pin that fails on the day somebody tries
    to use it — which is months later, in front of whoever asked for the
    replay."""
    _name, urn = _model(ctx)
    made = _open(ctx, urn, snapshot_id="snap-does-not-exist")
    if made.status_code >= 400:
        return PASS, (f"refused at open ('{code_of(made)}') — the pin is "
                      f"resolved when it is cheap to fix")
    vid = made.json()["id"]
    _record(ctx, vid)
    replay = ctx.api.post(f"{V}/{vid}/replay-from-storage", json={},
                          auth=ctx.people["validator"])
    if replay.status_code < 400:
        return FAIL, ("an episode pinned to a snapshot that does not exist "
                      "replayed anyway, so the pin means nothing at either end")
    return FAIL, (f"accepted at open and discovered only at replay "
                  f"('{code_of(replay)}'): the episode carries a pin to "
                  f"'snap-does-not-exist' for as long as nobody replays it, "
                  f"and the failure lands on whoever asked for the evidence "
                  f"rather than on whoever typed the identifier")


@case("QA-AM-027", "`due_at` set to a moment in the past at open")
def am_027(ctx: Ctx) -> Result:
    """A date the platform stores and never evaluates is a date somebody will
    believe is enforced. The queue and the backlog forecast both compute what
    falls due from the RE-VALIDATION TRIGGERS, not from this field."""
    _name, urn = _model(ctx)
    week_ago = time.time() - 7 * 86400
    made = _open(ctx, urn, due_at=week_ago)
    if made.status_code >= 400:
        return PASS, (f"refused ('{code_of(made)}') — a due date already past "
                      f"is not accepted")
    vid = made.json()["id"]
    stored = _summary(ctx, vid)
    if stored.get("due_at") not in (week_ago, round(week_ago, 6)):
        if not stored.get("due_at"):
            return PASS, "the field is not stored, so nothing can rely on it"
    queue = ctx.api.get("/api/v1/validation-queue", auth=ctx.people["risk"])
    backlog = ctx.api.get("/api/v1/validation-backlog", auth=ctx.people["risk"])
    seen = f"{queue.text if queue.status_code < 400 else ''}" \
           f"{backlog.text if backlog.status_code < 400 else ''}"
    if vid in seen:
        return PASS, "the overdue episode surfaces in the queue or the backlog"
    return FAIL, ("an episode opened a week overdue is stored with that date "
                  "and read by nothing: the queue and the backlog both compute "
                  "what falls due from the re-validation triggers, so `due_at` "
                  "is written at open and never evaluated — a date somebody "
                  "will believe is enforced")


@case("QA-AM-028",
      "Every operation in this group, run a second time against the same "
      "episode")
def am_028(ctx: Ctx) -> Result:
    """The second run is where a partially written episode shows up. Each
    repeat must refuse with the SAME code as the first — a different one means
    state was left behind by the attempt that failed."""
    _name, urn = _model(ctx)
    vid = _episode(ctx, urn)
    if not vid:
        return BLOCKED, "the episode could not be opened"
    _record(ctx, vid)
    first = _conclude(ctx, vid, outcome="rejected")
    if first.status_code >= 400:
        return BLOCKED, f"the conclusion failed: {first.text[:140]}"
    repeats = {
        "conclude again": lambda: _conclude(ctx, vid),
        "conclude differently": lambda: _conclude(ctx, vid,
                                                  outcome="approved"),
        "record after concluding": lambda: _record(ctx, vid),
    }
    codes = {}
    for label, call in repeats.items():
        one, two = call(), call()
        if one.status_code < 400 or two.status_code < 400:
            return FAIL, f"'{label}' was accepted against a concluded episode"
        if code_of(one) != code_of(two):
            return FAIL, (f"'{label}' refused '{code_of(one)}' then "
                          f"'{code_of(two)}'; the second attempt saw different "
                          f"state, so the first left something behind")
        codes[label] = code_of(one)
    return PASS, f"three repeats, each stable: {sorted(set(codes.values()))}"
