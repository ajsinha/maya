"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section H — who owns a finding, and how the date it is owed by moves.

`h_finding_acts.py` covers the acts themselves. This covers the two questions
somebody asks about them a year later: **who was this for** and **why is it
still open**. Both are answered by a handover record and by an extension that
cost somebody a reason — and both are exactly the records a well-meaning edit
erases.

The due-date cases are the sharp ones. An owner who can move their own date is
an owner with an extension mechanism that needs nobody's agreement and leaves
no count, and a report of *findings extended this quarter* built on top of it
reads zero.
"""
from __future__ import annotations

import time

from qa.regression_suite.scenarios.common import (BLOCKED, DENIAL, FAIL, PASS,
                                                  Ctx, Result, case, code_of,
                                                  refused_by_the_control)

F = "/api/v1/findings"
M = "/api/v1/models"
TIER = {"model_class": "logistic", "domain": "credit",
        "legal_entity": "LE-US-01", "purpose": "credit_decision"}
DAY = 86400.0


def _person(ctx: Ctx, role: str = "model_owner"):
    who = ctx.unique("fo")
    made = ctx.api.post("/api/v1/principals",
                        json={"username": who, "display_name": who,
                              "roles": [role], "password": f"{who}-password",
                              "legal_entities": [], "domains": []})
    return (who, f"{who}-password") if made.status_code < 400 else None


def _finding(ctx: Ctx, owner: str = "person/owner", severity: str = "High"):
    name = ctx.unique("fo")
    ctx.api.post(M, json={"urn": f"maya://model/{name}", "name": name,
                          "owner": "owner", **TIER})
    made = ctx.api.post(F, json={"urn": f"maya://model/{name}",
                                 "severity": severity, "title": "A QA finding",
                                 "owner": owner, "description": "qa",
                                 "category": "general", "source": "validation"},
                        auth=ctx.people["risk"])
    return made.json()["id"] if made.status_code < 400 else ""


def _read(ctx: Ctx, fid: str) -> dict:
    got = ctx.api.get(f"{F}/{fid}", auth=ctx.people["risk"])
    if got.status_code >= 400:
        return {}
    body = got.json() or {}
    return body.get("finding") or body


def _mine(ctx: Ctx, worklist, authz, username: str,
          role: str = "validator") -> list:
    """The worklist is a derived view rendered on a screen; there is no JSON
    route to it, so it is read the way `ui_routes` reads it.

    The ROLE matters: a finding row is filtered by `finding:close`, which the
    owner of a model does not hold. Reading as a `model_owner` returned an
    empty list and would have made these cases assert that nothing appears —
    which is true, and about permissions rather than about derivation.
    """
    registry = ctx.ui.app.state.ctx.get("registry")
    models = registry.list() if registry else []
    who = {"username": username, "roles": [role],
           "legal_entities": [], "domains": []}
    out = worklist.mine(who, authz, models)
    return out.get("items", out) if isinstance(out, dict) else list(out or [])


def _blocking(ctx: Ctx):
    """A BLOCKING finding, because the worklist deliberately leaves an open
    non-blocking one off until it is near its date — "not yet worth anyone's
    attention". A case built on a High-but-not-blocking finding would assert
    that nothing appears, which is true and is about the urgency rule rather
    than about derivation."""
    name = ctx.unique("fo")
    urn = f"maya://model/{name}"
    ctx.api.post(M, json={"urn": urn, "name": name, "owner": "owner", **TIER})
    made = ctx.api.post(F, json={"urn": urn, "severity": "High",
                                 "title": ctx.unique("blocking finding"),
                                 "owner": "person/owner", "description": "qa",
                                 "category": "general", "source": "validation",
                                 "blocking": True},
                        auth=ctx.people["risk"])
    return urn, (made.json().get("id", "") if made.status_code < 400 else "")


@case("QA-AM-900", "An unacknowledged finding is reported as unacknowledged")
def am_900(ctx: Ctx) -> Result:
    """*Raised* and *somebody has taken it on* are different facts and the
    second is the one a committee is shown. A register that reported them as
    one would show a quarter's findings as being worked on when nobody had
    read any of them."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "no finding could be raised"
    row = _read(ctx, fid)
    if not row:
        return BLOCKED, "the finding could not be read back"
    acknowledged = row.get("acknowledged_at") or row.get("acknowledged_by")
    if acknowledged:
        return FAIL, (f"a freshly raised finding reports itself acknowledged "
                      f"({acknowledged}), so nothing distinguishes a finding "
                      f"somebody took on from one nobody has opened")
    if row.get("status") not in ("open", "raised", None):
        return FAIL, f"a fresh finding is already '{row.get('status')}'"
    ageing = ctx.api.get(f"{F}/ageing", auth=ctx.people["risk"])
    if ageing.status_code >= 400:
        return PASS, "the finding itself reports unacknowledged"
    if "unacknowledged" not in ageing.text and "acknowledged" not in ageing.text:
        return FAIL, ("the finding is unacknowledged and the estate view says "
                      "nothing about acknowledgement, so the fact exists on "
                      "the row and reaches no reader")
    return PASS, "unacknowledged on the row and visible in the estate view"


