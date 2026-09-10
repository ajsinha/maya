"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Who wants to be told what, and where they have got to.

**A webhook is an egress, and this platform is meant to be deployable
air-gapped.** Every asset here is vendored for that reason, and a subscription is
the first thing that deliberately reaches outward. So it is off unless somebody
creates one, the URL goes through the same outbound guard as every other outward
call, and — the part usually skipped — **the content question is answered
explicitly**: a chain node's payload carries model inventory, findings and
exposure figures, so `kinds` is mandatory and `*` is refused. A subscription that
receives everything is one nobody decided the content of, and *we send you all
our events* is not a data-sharing decision anybody made.

**The cursor is per subscription.** A receiver that is failing falls behind on
its own; it does not hold up the others, and it is not silently skipped past. Its
backlog is a number somebody can look at, which is what makes a broken integration
visible instead of quiet.

**Each delivery is signed**, so a receiver can tell an event from this platform
from anything else that finds the URL. The secret is returned once, at creation,
and never on a read: a secret a listing endpoint hands back is a secret held by
everybody with read access.

**A subscription is suspended, never deleted, after repeated failure.** Deleting
it would lose the record that somebody was being told and stopped being told, and
the cursor with it — so a receiver that comes back would either miss everything
in between or be resent the whole chain.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional, Sequence

from core.events.common import EventError
from core.log import get_logger
from core.outbound import OutboundError, permit

logger = get_logger(__name__)

#: The header a receiver verifies. HMAC-SHA256 over the exact body sent, so a
#: receiver can tell an event from this platform from anything else that finds
#: the URL.
SIGNATURE_HEADER = "X-MAYA-Signature"
SEQUENCE_HEADER = "X-MAYA-Sequence"

#: How many consecutive failures before a subscription is suspended. Five,
#: because a receiver down for a deploy should not be suspended and one down for
#: a week should be.
MAX_FAILURES = 5

#: How many events one delivery carries.
BATCH = 50


