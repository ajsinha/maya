"""
Composition root: one ASGI application serving the API under ``/api/v1`` and
the web UI beside it. The UI reaches the API only through the SDK's
``inproc`` transport, so it holds no privileged path (§13, §16).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from maya.api.app import create_api


def build_app(platform: Any) -> FastAPI:
    app = create_api(platform)
    from maya.web.app import mount_web
    mount_web(app, secret_key=platform.settings.session_secret(),
              secure_cookies=platform.settings.environment != "dev")
    return app
