"""Gate 6 — a proxied package is imported only inside its own seam (§13.4.3).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import sys

from _common import imports_of, module_name, python_files, report

SEAMS = {
    "orjson": ("maya.core.djson",),
    "zstandard": ("maya.core.compress",),
    "psutil": ("maya.core.compress",),
    "argon2": ("maya.core.kdf",),
    "cryptography": ("maya.core.crypto", "maya.services.bundle"),
    "deltalake": ("maya_delta",),
    "duckdb": ("maya.core.pushdown",),
    "uvloop": ("maya.core.backends",),
    "opentelemetry": ("maya.observability.tracing",),
    "openpyxl": ("maya.formula.xlsx",),
    "anthropic": ("maya.assistant.claude",),
    "onelogin": ("maya.security.saml",),
    "xmlsec": ("maya.security.saml",),
    "webauthn": ("maya.security.passkeys",),
}


def main() -> int:
    failures = []
    for path in python_files():
        mod = module_name(path)
        for name, line in imports_of(path):
            top = name.split(".")[0]
            allowed = SEAMS.get(top)
            if allowed and not mod.startswith(allowed) and not mod.startswith("tools."):
                failures.append(f"{mod}:{line} imports '{top}' outside its seam {allowed}")
    return report("seam imports", failures)


if __name__ == "__main__":
    sys.exit(main())