@case("QA-AM-901", "A handover records who it moved from and to")
def am_901(ctx: Ctx) -> Result:
    """An act rather than an edit. *Who was this originally for* is the
    question asked about the findings that were not done, and an edit that
    overwrites the owner erases the answer."""
    fid = _finding(ctx, owner="person/owner")
    taker = _person(ctx)
    if not fid or not taker:
        return BLOCKED, "no finding or no second person"
    moved = ctx.api.post(f"{F}/{fid}/assign",
                         json={"to": f"person/{taker[0]}",
                               "reason": "the original owner has left"},
                         auth=ctx.people["risk"])
    if moved.status_code >= 400:
        return BLOCKED, f"the handover answered {moved.status_code}: {moved.text[:120]}"
    # The history is on the finding's own reading. `/finding-acts` publishes
    # the VOCABULARY of acts and what each means, which is a different thing —
    # reading it here would have made this case pass on a page that never
    # mentions this finding.
    acts = ctx.api.get(f"{F}/{fid}", auth=ctx.people["risk"])
    if acts.status_code >= 400:
        return FAIL, (f"the handover was accepted and the finding answered "
                      f"{acts.status_code}, so nothing records that it "
                      f"happened")
    text = acts.text
    absent = [w for w in ("owner", taker[0], "left") if w not in text]
    if absent == ["left"] and "reason" in text.lower():
        absent = []
    if absent:
        return FAIL, (f"the act log does not carry {absent}: a handover that "
                      f"does not name where the finding came from, where it "
                      f"went and why is an edit with a timestamp")
    return PASS, "the act names the previous owner, the new one and the reason"


@case("QA-AM-902", "Assign to the person who already owns it")
def am_902(ctx: Ctx) -> Result:
    """Either refused as a no-op or accepted and recorded — but not accepted
    and SILENT. A handover to the current owner that leaves an act saying
    ownership moved is a record of something that did not happen."""
    fid = _finding(ctx, owner="person/owner")
    if not fid:
        return BLOCKED, "no finding"
    got = ctx.api.post(f"{F}/{fid}/assign",
                       json={"to": "person/owner", "reason": "no change"},
                       auth=ctx.people["risk"])
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return BLOCKED, f"answered '{code_of(got)}' — not reached"
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}' as a no-op"
    row = _read(ctx, fid)
    if (row.get("owner") or "").endswith("owner"):
        return PASS, ("accepted and the owner is unchanged, so the act is a "
                      "recorded no-op rather than a move that did not happen")
    return FAIL, (f"assigning to the current owner changed the owner to "
                  f"{row.get('owner')!r}")


@case("QA-AM-903", "Assign with no reason")
def am_903(ctx: Ctx) -> Result:
    """The reason is the whole content of a handover. Without it the record
    says a finding changed hands and nothing about why, which is the same
    information as the timestamp alone."""
    fid = _finding(ctx)
    taker = _person(ctx)
    if not fid or not taker:
        return BLOCKED, "no finding or no second person"
    return refused_by_the_control(
        ctx.api.post(f"{F}/{fid}/assign",
                     json={"to": f"person/{taker[0]}", "reason": "   "},
                     auth=ctx.people["risk"]),
        "a finding changed hands with no reason recorded, so the act says "
        "only that it moved")


@case("QA-AM-904", "Extend a due date into the past")
def am_904(ctx: Ctx) -> Result:
    """An extension backwards is not an extension. Accepted, it makes a
    finding overdue the moment it is granted — and the overdue count, which is
    the number anybody looks at, moves in the wrong direction because somebody
    asked for more time."""
    fid = _finding(ctx)
    if not fid:
        return BLOCKED, "no finding"
    got = ctx.api.post(f"{F}/{fid}/extend",
                       json={"reason": "a QA extension",
                             "due_at": time.time() - 30 * DAY},
                       auth=ctx.people["risk"])
    return refused_by_the_control(
        got, "a due date was extended to a date thirty days in the past, so "
             "asking for more time made the finding overdue")


@case("QA-AM-905", "The owner extends their own due date")
def am_905(ctx: Ctx) -> Result:
    """The one that matters. If the owner may move their own date, the
    remediation window is advisory: there is an extension mechanism needing
    nobody's agreement, and a report of *findings extended this quarter* built
    over it reads zero while every date moves."""
    owner = _person(ctx)
    if not owner:
        return BLOCKED, "no owner could be minted"
    fid = _finding(ctx, owner=f"person/{owner[0]}")
    if not fid:
        return BLOCKED, "no finding"
    got = ctx.api.post(f"{F}/{fid}/extend",
                       json={"reason": "I need longer", "days": 60},
                       auth=owner)
    if got.status_code >= 500:
        return FAIL, f"{got.status_code} {got.text[:140]}"
    if code_of(got) in DENIAL:
        return PASS, (f"refused '{code_of(got)}' — the owner does not hold the "
                      f"permission, which is the same answer by another route")
    if got.status_code >= 400:
        return PASS, f"refused '{code_of(got)}'"
    acts = ctx.api.get(f"/api/v1/finding-acts?finding_id={fid}",
                       auth=ctx.people["risk"])
    counted = acts.status_code < 400 and "extend" in acts.text.lower()
    return FAIL, (
        "the owner extended their own finding by sixty days"
        + (" and it is recorded as an extension, so the window is advisory "
           "but at least counted" if counted else
           " and no act records it, so the window is advisory AND the "
           "extension count is zero"))


