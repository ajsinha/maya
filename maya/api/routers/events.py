"""
The event stream and webhooks (§18.1).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response, StreamingResponse

from maya.api import schemas as s
from maya.api.deps import Me, Plat, ok
from maya.security.authz import Principal

router = APIRouter(tags=["events"])


@router.get("/events")
def events(after: int = 0, limit: int = 500, type: str | None = None,
           page_size: int | None = None, cursor: str | None = None,
                  sort: str | None = None, total: bool = False, me: Principal = Me, plat: Any = Plat) -> Response:
    if page_size is not None or cursor is not None:
        return ok(plat.webhooks.events_page(me, type_prefix=type, page_size=page_size, cursor=cursor, sort=sort, total=total))
    return ok(plat.webhooks.events(me, after=after, limit=limit, type_prefix=type))


@router.get("/events/stream")
async def event_stream(after: int = 0, me: Principal = Me, plat: Any = Plat) -> StreamingResponse:
    """Server-sent events from ``after`` onward; reconnect with the last id seen."""
    plat.webhooks.events(me, after=after, limit=1)          # authorization first

    async def stream() -> Any:
        cursor = after
        for _ in range(7200):
            rows = await asyncio.to_thread(plat.webhooks.events, me, after=cursor, limit=200)
            for e in rows:
                cursor = e["seq"]
                yield f"id: {cursor}\nevent: {e['type']}\ndata: {json.dumps(e, default=str)}\n\n"
            await asyncio.sleep(0.5 if rows else 2.0)
    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/webhooks")
def webhooks(me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.webhooks.list(me))


@router.post("/webhooks", status_code=201)
def create_webhook(body: s.WebhookIn, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.webhooks.create(me, **body.model_dump()), 201)


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    plat.webhooks.delete(me, webhook_id)
    return ok({"ok": True})


@router.get("/webhooks/{webhook_id}/deliveries")
def deliveries(webhook_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(plat.webhooks.deliveries(me, webhook_id))


@router.post("/webhooks/{webhook_id}/ping")
async def ping(webhook_id: str, me: Principal = Me, plat: Any = Plat) -> Response:
    return ok(await asyncio.to_thread(plat.webhooks.ping, me, webhook_id))
