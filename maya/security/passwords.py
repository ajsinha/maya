"""
What a password must be, how long it may live, and what it may not repeat (§12).

``password_policy: {min_length, require_classes, history, max_age_days}`` is four
rules, and each is refused with its own reason: a caller who is told only "that
password is not acceptable" tries the same thing again. The rules live here rather
than in the authentication service because three separate paths apply them — a person
changing their own password, an administrator resetting someone else's, and a reset
token being redeemed — and they must not drift apart.

History is kept as hashes of the last ``history`` passwords, the current one included,
and compared with the key derivation function rather than by equality: the stored form
is salted, so there is no cheaper way to ask "is this the same password again".

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from maya.core import kdf
from maya.core.clock import utcnow
from maya.core.errors import ValidationFailed

CLASS_NAMES = ("lower", "upper", "digit", "symbol")


def classes_in(password: str) -> int:
    return sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )


class PasswordRules:
    """The configured password policy, and the three refusals it can make."""

    def __init__(self, settings: Any) -> None:
        self.min_length = settings.int("auth.password.min_length", 8)
        self.require_classes = settings.int("auth.password.require_classes", 2)
        self.force_change = settings.bool("auth.password.force_change", False)
        self.history = settings.int("auth.password.history", 5)
        self.max_age = dt.timedelta(days=settings.int("auth.password.max_age_days", 90))
        self.reset_token_life = dt.timedelta(
            minutes=settings.int("auth.password.reset_token_minutes", 60)
        )

    def check(self, password: str) -> None:
        """Shape only: length and character classes."""
        if len(password) < self.min_length or classes_in(password) < self.require_classes:
            raise ValidationFailed(
                f"Password must be at least {self.min_length} characters and use "
                f"{self.require_classes} of: {', '.join(CLASS_NAMES)}"
            )

    def check_history(self, uow: Any, user: dict[str, Any], password: str) -> None:
        """Refuse a password this account has used within the remembered window."""
        if self.history <= 0:
            return
        for stored in self._remembered(uow, user):
            if stored and kdf.verify_password(password, stored):
                raise ValidationFailed(
                    f"That password was used before. MAYA remembers the last "
                    f"{self.history}; choose one none of them matches"
                )

    def _remembered(self, uow: Any, user: dict[str, Any]) -> list[str]:
        rows = uow.repo("password_history").list(
            user_id=user["id"], order_by=["-created_at"], limit=self.history
        )
        return [user["password_hash"] or ""] + [r["password_hash"] for r in rows]

    def remember(self, uow: Any, user: dict[str, Any]) -> None:
        """Record the password being replaced, then forget anything past the window.

        Called before the new hash is written, so the row it adds is the *old* password;
        the current one needs no row because the user record still holds it."""
        if self.history <= 0 or not user["password_hash"]:
            return
        repo = uow.repo("password_history")
        repo.add({"user_id": user["id"], "password_hash": user["password_hash"]})
        # keep history-1 rows: the user row itself counts as the most recent entry
        kept = max(self.history - 1, 0)
        for row in repo.list(user_id=user["id"], order_by=["-created_at"])[kept:]:
            repo.delete(row["id"])

    def past_its_age(self, user: dict[str, Any]) -> int | None:
        """Days over the maximum age, or None while the password may still be used.

        A password whose change was never recorded is not expired: MAYA does not know
        when it was set, and guessing would lock out every account the day a maximum
        age is first configured."""
        if not self.max_age or user["auth_source"] != "db":
            return None
        changed = user.get("password_changed_at")
        if changed is None:
            return None
        over = (utcnow() - changed) - self.max_age
        return over.days if over.total_seconds() > 0 else None

    def age_refusal(self, days_over: int) -> str:
        return (
            f"Your password passed the {self.max_age.days}-day maximum age "
            f"{days_over} day{'s' if days_over != 1 else ''} ago and must be changed "
            "before you can sign in: ask an administrator for a reset link"
        )


__all__ = ["CLASS_NAMES", "PasswordRules", "classes_in"]
