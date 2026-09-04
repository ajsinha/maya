"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Notification: delivery, not a second source of truth.

The outstanding work already exists. It is derived from the register — no task
table, so it cannot go stale, disagree with the register, or accumulate orphans —
and the dashboard already shows each person what they can act on. What was
missing was that nothing ever *reached out*, so an item nobody happened to log in
and look at simply sat there.

This reaches out. It does not invent a queue.

**A digest, not a firehose.** One message per person per run, summarising their
outstanding work. A message per finding is how somebody starts filtering the
sender, at which point the platform has made itself invisible while appearing
diligent.

**Silence when nothing has changed.** Each delivery records the digest of the
work it described. An unchanged worklist is *suppressed* until a quiet period has
passed. Nothing is more certain to be ignored than a daily message that says
exactly what yesterday's said, and a control everybody ignores is not a control.

**Escalation is by role, not by hierarchy.** MAYA does not know who reports to
whom and should not pretend to. What it does know is that an item overdue and
unactioned for a week is no longer only its owner's problem, so the second line
is told as well.

**A failed delivery is recorded.** Silence about a failed send is how somebody
concludes they were never told, which is worse than not having sent at all —
they would at least have known.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence

from core.evidence import EvidenceEngine
from core.log import get_logger
from core.notify.common import (CHANNELS, DEFAULT_ESCALATE_DAYS,
                                DEFAULT_QUIET_HOURS, ESCALATION_ROLE, FAILED,
                                LOG, SENT, SUPPRESSED, NotifyError)
from db.database import digest as canonical_digest

logger = get_logger(__name__)

DAY = 86400.0
HOUR = 3600.0