@case("QA-AM-906", "The worklist is derived, not assigned")
def am_906(ctx: Ctx) -> Result:
    """Nobody is handed a worklist here; it is computed from what the reader
    owns. The difference matters because an assigned list goes stale silently
    — a finding closed elsewhere stays on it — and a derived one cannot."""
    reader = _person(ctx, role="validator")
    if not reader:
        return BLOCKED, "no reader could be minted"
    worklist = ctx.ui.app.state.ctx.get("worklist")
    authz = ctx.ui.app.state.ctx.get("authz")
    if worklist is None or authz is None:
        return BLOCKED, "no worklist is wired"
    started = len(_mine(ctx, worklist, authz, reader[0]))
    urn, fid = _blocking(ctx)
    if not fid:
        return BLOCKED, "no finding"
    items = _mine(ctx, worklist, authz, reader[0])
    if len(items) <= started:
        return FAIL, (f"a blocking finding was raised and the worklist still "
                      f"holds {len(items)} item(s), so the list is not derived "
                      f"from the register's state")
    if not any(urn in str(i) for i in items):
        return FAIL, (f"the worklist grew and no item names {urn}, so what "
                      f"appeared is something else")
    return PASS, (f"the finding appeared without anybody assigning a list "
                  f"({started} -> {len(items)} item(s))")


@case("QA-AM-907", "A closed finding leaves the worklist")
def am_907(ctx: Ctx) -> Result:
    """The other half of derived, and the half an assigned list gets wrong.
    A list that keeps a closed finding is one somebody stops reading."""
    reader = _person(ctx, role="validator")
    if not reader:
        return BLOCKED, "no reader could be minted"
    worklist = ctx.ui.app.state.ctx.get("worklist")
    authz = ctx.ui.app.state.ctx.get("authz")
    if worklist is None or authz is None:
        return BLOCKED, "no worklist is wired"
    urn, fid = _blocking(ctx)
    if not fid:
        return BLOCKED, "no finding"
    if not any(urn in str(i) for i in _mine(ctx, worklist, authz, reader[0])):
        return BLOCKED, "the finding never reached the worklist"
    # NOT as `risk`, who raised it: the person who raised a finding may not
    # close it, and that control firing here would look like the worklist
    # working.
    closer = _person(ctx, role="validator")
    if not closer:
        return BLOCKED, "no second validator"
    closed = ctx.api.post(f"{F}/{fid}/close",
                          json={"evidence": {"note": "closed by QA"}},
                          auth=closer)
    if closed.status_code >= 400:
        return BLOCKED, f"the finding could not be closed: {closed.text[:120]}"
    if any(urn in str(i) for i in _mine(ctx, worklist, authz, reader[0])):
        return FAIL, ("a closed finding is still on its owner's worklist, so "
                      "the list accumulates work nobody has to do and stops "
                      "being read")
    return PASS, "the closed finding left the list without anybody removing it"


@case("QA-AM-908", "A digest is not sent twice for an unchanged worklist")
def am_908(ctx: Ctx) -> Result:
    """A daily digest that arrives identical every morning is one nobody
    opens, which turns the notification channel off by habit rather than by
    configuration — and nothing anywhere records that it happened."""
    preview = ctx.api.get("/api/v1/notifications/preview")
    if preview.status_code >= 400:
        return BLOCKED, f"the preview answered {preview.status_code}"
    first = ctx.api.post("/api/v1/notifications/run", json={"dry_run": True})
    if first.status_code >= 400:
        return BLOCKED, f"the run answered {first.status_code}: {first.text[:120]}"
    second = ctx.api.post("/api/v1/notifications/run", json={"dry_run": True})
    if second.status_code >= 400:
        return FAIL, f"a second run answered {second.status_code}"

    def sent(response):
        body = response.json() or {}
        for key in ("sent", "delivered", "notifications", "results"):
            value = body.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, list):
                return len(value)
        return None

    one, two = sent(first), sent(second)
    if one is None or two is None:
        return BLOCKED, f"the run does not report what it sent: {first.text[:130]}"
    if one and two >= one:
        return FAIL, (f"the first run would send {one} and the second {two} "
                      f"with nothing changed between them, so a digest "
                      f"repeats until the reader stops opening it")
    return PASS, (f"the first run would send {one}, the second {two} with "
                  f"nothing changed")
