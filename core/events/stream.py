"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The domain event stream, which is the evidence chain read forwards.

**There is no event table, and that is the design.** Every act that changes this
register already appends to the evidence chain: hash-linked, append-only, in a
**total order**. A separate event log would be a second thing to keep in step,
and the first time the two disagreed nobody would be able to say which was true —
which is precisely the failure a governance platform cannot afford, because the
chain is the thing an examiner is shown.

The chain's `seq` is what makes this work. A cursor is an integer, ordering is
guaranteed, and a consumer that stores the last `seq` it processed can resume
exactly where it stopped — no window, no watermark, no duplicate-detection
heuristics on the consumer's side.

**Delivery is at-least-once, and the envelope gives a receiver the means to
deduplicate on something meaningful.** Every event carries its `seq` and the
chain node's own `content_hash`, so a receiver deduplicates on a fact rather than
on a UUID this platform invented. Saying *make your handler idempotent* without
supplying the key is how at-least-once becomes at-least-twice in production.

**The envelope is versioned.** A consumer written today has to keep working when
a payload gains a field, and the only way anybody can reason about that is if the
shape has a number on it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

#: The envelope's shape. A consumer written today has to keep working when a
#: payload gains a field, and a version is the only thing that lets anybody
#: reason about when it will not.
ENVELOPE_VERSION = 1

#: How many events one read returns. Bounded because a consumer that has been
#: down for a week must not be handed the whole chain in one response — and
#: because the answer says whether more remain, which a caller can act on.
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


def envelope(node: Dict[str, Any]) -> Dict[str, Any]:
    """One chain node, as an event a foreign system can consume.

    The `seq` and `content_hash` are the two fields that matter to a receiver:
    the first is the cursor, and the second is what it should deduplicate on.
    Telling somebody to make their handler idempotent without giving them a key
    is how at-least-once becomes at-least-twice.
    """
    return {
        "envelope": ENVELOPE_VERSION,
        "seq": node.get("seq"),
        "id": node.get("id"),
        "content_hash": node.get("content_hash"),
        "kind": node.get("kind"),
        "subject_type": node.get("subject_type"),
        "subject_id": node.get("subject_id"),
        "payload": node.get("payload"),
        "actor": node.get("recorded_by"),
        "at": node.get("recorded_at"),
    }


class EventStream:
    """Reads the evidence chain forwards, from a cursor."""

    def __init__(self, evidence):
        self.evidence = evidence

    def read(self, after: int = 0, limit: int = DEFAULT_LIMIT,
             kinds: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        """Events after this sequence, in order."""
        from core.events.common import EventError

        if limit < 1 or limit > MAX_LIMIT:
            raise EventError(
                "limit_out_of_range",
                f"{limit} is not a page size; the bound is 1 to {MAX_LIMIT}",
                f"a consumer that has been down for a week is handed at most "
                f"{MAX_LIMIT} events and told more remain, rather than the "
                f"whole chain in one response")
        wanted = set(kinds or ())
        nodes = [n for n in self.evidence.repo.many()
                 if (n.get("seq") or 0) > after
                 and (not wanted or n.get("kind") in wanted)]
        nodes.sort(key=lambda n: n.get("seq") or 0)
        page = nodes[:limit]
        return {
            "events": [envelope(n) for n in page],
            "count": len(page),
            "cursor": page[-1]["seq"] if page else after,
            # Whether to come back immediately or wait. A consumer that cannot
            # tell catching-up from caught-up either polls too often or falls
            # further behind.
            "more": len(nodes) > len(page),
            "envelope_version": ENVELOPE_VERSION,
            "detail": (
                f"{len(page)} event(s) after sequence {after}"
                + (", and more remain" if len(nodes) > len(page) else
                   ", which is all of them")
                + ". These are evidence-chain nodes read forwards, not a "
                  "separate log: a second event table would be a second thing "
                  "to keep in step, and the first time they disagreed nobody "
                  "could say which was true"),
        }

    def kinds(self) -> List[str]:
        """Every event kind the chain has actually produced.

        Derived rather than declared, because a hand-written list of event kinds
        goes stale the first time somebody appends a new one — and a subscriber
        filtering on a kind that no longer exists receives nothing and is told
        nothing.
        """
        return sorted({n.get("kind") for n in self.evidence.repo.many()
                       if n.get("kind")})

    def head(self) -> int:
        """The sequence a new subscriber starts from."""
        nodes = self.evidence.repo.many()
        return max((n.get("seq") or 0 for n in nodes), default=0)
