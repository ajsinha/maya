"""
Where a LaTeX build's limits are decided (§17.1).

``maya.core.typeset`` knows how to cap a build; it deliberately does not know what this
deployment's caps are, nor whether this host can give a build a network namespace. The
first is configuration and the second is a probe that lives in ``maya.security.sandbox``
— and ``maya.core`` importing ``maya.security`` would invert the layering, so the two
meet here, in the services layer that may see both.

Every caller that renders a PDF goes through ``render`` rather than calling
``render_pdf`` directly, so a specification and an execution manifest are built under the
same limits. A PDF built under looser limits than the one beside it would be a quiet
difference in how much evidence each is worth.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from maya.core.typeset import Caps, render_pdf
from maya.security.sandbox import net_jail


def caps_from(settings: Any) -> Caps:
    """This deployment's build caps."""
    return Caps(
        seconds=settings.int("typeset.timeout_seconds", 120),
        memory_mb=settings.int("typeset.memory_mb", 2048),
        output_mb=settings.int("typeset.output_mb", 64),
    )


def render(settings: Any, latex: str, *, force_draft: bool = False) -> tuple[bytes, dict[str, Any]]:
    """Render ``latex`` under this deployment's caps, in a network namespace where the
    host provides one. The metadata records which caps applied, so a model version says
    what its build was allowed to do rather than what the defaults were that day."""
    return render_pdf(latex, caps=caps_from(settings), jail=net_jail(), force_draft=force_draft)


__all__ = ["caps_from", "render"]
