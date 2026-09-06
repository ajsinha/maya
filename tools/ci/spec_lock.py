"""
MAYA — the published API, and whether it changed without anybody saying so.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The interface is a contract with every engine and every client a bank writes
against it. A route renamed, a field dropped from a response, a body that
quietly gains a required key — each is a breaking change that no test here
would notice, because the suite calls the API the way the code currently spells
it.

So the shape of the API is written down. This regenerates it and compares; a
difference is not an error, it is a decision that has to be visible in the
review that makes it.

    python tools/ci/spec_lock.py            # check
    python tools/ci/spec_lock.py --update   # accept the current shape

`--update` is the whole point. The lock is not a wall, it is a diff nobody can
merge without reading.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "openapi.lock.json"
sys.path.insert(0, str(ROOT))


def shape() -> Dict[str, Any]:
    """The API's SHAPE: paths, methods, parameters, and body field names.

    Deliberately not the whole OpenAPI document. That document carries
    descriptions, examples and every schema title, so a reworded docstring
    would show up as an interface change and the gate would be noise within a
    week. What is locked is what a client would break on.
    """
    logging.disable(logging.CRITICAL)
    with tempfile.TemporaryDirectory() as tmp:
        config = Path(tmp) / "application.yaml"
        config.write_text(
            "app: {name: MAYA, version: '0.0.0', tagline: t, slogan: s}\n"
            f"database: {{url: 'sqlite:///{tmp}/maya.db'}}\n"
            f"data: {{dir: '{tmp}/data'}}\n"
            "logging: {level: CRITICAL}\n")
        os.environ["MAYA_CONFIG"] = str(config)

        from core.config import PropertiesConfigurator
        from run_maya_web import create_app

        PropertiesConfigurator.reset()
        app = create_app(PropertiesConfigurator(str(config), reload_interval=0))
        document = app.openapi()

    paths: Dict[str, Any] = {}
    for path, methods in sorted(document.get("paths", {}).items()):
        entry: Dict[str, Any] = {}
        for method, operation in sorted(methods.items()):
            entry[method] = {
                "parameters": sorted(
                    f"{p.get('in')}:{p.get('name')}"
                    + ("!" if p.get("required") else "")
                    for p in operation.get("parameters", [])),
                "body": _body(document, operation),
                "responses": sorted(operation.get("responses", {})),
            }
        paths[path] = entry
    return {"openapi": document.get("openapi"), "paths": paths}


def _body(document: Dict[str, Any], operation: Dict[str, Any]) -> List[str]:
    """The request body's field names, with `!` on the required ones.

    Names and requiredness only. A type widened from `int` to `float` does not
    break a client; a field appearing in the required list does.
    """
    content = ((operation.get("requestBody") or {}).get("content") or {})
    for media in content.values():
        schema = media.get("schema") or {}
        ref = schema.get("$ref", "")
        if ref.startswith("#/components/schemas/"):
            schema = ((document.get("components") or {}).get("schemas") or {}
                      ).get(ref.rsplit("/", 1)[1], {})
        required = set(schema.get("required") or [])
        return sorted(f"{name}{'!' if name in required else ''}"
                      for name in (schema.get("properties") or {}))
    return []


def differences(locked: Dict[str, Any],
                current: Dict[str, Any]) -> List[str]:
    """Every way the two disagree, in the words somebody would use."""
    out: List[str] = []
    was, now = locked.get("paths", {}), current.get("paths", {})
    for path in sorted(set(was) - set(now)):
        out.append(f"REMOVED  {path} — every client calling it breaks")
    for path in sorted(set(now) - set(was)):
        out.append(f"added    {path}")
    for path in sorted(set(was) & set(now)):
        for method in sorted(set(was[path]) - set(now[path])):
            out.append(f"REMOVED  {method.upper()} {path}")
        for method in sorted(set(now[path]) - set(was[path])):
            out.append(f"added    {method.upper()} {path}")
        for method in sorted(set(was[path]) & set(now[path])):
            before, after = was[path][method], now[path][method]
            for field in ("parameters", "body", "responses"):
                gone = sorted(set(before[field]) - set(after[field]))
                fresh = sorted(set(after[field]) - set(before[field]))
                if gone:
                    out.append(f"REMOVED  {method.upper()} {path} {field}: "
                               f"{', '.join(gone)}")
                if fresh:
                    out.append(f"added    {method.upper()} {path} {field}: "
                               f"{', '.join(fresh)}")
    return out


def main() -> int:
    current = shape()
    if "--update" in sys.argv:
        LOCK.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n")
        print(f"locked {len(current['paths'])} paths into {LOCK.name}")
        return 0

    if not LOCK.exists():
        print(f"{LOCK.name} does not exist. Run with --update to create it.")
        return 1

    changes = differences(json.loads(LOCK.read_text()), current)
    if not changes:
        print(f"the API matches {LOCK.name}: {len(current['paths'])} paths")
        return 0

    print(f"the API has changed and {LOCK.name} has not:\n")
    for line in changes:
        print(f"    {line}")
    print("\nEvery line above is a change a client would see. If they are "
          "intended, run `python tools/ci/spec_lock.py --update` and commit the "
          "lock with them, so the diff appears in the review that made them.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
