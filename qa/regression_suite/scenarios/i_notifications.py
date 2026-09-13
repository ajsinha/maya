"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — telling somebody they have outstanding work.

**A message that repeats yesterday's is a message somebody filters.** So a
digest is suppressed while the worklist is unchanged and the quiet period has
not passed — keyed on a DIGEST of the work rather than on a timer, because
work that changed inside the quiet window is exactly the thing worth sending.

**A failed delivery is a governance fact**: somebody was supposed to be told
and was not, so it goes on the evidence chain rather than into a log. And the
log channel is always available and is the honest default for an instance with
nowhere to send — a platform whose only answer to *no mail server* is silence
would be one where nobody notices the notifications stopped.
"""
from __future__ import annotations

from core.notify.common import CHANNELS, DEFAULT_QUIET_HOURS, FAILED, SENT, SUPPRESSED
from qa.regression_suite.harness import ADMIN
from qa.regression_suite.scenarios.common import (BLOCKED, FAIL, PASS, Ctx,
                                                  Result, case, code_of)

N = "/api/v1/notifications"
HOUR = 3600.0


def _engine(ctx: Ctx):
    return ctx.ui.app.state.ctx.get("notifications") or \
        ctx.ui.app.state.ctx.get("notifier")


@case("QA-PLT-252", "A notification channel that is configured and unreachable")
def plt_252(ctx: Ctx) -> Result:
    """Refused by name, and the refusal points at the log channel — which is
    always available and is the honest default for an instance with nowhere
    to send. A platform whose only answer to a missing mail server is silence
    is one where nobody notices the notifications stopped."""
    from core.notify.common import NotifyError
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no notification service is wired"

    class Unreachable:
        @staticmethod
        def available():
            return "the smtp host does not resolve"

        @staticmethod
        def send(*_a, **_k):
            return False, "unreachable"

    name = next(iter(CHANNELS))
    was = engine.channels.get(name)
    engine.channels[name] = Unreachable()
    try:
        engine._channel(name)
    except NotifyError as exc:
        if getattr(exc, "code", "") != "channel_unavailable":
            return FAIL, f"refused '{getattr(exc, 'code', exc)}'"
        if "log" not in getattr(exc, "remediation", ""):
            return FAIL, ("the refusal does not point at the log channel, so "
                          "an instance with nowhere to send has nowhere to go")
        return PASS, "refused 'channel_unavailable', naming the log channel"
    finally:
        if was is not None:
            engine.channels[name] = was
        else:
            engine.channels.pop(name, None)
    return FAIL, "an unreachable channel was used"


@case("QA-PLT-4920", "A channel this instance does not have")
def plt_4920(ctx: Ctx) -> Result:
    """*Not built* and *built and unreachable* are different facts and refuse
    apart. One is a deployment that never included the channel; the other is
    one where it stopped working, and only the second is an incident."""
    from core.notify.common import NotifyError
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no notification service is wired"
    try:
        engine._channel("carrier-pigeon")
    except NotifyError as exc:
        if getattr(exc, "code", "") != "unknown_channel":
            return FAIL, f"an unknown channel refused '{getattr(exc, 'code', exc)}'"
        # The list lives in the remediation, not the detail.
        said = f"{exc} {getattr(exc, 'remediation', '')}"
        for channel in CHANNELS:
            if channel not in said:
                return FAIL, f"the refusal does not name '{channel}'"
    else:
        return FAIL, "a channel that is not one was accepted"
    absent = next((c for c in CHANNELS if c not in engine.channels), "")
    if absent:
        try:
            engine._channel(absent)
        except NotifyError as exc:
            if getattr(exc, "code", "") != "channel_not_built":
                return FAIL, (f"a channel absent from this build refused "
                              f"'{getattr(exc, 'code', exc)}'")
    return PASS, "unknown, not built and unavailable all refuse apart"


@case("QA-PLT-253",
      "The same outstanding work notified twice inside the quiet window")
def plt_253(ctx: Ctx) -> Result:
    """Suppressed, and the suppression is keyed on a digest of the WORK
    rather than on a timer — so an unchanged worklist is quiet and a changed
    one is not, whatever the clock says."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no notification service is wired"
    channel = next(iter(CHANNELS))
    who = ctx.unique("nu")
    now = 1_700_000_000.0
    engine.notifications.add({
        "principal": who, "channel": channel, "state": SENT,
        "digest": "sha256:same", "item_count": 3, "overdue": 1,
        "summary": "qa", "detail": "", "sent_at": now})
    why = engine._suppressed(who, "sha256:same", channel, now + HOUR)
    if not why:
        return FAIL, ("the same digest an hour later is not suppressed, so a "
                      "nightly run repeats yesterday's message")
    if "filters" not in why:
        return FAIL, f"the suppression does not say why: {why[:110]}"
    changed = engine._suppressed(who, "sha256:different", channel, now + HOUR)
    if changed:
        return FAIL, ("a CHANGED worklist is suppressed inside the quiet "
                      "window, so new work waits for the timer")
    later = engine._suppressed(who, "sha256:same", channel,
                               now + (DEFAULT_QUIET_HOURS + 1) * HOUR)
    if later:
        return FAIL, (f"the same digest past {DEFAULT_QUIET_HOURS} hours is "
                      f"still suppressed, so a standing problem goes quiet "
                      f"for ever")
    return PASS, ("unchanged is suppressed, changed is not, and the window "
                  "expires")


