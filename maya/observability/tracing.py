"""
Tracing (§20): one trace from HTTP request through service, resolution and job.

Trace context is W3C ``traceparent``, always — accepted from the caller, created
when absent, returned on every response, written into every log line, audit
entry and job. That much needs nothing installed. Exporting spans is the
``tracing`` seam: with the OpenTelemetry SDK installed *and*
``observability.otlp.endpoint`` configured, spans are exported over OTLP/HTTP;
otherwise MAYA still propagates and records trace ids, and the health page says
spans are not exported rather than letting a dashboard stay silently empty.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import contextlib
import re
import secrets
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator

_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    sampled: bool = True

    def header(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{'01' if self.sampled else '00'}"


_CURRENT: ContextVar[TraceContext | None] = ContextVar("maya_trace", default=None)
_STATE: dict[str, Any] = {"tracer": None, "exporting": False, "detail": "not configured"}


def parse(header: str | None) -> TraceContext | None:
    m = _TRACEPARENT.match((header or "").strip().lower())
    if not m or m.group(1) == "0" * 32 or m.group(2) == "0" * 16:
        return None
    return TraceContext(m.group(1), m.group(2), m.group(3) == "01")


def new_context(parent: TraceContext | None = None) -> TraceContext:
    return TraceContext(parent.trace_id if parent else secrets.token_hex(16),
                        secrets.token_hex(8), parent.sampled if parent else True)


def current() -> TraceContext | None:
    return _CURRENT.get()


def current_trace_id() -> str | None:
    ctx = _CURRENT.get()
    return ctx.trace_id if ctx else None


def configure(endpoint: str | None, *, exporter: Any = None, service: str = "maya") -> dict[str, Any]:
    """Enable span export. ``exporter`` injects one (tests); else OTLP/HTTP to ``endpoint``."""
    from maya.core.backends import has_module
    if exporter is None and not endpoint:
        _STATE.update(tracer=None, exporting=False,
                      detail="trace ids propagate; spans are not exported "
                             "(observability.otlp.endpoint is not set)")
        return dict(_STATE)
    if not has_module("opentelemetry.sdk"):
        _STATE.update(tracer=None, exporting=False,
                      detail="trace ids propagate; spans are not exported: the OpenTelemetry "
                             "SDK is not installed (pip install opentelemetry-sdk "
                             "opentelemetry-exporter-otlp-proto-http)")
        return dict(_STATE)
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        detail = "spans exported to an injected exporter"
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        detail = f"spans exported over OTLP/HTTP to {endpoint}"
    _STATE.update(tracer=provider.get_tracer("maya"), provider=provider, exporting=True,
                  detail=detail)
    return dict(_STATE)


def status() -> dict[str, Any]:
    return {"exporting": _STATE["exporting"], "detail": _STATE["detail"]}


@contextlib.contextmanager
def span(name: str, *, parent: TraceContext | None = None,
         attributes: dict[str, Any] | None = None) -> Iterator[TraceContext]:
    """Enter a span: always a trace context; an exported OpenTelemetry span when enabled."""
    base = parent or _CURRENT.get()
    tracer = _STATE["tracer"]
    if tracer is None:
        ctx = new_context(base)
        token = _CURRENT.set(ctx)
        try:
            yield ctx
        finally:
            _CURRENT.reset(token)
        return
    from opentelemetry import trace
    from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
    otel_parent = None
    if base is not None:
        otel_parent = trace.set_span_in_context(NonRecordingSpan(SpanContext(
            int(base.trace_id, 16), int(base.span_id, 16), is_remote=True,
            trace_flags=TraceFlags(1 if base.sampled else 0))))
    with tracer.start_as_current_span(name, context=otel_parent,
                                      attributes={k: str(v) for k, v in
                                                  (attributes or {}).items()}) as s:
        sc = s.get_span_context()
        ctx = TraceContext(f"{sc.trace_id:032x}", f"{sc.span_id:016x}", True)
        token = _CURRENT.set(ctx)
        try:
            yield ctx
        except Exception as exc:
            s.record_exception(exc)
            raise
        finally:
            _CURRENT.reset(token)
