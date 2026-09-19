"""
maya_delta errors.

Every failure the lake layer raises on purpose is a ``MayaDeltaError``. A table
that needs a protocol capability this implementation does not have raises
``UnsupportedFeature`` naming the capability — never an approximation.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations


class MayaDeltaError(Exception):
    """Root of every deliberate maya_delta error."""


class UnsupportedFeature(MayaDeltaError):
    """The table requires a Delta protocol feature this backend does not implement."""

    def __init__(self, feature: str, detail: str = "") -> None:
        self.feature = feature
        msg = f"Delta table requires unsupported protocol feature '{feature}'"
        super().__init__(f"{msg}: {detail}" if detail else msg)


class ConcurrentModification(MayaDeltaError):
    """A concurrent commit conflicts with this one and it cannot be retried."""


class TableNotFound(MayaDeltaError):
    """No Delta table exists at the given path."""
