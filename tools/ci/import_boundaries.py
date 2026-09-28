"""Gates 4 and 5 — the two import boundaries (§13, §14, §16).

* Nothing outside ``maya.persistence`` imports ``sqlalchemy``.
* Application code reaches the database only through the unit of work
  (``maya.persistence.session``), the engine factory (``maya.persistence.engine``)
  and the external-source reader (``maya.persistence.external``), plus the two whole-schema
  operations (``estate`` and ``purge``) exposed as single functions — never the ORM
  models, the schema, a session, an engine or table metadata.
* Nothing under ``maya.web`` imports any ``maya`` module except the SDK
  (plus the version and error modules the SDK itself re-exports).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
import sys

from _common import imports_of, module_name, python_files, report

WEB_ALLOWED = ("maya.sdk", "maya.core.version", "maya.core.errors")
PERSISTENCE_API = (
    "maya.persistence.session",
    "maya.persistence.engine",
    "maya.persistence.external",
    "maya.persistence.estate",
    "maya.persistence.purge",  # like the estate: a whole-schema operation behind one function
)
LEAKS = re.compile(
    r"\buow\.session\b|\.db\.engine\b|\bBase\.metadata\b|"
    r"(?<!request)\.session\.(execute|scalars|query|get|add|flush|commit)\("
)


def main() -> int:
    failures = []
    for path in python_files():
        mod = module_name(path)
        for name, line in imports_of(path):
            if (
                name.split(".")[0] == "sqlalchemy"
                and not mod.startswith("maya.persistence")
                and not mod.startswith("tools.")
            ):
                failures.append(f"{mod}:{line} imports sqlalchemy outside maya.persistence")
            if (
                name.startswith("maya.persistence")
                and not mod.startswith(("maya.persistence", "tools."))
                and not (name in ("maya.persistence",) or name.startswith(PERSISTENCE_API))
            ):
                failures.append(
                    f"{mod}:{line} imports {name}; application code may use only "
                    "the unit of work, the engine factory and the external reader"
                )
            if (
                mod.startswith("maya.web")
                and name.startswith("maya")
                and not name.startswith(WEB_ALLOWED + ("maya.web",))
            ):
                failures.append(f"{mod}:{line} imports {name}; maya.web may use only maya.sdk")
        if mod.startswith("maya.") and not mod.startswith("maya.persistence"):
            for n, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if LEAKS.search(text):
                    failures.append(f"{mod}:{n} reaches past the unit of work: {text.strip()}")
    return report("import boundaries (persistence, web→sdk)", failures)


if __name__ == "__main__":
    sys.exit(main())
