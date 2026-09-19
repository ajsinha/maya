"""
The one seam resolver (§13.4).

Every capability MAYA takes from a component that might not be installed is
reached through a named seam, and every seam is settled here, once, at
startup. The result is printed in the banner, shown on the health page and
returned by ``/readyz``, and it is written into every pin's provenance record
and every warrant, because a result that cannot be reproduced for want of
knowing which implementation produced it is not evidence.

Rules this module enforces:

* One resolver, one report. Nothing else in MAYA probes for an optional
  package; ``tools/ci/seam_imports.py`` fails the build if it does.
* Selection is never silent: every fallback carries the reason and its cost.
* Any seam may be pinned by configuration: ``seams.<name>: <backend>``.
* Type C seams never downgrade. Absence is a refusal naming what was wanted.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class SeamChoice:
    """The resolved state of one seam."""

    seam: str
    polarity: str          # A, B or C (§13.4.1)
    selected: str
    preferred: str
    fallback: str
    available: bool = True
    pinned: bool = False
    reason: str = ""
    cost: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def has_module(name: str) -> bool:
    """True when ``name`` can be imported. The only probe MAYA uses."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


@dataclass
class _SeamSpec:
    name: str
    polarity: str
    preferred: str
    fallback: str
    probe: Callable[[], bool]
    cost: str
    refuse_without_preferred: bool = False


def _native_lake_usable() -> bool:
    """The test maya_delta itself applies: importing deltalake is not enough, it must
    pass the write/read self-check — else health would say native while pins say pure."""
    if not has_module("deltalake"):
        return False
    from maya_delta import _native_problem
    return _native_problem() is None


def _specs() -> list[_SeamSpec]:
    return [
        _SeamSpec("lake", "A", "native", "pure", _native_lake_usable,
                  "Slower Delta reads and writes; declared protocol subset"),
        _SeamSpec("json", "A", "orjson", "stdlib", lambda: has_module("orjson"),
                  "Slower encode; canonical JSON is always stdlib (Type B)"),
        _SeamSpec("frames", "A", "polars", "pandas", lambda: has_module("polars"),
                  "Slower resolution kernels"),
        _SeamSpec("pushdown", "A", "duckdb", "maya", lambda: has_module("duckdb"),
                  "Wider scans; partition pruning still applies"),
        _SeamSpec("pg_driver", "A", "psycopg", "pg8000",
                  lambda: has_module("psycopg"), "Slower PostgreSQL I/O"),
        _SeamSpec("search", "A", "inverted-index", "inverted-index", lambda: True,
                  "none: MAYA's own index is the one search backend on both databases"),
        _SeamSpec("compress", "A", "zstandard", "zlib",
                  lambda: has_module("zstandard"), "Larger payloads"),
        _SeamSpec("tzdb", "A", "system", "tzdata", _system_tz_available,
                  "None when tzdata is installed; required on Windows"),
        _SeamSpec("procstat", "A", "psutil", "os", lambda: has_module("psutil"),
                  "Coarser resource reporting only"),
        _SeamSpec("kdf", "A", "argon2id", "scrypt", lambda: has_module("argon2"),
                  "Weaker but standard KDF; algorithm stored per hash"),
        _SeamSpec("typeset", "A", "tectonic", "draft", _tectonic_available,
                  "Draft PDFs, watermarked and refused as evidence"),
        _SeamSpec("event_loop", "A", "uvloop", "asyncio",
                  lambda: has_module("uvloop") and sys.platform != "win32",
                  "Lower HTTP throughput"),
        _SeamSpec("tracing", "A", "otel", "ids", lambda: has_module("opentelemetry.sdk"),
                  "Trace ids still propagate to logs, audit and jobs; spans are not exported"),
        _SeamSpec("canonical", "B", "maya", "maya", lambda: True,
                  "None. MAYA's canonicalizer is authoritative"),
        _SeamSpec("chunker", "B", "maya", "maya", lambda: True,
                  "None. MAYA's rolling-hash chunker is authoritative"),
        _SeamSpec("calendars", "A", "maya", "maya", lambda: True,
                  "None. MAYA ships its calendar data"),
        _SeamSpec("crypto", "C", "cryptography", "refuse",
                  lambda: has_module("cryptography"),
                  "Signing, sealing and certificates unavailable",
                  refuse_without_preferred=True),
        _SeamSpec("blob", "C", "local", "local", lambda: True,
                  "Configuration, not fallback"),
        _SeamSpec("queue", "C", "database", "inproc", lambda: True,
                  "Configuration, not fallback"),
    ]


