"""
The AI gateway: model profiles, the default, and the providers on offer (§21.6).

Reading the status needs only a signed-in user; everything that changes something is for an
administrator, and every change is audited.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from maya.api import schemas_governance as s
from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(tags=["ai"])


@router.get("/ai/status")
def ai_status(me: Principal = Me, plat: Any = Plat) -> Response:
    """Every model profile -- where it came from, where it points, whether it looks usable --
    which one is the default and who chose it, and every provider on offer. Nothing is called."""
    return ok(plat.ai.status(me))


@router.post("/ai/default")
def ai_set_default(body: s.AiDefaultIn, me: Principal = Me, plat: Any = Plat) -> Response:
    """Make a profile the default, at once and for every process; null returns the choice to
    the configuration."""
    return ok(plat.ai.set_default(me, body.profile))


@router.post("/ai/profiles/{name}/test")
def ai_test_profile(name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    """Ask the profile's model one short question: the reply, the time, the tokens, or why not."""
    return ok(plat.ai.test(me, name))


@router.put("/ai/profiles/{name}")
def ai_save_profile(
    name: str, body: dict[str, Any], me: Principal = Me, plat: Any = Plat
) -> Response:
    """Create or replace a profile: provider, model, max_tokens, temperature, options,
    description. Options name a key's environment variable; they never hold a key."""
    return ok(plat.ai.save_profile(me, name, body))


@router.delete("/ai/profiles/{name}")
def ai_delete_profile(name: str, me: Principal = Me, plat: Any = Plat) -> Response:
    """Remove a profile saved from the UI; one from the profiles file is edited there."""
    return ok(plat.ai.delete_profile(me, name))
