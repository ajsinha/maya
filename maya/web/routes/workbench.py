"""
Workbench (§16.2): the feature designer, the upload wizard with schema
inference, ingest (a knowledge-time batch; restatements append), live draft
preview with the fill report, the zero-ceremony quick feature, and the
feature set builder.

The upload wizard holds the uploaded bytes between "propose" and "confirm"
in a short-lived in-process stash (single-process web tier; a clustered
deployment would re-upload at confirm).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import secrets
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from maya.core.errors import ValidationFailed
from maya.web.routes.common import action, client, flash, page, parse_json, render

router = APIRouter()
_STASH: dict[str, tuple[float, bytes, str, str]] = {}
STASH_SECONDS = 1800
TYPES = ["float64", "float32", "int64", "int32", "decimal(18,6)", "bool", "string", "date",
         "timestamp", "list<float64>", "fixed_vector<float64,8>", "tensor<float64,[8,12]>"]
CALENDARS = ["natural_days", "ISO_business_days", "NYSE", "LSE", "TARGET"]
OPERATORS = ["project", "rename", "transform", "union", "intersect", "difference", "compose",
             "coalesce", "aggregate", "lag", "resample", "case"]


def _stash(data: bytes, fmt: str, filename: str) -> str:
    now = time.monotonic()
    for k in [k for k, v in _STASH.items() if now - v[0] > STASH_SECONDS]:
        _STASH.pop(k, None)
    key = secrets.token_urlsafe(12)
    _STASH[key] = (now, data, fmt, filename)
    return key


async def _catalog_refs(sdk: Any) -> list[str]:
    refs = []
    for f in await sdk.features.list():
        if f.get("latest_version"):
            refs.append(f"maya://feature/{f['namespace']}/{f['name']}@v{f['latest_version']}")
    return refs


def _ctx(namespaces: list[dict[str, Any]], refs: list[str]) -> dict[str, Any]:
    return {"namespaces": namespaces, "refs": refs, "types": TYPES, "calendars": CALENDARS,
            "operators": OPERATORS}


@router.get("/workbench")
@page
async def workbench(request: Request) -> Any:
    async with client(request) as sdk:
        drafts = [f for f in await sdk.features.list() if f["latest_state"] in
                  ("draft", "changes_requested")]
        sets = [s for s in await sdk.featuresets.list() if s["latest_state"] in
                ("draft", "changes_requested")]
    return await render(request, "workbench/index.html", {"drafts": drafts, "sets": sets})


# -- feature designer ------------------------------------------------------------------
def licence_from_form(data: Any) -> dict[str, Any] | None:
    """The vendor terms block (§29.6); None when the designer left it empty."""
    lic: dict[str, Any] = {}
    for key in ("vendor", "redistribution", "derived_works", "notes"):
        if (data.get(f"licence_{key}") or "").strip():
            lic[key] = data[f"licence_{key}"].strip()
    population = [g.strip() for g in (data.get("licence_population") or "").split(",")
                  if g.strip()]
    if population:
        lic["population"] = population
    if (data.get("licence_retention_days") or "").strip():
        lic["retention_days"] = int(data["licence_retention_days"])
    return lic or None


def definition_from_form(data: Any) -> dict[str, Any]:
    """Build a feature definition from the designer's structured controls."""
    definition = _definition_body(data)
    licence = licence_from_form(data)
    if licence:
        definition["licence"] = licence
    return definition


