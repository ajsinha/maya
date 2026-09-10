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

        # The OTHER area, so each index points at its sibling. The bar carries
        # Help and not Tutorials, which would otherwise leave six walkthroughs
        # reachable only by typing the URL — the same way eight screens were
        # unreachable until somebody went looking for them.
        SIBLING = {"help": "tutorials", "tutorials": "help"}

        def area_context(area: str) -> dict:
            meta = AREAS[area]
            other = AREAS[SIBLING[area]]
            return {"area": area, "area_kicker": meta["kicker"],
                    "area_heading": meta["heading"], "area_title": meta["title"],
                    "area_path": meta["path"], "area_blurb": meta["blurb"],
                    "sibling_title": other["title"], "sibling_path": other["path"],
                    "sibling_blurb": other["blurb"]}

        def index(request: Request, area: str):
            return self.page(request, "help.html", sections=content.sections(area),
                             content_dir=str(content.root), **area_context(area))

        def topic(request: Request, area: str, slug: str):
            found = content.get(area, slug)
            if found is None:
                return self.page(request, "not_found.html", http_status=404,
                                 what="help topic", identifier=f"{area}/{slug}",
                                 back_href="/help", back_label="Back to help")
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
            from db.table_backend import describe

            return {"status": "healthy",
                    "uptime_seconds": round(time.time() - started, 1),
                    "version": self.ctx["config"].get("app.version"),
                    # What holds the feature data: Delta or Iceberg, and for
                    # Delta which implementation is writing it — MAYA has its
                    # own for estates that forbid binary wheels. An operator
                    # should be able to ASK, rather than infer it from a
                    # start-up line that scrolled past a week ago.
                    "storage": describe(self.ctx.get("table_store"))}

        @self.app.get("/health/encryption", tags=["health"])
        def encryption():
            """What is actually encrypted, as opposed to what a checkbox claims.

            MAYA does not encrypt the database and does not pretend to:
            at-rest and in-transit encryption are the deployment's, and a
            platform shipping its own would be shipping a key-management
            decision nobody asked it to make. What it will not do is imply
            otherwise — every finding here is a setting that is not what a
            production instance should have.
            """
            from core.authz.datalayer import encryption_posture
            cfg = self.ctx["config"]
            return encryption_posture(
                https=cfg.get_bool("auth.session_https_only", False),
                cookie_secure=cfg.get_bool("auth.session_https_only", False),
                database_url=str(cfg.get("database.url", "")),
                session_secret_is_default=not cfg.get("auth.session_secret",
                                                      ""))

        @self.app.get("/health/live", tags=["health"])
        def live():
            return {"status": "alive"}

        @self.app.get("/health/ready", tags=["health"])
        def ready():
            """Readiness includes the evidence chain: a broken chain means the
            assurance claims cannot be trusted, so the node is not ready."""
            # The cheap question: has anything broken SINCE the chain was last
            # verified in full. This used to walk and re-hash every node on
            # every probe -- 2.9 seconds and 83 MB at forty thousand nodes, and
            # a busy instance reaches a million in half an hour, at which point
            # an orchestrator takes the node out of service for being slow to
            # say whether it is healthy. The full walk runs on the schedule,
            # where its cost is somebody's decision rather than a side effect.
            chain = self.ctx["evidence"].verify_since_checkpoint()
            # The scheduler reports on itself here for the same reason a monitor
            # does: one that has quietly stopped looks exactly like one with
            # nothing to do. Its state is informational — a stopped scheduler is
            # not a reason to take the node out of service.
            scheduler = self.ctx["scheduler"].health()
            # The anchor comparison is cheap — one row read per anchor — and it
            # is the only one here that a rewritten chain does not pass. The
            # incremental walk above compares the chain against itself, which
            # is exactly what an attacker with database access arranges.
            anchors = self.ctx["evidence"].verify_against_anchors()
            healthy = chain["valid"] and bool(anchors["agrees"])
            return JSONResponse({"status": "ready" if healthy else "degraded",
                                 "evidence_chain": chain, "anchors": anchors,
                                 "scheduler": scheduler},
                                status_code=200 if healthy else 503)