def _system_tz_available() -> bool:
    if sys.platform == "win32":
        return False
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("America/New_York")
        return True
    except Exception:  # noqa: BLE001 - any failure means "not usable"
        return False


def _tectonic_available() -> bool:
    import shutil
    return shutil.which("tectonic") is not None


class Backends:
    """Resolves every seam once and answers ``selected(name)`` thereafter."""

    _lock = threading.Lock()
    _choices: dict[str, SeamChoice] | None = None

    @classmethod
    def resolve(cls, pins: dict[str, str] | None = None) -> dict[str, SeamChoice]:
        """Resolve (or re-resolve) every seam, honouring configuration pins."""
        pins = {k: v for k, v in (pins or {}).items() if v and v != "auto"}
        with cls._lock:
            choices = {s.name: cls._resolve_one(s, pins.get(s.name)) for s in _specs()}
            cls._choices = choices
        for c in choices.values():
            if c.selected != c.preferred:
                logger.warning("seam %s: using %s instead of %s (%s). Cost: %s",
                               c.seam, c.selected, c.preferred, c.reason, c.cost)
        return choices

    @staticmethod
    def _resolve_one(spec: _SeamSpec, pin: str | None) -> SeamChoice:
        available = spec.probe()
        choice = SeamChoice(spec.name, spec.polarity, spec.preferred, spec.preferred,
                            spec.fallback, available=available, cost=spec.cost)
        if pin:
            choice.pinned = True
            if pin == spec.preferred and not available:
                choice.selected = spec.fallback
                choice.reason = f"pinned to {pin} but it is not available"
            else:
                choice.selected = pin
                choice.reason = "pinned by configuration"
            return choice
        if available:
            choice.reason = "preferred backend available"
            return choice
        choice.selected = spec.fallback
        choice.reason = f"{spec.preferred} is not installed"
        if spec.refuse_without_preferred:
            choice.available = False
        return choice

    @classmethod
    def choices(cls) -> dict[str, SeamChoice]:
        if cls._choices is None:
            cls.resolve()
        assert cls._choices is not None
        return cls._choices

    @classmethod
    def selected(cls, seam: str) -> str:
        return cls.choices()[seam].selected

    @classmethod
    def report(cls) -> list[dict[str, Any]]:
        return [c.as_dict() for c in cls.choices().values()]

    @classmethod
    def provenance(cls) -> dict[str, str]:
        """The compact backend set written into pins, warrants and bundles."""
        return {name: c.selected for name, c in sorted(cls.choices().items())}

    @classmethod
    def require(cls, seam: str) -> str:
        """Return the backend of a Type C seam, or refuse by name."""
        c = cls.choices()[seam]
        if not c.available or c.selected == "refuse":
            from maya.core.errors import CapabilityRefused
            raise CapabilityRefused(
                f"The '{seam}' capability wanted '{c.preferred}', which is not "
                f"installed. MAYA does not substitute a weaker implementation "
                f"here. Install '{c.preferred}' to enable it.",
                seam=seam, wanted=c.preferred)
        return c.selected


def pins_from_config(props: Any) -> dict[str, str]:
    """Collect ``seams.<name>`` pins (and ``lake.backend``) from configuration."""
    pins: dict[str, str] = {}
    for key, value in props.get_properties_by_pattern(r"^seams\.").items():
        pins[key.split(".", 1)[1]] = value
    lake = props.get("lake.backend")
    if lake:
        pins["lake"] = lake
    return pins
