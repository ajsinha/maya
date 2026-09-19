"""
Custody anchoring and effective licences (§29.6).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(tags=["custody"])


@router.get("/custody/anchors")
def anchors(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.custody.list(me))


@router.post("/custody/anchor", status_code=201)
def anchor(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.custody.anchor_now(me), 201)


@router.get("/custody/verify")
def verify(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.custody.verify(me))


@router.get("/licences")
def licence(kind: str, ref: str, me: Principal = Me, plat: Any = Plat) -> Response:
    """The effective licence of a feature or feature set, and who imposed each term."""
    return ok(plat.licences.show(me, kind, ref))