class Subscriptions:
    """Registers subscribers, and pushes the chain to them."""

    def __init__(self, repo, stream, evidence, sender=None):
        self.repo, self.stream, self.evidence = repo, stream, evidence
        # How a delivery is actually made. Injected so the governed path can be
        # exercised without anything leaving the process — which is the same
        # reason the mock assistance provider exists.
        self.sender = sender

    # ------------------------------------------------------------- subscribe
    def subscribe(self, *, name: str, url: str, kinds: Sequence[str],
                  owner: str, actor: str = "system") -> Dict[str, Any]:
        """Register a receiver. The secret is returned once and never again."""
        if not (name or "").strip():
            raise EventError("name_required",
                             "a subscription with no name is a row nobody can "
                             "identify when it starts failing",
                             "name it after the system receiving it")
        if not (owner or "").strip():
            raise EventError(
                "owner_required",
                "a subscription with no owner is an egress nobody is "
                "accountable for",
                "name the person who answers for this integration")
        wanted = [k for k in (kinds or ()) if k]
        if not wanted:
            raise EventError(
                "kinds_required",
                "a subscription must say which event kinds it receives. A "
                "chain node's payload carries model inventory, findings and "
                "exposure figures, so what leaves the institution is a "
                "decision somebody takes rather than a default",
                "name the kinds; GET /api/v1/events/kinds lists the ones this "
                "register has actually produced")
        if "*" in wanted:
            raise EventError(
                "wildcard_refused",
                "'*' is not a set of kinds. A subscription that receives "
                "everything is one nobody decided the content of, and *we send "
                "you all our events* is not a data-sharing decision anybody "
                "made",
                "name them. If the list is long, that is the decision being "
                "visible rather than avoided")
        try:
            checked = permit(url, what="the subscription url")
        except OutboundError as refused:
            logger.warning("subscription to %s refused: %s", url, refused.code)
            raise EventError(refused.code, refused.detail,
                             refused.remediation) from refused

        rows = self.repo.many()
        secret = secrets.token_urlsafe(32)
        row = {
            "reference": f"SUB-{len(rows) + 1:04d}", "name": name.strip(),
            "url": checked, "kinds": sorted(set(wanted)), "secret": secret,
            # From the head, not from zero. A new subscriber does not want the
            # entire history of the register delivered to it, and one that does
            # can rewind deliberately.
            "cursor": self.stream.head(), "state": "active", "failures": 0,
            "last_delivery_at": None, "last_failure_at": None,
            "last_failure": "", "owner": owner, "created_at": time.time(),
            "created_by": actor,
        }
        with self.evidence.recording():
            stored = self.repo.add(row)
            self.evidence.append(
                "event_subscription_created", "subscription", stored["id"],
                {"reference": row["reference"], "name": name, "url": checked,
                 "kinds": row["kinds"], "owner": owner,
                 "from_sequence": row["cursor"]}, actor=actor)
        logger.info("subscription %s created for %s (%d kind(s)) by %s",
                    row["reference"], checked, len(row["kinds"]), actor)
        # The one moment the secret is visible.
        return {**self._public(stored), "secret": secret,
                "detail": ("the secret is returned once and never again. It "
                           "signs every delivery, so the receiver can tell an "
                           "event from this platform from anything else that "
                           "finds the URL")}

    # -------------------------------------------------------------- delivery
    def deliver(self, reference: str,
                now: Optional[float] = None) -> Dict[str, Any]:
        """Push this subscriber's backlog, from its own cursor."""
        row = self.require(reference)
        moment = now if now is not None else time.time()
        if row["state"] != "active":
            return {"reference": reference, "delivered": 0,
                    "detail": f"{reference} is {row['state']}"}

        page = self.stream.read(after=row["cursor"], limit=BATCH,
                                kinds=row["kinds"])
        if not page["events"]:
            return {"reference": reference, "delivered": 0,
                    "cursor": row["cursor"],
                    "detail": "nothing new for this subscriber"}
        body = json.dumps({"envelope": page["envelope_version"],
                           "events": page["events"]},
                          sort_keys=True, separators=(",", ":"))
        headers = {
            SIGNATURE_HEADER: self.sign(row["secret"], body),
            SEQUENCE_HEADER: str(page["cursor"]),
            "Content-Type": "application/json",
        }
        if self.sender is None:
            return {"reference": reference, "delivered": 0,
                    "would_deliver": page["count"],
                    "detail": ("no sender is wired into this instance, so "
                               "nothing left the process. The backlog is "
                               "computed and reported rather than silently "
                               "dropped")}
        try:
            self.sender(row["url"], body, headers)
        except Exception as failure:
            # Recovered from rather than raised: one unreachable receiver must
            # not stop the others being told, and a delivery nobody knows
            # failed is worse than one that visibly did. `_failed` counts it
            # and suspends on enough of them.
            logger.warning("delivery to %s raised %s", row["reference"],
                           type(failure).__name__)
            return self._failed(row, failure, moment)
        with self.evidence.recording():
            self.repo.set({"cursor": page["cursor"], "failures": 0,
                           "last_delivery_at": moment, "last_failure": ""},
                          id=row["id"])
            self.evidence.append(
                "events_delivered", "subscription", row["id"],
                {"reference": reference, "events": page["count"],
                 "to_sequence": page["cursor"]}, actor="scheduler")
        return {"reference": reference, "delivered": page["count"],
                "cursor": page["cursor"], "more": page["more"],
                "detail": (f"{page['count']} event(s) delivered to "
                           f"{row['name']}, up to sequence {page['cursor']}")}

    def _failed(self, row: Dict[str, Any], failure: Exception,
                moment: float) -> Dict[str, Any]:
        """Record a failure, and suspend rather than delete after enough of them.

        Deleting would lose the record that somebody was being told and stopped
        being told, and the cursor with it — so a receiver that came back would
        either miss everything in between or be resent the whole chain.
        """
        failures = (row.get("failures") or 0) + 1
        state = "suspended" if failures >= MAX_FAILURES else row["state"]
        logger.warning("delivery to %s (%s) failed %d time(s): %s",
                       row["reference"], row["url"], failures, failure)
        with self.evidence.recording():
            self.repo.set({"failures": failures, "state": state,
                           "last_failure_at": moment,
                           "last_failure": str(failure)[:400]}, id=row["id"])
            if state == "suspended":
                self.evidence.append(
                    "event_subscription_suspended", "subscription", row["id"],
                    {"reference": row["reference"], "failures": failures,
                     "last_failure": str(failure)[:400]}, actor="scheduler")
        return {
            "reference": row["reference"], "delivered": 0,
            "failures": failures, "state": state,
            "detail": (f"delivery failed ({failure}). "
                       + (f"After {failures} consecutive failures this "
                          f"subscription is suspended — not deleted, because "
                          f"deleting it would lose the cursor and a receiver "
                          f"that came back would either miss everything in "
                          f"between or be resent the whole chain"
                          if state == "suspended" else
                          f"{MAX_FAILURES - failures} more before it is "
                          f"suspended")),
        }

    def deliver_all(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Push every active subscriber's backlog."""
        results = [self.deliver(r["reference"], now)
                   for r in self.repo.many(state="active")]
        delivered = sum(r.get("delivered", 0) for r in results)
        failed = [r for r in results if r.get("failures")]
        return {"subscriptions": len(results), "delivered": delivered,
                "failed": len(failed), "results": results,
                "detail": (f"{delivered} event(s) delivered across "
                           f"{len(results)} subscription(s)"
                           + (f", {len(failed)} failing" if failed else ""))}

    # --------------------------------------------------------------- signing
    @staticmethod
    def sign(secret: str, body: str) -> str:
        """HMAC-SHA256 over the exact bytes sent.

        Over the body rather than over a summary of it: a signature covering
        anything less than what was sent leaves the rest unsigned, and a
        receiver has no way to know which part it verified.
        """
        return "sha256=" + hmac.new(secret.encode("utf-8"),
                                    body.encode("utf-8"),
                                    hashlib.sha256).hexdigest()

    # ------------------------------------------------------------------ read
    def require(self, reference: str) -> Dict[str, Any]:
        row = self.repo.one(reference=reference)
        if not row:
            raise EventError("no_subscription",
                             f"no subscription '{reference}'",
                             "references look like SUB-0001")
        return row

    def resume(self, reference: str, actor: str = "system") -> Dict[str, Any]:
        """Bring a suspended subscription back, from where it stopped."""
        row = self.require(reference)
        if row["state"] == "active":
            raise EventError("already_active", f"{reference} is active",
                             "nothing to resume")
        with self.evidence.recording():
            self.repo.set({"state": "active", "failures": 0}, id=row["id"])
            self.evidence.append("event_subscription_resumed", "subscription",
                                 row["id"], {"reference": reference,
                                             "from_sequence": row["cursor"]},
                                 actor=actor)
        return self._public(self.require(reference))

    def across_the_estate(self) -> Dict[str, Any]:
        """Every subscriber, and how far behind each has fallen."""
        head = self.stream.head()
        rows = []
        for row in self.repo.many():
            public = self._public(row)
            public["behind"] = max(0, head - (row.get("cursor") or 0))
            rows.append(public)
        rows.sort(key=lambda r: -r["behind"])
        suspended = [r for r in rows if r["state"] == "suspended"]
        behind = [r for r in rows if r["behind"] > 0 and r["state"] == "active"]
        return {
            "subscriptions": rows, "count": len(rows), "head": head,
            "suspended": len(suspended), "behind": len(behind),
            "detail": (
                f"{len(rows)} subscription(s) against a chain head of {head}"
                + (f"; {len(suspended)} suspended after repeated failure — "
                   f"suspended and not deleted, so the cursor survives and a "
                   f"receiver that comes back resumes where it stopped"
                   if suspended else "")
                + (f"; {len(behind)} active and behind, which is what a broken "
                   f"integration looks like before anybody notices"
                   if behind else "")
                if rows else
                "nothing subscribes to this register's events. Webhooks are an "
                "egress and this platform is meant to be deployable "
                "air-gapped, so that is the resting state rather than a gap"),
        }

    @staticmethod
    def _public(row: Dict[str, Any]) -> Dict[str, Any]:
        """A subscription without its secret.

        A secret a listing endpoint hands back is a secret held by everybody
        with read access, which is not a secret.
        """
        return {k: v for k, v in row.items() if k != "secret"}


def http_sender(timeout: float = 10.0):
    """The real sender: an HTTP POST, and nothing more.

    Separate from the class and injected, for the same reason the mock
    assistance provider exists: the whole governed path — cursor, filter,
    signature, backoff, suspension — is exercisable without anything leaving
    the process, and a test that has to reach the network is a test nobody
    runs.

    It raises rather than returning a flag. The caller records the failure,
    counts it and suspends on enough of them, and a sender that swallowed the
    error would leave that machinery with nothing to act on.
    """
    import urllib.error
    import urllib.request

    def send(url: str, body: str, headers: Dict[str, str]) -> None:
        request = urllib.request.Request(url, data=body.encode("utf-8"),
                                         headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise EventError(
                    "delivery_refused",
                    f"the receiver answered {response.status}",
                    "a 2xx is the only answer treated as delivered")

    return send
