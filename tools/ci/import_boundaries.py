"""Gates 4 and 5 — the two import boundaries (§13, §14, §16).

* Nothing outside ``maya.persistence`` imports ``sqlalchemy``.
* Nothing under ``maya.web`` imports any ``maya`` module except the SDK
  (plus the version and error modules the SDK itself re-exports).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import sys

from _common import imports_of, module_name, python_files, report

WEB_ALLOWED = ("maya.sdk", "maya.core.version", "maya.core.errors")


def main() -> int:
    failures = []
    for path in python_files():
        mod = module_name(path)
        for name, line in imports_of(path):
            if name.split(".")[0] == "sqlalchemy" and not mod.startswith("maya.persistence") \
                    and not mod.startswith("tools."):
                failures.append(f"{mod}:{line} imports sqlalchemy outside maya.persistence")
            if mod.startswith("maya.web") and name.startswith("maya") and \
                    not name.startswith(WEB_ALLOWED + ("maya.web",)):
                failures.append(f"{mod}:{line} imports {name}; maya.web may use only maya.sdk")
    return report("import boundaries (persistence, web→sdk)", failures)


if __name__ == "__main__":
    sys.exit(main())
