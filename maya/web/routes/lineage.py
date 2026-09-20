"""
The lineage and algebra canvas (§16.3): the page, the graph the canvas draws,
and the two small JSON endpoints its own script calls.

The graph itself comes from one SDK call. Everything the canvas needs *about*
a node — owner, state, namespace, when it last changed — comes from the
catalog browse the canvas would otherwise have to guess at, fetched once per
(type, namespace) pair present in the graph rather than once per node. Cost is
not in that payload: pricing a node means reading its pins, so it is a
separate call the canvas makes only when somebody asks for the cost overlay.

``GET /lineage`` leaves out what the caller may not read and counts it in
``hidden``. The canvas draws that count rather than quietly showing a smaller
graph, because a lineage picture that silently omits half the estate is worse
than no picture at all.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from maya.core.errors import MayaError
from maya.web.routes.common import api_json, client, page, render

router = APIRouter()

CATALOG_KINDS = ("feature", "featureset", "model")
BROWSE_CALLS = 12  # (type, namespace) pairs priced into one draw; beyond it, meta thins out
PRICED_NODES = 40  # objects the cost overlay reads pins for in one request


def bare(ref: str) -> str:
    """The object a node names, without its version or pin: the key ``meta`` is filed by."""
    return ref.split("@")[0].split("#")[0]


def parts(ref: str) -> tuple[str, str] | None:
    """``(kind, namespace)`` for a catalog object reference, else None."""
    if not ref.startswith("maya://"):
        return None
    path = bare(ref)[len("maya://") :].split("/")
    if len(path) != 3 or path[0] not in CATALOG_KINDS:
        return None
    return path[0], path[1]


def _pairs(nodes: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """The (type, namespace) pairs the graph touches, in a stable order."""
    seen: list[tuple[str, str]] = []
    for node in nodes:
        pair = parts(str(node.get("id", "")))
        if pair and pair not in seen:
            seen.append(pair)
    return seen


def _meta_of(row: dict[str, Any]) -> dict[str, Any]:
    """What the canvas shows about an object: enough to filter, colour and hover."""
    return {
        "type": row.get("type"),
        "name": row.get("name"),
        "namespace": row.get("namespace"),
        "owner": row.get("owner"),
        "state": row.get("latest_state"),
        "latest_version": row.get("latest_version"),
        "updated": row.get("updated_at"),
        "change_class": row.get("change_class"),
        "needs_reapproval": row.get("needs_reapproval"),
        "url": row.get("url"),
        "description": row.get("description"),
    }


async def graph(sdk: Any, root: str, direction: str, depth: int) -> dict[str, Any]:
    """The lineage graph plus per-node catalog metadata, for one draw of the canvas."""
    g = await sdk.access.lineage(root, direction=direction, depth=depth)
    wanted = {bare(str(n["id"])) for n in g["nodes"]}
    pairs = _pairs(g["nodes"])
    listings = await asyncio.gather(
        *(sdk.catalog.browse(type=t, namespace=ns) for t, ns in pairs[:BROWSE_CALLS]),
        return_exceptions=True,
    )
    meta: dict[str, Any] = {}
    for rows in listings:
        if isinstance(rows, BaseException):
            continue  # a namespace that went away between the walk and the browse
        for row in rows:
            if row.get("ref") in wanted:
                meta[row["ref"]] = _meta_of(row)
    return {
        **g,
        "direction": direction,
        "depth": depth,
        "meta": meta,
        "meta_complete": len(pairs) <= BROWSE_CALLS,
    }


@router.get("/lineage")
@page
async def lineage_page(request: Request) -> Any:
    qp = request.query_params
    return await render(
        request,
        "lineage.html",
        {
            "root": qp.get("root", ""),
            "direction": qp.get("direction", "both"),
            "depth": qp.get("depth", "3"),
        },
    )


@router.get("/ui/lineage")
@api_json
async def lineage_json(request: Request) -> Any:
    qp = request.query_params
    async with client(request) as sdk:
        return await graph(
            sdk, qp.get("root", ""), qp.get("direction", "both"), int(qp.get("depth", "3"))
        )


async def _price(sdk: Any, ref: str) -> dict[str, Any]:
    """What this object's sealed pins occupy. A feature set's pins come with its
    record; a feature's come a page at a time, so only the first page is summed and
    the answer says when there are more."""
    kind = (parts(ref) or ("", ""))[0]
    if kind == "feature":
        obj = await sdk.features.get(ref)
        pins, total = obj.get("pins") or [], obj.get("pins_total")
    elif kind == "featureset":
        obj = await sdk.featuresets.get(ref)
        pins = obj.get("pins") or []
        total = len(pins)
    else:
        return {"ref": ref, "bytes": None, "note": "nothing is pinned against this kind"}
    sealed = [p for p in pins if p.get("state") == "sealed"]
    return {
        "ref": ref,
        "bytes": sum(int(p.get("bytes_total") or 0) for p in sealed),
        "pins": len(sealed),
        "partial": bool(total and total > len(pins)),
    }


@router.get("/ui/lineage/cost")
@api_json
async def lineage_cost(request: Request) -> Any:
    """The cost overlay (§16.3): what each object in the drawn graph has pinned."""
    refs, seen = [], set()
    for raw in (request.query_params.get("refs") or "").split(","):
        ref = bare(raw.strip())
        if ref and ref not in seen and parts(ref):
            seen.add(ref)
            refs.append(ref)
    async with client(request) as sdk:
        priced = await asyncio.gather(
            *(_price(sdk, r) for r in refs[:PRICED_NODES]), return_exceptions=True
        )
    items = {p["ref"]: p for p in priced if isinstance(p, dict)}
    unreadable = [
        r for r, p in zip(refs, priced) if isinstance(p, MayaError)
    ]  # priced later, or never: either way it is named, not hidden
    return {
        "items": items,
        "unpriced": unreadable,
        "over_limit": max(0, len(refs) - PRICED_NODES),
    }


__all__ = ["router"]
