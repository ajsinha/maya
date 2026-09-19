"""Gate 9 — no secret in the tracked config/application.yaml (§24.2).

Every key that names a password, secret, token or key must be empty or a
``${ENV:…}`` reference with an empty default.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
import sys

import yaml

from _common import ROOT, report

CONFIG = ROOT / "config" / "application.yaml"
SENSITIVE = re.compile(r"(password|secret|token|api_key|private_key)$", re.IGNORECASE)
SAFE = re.compile(r"^\$\{[A-Z0-9_]+:\}$")


def walk(node: object, prefix: str = ""):  # type: ignore[no-untyped-def]
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, f"{prefix}.{k}" if prefix else str(k))
    else:
        yield prefix, node


def main() -> int:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    failures = []
    for key, value in walk(data):
        leaf = key.rsplit(".", 1)[-1]
        if (
            SENSITIVE.search(leaf)
            and value not in (None, "")
            and not SAFE.match(str(value))
            and "allow_" not in leaf
            and "min_length" not in key
        ):
            failures.append(f"{key} carries a value in a tracked file")
    return report("no secrets in config/application.yaml", failures)


if __name__ == "__main__":
    sys.exit(main())
