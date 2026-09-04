"""
MAYA — health and readiness endpoints.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.
"""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import JSONResponse


class HealthRoutes:
    """Unauthenticated probes, so a load balancer can reach them freely."""

    def __init__(self, app: FastAPI, ctx: Dict[str, Any]):
        self.app, self.ctx = app, ctx
        self._started = time.time()
        self._register()

    def _register(self) -> None:
        @self.app.get("/health", tags=["health"])
        def health():
            return {"status": "healthy", "uptime_seconds": round(time.time() - self._started, 1),
                    "version": self.ctx["config"].get("app.version")}

        @self.app.get("/health/live", tags=["health"])
        def live():
            return {"status": "alive"}

        @self.app.get("/health/ready", tags=["health"])
        def ready():
            """Readiness includes the evidence chain: a broken chain means the
            assurance claims cannot be trusted, so the node is not ready."""
            chain = self.ctx["evidence"].verify_chain()
            body = {"status": "ready" if chain["valid"] else "degraded", "evidence_chain": chain}
            return JSONResponse(body, status_code=200 if chain["valid"] else 503)
