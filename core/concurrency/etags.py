"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Two people changing one thing at once.

An ETag is the answer to *is this still what I read*, and the lost update it
prevents is the quietest failure in any register: two people open a model
record, both edit, both save, and the second write silently discards the first.
Nothing is refused, nothing is logged as wrong, and the only trace is a field
that says something nobody typed.

**The tag is derived from the representation, never stored.** A version column
is a second thing to keep in step, and the first time somebody writes a row
without bumping it the tag says *unchanged* about something that changed. The
digest is the platform's own canonical digest — the same function the evidence
chain hashes with — so a tag cannot drift from the thing it describes.

**A precondition is never silently ignored.** This is the rule that matters. A
client sending `If-Match` believes it has optimistic concurrency; a server that
drops the header gives it none and says nothing, which is strictly worse than
not supporting preconditions at all, because the client has stopped checking for
itself. Where a route cannot evaluate the precondition, the request is refused
by name.
"""
from __future__ import annotations

from typing import Any, Optional

from core.concurrency.idempotency import IdempotencyError
from db.database import digest as canonical_digest

ETAG_HEADER = "etag"
IF_MATCH = "if-match"
IF_NONE_MATCH = "if-none-match"

#: Fields that change on every read or on nothing anybody cares about. Excluded
#: so a tag identifies the *state* of a thing rather than the moment it was
#: rendered — a tag that changes when nothing did makes every conditional
#: request a full one and teaches clients to stop sending the header.
VOLATILE = ("detail", "as_at", "now", "generated_at", "seconds_left")


def etag_of(value: Any) -> str:
    """A weak entity tag for a representation.

    Weak (`W/`) and correctly so: this is a digest of the *semantic* content
    with rendering noise removed, not of the octets. Two responses with the same
    weak tag are the same answer, which is what a caller asking *is this still
    what I read* means, and claiming octet equality would be a claim this does
    not check.
    """
    return f'W/"{canonical_digest(_strip(value))[:32]}"'


def _strip(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in sorted(value.items())
                if k not in VOLATILE}
    if isinstance(value, list):
        return [_strip(v) for v in value]
    return value


def matches(supplied: Optional[str], current: str) -> bool:
    """Whether a precondition header is satisfied by the current tag.

    `*` matches anything that exists, which is the header's way of saying *only
    if it is there*. A list is matched member-wise, and the weak prefix is
    compared as given rather than normalised away — a caller that sent a strong
    tag is asking a stronger question than this can answer, and quietly treating
    it as weak would answer a different question from the one asked.
    """
    if not supplied:
        return False
    candidates = [part.strip() for part in supplied.split(",") if part.strip()]
    if "*" in candidates:
        return True
    return current in candidates


class PreconditionError(IdempotencyError):
    """A conditional request whose condition did not hold.

    A subclass rather than a separate type: both are the same kind of refusal —
    *this request was written against a state of the world that is no longer
    true* — and giving them one handler at the edge is the whole reason they
    share a shape.
    """


def require_match(supplied: Optional[str], current: Optional[str],
                  path: str) -> None:
    """Evaluate a precondition, or refuse. Never silently pass.

    The rule this module exists for. A client sending `If-Match` believes it has
    optimistic concurrency; a server that drops the header gives it none and
    says nothing, which is strictly worse than not supporting preconditions at
    all — the client has stopped checking for itself.
    """
    if current is None:
        raise PreconditionError(
            "precondition_unevaluable",
            f"this request carries If-Match, and {path} has no representation "
            f"to compare it against. Ignoring the header would give you "
            f"optimistic concurrency you do not have",
            "drop the header, or address a path that can be read back")
    if not matches(supplied, current):
        raise PreconditionError(
            "precondition_failed",
            "this resource has changed since you read it, so the write you are "
            "making was decided against something that is no longer true",
            "read it again, reconcile, and retry")