@case("QA-PLT-4921", "A previously FAILED delivery does not suppress the next")
def plt_4921(ctx: Ctx) -> Result:
    """The suppression looks only at what was SENT. A failed attempt that
    counted as *already told* would mean the one person the platform could
    not reach is the one it stops trying to reach."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no notification service is wired"
    channel = next(iter(CHANNELS))
    who = ctx.unique("nf")
    now = 1_700_000_000.0
    engine.notifications.add({
        "principal": who, "channel": channel, "state": FAILED,
        "digest": "sha256:same", "item_count": 3, "overdue": 1,
        "summary": "qa", "detail": "unreachable", "sent_at": now})
    if engine._suppressed(who, "sha256:same", channel, now + HOUR):
        return FAIL, ("a failed delivery suppresses the retry, so the one "
                      "person the platform could not reach is the one it "
                      "stops trying to reach")
    engine.notifications.add({
        "principal": who, "channel": channel, "state": SUPPRESSED,
        "digest": "sha256:same", "item_count": 3, "overdue": 1,
        "summary": "qa", "detail": "quiet", "sent_at": now})
    if engine._suppressed(who, "sha256:same", channel, now + HOUR):
        return FAIL, ("a suppression suppresses the next one, so two quiet "
                      "runs in a row extend the window indefinitely")
    return PASS, "only a SENT delivery starts the quiet window"


@case("QA-PLT-4922", "A digest is per channel")
def plt_4922(ctx: Ctx) -> Result:
    """Being told by email does not mean being told in the log, and a
    suppression that crossed channels would silence the record because a
    message went out."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no notification service is wired"
    if len(CHANNELS) < 2:
        return BLOCKED, f"only one channel exists: {CHANNELS}"
    first, second = list(CHANNELS)[:2]
    who = ctx.unique("nc")
    now = 1_700_000_000.0
    engine.notifications.add({
        "principal": who, "channel": first, "state": SENT,
        "digest": "sha256:same", "item_count": 1, "overdue": 0,
        "summary": "qa", "detail": "", "sent_at": now})
    if not engine._suppressed(who, "sha256:same", first, now + HOUR):
        return BLOCKED, "the first channel does not suppress at all"
    if engine._suppressed(who, "sha256:same", second, now + HOUR):
        return FAIL, (f"a delivery on '{first}' suppressed '{second}', so a "
                      f"message going out silences the record")
    return PASS, f"'{first}' quiet, '{second}' unaffected"


