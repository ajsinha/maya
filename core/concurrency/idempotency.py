"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Sending the same request twice.

A client whose connection dropped mid-POST does not know whether the act
happened. Its choices are to retry — and risk two attestations, two waivers, two
break-glass grants — or not to, and risk none. An idempotency key removes the
choice: retry, and the second request returns the first one's answer without
doing anything again.

**A key that ignores the body is worse than no key at all.** An implementation
that replays the first response to *any* second request with the same key tells
a client that retried with a **corrected** payload that the correction succeeded
— when what it actually returned was the answer to the mistake. So the record
carries a digest of the request, and a key reused with a different body is a
**conflict** and not a replay.

**Keys are scoped to the principal.** A key is chosen by the caller, and a
well-chosen UUID does not protect you from somebody else's badly chosen one.

**The record is written before the work, not after.** Two requests with the same
key arriving at the same moment are the case this is actually for — a retry
usually races the original rather than following it politely. The first insert
wins; the second sees `in_flight` and is refused with *ask again shortly*, which
is true, rather than being told the act succeeded when it has not finished.

**A failed request releases the key.** This is the half implementations get
wrong. If a 500 or a refusal is recorded as the key's outcome, the client's
retry replays the failure forever and the key becomes a tombstone for an act
that never happened. Only a **successful** response is retained; anything else
deletes the record, so a retry is a real retry.

**What this does not make idempotent, said plainly.** It makes the *response*
idempotent. Effects the response does not describe — an evidence node, a
notification already sent — happened once and are not undone, which is correct:
the point is that they do not happen twice. And an act that half-succeeded
before the process died leaves no completed record, so the retry runs again; a
platform that cannot distinguish *partly done* from *not done* should re-run
rather than skip, because every act here is a governance act with its own
refusals in front of it.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

from core.log import get_logger
from db.database import digest as canonical_digest

logger = get_logger(__name__)

HEADER = "idempotency-key"

#: Set on a replayed response, so a client can tell that its retry was a retry.
#: Silence here would make a replay indistinguishable from a second successful
#: act, which is precisely the ambiguity the key exists to remove.
REPLAYED = "idempotency-replayed"

#: How long a completed record is kept. Long enough that a client retrying after
#: an outage still gets its answer, short enough that the table is not a
#: permanent copy of every response the platform has ever produced.
RETENTION_HOURS = 24.0

#: How long an `in_flight` record may sit before it is assumed dead. A process
#: killed mid-request leaves one behind, and without this the key is poisoned
#: forever — which turns a crash into a permanent inability to retry.
STALE_MINUTES = 15.0

MAX_KEY = 255


def _body_digest(body: bytes) -> str:
    """A digest of what the request MEANS, not of how it was serialised.

    Taken over the raw bytes, `{"a":1,"b":2}` and `{"b":2,"a":1}` hash
    differently — so a client retrying the identical request through a
    different JSON library, a proxy that re-serialised it, or a language whose
    mapping order differs, was refused `idempotency_key_reused`. The refusal
    told them the key "was used for a different POST", which was not true: it
    was the same request, spelled in a different order.

    That is the wrong direction for this control to fail in. Idempotency exists
    so a client that is unsure whether its request arrived can safely send it
    again, and this made the safe retry the one thing guaranteed to fail.

    `canonical_digest` sorts keys, so parsing first makes ordering irrelevant
    while leaving every actual difference — a changed value, an added field, a
    removed one — as visible as before. A body that is not JSON falls back to
    the raw bytes, where byte equality is the only meaning available.
    """
    text = body.decode("utf-8", "replace")
    if not text.strip():
        return canonical_digest({"json": None})
    try:
        parsed = json.loads(text)
    except ValueError as not_json:
        # Not an error: an endpoint may take a form post, an upload or an
        # opaque payload, and for those the bytes ARE the meaning. Logged at
        # debug rather than swallowed, because "this key behaved differently
        # from the JSON ones" is otherwise unexplainable from outside.
        logger.debug("idempotent body is not JSON (%s); digesting the raw "
                     "bytes, where byte equality is the only meaning "
                     "available", not_json)
        return canonical_digest({"raw": text})
    return canonical_digest({"json": parsed})


