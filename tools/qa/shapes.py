"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The real shape of a request, read rather than guessed.

    python -m tools.qa.shapes POST /api/v1/monitors

Writing the hand-written cases was slow for a reason that had nothing to do
with the cases: every scenario discovered the request body by sending a wrong
one and reading the 422. `threshold` is a mapping and not a float, `claims`
are objects and not strings, a backup manifest's version key is
`manifest_version` — each of those cost a round trip, an edit and a re-run,
and each looked briefly like a defect.

`openapi.lock.json` records field NAMES. The live document records their
types, and the application will happily produce it. So this reads the schema
and builds a body that satisfies it, and a scenario that needs a valid request
asks for one instead of inventing it.

**A generated body is a starting point, not the case.** It carries
type-correct filler, which is exactly right for "does this operation answer"
and exactly wrong for "does this control fire" — a case about a control still
states its own values. What this removes is the tax of getting the twelve
uninteresting fields right.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any, Dict, Optional

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_DOCUMENT: Optional[Dict[str, Any]] = None


def document(client=None) -> Dict[str, Any]:
    """The live OpenAPI document, fetched once."""
    global _DOCUMENT
    if _DOCUMENT is not None:
        return _DOCUMENT
    if client is not None:
        got = client.get("/api/v1/openapi.json")
        if got.status_code < 400:
            _DOCUMENT = got.json()
            return _DOCUMENT
    from tools.qa.harness import live_client
    with live_client() as (_ui, api, _observer):
        _DOCUMENT = api.get("/api/v1/openapi.json").json()
    return _DOCUMENT


def _resolve(schema: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    """Follow a `$ref` to the component it names."""
    seen = 0
    while "$ref" in schema and seen < 10:
        pointer = schema["$ref"].lstrip("#/").split("/")
        target: Any = spec
        for step in pointer:
            target = target.get(step, {})
        schema = target
        seen += 1
    return schema


def example(schema: Dict[str, Any], spec: Dict[str, Any],
            depth: int = 0) -> Any:
    """A value that satisfies this schema.

    Deliberately boring. The point is to be *accepted*, so that a case can
    assert on the one field it cares about rather than on twelve it does not.
    """
    schema = _resolve(schema or {}, spec)
    if depth > 6:
        return None
    for combinator in ("anyOf", "oneOf", "allOf"):
        options = schema.get(combinator)
        if options:
            # The first non-null branch: `Optional[X]` renders as
            # `anyOf: [X, null]`, and choosing null would omit the field the
            # caller asked for.
            for option in options:
                resolved = _resolve(option, spec)
                if resolved.get("type") != "null":
                    return example(resolved, spec, depth + 1)
            return None
    if "default" in schema:
        return schema["default"]
    if schema.get("enum"):
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        out: Dict[str, Any] = {}
        required = set(schema.get("required") or [])
        for name, child in (schema.get("properties") or {}).items():
            if name in required or depth == 0:
                out[name] = example(child, spec, depth + 1)
        return out
    if kind == "array":
        return [example(schema.get("items") or {}, spec, depth + 1)]
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return "qa"


def body_for(method: str, path: str, client=None) -> Dict[str, Any]:
    """A body the endpoint will accept, built from its own schema."""
    spec = document(client)
    operation = (spec.get("paths", {}).get(path, {})
                 .get(method.lower(), {}))
    schema = (operation.get("requestBody", {})
              .get("content", {}).get("application/json", {})
              .get("schema"))
    if not schema:
        return {}
    made = example(schema, spec)
    return made if isinstance(made, dict) else {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("method")
    ap.add_argument("path")
    args = ap.parse_args(argv)
    print(json.dumps(body_for(args.method, args.path), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
