"""
Composition root: one ASGI application serving the API under ``/api/v1`` and
the web UI beside it. The UI reaches the API only through the SDK's
``inproc`` transport, so it holds no privileged path (§13, §16).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI

from maya.api.app import create_api


def build_app(platform: Any) -> FastAPI:
    app = create_api(platform)
    from maya.web.app import mount_web
    mount_web(app, secret_key=platform.settings.session_secret(),
              secure_cookies=platform.settings.environment != "dev")
    return app


def web_worker() -> FastAPI:
    """uvicorn's application factory for each web process when ``server.workers`` is
    above 1. Every process serves the same application; only the launching process
    (``run_maya_web.py``) seeds, reaps and runs jobs, webhooks and the scheduler. Jobs
    submitted here are rows in the shared database, which its workers poll."""
    from maya.config import load_settings
    from maya.observability.logs import configure
    from maya.services.platform import Platform
    settings = load_settings(os.environ.get("MAYA_CONFIG_FILE"))
    configure(settings.get("logging.level", "INFO") or "INFO",
              settings.get("logging.format", "text") or "text", settings.get("logging.file"))
    return build_app(Platform.build(settings, start_workers=False, primary=False))
