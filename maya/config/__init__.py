"""
Typed access to MAYA's configuration.

``load_settings`` builds the DishtaYantra-style ``PropertiesConfigurator`` over
``config/application.yaml`` (plus its git-ignored ``.local`` overlay) and wraps
it in ``Settings``, which validates the values that materially change
behaviour — database dialect, environment, auth mode — and fails at startup
naming the key rather than guessing (§22.2, §24.2).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from maya.core.errors import ConfigurationError
from maya.core.properties_configurator import PropertiesConfigurator

DIALECTS = ("sqlite", "postgresql")
ENVIRONMENTS = ("dev", "uat", "prod")
AUTH_MODES = ("db", "sso", "hybrid")
DEFAULT_CONFIG = Path("config/application.yaml")


class Settings:
    """Validated, typed view over the configurator."""

    def __init__(self, props: PropertiesConfigurator) -> None:
        self.props = props
        self.environment = self._choice("app.environment", ENVIRONMENTS)
        self.dialect = self._choice("db.dialect", DIALECTS)
        self.auth_mode = self._choice("auth.mode", AUTH_MODES)
        self.storage_root = Path(props.require("storage.root")).expanduser()
        if self.environment == "prod" and self.dialect == "sqlite":
            raise ConfigurationError(
                "app.environment is prod but db.dialect is sqlite. SQLite is a "
                "single-node, small-team backend (spec §14.1); set "
                "db.dialect=postgresql for production.", key="db.dialect")

    def _choice(self, key: str, allowed: tuple[str, ...]) -> str:
        value = self.props.require(key).strip().lower()
        if value not in allowed:
            raise ConfigurationError(
                f"Setting '{key}' is '{value}'; expected one of {', '.join(allowed)}.",
                key=key, allowed=list(allowed))
        return value

    # -- typed helpers ---------------------------------------------------
    def get(self, key: str, default: str | None = None) -> str | None:
        return self.props.get(key, default)

    def int(self, key: str, default: int) -> int:
        value = self.props.get_int(key, default)
        return default if value is None else value

    def bool(self, key: str, default: bool = False) -> bool:
        value = self.props.get_bool(key, default)
        return default if value is None else value

    @property
    def is_dev(self) -> bool:
        return self.environment == "dev"

    def database_url(self) -> str:
        """The SQLAlchemy URL for the configured dialect."""
        if self.dialect == "sqlite":
            path = Path(self.props.require("db.sqlite.path")).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{path.resolve().as_posix()}"
        p = "db.postgresql."
        user = self.props.require(p + "user")
        password = self.props.get(p + "password") or ""
        host = self.props.require(p + "host")
        port = self.props.require(p + "port")
        database = self.props.require(p + "database")
        from urllib.parse import quote
        cred = quote(user) + (":" + quote(password) if password else "")
        return f"postgresql+psycopg://{cred}@{host}:{port}/{database}"

    def session_secret(self) -> str:
        """The session-signing secret; generated under storage in dev only."""
        configured = (self.props.get("app.secret_key") or "").strip()
        if configured:
            return configured
        if not self.is_dev:
            raise ConfigurationError(
                "app.secret_key is not set. Outside dev MAYA will not generate "
                "one; set MAYA_SECRET_KEY or put it in config/application.local.yaml.",
                key="app.secret_key")
        path = self.storage_root / "keys" / "session.secret"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        return path.read_text(encoding="utf-8").strip()

    def effective(self) -> list[dict[str, Any]]:
        """Every setting with its source, secrets redacted (admin config page)."""
        rows = []
        sources = self.props.get_all_sources()
        for key, value in sorted(self.props.get_all_properties().items()):
            secret = any(s in key for s in ("password", "secret", "token"))
            rows.append({"key": key, "value": "••••••" if secret and value else value,
                         "source": sources.get(key, "file")})
        return rows


def load_settings(config_path: str | Path | None = None, *, fresh: bool = False) -> Settings:
    """Load (once) and validate the configuration."""
    if fresh:
        PropertiesConfigurator.reset_instance()
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {path}", path=str(path))
    return Settings(PropertiesConfigurator([str(path)]))
