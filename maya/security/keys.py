"""
API keys and client credentials beyond the secret itself (§12): a key's own
rate-limit budget, rotation with an overlap, and the report that asks for a key to be
rotated or revoked.

The budget reuses the token bucket the request limiter already keeps per caller
(``maya/api/limits.py``), because §12's "its own rate-limit budget" is the same
question as "how many requests a minute may this caller make" — and because the key id
is already that limiter's bucket name. What is different is where the answer comes
from: the process limit is configuration, a key's budget is a column on the key, which
a middleware cannot know without a lookup. So the budget is charged where the key is
resolved, which is also the only place every surface — API, SDK, CLI — must pass
through.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Any, cast

from maya.api.limits import RateLimit
from maya.core.clock import utcnow
from maya.core.errors import QuotaExceeded

# A key's budget is a whole minute in hand: a script may spend it at once and then waits
# while the bucket refills at the per-minute rate. "Six a minute" that refuses the second
# request in the same second would be a rate of one every ten seconds, which is not what
# the number says.


class KeyBudgets:
    """Per-key token buckets, one bucket per key id, each at that key's own rate.

    One ``RateLimit`` per distinct rate: the rate is a property of the limiter, the
    bucket of the caller, and this way the bucket arithmetic — refill, burst and the
    eviction of buckets nobody has used — stays in the one implementation."""

    def __init__(self) -> None:
        self._by_rate: dict[int, RateLimit] = {}
        self._lock = threading.Lock()

    def charge(self, key_id: str, per_minute: int) -> None:
        """Spend one request against this key's budget, or refuse with how long to wait."""
        if per_minute <= 0:
            return
        with self._lock:
            limiter = self._by_rate.get(per_minute)
            if limiter is None:
                # no ASGI application: only the bucket arithmetic is wanted here
                limiter = RateLimit(cast(Any, None), per_minute, per_minute)
                self._by_rate[per_minute] = limiter
            wait = limiter.take(key_id, time.monotonic())
        if wait:
            raise QuotaExceeded(
                f"This API key's budget of {per_minute} requests a minute is spent; "
                f"retry in {int(wait) + 1}s",
                key_id=key_id,
                retry_after=int(wait) + 1,
            )

    def forget(self, key_id: str) -> None:
        """Drop a revoked or rotated key's bucket rather than leave it to age out."""
        with self._lock:
            for limiter in self._by_rate.values():
                limiter.buckets.pop(key_id, None)


def successor(old: dict[str, Any], *, key_id: str, secret_hash: str, days: int) -> dict[str, Any]:
    """The row for a rotated key's successor: the same authority, a new secret."""
    return {
        "key_id": key_id,
        "user_id": old["user_id"],
        "name": old["name"],
        "env": old["env"],
        "kind": old["kind"],
        "secret_hash": secret_hash,
        "roles": list(old["roles"]),
        "namespaces": list(old["namespaces"]),
        "actions": list(old["actions"]),
        "cidrs": list(old["cidrs"]),
        "rate_per_minute": old["rate_per_minute"],
        "expires_at": utcnow() + dt.timedelta(days=days),
        "rotated_from": old["key_id"],
    }


def retirement(old: dict[str, Any], overlap_days: int) -> dt.datetime:
    """When the rotated key stops working: the end of the overlap, or its own expiry if
    that comes first. Rotation never extends a key's life."""
    return min(old["expires_at"], utcnow() + dt.timedelta(days=overlap_days))


def report(
    rows: list[dict[str, Any]], *, unused_days: int, remind_days: int
) -> list[dict[str, Any]]:
    """Keys that want attention, each with the reason (§12: unused keys are reported for
    revocation, and a rotation reminder is due before expiry)."""
    now, out = utcnow(), []
    for row in rows:
        if row["revoked_at"]:
            continue
        reasons = []
        if row["expires_at"] < now:
            reasons.append("expired")
        elif (row["expires_at"] - now).days <= remind_days:
            reasons.append(f"expires in {(row['expires_at'] - now).days} days: rotate it")
        used = row["last_used_at"]
        if used is None and (now - row["created_at"]).days >= unused_days:
            reasons.append(f"never used in {(now - row['created_at']).days} days: revoke it")
        elif used is not None and (now - used).days >= unused_days:
            reasons.append(f"unused for {(now - used).days} days: revoke it")
        if row["successor_key_id"]:
            reasons.append(f"rotated: {row['successor_key_id']} replaces it")
        if reasons:
            entry = {k: v for k, v in row.items() if k != "secret_hash"}
            out.append({**entry, "reasons": reasons})
    return out


__all__ = ["KeyBudgets", "report", "retirement", "successor"]
