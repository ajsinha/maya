"""
The lineage and algebra canvas (§16.3): the page, the graph the canvas draws,
and the JSON endpoint its own script calls.

One draw is two SDK calls: the graph, and then everything about its nodes.
``catalog.nodes`` answers per reference — owner, the state of the version that
node actually names, when the object changed, how fresh a feature's data is, and
what its sealed pins occupy — so the approval, freshness and cost overlays are
exact. The canvas used to browse the catalog once per (type, namespace) the graph
touched, up to a dozen calls, and still had to borrow the *latest* version's state
for a node naming an older one, and had no idea of data freshness at all.

``GET /lineage`` leaves out what the caller may not read and counts it in
``hidden``. The canvas draws that count rather than quietly showing a smaller
graph, because a lineage picture that silently omits half the estate is worse
than no picture at all. For the same reason the count is a count: a breakdown by
namespace would be a directory of the namespaces you are shut out of.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from maya.web.routes.common import api_json, client, page, render

router = APIRouter()

CATALOG_KINDS = ("feature", "featureset", "model")
NODE_LIMIT = 500  # nodes described in one draw; the service caps it at the same number


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


def catalog_refs(nodes: list[dict[str, Any]]) -> list[str]:
    """The catalog object references in a graph, deduplicated, in a stable order.

    A node is asked about by its *object* reference rather than its version: one query
    per object then answers for every version and pin of it that the graph draws, and the
    per-version state comes back keyed by the version the node names.
    """
    seen: list[str] = []
    for node in nodes:
        ref = bare(str(node.get("id", "")))
        if parts(ref) and ref not in seen:
            seen.append(ref)
    return seen


async def graph(sdk: Any, root: str, direction: str, depth: int) -> dict[str, Any]:
    """The lineage graph plus per-node metadata, for one draw of the canvas."""
    g = await sdk.access.lineage(root, direction=direction, depth=depth)
    refs = catalog_refs(g["nodes"])
    meta = await sdk.catalog.nodes(refs[:NODE_LIMIT]) if refs else {}
    return {
        **g,
        "direction": direction,
        "depth": depth,
        # Only what the caller may read is described; a withheld reference answers
        # {"hidden": true} and is dropped here, since the graph has already left it out.
        "meta": {ref: row for ref, row in meta.items() if not row.get("hidden")},
        "meta_complete": len(refs) <= NODE_LIMIT,
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


__all__ = ["router"]