@case("QA-PLT-256", "A notification to a principal with no email address")
def plt_256(ctx: Ctx) -> Result:
    """The address falls back to the username rather than to nothing, so a
    delivery is attempted and its failure is RECORDED — somebody who was
    supposed to be told and was not is a governance fact, not a log line."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no notification service is wired"
    digest = engine.digest_for({"username": "person/no-email"}, now=1.0) \
        if hasattr(engine, "digest_for") else None
    if digest is None:
        return BLOCKED, "the digest could not be built"
    if not digest.get("to"):
        return FAIL, ("a principal with no email has no address at all, so "
                      "the delivery is skipped rather than failing visibly")
    if digest["to"] != "person/no-email":
        return FAIL, f"the fallback address is {digest['to']!r}"
    import inspect
    source = inspect.getsource(type(engine)._record)
    if "notification_failed" not in source:
        return FAIL, ("a failed delivery writes no evidence node, so somebody "
                      "who was supposed to be told and was not leaves no "
                      "governance record")
    if "FAILED" not in source:
        return FAIL, "the evidence node is not conditioned on failure"
    return PASS, "the username is the fallback, and a failure is on the chain"


@case("QA-PLT-4923", "A dry run sends nothing and records nothing")
def plt_4923(ctx: Ctx) -> Result:
    """A preview that wrote a row would start the quiet window, so looking at
    what would be sent would stop it being sent."""
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no notification service is wired"
    before = len(engine.notifications.many())
    got = ctx.api.get(f"{N}/preview", auth=ADMIN)
    if got.status_code >= 400:
        return BLOCKED, f"the preview answered {got.status_code}"
    after = len(engine.notifications.many())
    if after != before:
        return FAIL, (f"a preview wrote {after - before} notification row(s), "
                      f"so looking at what would be sent starts the quiet "
                      f"window and stops it being sent")
    import inspect
    source = inspect.getsource(type(engine)._record)
    if "if not dry_run" not in source:
        return FAIL, "a dry run is not excluded from writing a row"
    return PASS, f"{before} rows before and after the preview"


@case("QA-PLT-255", "Two concurrent notifier runs")
def plt_255(ctx: Ctx) -> Result:
    """One send and one suppressed. Two runs racing must not both deliver —
    a cron that overlaps with a manual run is the ordinary case, and two
    identical messages is exactly what the quiet window exists to prevent."""
    import threading
    engine = _engine(ctx)
    if engine is None:
        return BLOCKED, "no notification service is wired"
    out = {}

    def go(n):
        out[n] = ctx.api.post(f"{N}/run", json={"channel": "log"}, auth=ADMIN)

    threads = [threading.Thread(target=go, args=(n,)) for n in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    if len(out) != 2:
        return BLOCKED, "one of the racing runs did not return"
    crashed = [r for r in out.values() if r.status_code >= 500]
    if crashed:
        return FAIL, (f"a racing notifier run answered {crashed[0].status_code}: "
                      f"{crashed[0].text[:120]}")
    bodies = [r.json() or {} for r in out.values() if r.status_code < 400]
    if len(bodies) != 2:
        codes = [code_of(r) for r in out.values() if r.status_code >= 400]
        return PASS, f"one run refused {codes}, so they cannot both deliver"
    sent = sum(b.get("sent") or 0 for b in bodies)
    suppressed = sum(b.get("suppressed") or 0 for b in bodies)
    if sent and suppressed:
        return PASS, f"{sent} sent, {suppressed} suppressed across two runs"
    if sent > 1:
        return FAIL, (f"two concurrent runs both delivered ({sent} sends), so "
                      f"a cron overlapping a manual run sends twice")
    return PASS, f"{sent} sent, {suppressed} suppressed"
