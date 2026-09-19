"""
Helpers for the API contract tests: every endpoint from the OpenAPI document, a
concrete path for it, and a minimal body that passes schema validation — so a
test reaches the handler and exercises authorization, not just the body parser.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import re
from typing import Any

PREFIX = "/api/v1"
UNKNOWN_ID = "0" * 32
FILL = {"namespace": "nosuchns", "name": "nosuch", "version_no": "999",
        "transition": "submit", "object_type": "feature_version"}


def endpoints(app: Any) -> list[tuple[str, str, dict[str, Any]]]:
    """(METHOD, templated path, operation) for every versioned endpoint."""
    out = []
    for path, ops in app.openapi()["paths"].items():
        if path.startswith(PREFIX):
            for method, op in ops.items():
                out.append((method.upper(), path, op))
    return sorted(out, key=lambda e: (e[1], e[0]))


def concrete(path: str, **over: str) -> str:
    return re.sub(r"\{(\w+)(?::path)?\}",
                  lambda m: over.get(m.group(1), FILL.get(m.group(1), UNKNOWN_ID)), path)


def _resolve(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        schema = components[schema["$ref"].rsplit("/", 1)[1]]
    if "anyOf" in schema:
        options = [s for s in schema["anyOf"] if s.get("type") != "null"]
        schema = _resolve(options[0], components) if options else {"type": "null"}
    if "allOf" in schema and len(schema["allOf"]) == 1:
        schema = _resolve(schema["allOf"][0], components)
    return schema


def sample(schema: dict[str, Any], components: dict[str, Any]) -> Any:
    """A minimal value satisfying ``schema``: required properties only."""
    schema = _resolve(schema, components)
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        props = schema.get("properties", {})
        return {k: sample(props[k], components) for k in schema.get("required", [])}
    return {"string": "x", "integer": 1, "number": 1.0, "boolean": False,
            "array": [], "null": None}.get(kind, "x")


def body_for(app: Any, op: dict[str, Any]) -> tuple[str, Any] | None:
    """("json", value) or ("multipart", files+data) for an operation's request body."""
    rb = op.get("requestBody")
    if not rb:
        return None
    components = app.openapi().get("components", {}).get("schemas", {})
    content = rb.get("content", {})
    if "application/json" in content:
        return "json", sample(content["application/json"]["schema"], components)
    form = content.get("multipart/form-data") or content.get(
        "application/x-www-form-urlencoded")
    schema = _resolve(form["schema"], components)
    files, data = {}, {}
    for key in schema.get("required", []):
        prop = _resolve(schema["properties"][key], components)
        if prop.get("format") == "binary" or prop.get("contentMediaType"):
            files[key] = ("f.csv", b"date,x\n2026-01-01,1\n", "text/csv")
        else:
            data[key] = str(sample(prop, components))
    return "multipart", {"files": files or None, "data": data}


def call(client: Any, app: Any, method: str, path: str, op: dict[str, Any],
         headers: dict[str, str] | None = None, *, with_body: bool = True, **over: str) -> Any:
    url = concrete(path, **over)
    body = body_for(app, op) if with_body else None
    if body is None:
        return client.request(method, url, headers=headers)
    kind, value = body
    if kind == "json":
        return client.request(method, url, headers=headers, json=value)
    return client.request(method, url, headers=headers, files=value["files"], data=value["data"])
