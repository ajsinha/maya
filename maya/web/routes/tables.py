"""
Server-side table pages (§16.7, §18.1): the JSON behind a table in server mode.

A table that can grow without bound renders its first page with the page and
fetches every later one here: ``GET /ui/table/<name>?page_size=&cursor=&sort=&q=``.
Rows come back as HTML rendered by the same macro in ``templates/_rows.html``
that drew the first page, so a row is defined once. Filters the page itself
applies (namespace, action, event type) travel in the table's source URL.

``TABLES`` is the registry; tools/ci/table_contract.py fails the build when a
template points a table at a name that is not in it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlencode

from fastapi import APIRouter, Request

from maya.core.errors import ValidationFailed
from maya.web.routes.common import TEMPLATES, api_json, client, csrf_token

router = APIRouter()
PAGE_SIZES = (25, 50, 100, 250, 1000)      # 1000: the CSV export's walk


@dataclass(frozen=True)
class Table:
    fetch: Callable[..., Any]               # (sdk, query params, **paging) -> awaitable page
    row: str                                # macro in templates/_rows.html
    sorts: dict[str, str]                   # column header -> server sort key
    default_sort: str
    filters: tuple[str, ...] = field(default=())
    needs_csrf: bool = False


def _opt(qp: Any, key: str) -> str | None:
    return qp.get(key) or None


TABLES: dict[str, Table] = {
    "features": Table(lambda sdk, qp, **kw: sdk.features.page(
        namespace=_opt(qp, "namespace"), q=_opt(qp, "q"), **kw),
        "feature_row", {"Name": "name", "Updated": "updated"}, "name", ("namespace",)),
    "featuresets": Table(lambda sdk, qp, **kw: sdk.featuresets.page(
        namespace=_opt(qp, "namespace"), q=_opt(qp, "q"), **kw),
        "featureset_row", {"Name": "name", "Updated": "updated"}, "name", ("namespace",)),
    "models": Table(lambda sdk, qp, **kw: sdk.models.page(
        namespace=_opt(qp, "namespace"), q=_opt(qp, "q"), **kw),
        "model_row", {"Name": "name", "Updated": "updated"}, "name", ("namespace",)),
    "audit": Table(lambda sdk, qp, **kw: sdk.admin.audit_page(
        q=_opt(qp, "q"), action=_opt(qp, "action"), **kw),
        "audit_row", {"#": "seq"}, "-seq", ("action",)),
    "events": Table(lambda sdk, qp, **kw: sdk.events.page(type=_opt(qp, "type"), **kw),
                    "event_row", {"Seq": "seq"}, "-seq", ("type",)),
    "jobs": Table(lambda sdk, qp, **kw: sdk.jobs.page(all=True, q=_opt(qp, "q"), **kw),
                  "job_row", {"Created": "created"}, "-created", needs_csrf=True),
}


def source(name: str, **filters: Any) -> str:
    """The data URL a page hands its table: the route plus the page's own filters."""
    kept = {k: v for k, v in filters.items() if v not in (None, "")}
    return f"/ui/table/{name}" + (f"?{urlencode(kept)}" if kept else "")


async def first_page(request: Request, sdk: Any, name: str, page_size: int = 25,
                     **filters: Any) -> dict[str, Any]:
    """What a page renders before any script runs: page one, with its total."""
    table = TABLES[name]
    page = await table.fetch(sdk, filters, page_size=page_size, sort=table.default_sort,
                             total=True)
    return {**page, "source": source(name, **filters), "sorts": table.sorts}


@router.get("/ui/table/{name}")
@api_json
async def table_page(request: Request, name: str) -> Any:
    table = TABLES.get(name)
    if table is None:
        raise ValidationFailed(f"No server-paged table named '{name}'")
    qp = request.query_params
    size = int(qp.get("page_size") or 25)
    if size not in PAGE_SIZES:
        raise ValidationFailed(f"page_size is one of {', '.join(map(str, PAGE_SIZES))}")
    async with client(request) as sdk:
        page = await table.fetch(sdk, qp, page_size=size, cursor=_opt(qp, "cursor"),
                                 sort=_opt(qp, "sort") or table.default_sort,
                                 total=qp.get("total") == "1")
    macro = getattr(TEMPLATES.env.get_template("_rows.html").module, table.row)
    extra = (csrf_token(request),) if table.needs_csrf else ()
    return {"rows": [str(macro(item, *extra)) for item in page["items"]],
            "next_cursor": page["next_cursor"], "total": page.get("total"),
            "sort": page["sort"], "page_size": page["page_size"]}