def _definition_body(data: Any) -> dict[str, Any]:
    mode = data.get("mode", "source")
    if mode == "extends":
        return {"extends": {"parent": data.get("parent", "").strip(),
                            "binding": data.get("binding", "pinned"),
                            "override": parse_json(data.get("override"), "Override", {})}}
    index = [n.strip() for n in data.getlist("index_name") if n.strip()]
    index_types = dict(zip(index, data.getlist("index_type")))
    schema, rules = [], {}
    for name, typ, unit, tag, rule in zip(data.getlist("attr_name"), data.getlist("attr_type"),
                                          data.getlist("attr_unit"), data.getlist("attr_tag"),
                                          data.getlist("attr_rule")):
        if not name.strip():
            continue
        attr = {"name": name.strip(), "type": typ.strip() or "float64"}
        if unit.strip():
            attr["unit"] = unit.strip()
        if tag.strip():
            attr["tag"] = tag.strip()
        schema.append(attr)
        if rule.strip():
            rules[name.strip()] = rule.strip()
    grid = data.get("grid") or "as_is"
    resolution: dict[str, Any] = {"grid": grid if grid == "as_is" else {"calendar": grid},
                                  "rules": rules}
    if data.get("default_rule", "").strip():
        resolution["default"] = data["default_rule"].strip()
    source: dict[str, Any] = {"type": data.get("source_type", "csv")}
    if data.get("knowledge_time_column", "").strip():
        source["knowledge_time_column"] = data["knowledge_time_column"].strip()
    if source["type"] == "delta":
        source["path"] = data.get("delta_path", "").strip()
    if source["type"] == "sql":
        source.update(connection=data.get("sql_connection", "").strip(),
                      query=data.get("sql_query", "").strip(),
                      params=parse_json(data.get("sql_params"), "SQL parameters", {}) or {})
    if mode == "derived":
        operands = [o.strip() for o in data.get("operands", "").splitlines() if o.strip()]
        source = {"type": "derived", "derivation": {
            "operator": data.get("operator", "union"), "operands": operands,
            "options": parse_json(data.get("options"), "Operator options", {})}}
    return {"index": index, "index_types": index_types, "schema": schema, "source": source,
            "resolution": resolution,
            "transform": parse_json(data.get("transform"), "Transform pipeline", []),
            "quality": parse_json(data.get("quality"), "Quality contract", [])}


@router.get("/workbench/features/new")
@page
async def designer_new(request: Request) -> Any:
    async with client(request) as sdk:
        ctx = _ctx(await sdk.namespaces.list(), await _catalog_refs(sdk))
    return await render(request, "workbench/designer.html", {**ctx, "d": {}, "f": None})


@router.post("/workbench/features/new")
@action
async def designer_create(request: Request) -> Any:
    data = await request.form()
    definition = definition_from_form(data)
    tags = [t.strip() for t in data.get("tags", "").split(",") if t.strip()]
    async with client(request) as sdk:
        await sdk.features.create(data["namespace"], data["name"], definition,
                                  description=data.get("description", ""), tags=tags)
    flash(request, "Feature created as draft v1. Ingest data, preview, then submit for review.",
          "success")
    return RedirectResponse(f"/workbench/features/{data['namespace']}/{data['name']}/edit",
                            status_code=303)


@router.get("/workbench/features/{ns}/{name}/edit")
@page
async def designer_edit(request: Request, ns: str, name: str) -> Any:
    async with client(request) as sdk:
        f = await sdk.features.get(f"{ns}/{name}")
        ctx = _ctx(await sdk.namespaces.list(), await _catalog_refs(sdk))
    draft = f["versions"][0] if f["versions"] else None
    return await render(request, "workbench/designer.html",
                        {**ctx, "f": f, "draft": draft, "d": (draft or {}).get("definition", {})})


@router.post("/workbench/features/{ns}/{name}/edit")
@action
async def designer_save(request: Request, ns: str, name: str) -> Any:
    data = await request.form()
    definition = definition_from_form(data)
    tags = [t.strip() for t in data.get("tags", "").split(",") if t.strip()]
    expected = int(data["row_version"]) if data.get("row_version") else None
    async with client(request) as sdk:
        await sdk.features.update_draft(f"{ns}/{name}", definition, expected_version=expected,
                                        description=data.get("description"), tags=tags)
        if data.get("then") == "submit":
            f = await sdk.features.get(f"{ns}/{name}")
            out = await sdk.features.transition(f"{ns}/{name}", f["versions"][0]["version_no"],
                                                "submit")
            flash(request, out["message"], "success")
            return RedirectResponse(f"/catalog/features/{ns}/{name}", status_code=303)
    flash(request, "Draft saved.", "success")
    return RedirectResponse(f"/workbench/features/{ns}/{name}/edit", status_code=303)


@router.get("/workbench/features/{ns}/{name}/preview")
@page
async def draft_preview(request: Request, ns: str, name: str) -> Any:
    async with client(request) as sdk:
        preview = await sdk.features.draft_preview(
            f"{ns}/{name}", as_of_known=request.query_params.get("as_of_known") or None)
    return await render(request, "workbench/preview.html", {
        "title": f"{ns}/{name} — draft preview", "preview": preview, "preview_error": None,
        "back": f"/workbench/features/{ns}/{name}/edit"})


# -- ingest -------------------------------------------------------------------------------
@router.get("/workbench/features/{ns}/{name}/ingest")
@page
async def ingest_page(request: Request, ns: str, name: str) -> Any:
    async with client(request) as sdk:
        f = await sdk.features.get(f"{ns}/{name}")
    return await render(request, "workbench/ingest.html", {"f": f})


