"""
The web UI (§16): server-rendered Jinja2 over vendored Bootstrap 5 and
jQuery, mounted beside the API in the same ASGI application.

Every route parses the request, calls the Python SDK with the logged-in
user's session token (``inproc`` transport), and renders. ``maya.web``
imports ``maya.sdk`` and nothing deeper; CI enforces it.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from maya.web.routes import (
    admin,
    auth,
    catalog,
    governance,
    home,
    integrations,
    lineage,
    models,
    tables,
    warrants,
    workbench,
    workflow,
    workspaces,
)

STATIC = Path(__file__).resolve().parent / "static"
SESSION_SECONDS = 12 * 3600


def mount_web(app: FastAPI, *, secret_key: str, secure_cookies: bool) -> None:
    """Attach sessions, static assets and every UI route to ``app``."""
    app.add_middleware(
        SessionMiddleware,
        secret_key=secret_key,
        session_cookie="maya_session",
        max_age=SESSION_SECONDS,
        same_site="lax",
        https_only=secure_cookies,
    )
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
    for module in (
        auth,
        home,
        catalog,
        lineage,
        workbench,
        workspaces,
        models,
        warrants,
        governance,
        integrations,
        workflow,
        admin,
        tables,
    ):
        app.include_router(module.router, include_in_schema=False)
