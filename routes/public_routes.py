"""
MAYA — public pages and health probes.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reachable without a session. Everything behind them is not.
"""
from __future__ import annotations

import time

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from routes.base import Routes


class PublicRoutes(Routes):
    def register(self) -> None:
        started = time.time()

        @self.app.get("/", response_class=HTMLResponse, tags=["public"])
        def landing(request: Request):
            return self.page(request, "landing.html",
                             model_count=len(self.ctx["registry"].list()))

        content = self.ctx["content"]

        @self.app.get("/about", response_class=HTMLResponse, tags=["public"])
        def about(request: Request):
            return self.page(request, "about.html", topics=content.topics("about"))

        @self.app.get("/help", response_class=HTMLResponse, tags=["public"])
        def help_index(request: Request):
            """Cards, grouped by section, from the markdown on disk."""
            return self.page(request, "help.html", sections=content.sections("help"),
                             content_dir=str(content.root))

        @self.app.get("/help/{slug}", response_class=HTMLResponse, tags=["public"])
        def help_topic(request: Request, slug: str):
            topic = content.get("help", slug)
            if topic is None:
                return self.page(request, "not_found.html", status=404, name=f"help/{slug}")
            related = [t for t in content.topics("help") if t.section == topic.section]
            return self.page(request, "help_topic.html", topic=topic, related=related)

        @self.app.get("/health", tags=["health"])
        def health():
            return {"status": "healthy", "uptime_seconds": round(time.time() - started, 1),
                    "version": self.ctx["config"].get("app.version")}

        @self.app.get("/health/live", tags=["health"])
        def live():
            return {"status": "alive"}

        @self.app.get("/health/ready", tags=["health"])
        def ready():
            """Readiness includes the evidence chain: a broken chain means the
            assurance claims cannot be trusted, so the node is not ready."""
            chain = self.ctx["evidence"].verify_chain()
            return JSONResponse({"status": "ready" if chain["valid"] else "degraded",
                                 "evidence_chain": chain},
                                status_code=200 if chain["valid"] else 503)
