"""
The durable event stream (§18.1): which audit entries are also events.

An event is written by the unit of work *in the same transaction* as the audit
entry that caused it, so an event can never describe something that did not
commit, and nothing that committed can go unannounced. Workflow transitions are
named by the object and the state reached — ``feature_version.approved``,
``model_version.deprecated`` — which is what a subscriber actually wants.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

EVENT_ACTIONS = {
    "pin.sealed",
    "pin.failed",
    "pin.retired",
    "featureset.cascade_rolled_back",
    "feature.ingested",
    "feature.pulled",
    "warrant.created",
    "warrant.parameters_uploaded",
    "warrant.sealed",
    "warrant.revoked",
    "warrant.exec_created",
    "warrant.exec_sealed",
    "warrant.suspended",
    "warrant.reinstated",
    "warrant.exec_revoked",
    "bundle.exported",
    "access.granted",
    "access.revoked",
    "auth.lockout",
    "auth.mfa_reset",
    # The emergency door (§13.3). A subscriber that watches nothing else should watch
    # this: a break-glass sign-in is either an outage being handled or a stolen password,
    # and the difference is worth a page rather than a line in an audit table.
    "auth.break_glass_login",
    "workspace.submitted",
    "workspace.merged",
    "integrity.verified",
    "policy.activated",
    "workflow.break_glass",
    "job.dead_letter",
    "audit.anchored",
    "warrant.limit_exceeded",
}


def event_type(entry: dict[str, Any]) -> str | None:
    """The event an audit entry announces, or None."""
    action = entry.get("action", "")
    if action.startswith("workflow.") and action not in (
        "workflow.approval_recorded",
        "workflow.break_glass",
    ):
        to = (entry.get("detail") or {}).get("to")
        return f"{entry.get('object_type')}.{to}" if to and entry.get("object_type") else None
    return action if action in EVENT_ACTIONS else None


def matches(subscribed: list[str], etype: str) -> bool:
    """Empty means everything; a trailing '*' is a prefix (``warrant.*``)."""
    if not subscribed:
        return True
    return any(etype == s or (s.endswith("*") and etype.startswith(s[:-1])) for s in subscribed)