class NotificationService:
    """Turns the derived worklist into messages, once, and records what happened."""

    def __init__(self, notifications, worklist, principals, authz, registry,
                 evidence: EvidenceEngine,
                 channels: Optional[Dict[str, Any]] = None,
                 default_channel: str = LOG,
                 quiet_hours: float = DEFAULT_QUIET_HOURS,
                 escalate_days: float = DEFAULT_ESCALATE_DAYS,
                 base_url: str = ""):
        self.notifications, self.worklist = notifications, worklist
        self.principals, self.authz, self.registry = principals, authz, registry
        self.evidence = evidence
        self.channels = channels or {}
        self.default_channel = default_channel
        self.quiet_hours, self.escalate_days = quiet_hours, escalate_days
        self.base_url = base_url.rstrip("/")

    # -------------------------------------------------------------------- run
    def run(self, now: Optional[float] = None, channel: Optional[str] = None,
            dry_run: bool = False, actor: str = "system") -> Dict[str, Any]:
        """Notify everybody with outstanding work, once."""
        moment = now if now is not None else time.time()
        name = channel or self.default_channel
        transport = self._channel(name)

        results: List[Dict[str, Any]] = []
        for principal in self.principals.list():
            digest = self.digest_for(principal, moment)
            if not digest["count"]:
                continue
            results.append(self._deliver(principal, digest, name, transport,
                                         moment, dry_run, actor))
        sent = [r for r in results if r["state"] == SENT]
        return {
            "channel": name, "dry_run": dry_run,
            "considered": len(results), "sent": len(sent),
            "suppressed": sum(1 for r in results if r["state"] == SUPPRESSED),
            "failed": sum(1 for r in results if r["state"] == FAILED),
            "deliveries": results,
            "detail": self._detail(results, name, dry_run),
        }

    def _channel(self, name: str):
        if name not in CHANNELS:
            raise NotifyError("unknown_channel", f"unknown channel '{name}'",
                              f"expected one of {', '.join(CHANNELS)}")
        transport = self.channels.get(name)
        if transport is None:
            raise NotifyError(
                "channel_not_built",
                f"the '{name}' channel is not present on this instance", "")
        if (why := transport.available()):
            raise NotifyError(
                "channel_unavailable", why,
                "configure it, or notify through the log channel, which is "
                "always available and is the honest default for an instance "
                "with nowhere to send")
        return transport

    # --------------------------------------------------------------- digest
    def digest_for(self, principal: Dict[str, Any],
                   now: Optional[float] = None) -> Dict[str, Any]:
        """One person's outstanding work, as a message rather than a list."""
        moment = now if now is not None else time.time()
        # The same call the dashboard makes, so a person is told exactly what
        # they would have seen on logging in. Two views of one derivation, not
        # two derivations.
        mine = self.worklist.mine(principal, self.authz,
                                  self.registry.list(), moment)
        items = mine["items"]
        escalated = self._escalated(principal, items, moment)
        overdue = [i for i in items if i.get("urgency") == "overdue"]
        due = [i for i in items if i.get("urgency") == "due"]
        return {
            "principal": principal.get("username"),
            "to": principal.get("email") or principal.get("username"),
            "count": len(items) + len(escalated),
            "overdue": len(overdue), "due_soon": len(due),
            "items": items, "escalated": escalated,
            "headlines": [f"{i['model']}: {i['title']}" for i in
                          (overdue + due)[:5]],
            "summary": self._summary(principal, items, overdue, due, escalated),
            "footer": (f"{self.base_url}/dashboard" if self.base_url
                       else "See the dashboard for the detail."),
            # The digest of the WORK, not of the message: two runs describing the
            # same outstanding work are the same notification however the prose
            # is assembled.
            "digest": canonical_digest(
                [(i.get("kind"), i.get("urn"), i.get("title"), i.get("urgency"))
                 for i in sorted(items + escalated,
                                 key=lambda x: (x.get("urn", ""),
                                                x.get("title", "")))]),
        }

    @staticmethod
    def _summary(principal, items, overdue, due, escalated) -> str:
        parts = []
        if overdue:
            parts.append(f"{len(overdue)} overdue")
        if due:
            parts.append(f"{len(due)} due soon")
        rest = len(items) - len(overdue) - len(due)
        if rest:
            parts.append(f"{rest} open")
        if escalated:
            parts.append(f"{len(escalated)} escalated to you")
        return (f"{principal.get('username')}: "
                + (", ".join(parts) if parts else "nothing outstanding"))

    def _escalated(self, principal: Dict[str, Any],
                   already: Sequence[Dict[str, Any]],
                   now: float) -> List[Dict[str, Any]]:
        """Items overdue long enough that they are no longer only their owner's.

        By role, not by hierarchy: MAYA does not know who reports to whom and
        should not pretend to. What it does know is that an item overdue and
        unactioned for a week has stopped being one person's problem.
        """
        if ESCALATION_ROLE not in (principal.get("roles") or []):
            return []
        cutoff = now - self.escalate_days * DAY
        seen = {(i.get("kind"), i.get("urn"), i.get("title")) for i in already}
        out = []
        for item in self.worklist.across(self.registry.list(), now):
            row = item.as_dict() if hasattr(item, "as_dict") else item
            if (row.get("kind"), row.get("urn"), row.get("title")) in seen:
                continue          # already theirs; escalating it to them is noise
            if row.get("urgency") == "overdue" and (row.get("due_at") or now) < cutoff:
                out.append({**row, "escalated": True})
        return out

    # -------------------------------------------------------------- delivery
    def _deliver(self, principal: Dict[str, Any], digest: Dict[str, Any],
                 channel: str, transport, now: float, dry_run: bool,
                 actor: str) -> Dict[str, Any]:
        username = principal.get("username")
        if (why := self._suppressed(username, digest["digest"], channel, now)):
            return self._record(username, digest, channel, SUPPRESSED, why,
                                now, dry_run, actor)
        subject = (f"MAYA: {digest['overdue']} overdue"
                   if digest["overdue"] else
                   f"MAYA: {digest['count']} items outstanding")
        if dry_run:
            return self._record(username, digest, channel, SUPPRESSED,
                                "dry run: nothing was sent", now, True, actor)
        ok, why = transport.send(digest["to"], subject, digest)
        return self._record(username, digest, channel,
                            SENT if ok else FAILED, why, now, False, actor)

    def _suppressed(self, username: str, digest: str, channel: str,
                    now: float) -> Optional[str]:
        """Quiet while the work is unchanged and the quiet period has not passed."""
        previous = self.notifications.first(
            "sent_at", desc=True, principal=username, channel=channel,
            state=SENT)
        if previous is None:
            return None
        if previous.get("digest") != digest:
            return None
        elapsed = (now - (previous.get("sent_at") or 0)) / HOUR
        if elapsed >= self.quiet_hours:
            return None
        return (f"the same outstanding work was notified {elapsed:.1f} hours ago; "
                f"a message that repeats yesterday's is a message somebody "
                f"filters")

    def _record(self, username: str, digest: Dict[str, Any], channel: str,
                state: str, why: str, now: float, dry_run: bool,
                actor: str) -> Dict[str, Any]:
        row = {"principal": username, "channel": channel, "state": state,
               "digest": digest["digest"], "item_count": digest["count"],
               "overdue": digest["overdue"], "summary": digest["summary"],
               "detail": why, "sent_at": now}
        if not dry_run:
            self.notifications.add(row)
            if state == FAILED:
                # A failed delivery is a governance fact: somebody was supposed
                # to be told and was not.
                self.evidence.append("notification_failed", "principal",
                                     username, {"channel": channel,
                                                "reason": why,
                                                "items": digest["count"]},
                                     actor=actor)
        return {**row, "to": digest["to"]}

    @staticmethod
    def _detail(results: List[Dict[str, Any]], channel: str,
                dry_run: bool) -> str:
        if not results:
            return "nobody has outstanding work"
        sent = sum(1 for r in results if r["state"] == SENT)
        failed = sum(1 for r in results if r["state"] == FAILED)
        quiet = sum(1 for r in results if r["state"] == SUPPRESSED)
        parts = [f"{sent} sent over {channel}"]
        if quiet:
            parts.append(f"{quiet} unchanged since the last message")
        if failed:
            parts.append(f"{failed} could not be delivered")
        return ("would have sent: " if dry_run else "") + "; ".join(parts)

    # ------------------------------------------------------------------ query
    def history(self, principal: Optional[str] = None,
                limit: int = 50) -> List[Dict[str, Any]]:
        rows = (self.notifications.many(principal=principal) if principal
                else self.notifications.many())
        return sorted(rows, key=lambda r: r.get("sent_at") or 0,
                      reverse=True)[:limit]

    def status(self) -> Dict[str, Any]:
        """Whether anything is actually reaching anybody."""
        rows = self.notifications.many()
        failed = [r for r in rows if r["state"] == FAILED]
        usable = {name: (t.available() is None)
                  for name, t in self.channels.items()}
        return {
            "channels": [{"channel": n, "usable": ok,
                          "unavailable_because": self.channels[n].available()}
                         for n, ok in sorted(usable.items())],
            "default": self.default_channel,
            "quiet_hours": self.quiet_hours,
            "escalate_after_days": self.escalate_days,
            "delivered": sum(1 for r in rows if r["state"] == SENT),
            "failed": len(failed),
            "detail": (f"{len(failed)} delivery failure(s) recorded; somebody was "
                       f"supposed to be told and was not"
                       if failed else
                       f"{sum(1 for r in rows if r['state'] == SENT)} "
                       f"notification(s) delivered"),
        }
