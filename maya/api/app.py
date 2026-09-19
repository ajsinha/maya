"""
The API application (§18.1): versioned at ``/api/v1``, OpenAPI generated from
the Pydantic models, RFC 9457 problem documents for every error, and
unauthenticated ``/healthz`` and ``/readyz``.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from maya.api.deps import ok, problem_response
from maya.api.routers import admin, catalog, custody, events, registry, workflow, workspaces
from maya.core.errors import MayaError
from maya.core.version import API_VERSION, APP_NAME, VERSION

logger = logging.getLogger(__name__)
PREFIX = f"/api/{API_VERSION}"
MIN_CLIENT = (0, 1)


def create_api(platform: Any) -> FastAPI:
    app = FastAPI(title=f"{APP_NAME} API", version=VERSION,
                  description="Model & AI Lifecycle Assurance — the public API. "
                              "The web UI and the SDK use exactly these endpoints.",
                  openapi_url=f"{PREFIX}/openapi.json", docs_url=f"{PREFIX}/docs",
                  redoc_url=None)
    app.state.platform = platform
    for r in (admin.router, catalog.router, registry.router, workflow.router,
              workspaces.router, events.router, custody.router):
        app.include_router(r, prefix=PREFIX)
    install_handlers(app)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> Any:
        return ok({"alive": True, "version": VERSION})

    @app.get("/metrics", include_in_schema=False)
    def metrics(request: Request) -> Any:
        """Prometheus exposition. Protected by a bearer token when one is configured."""
        import hmac
        import os
        from fastapi.responses import PlainTextResponse
        from maya.observability.metrics import METRICS
        env = platform.settings.get("observability.metrics.token_env") or ""
        expected = os.environ.get(env) if env else None
        if env and (not expected or not hmac.compare_digest(
                request.headers.get("authorization", ""), f"Bearer {expected}")):
            return PlainTextResponse("metrics require the configured bearer token\n", 401)
        return PlainTextResponse(METRICS.render(),
                                 media_type="text/plain; version=0.0.4; charset=utf-8")

    @app.get("/readyz", tags=["ops"])
    def readyz() -> Any:
        state = platform.ops.ready()
        return ok(state, 200 if state["ready"] else 503)

    return app


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(MayaError)
    async def maya_error(_: Request, exc: MayaError) -> JSONResponse:
        return problem_response(exc)

    @app.exception_handler(RequestValidationError)
    async def bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        problem = {"type": "validation_failed", "title": "ValidationFailed", "status": 422,
                   "detail": "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}"
                                       for e in exc.errors()), "context": {}}
        return JSONResponse(problem, status_code=422, media_type="application/problem+json")

    @app.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        import time
        from maya.observability import tracing
        from maya.observability.metrics import METRICS
        parent = tracing.parse(request.headers.get("traceparent"))
        started = time.perf_counter()
        with tracing.span(f"HTTP {request.method}", parent=parent,
                          attributes={"http.method": request.method,
                                      "http.target": request.url.path}) as ctx:
            request.state.request_id = request.headers.get("x-request-id") or ctx.trace_id
            response = await _inner(request, call_next)
            route = getattr(request.scope.get("route"), "path", None) or "unmatched"
            if request.url.path.startswith(PREFIX + "/") and not route.startswith(PREFIX):
                route = PREFIX + route      # nested routers report router-relative templates
            labels = {"method": request.method, "route": route}
            METRICS.inc("maya_http_requests_total", {**labels, "status": response.status_code})
            METRICS.observe("maya_http_request_duration_seconds", time.perf_counter() - started,
                            labels)
            response.headers["traceparent"] = ctx.header()
        return response

    async def _inner(request: Request, call_next: Any) -> Any:
        client = request.headers.get("x-maya-client", "")
        if client.startswith("python/") and _too_old(client[7:]):
            return JSONResponse({"type": "client_too_old", "status": 426,
                                 "detail": "This SDK is older than the server supports. "
                                           "Upgrade with: pip install -U maya-sdk"},
                                status_code=426)
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if not request.url.path.startswith(f"{PREFIX}/docs"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; font-src 'self' data:; frame-ancestors 'none'")
        return response


def _too_old(version: str) -> bool:
    try:
        parts = tuple(int(x) for x in version.split(".")[:2])
    except ValueError:
        return False
    return parts < MIN_CLIENT