@router.post("/workbench/features/{ns}/{name}/ingest")
@action
async def ingest(request: Request, ns: str, name: str) -> Any:
    data = await request.form()
    upload = data.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        raise ValidationFailed("Choose a file to ingest")
    content = await upload.read()
    async with client(request) as sdk:
        out = await sdk.features.ingest(f"{ns}/{name}", content, fmt=data.get("fmt", "csv"),
                                        filename=upload.filename,
                                        knowledge_time=data.get("knowledge_time") or None,
                                        note=data.get("note", ""))
    msg = f"Ingested {out['rows']} row(s) at knowledge time {out['knowledge_time']}."
    if out.get("restatement"):
        msg += " RESTATEMENT: these keys existed before; the old values stay reproducible."
    if out.get("duplicate_upload_of"):
        msg += f" Note: these exact bytes were uploaded before as '{out['duplicate_upload_of']}'."
    flash(request, msg, "warning" if out.get("restatement") else "success")
    return RedirectResponse(f"/catalog/features/{ns}/{name}", status_code=303)


# -- upload wizard ------------------------------------------------------------------------
@router.post("/workbench/features/{ns}/{name}/pull")
@action
async def pull(request: Request, ns: str, name: str) -> Any:
    async with client(request) as sdk:
        out = await sdk.features.pull(f"{ns}/{name}")
    flash(request, f"Pulled {out['rows']} row(s) from the source"
                   + (" — a restatement: earlier values stay resolvable as of earlier knowledge"
                      if out["restatement"] else "."), "success")
    return RedirectResponse(f"/workbench/features/{ns}/{name}/ingest", status_code=303)


@router.get("/workbench/upload")
@page
async def upload_page(request: Request) -> Any:
    return await render(request, "workbench/upload.html", {"proposal": None})


@router.post("/workbench/upload")
@action
async def upload_propose(request: Request) -> Any:
    data = await request.form()
    upload = data.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        raise ValidationFailed("Choose a file to upload")
    content = await upload.read()
    fmt = data.get("fmt", "csv")
    async with client(request) as sdk:
        proposal = await sdk.features.infer(content, fmt=fmt, filename=upload.filename)
        namespaces = await sdk.namespaces.list()
    key = _stash(content, fmt, upload.filename)
    stem = upload.filename.rsplit(".", 1)[0].replace("-", "_").replace(" ", "_").lower()
    return await render(request, "workbench/upload.html", {
        "proposal": proposal, "key": key, "fmt": fmt, "stem": stem, "namespaces": namespaces,
        "types": TYPES, "calendars": CALENDARS})


@router.post("/workbench/upload/confirm")
@action
async def upload_confirm(request: Request) -> Any:
    data = await request.form()
    stashed = _STASH.get(data.get("key", ""))
    if stashed is None:
        raise ValidationFailed("The upload expired; upload the file again")
    _, content, fmt, filename = stashed
    definition = definition_from_form(data)
    async with client(request) as sdk:
        await sdk.features.create(data["namespace"], data["name"], definition,
                                  description=data.get("description", ""))
        out = await sdk.features.ingest(f"{data['namespace']}/{data['name']}", content, fmt=fmt,
                                        filename=filename,
                                        knowledge_time=data.get("knowledge_time") or None)
    _STASH.pop(data.get("key", ""), None)
    flash(request, f"Feature created and {out['rows']} row(s) ingested. Preview, then submit.",
          "success")
    return RedirectResponse(f"/catalog/features/{data['namespace']}/{data['name']}",
                            status_code=303)


# -- quick feature ---------------------------------------------------------------------------
@router.get("/workbench/quick")
@page
async def quick_page(request: Request) -> Any:
    return await render(request, "workbench/quick.html")


@router.post("/workbench/quick")
@action
async def quick(request: Request) -> Any:
    data = await request.form()
    upload = data.get("file")
    if upload is None or not getattr(upload, "filename", ""):
        raise ValidationFailed("Choose a CSV to turn into a feature")
    content = await upload.read()
    async with client(request) as sdk:
        out = await sdk.features.quick(content, data["name"], fmt=data.get("fmt", "csv"))
    ns = out["ref"].split("://", 1)[1].split("/")[1]
    flash(request, f"{out['ref']} is typed, resolvable and shareable ({out['rows']} rows). "
                   "It is ungoverned until you promote it.", "success")
    return RedirectResponse(f"/catalog/features/{ns}/{data['name']}", status_code=303)


