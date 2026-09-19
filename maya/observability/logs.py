"""
Logging configuration (§20): text or structured JSON, one event per line,
to stdout and a rotating file. Switching format changes every line without
touching a call site — the same arrangement as DishtaYantra's log_config.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        from maya.observability.tracing import current
        payload = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
                   "level": record.levelname, "logger": record.name,
                   "message": record.getMessage()}
        ctx = current()
        if ctx is not None:
            payload.update(trace_id=ctx.trace_id, span_id=ctx.span_id)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure(level: str = "INFO", fmt: str = "text", logfile: str | None = None) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())
    formatter: logging.Formatter = JsonFormatter() if fmt == "json" else \
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)
    if logfile:
        Path(logfile).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(logfile, maxBytes=20 * 2 ** 20,
                                                       backupCount=5, encoding="utf-8")
        handler.setFormatter(formatter)
        root.addHandler(handler)
