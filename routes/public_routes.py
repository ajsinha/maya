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

        # Two content areas, one renderer. Adding a third is a directory and a
        # dictionary entry, not another pair of routes.
        AREAS = {
            "help": {
                "kicker": "HELP", "heading": "Documentation",
                "title": "Help", "path": "/help",
                "blurb": ("Everything below is available over the API; nothing "
                          "requires this interface. These pages are markdown files "
                          "under content/help/, rendered at request time \u2014 so they "
                          "are versioned, reviewable in a pull request alongside the "
                          "behaviour they describe, and cannot drift from the release "
                          "that shipped them."),
            },
            "tutorials": {
                "kicker": "TUTORIALS", "heading": "Working through MAYA",
                "title": "Tutorials", "path": "/tutorials",
                "blurb": ("Worked walkthroughs, end to end and with real calls: "
                          "registering a model and taking it through attestation, "
                          "storing artifacts, running several versions at once, "
                          "building a point-in-time feature set, and writing a "
                          "warrant for each family of model a bank runs."),
            },
        }

        def area_context(area: str) -> dict:
            meta = AREAS[area]
            return {"area": area, "area_kicker": meta["kicker"],
                    "area_heading": meta["heading"], "area_title": meta["title"],
                    "area_path": meta["path"], "area_blurb": meta["blurb"]}

        def index(request: Request, area: str):
            return self.page(request, "help.html", sections=content.sections(area),
                             content_dir=str(content.root), **area_context(area))

        def topic(request: Request, area: str, slug: str):
            found = content.get(area, slug)
            if found is None:
                return self.page(request, "not_found.html", status=404,
                                 name=f"{area}/{slug}")
            related = [t for t in content.topics(area) if t.section == found.section]
            return self.page(request, "help_topic.html", topic=found, related=related,
                             **area_context(area))

        @self.app.get("/help", response_class=HTMLResponse, tags=["public"])
        def help_index(request: Request):
            """Cards, grouped by section, from the markdown on disk."""
            return index(request, "help")

        @self.app.get("/help/{slug}", response_class=HTMLResponse, tags=["public"])
        def help_topic(request: Request, slug: str):
            return topic(request, "help", slug)

        @self.app.get("/tutorials", response_class=HTMLResponse, tags=["public"])
        def tutorials_index(request: Request):
            return index(request, "tutorials")

        @self.app.get("/tutorials/{slug}", response_class=HTMLResponse, tags=["public"])
        def tutorial(request: Request, slug: str):
            return topic(request, "tutorials", slug)

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
