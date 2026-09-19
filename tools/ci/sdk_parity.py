"""Gate 15 — every public endpoint has an SDK method and every method an endpoint (SC-13).

The server's side is read from its generated OpenAPI document; the SDK's side
from the ``@endpoint`` registry in ``maya/sdk/resources.py``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import sys

from _common import report

PREFIX = "/api/v1"
UNVERSIONED = {"/healthz", "/readyz"}


def server_endpoints() -> set[tuple[str, str]]:
    from fastapi import FastAPI
    from maya.api.routers import admin, catalog, registry, workflow, workspaces
    app = FastAPI()
    for r in (admin.router, catalog.router, registry.router, workflow.router,
              workspaces.router):
        app.include_router(r, prefix=PREFIX)
    out = set()
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            out.add((method.upper(), path[len(PREFIX):] if path.startswith(PREFIX) else path))
    return out


def main() -> int:
    from maya.sdk.resources import ENDPOINTS
    server = server_endpoints()
    sdk = set(ENDPOINTS)
    failures = [f"endpoint {m} {p} has no SDK method" for m, p in sorted(server - sdk)]
    failures += [f"SDK method {ENDPOINTS[(m, p)]} calls {m} {p}, which the API does not have"
                 for m, p in sorted(sdk - server)]
    print(f"     {len(server)} endpoints, {len(sdk)} SDK methods")
    return report("SDK ↔ API parity", failures)


if __name__ == "__main__":
    sys.exit(main())
