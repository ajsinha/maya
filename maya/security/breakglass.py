"""
The administrator's way in when the identity provider is not there (§13.3).

§13.3 promises that an unreachable IdP leaves "a break-glass path for
administrators". Under ``auth.mode: sso`` MAYA refuses every password sign-in, so
without something here the only path is restarting the platform in ``hybrid`` — which
needs a configuration change and a restart of every process at the worst possible
moment, and which then opens password sign-in to *every* database account rather than
to the one account kept for this.

So: ``auth.break_glass.users`` names the accounts — usually one — that may sign in
with a password whatever ``auth.mode`` says. Nothing else about them is special. They
are ordinary database accounts, they must hold the administrator role (a break-glass
account that cannot administer anything is a password with no purpose), MFA applies to
them exactly as it does to anyone, their session is short
(``auth.break_glass.session_minutes``), and every use is audited durably, notified to
every administrator and logged at warning level. The point is not to make the door
quieter but to make sure it exists and that walking through it cannot go unnoticed.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

ADMIN_ROLE = "admin"


def designated(settings: Any) -> set[str]:
    """The accounts configuration names as break-glass, lower-cased."""
    names = settings.props.get_list("auth.break_glass.users") or []
    return {str(n).strip().lower() for n in names if str(n).strip()}


def is_designated(settings: Any, username: str | None) -> bool:
    return bool(username) and str(username).strip().lower() in designated(settings)


def why_refused(settings: Any, user: dict[str, Any] | None, roles: list[str]) -> str | None:
    """Why this break-glass sign-in cannot be allowed, or None when it can.

    Checked in the order that gives the most useful answer to the operator reading the
    audit trail afterwards: does the account exist as a database account at all, and is
    it actually an administrator."""
    if user is None or user["auth_source"] != "db" or user["is_service"]:
        return "the break-glass account is not a database account"
    if ADMIN_ROLE not in roles:
        return "the break-glass account does not hold the administrator role"
    return None


def notice(username: str) -> str:
    return (
        f"Break-glass sign-in: '{username}' signed in with a password while MAYA is in "
        "SSO-only mode. Confirm this was expected, and review what the account did."
    )


__all__ = ["ADMIN_ROLE", "designated", "is_designated", "notice", "why_refused"]