class IdempotencyError(RuntimeError):
    """An idempotent replay was refused. The message always says why."""

    def __init__(self, code: str, detail: str, remediation: str = ""):
        super().__init__(detail)
        self.code, self.detail, self.remediation = code, detail, remediation

    def as_problem(self) -> Dict[str, str]:
        return {"error": self.code, "detail": self.detail,
                "remediation": self.remediation}


class IdempotencyStore:
    """Claims a key before the work, and keeps only what succeeded."""

    def __init__(self, repo):
        self.repo = repo

    # ---------------------------------------------------------------- claim
    def claim(self, key: str, principal: str, method: str, path: str,
              body: bytes) -> Optional[Dict[str, Any]]:
        """Take the key, or hand back the answer already given under it.

        Returns `None` when the caller should go and do the work, or the stored
        response to replay. Raises when the key cannot be honoured.
        """
        if len(key) > MAX_KEY:
            raise IdempotencyError(
                "idempotency_key_too_long",
                f"an idempotency key of {len(key)} characters is not a key, it "
                f"is a payload",
                f"at most {MAX_KEY} characters — a UUID is the usual choice")
        request_digest = canonical_digest(
            {"method": method, "path": path, "body": _body_digest(body)})

        existing = self.repo.one(idempotency_key=key, principal=principal)
        if existing is None:
            self.repo.add({"idempotency_key": key, "principal": principal,
                           "method": method, "path": path,
                           "request_digest": request_digest,
                           "state": "in_flight", "status": None, "body": None,
                           "started_at": time.time(), "completed_at": None})
            return None

        if existing["request_digest"] != request_digest:
            raise IdempotencyError(
                "idempotency_key_reused",
                f"this idempotency key was used for a different "
                f"{existing['method']} to {existing['path']}. Replaying the "
                f"earlier answer would tell you a request you have since "
                f"corrected succeeded",
                "use a new key for a changed request; a key identifies one "
                "attempt at one act, not a session")

        if existing["state"] == "in_flight":
            age = (time.time() - existing["started_at"]) / 60.0
            if age < STALE_MINUTES:
                raise IdempotencyError(
                    "idempotency_in_flight",
                    "an identical request under this key is still running. It "
                    "has not failed and it has not succeeded, and saying "
                    "either would be a guess",
                    "ask again shortly — a retry that races the original is "
                    "the ordinary case and this is why the key is claimed "
                    "before the work rather than after")
            # A process killed mid-request left this behind. Without this the
            # key is poisoned forever, which turns a crash into a permanent
            # inability to retry the very act that crashed.
            logger.warning("idempotency key %s for %s was in flight for %.0f "
                           "minutes and is assumed dead; releasing it",
                           key, principal, age)
            self.repo.set({"state": "in_flight", "started_at": time.time()},
                          id=existing["id"])
            return None

        return {"status": existing["status"], "body": existing["body"]}

    # -------------------------------------------------------------- outcome
    def complete(self, key: str, principal: str, status: int,
                 body: bytes) -> None:
        """Keep a successful answer so the retry can have it."""
        row = self.repo.one(idempotency_key=key, principal=principal)
        if row is None:
            return
        self.repo.set({"state": "complete", "status": status,
                       "body": body.decode("utf-8", "replace"),
                       "completed_at": time.time()}, id=row["id"])

    def release(self, key: str, principal: str) -> None:
        """Let go of a key whose request did not succeed.

        The half implementations get wrong. A recorded failure makes the
        client's retry replay that failure forever, and the key becomes a
        tombstone for an act that never happened.
        """
        row = self.repo.one(idempotency_key=key, principal=principal)
        if row is not None:
            self.repo.remove(id=row["id"])

    # ---------------------------------------------------------------- sweep
    def sweep(self, now: Optional[float] = None) -> Dict[str, Any]:
        """Drop records nobody can still be waiting on."""
        moment = now if now is not None else time.time()
        horizon = moment - RETENTION_HOURS * 3600.0
        dropped = 0
        for row in self.repo.many():
            if (row.get("started_at") or 0) >= horizon:
                continue
            self.repo.remove(id=row["id"])
            dropped += 1
        return {"dropped": dropped,
                "detail": (f"{dropped} idempotency record(s) older than "
                           f"{RETENTION_HOURS:.0f} hours were dropped. A "
                           f"client still retrying after that is retrying "
                           f"something it should be told about rather than "
                           f"quietly given an old answer to"
                           if dropped else
                           "no idempotency record is older than the retention "
                           "window")}
