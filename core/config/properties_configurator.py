"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Properties configurator.

Adopted from the DishtaYantra project and reduced to what MAYA needs: YAML
configuration with a git-ignored ``.local`` overlay, ``${...}`` resolution,
typed accessors, and a documented order of precedence.

Order of precedence, highest first:

    1. Command line   --key=value
    2. Environment    MAYA_APP_NAME  (dots and dashes become underscores)
    3. Files          rightmost file wins; ``x.local.yaml`` overlays ``x.yaml``

Nested YAML is flattened to dotted keys, so ``app: {name: MAYA}`` is read as
``app.name``. Values are stored as strings and coerced on access, so
``port: 8080`` and ``port: "${PORT:8080}"`` behave identically.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)

_REF = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")
_TRUE = {"1", "true", "yes", "on", "y", "t"}


class ConfigError(RuntimeError):
    """Configuration could not be loaded or a required key is absent."""


class PropertiesConfigurator:
    """Thread-safe singleton over one or more YAML configuration files."""

    _instance: Optional["PropertiesConfigurator"] = None
    _singleton_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, files: Union[str, List[str], None] = None, reload_interval: int = 300):
        if getattr(self, "_initialised", False):
            return
        self._initialised = True
        self._lock = threading.RLock()
        self._properties: Dict[str, str] = {}
        self._sources: Dict[str, str] = {}
        self._timestamps: Dict[str, float] = {}
        self._stop = threading.Event()

        # An explicit pointer always wins, whoever initialises the singleton first.
        files = os.environ.get("MAYA_CONFIG_FILE") or files
        self._files = self._with_local_overlays(self._parse_paths(files))
        self._reload_interval = reload_interval
        self._cli = self._parse_cli()
        self.reload()

        if reload_interval > 0:
            self._thread = threading.Thread(target=self._reload_worker, daemon=True,
                                            name="maya-config-reload")
            self._thread.start()

    # ------------------------------------------------------------------ setup
    @staticmethod
    def _parse_paths(files) -> List[str]:
        if not files:
            return [str(Path("config") / "application.yaml")]
        if isinstance(files, str):
            return [f.strip() for f in files.split(",") if f.strip()]
        return [str(f) for f in files]

    @staticmethod
    def _with_local_overlays(files: List[str]) -> List[str]:
        """Append ``<name>.local<ext>`` after each file, if present.

        A deployment-local overlay for values a machine needs but that must not
        be committed. Later files win key by key, so the overlay sets only what
        it names. A missing overlay is a no-op.
        """
        out: List[str] = []
        for f in files:
            out.append(f)
            p = Path(f)
            local = p.with_suffix("").as_posix() + ".local" + p.suffix
            if Path(local).exists():
                out.append(local)
        return out

    @staticmethod
    def _parse_cli() -> Dict[str, str]:
        cli: Dict[str, str] = {}
        for arg in sys.argv[1:]:
            if arg.startswith("--") and "=" in arg:
                key, _, value = arg[2:].partition("=")
                cli[key.strip()] = value.strip()
        return cli

    # ------------------------------------------------------------------ load
    @staticmethod
    def _flatten(node: Any, prefix: str = "") -> Dict[str, str]:
        flat: Dict[str, str] = {}
        if isinstance(node, dict):
            for k, v in node.items():
                flat.update(PropertiesConfigurator._flatten(v, f"{prefix}{k}."))
        elif isinstance(node, list):
            flat[prefix.rstrip(".")] = ",".join(str(x) for x in node)
        elif node is not None:
            flat[prefix.rstrip(".")] = str(node)
        return flat

    def reload(self) -> None:
        """Re-read every configured file and rebuild the property map."""
        merged: Dict[str, str] = {}
        sources: Dict[str, str] = {}
        for path in self._files:
            p = Path(path)
            if not p.exists():
                logger.debug("configuration file absent, skipped: %s", path)
                continue
            try:
                data = yaml.safe_load(p.read_text()) or {}
            except yaml.YAMLError as exc:
                raise ConfigError(f"{path}: {exc}") from exc
            for k, v in self._flatten(data).items():
                merged[k], sources[k] = v, f"file:{path}"
            self._timestamps[path] = p.stat().st_mtime

        for key in list(merged) + list(self._cli):
            env_key = "MAYA_" + key.upper().replace(".", "_").replace("-", "_")
            if env_key in os.environ:
                merged[key], sources[key] = os.environ[env_key], "env"
        for k, v in self._cli.items():
            merged[k], sources[k] = v, "commandline"

        with self._lock:
            self._properties, self._sources = merged, sources
        logger.info("configuration loaded: %d keys from %s", len(merged), self._files)

    def _reload_worker(self) -> None:
        while not self._stop.wait(self._reload_interval):
            try:
                changed = any(Path(f).exists() and Path(f).stat().st_mtime != self._timestamps.get(f)
                              for f in self._files)
                if changed:
                    logger.info("configuration change detected, reloading")
                    self.reload()
            except Exception:                                  # never kill the thread
                logger.exception("configuration reload failed")

    def stop(self) -> None:
        self._stop.set()

    # -------------------------------------------------------------- accessors
    def _resolve(self, value: str, seen: Optional[set] = None) -> str:
        """Expand ``${key}`` and ``${key:default}`` against properties then env."""
        seen = seen or set()

        def sub(m: re.Match) -> str:
            key, default = m.group(1), m.group(2)
            if key in seen:                                    # cycle: leave as written
                return m.group(0)
            raw = self._properties.get(key, os.environ.get(key))
            if raw is None:
                if default is None:
                    return m.group(0)
                raw = default
            return self._resolve(raw, seen | {key})

        return _REF.sub(sub, value)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            raw = self._properties.get(key)
        return default if raw is None else self._resolve(raw)

    def require(self, key: str) -> str:
        value = self.get(key)
        if value is None or value == "":
            raise ConfigError(f"required configuration key is missing: {key}")
        return value

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(str(self.get(key, default)).strip())
        except (TypeError, ValueError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        try:
            return float(str(self.get(key, default)).strip())
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.get(key)
        return default if raw is None else str(raw).strip().lower() in _TRUE

    def get_list(self, key: str, default: Optional[List[str]] = None) -> List[str]:
        raw = self.get(key)
        if raw is None:
            return list(default or [])
        return [x.strip() for x in str(raw).split(",") if x.strip()]

    def source_of(self, key: str) -> Optional[str]:
        """Where a value came from: ``commandline``, ``env`` or ``file:<path>``."""
        with self._lock:
            return self._sources.get(key)

    def as_dict(self) -> Dict[str, str]:
        with self._lock:
            return {k: self._resolve(v) for k, v in self._properties.items()}

    @classmethod
    def reset(cls) -> None:
        """Drop the singleton. For tests only."""
        with cls._singleton_lock:
            if cls._instance is not None:
                cls._instance.stop()
            cls._instance = None


def config(files=None) -> PropertiesConfigurator:
    """Module-level accessor for the singleton."""
    return PropertiesConfigurator(files)
