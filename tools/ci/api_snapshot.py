"""Gate 19 — the API contract against a committed snapshot (plan §7).

The snapshot (``tools/ci/openapi.lock.json``) is a projection of the generated
OpenAPI document onto the contract alone: each operation's parameters (name,
place, required, type) and request/response bodies, and each schema's fields,
types and required list. Descriptions and titles are left out, so rewording a
docstring changes nothing; changing what a client sends or receives does.

A difference fails the gate and names it. Changing the contract is a decision:
``python tools/ci/api_snapshot.py --update`` rewrites the snapshot, and the
diff is reviewed with the change.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from _common import ROOT, api_app, report

LOCK = ROOT / "tools" / "ci" / "openapi.lock.json"
DROP = {"description", "title", "summary", "examples", "example", "operationId", "tags"}


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip(v) for k, v in sorted(node.items()) if k not in DROP}
    if isinstance(node, list):
        return [_strip(v) for v in node]
    return node


def contract() -> dict[str, Any]:
    doc = api_app().openapi()
    return {
        "paths": _strip(doc.get("paths", {})),
        "schemas": _strip(doc.get("components", {}).get("schemas", {})),
    }


def _diff(old: Any, new: Any, where: str = "") -> list[str]:
    if isinstance(old, dict) and isinstance(new, dict):
        out = [f"removed {where}/{k}" for k in sorted(set(old) - set(new))]
        out += [f"added {where}/{k}" for k in sorted(set(new) - set(old))]
        for k in sorted(set(old) & set(new)):
            out += _diff(old[k], new[k], f"{where}/{k}")
        return out
    return [] if old == new else [f"changed {where}"]


def main(argv: list[str]) -> int:
    now = contract()
    if "--update" in argv:
        LOCK.write_text(json.dumps(now, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {LOCK.relative_to(ROOT)}")
        return 0
    if not LOCK.exists():
        return report("API contract snapshot", [f"{LOCK.name} is missing; run with --update"])
    changes = _diff(json.loads(LOCK.read_text(encoding="utf-8")), now)
    if changes:
        changes.append("if intended: python tools/ci/api_snapshot.py --update, and review")
    return report(
        "API contract snapshot",
        changes[:40] + ([f"... {len(changes) - 40} more"] if len(changes) > 40 else []),
    )


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