# -- feature set builder ------------------------------------------------------------------------
def fs_definition_from_form(data: Any) -> dict[str, Any]:
    if data.get("mode") == "extends":
        return {"extends": {"parent": data.get("parent", "").strip(),
                            "binding": data.get("binding", "pinned"),
                            "override": parse_json(data.get("override"), "Override", {})}}
    members = []
    for attr, ref, src, cast, rule in zip(data.getlist("m_attr"), data.getlist("m_ref"),
                                          data.getlist("m_source"), data.getlist("m_cast"),
                                          data.getlist("m_rule")):
        if attr.strip():
            members.append({"attr": attr.strip(), "ref": ref.strip(), "source_attr": src.strip(),
                            "cast": cast.strip() or None, "rule": rule.strip() or None})
    grid = data.get("grid") or "as_is"
    alignment: dict[str, Any] = {"mode": data.get("align_mode", "inner")}
    if alignment["mode"] == "left":
        alignment["member"] = data.get("align_member", "").strip()
    if alignment["mode"] == "asof":
        alignment.update(tolerance_days=int(data.get("tolerance_days") or 5),
                         direction=data.get("asof_direction", "backward"))
    filters = {k: data.get(k).strip() for k in ("start", "end", "expr") if data.get(k, "").strip()}
    universe = [u.strip() for u in data.get("universe", "").split(",") if u.strip()]
    if universe:
        filters["universe"] = universe
    gp: dict[str, Any] = {"rules": parse_json(data.get("global_rules"), "Global rules", {})}
    if data.get("global_default", "").strip():
        gp["default"] = data["global_default"].strip()
    return {"index": [c.strip() for c in data.get("index", "").split(",") if c.strip()],
            "grid": grid if grid == "as_is" else {"calendar": grid}, "alignment": alignment,
            "filters": filters, "global_policy": gp,
            "group_policies": parse_json(data.get("group_policies"), "Group policies", []),
            "members": members}


@router.get("/workbench/featuresets/new")
@page
async def fs_new(request: Request) -> Any:
    async with client(request) as sdk:
        ctx = _ctx(await sdk.namespaces.list(), await _catalog_refs(sdk))
    return await render(request, "workbench/fs_builder.html", {**ctx, "d": {}, "fs": None})


@router.post("/workbench/featuresets/new")
@action
async def fs_create(request: Request) -> Any:
    data = await request.form()
    async with client(request) as sdk:
        await sdk.featuresets.create(data["namespace"], data["name"],
                                     fs_definition_from_form(data),
                                     description=data.get("description", ""))
    flash(request, "Feature set created as draft v1.", "success")
    return RedirectResponse(f"/workbench/featuresets/{data['namespace']}/{data['name']}/edit",
                            status_code=303)


@router.get("/workbench/featuresets/{ns}/{name}/edit")
@page
async def fs_edit(request: Request, ns: str, name: str) -> Any:
    async with client(request) as sdk:
        fs = await sdk.featuresets.get(f"{ns}/{name}")
        ctx = _ctx(await sdk.namespaces.list(), await _catalog_refs(sdk))
    draft = fs["versions"][0] if fs["versions"] else None
    return await render(request, "workbench/fs_builder.html",
                        {**ctx, "fs": fs, "draft": draft, "d": (draft or {}).get("definition", {})})


@router.post("/workbench/featuresets/{ns}/{name}/edit")
@action
async def fs_save(request: Request, ns: str, name: str) -> Any:
    data = await request.form()
    async with client(request) as sdk:
        await sdk.featuresets.update_draft(f"{ns}/{name}", fs_definition_from_form(data))
        if data.get("then") == "submit":
            fs = await sdk.featuresets.get(f"{ns}/{name}")
            out = await sdk.featuresets.transition(f"{ns}/{name}",
                                                   fs["versions"][0]["version_no"], "submit")
            flash(request, out["message"], "success")
            return RedirectResponse(f"/catalog/featuresets/{ns}/{name}", status_code=303)
    flash(request, "Draft saved.", "success")
    return RedirectResponse(f"/workbench/featuresets/{ns}/{name}/edit", status_code=303)


@router.get("/workbench/featuresets/{ns}/{name}/preview")
@page
async def fs_preview(request: Request, ns: str, name: str) -> Any:
    async with client(request) as sdk:
        preview = await sdk.featuresets.draft_preview(f"{ns}/{name}")
    return await render(request, "workbench/preview.html", {
        "title": f"{ns}/{name} — feature set draft preview", "preview": preview,
        "preview_error": None, "back": f"/workbench/featuresets/{ns}/{name}/edit"})
