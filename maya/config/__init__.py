"""
Typed access to MAYA's configuration.

``load_settings`` builds the DishtaYantra-style ``PropertiesConfigurator`` over
``config/application.yaml`` (plus its git-ignored ``.local`` overlay) and wraps
it in ``Settings``, which checks every configured key against the declared
schema in ``maya/config/schema.py`` and fails at startup naming the key rather
than guessing (§22.2, §24.2).

Two layers are treated differently, on purpose. A key in a configuration
**file** that the schema does not declare is refused: the file is MAYA's own,
so an undeclared key there is a typo, and a typo that silently does nothing is
how a deployment ends up believing it set something it did not. A key on the
**command line** that the schema does not declare is reported instead — the
process's argument list is shared with whatever launched it (``pytest --cov=…``
reaches ``sys.argv`` exactly as ``--db.dialect=…`` does), so refusing there
would make MAYA refuse to start for reasons that are none of its business.
Unknown overrides are listed in ``Settings.unknown_overrides``, logged once at
startup, and visible on the effective-configuration page.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Any

from maya.config import schema
from maya.core.errors import ConfigurationError
from maya.core.properties_configurator import PropertiesConfigurator

logger = logging.getLogger(__name__)

DIALECTS = ("sqlite", "postgresql")
ENVIRONMENTS = ("dev", "uat", "prod")
AUTH_MODES = ("db", "sso", "hybrid")
DEFAULT_CONFIG = Path("config/application.yaml")


def project_root() -> Path:
    """The checkout this package was imported from, or the working directory.

    A package installed into site-packages has no project root, so the working directory
    is the honest fallback: there is nowhere else a relative path could sensibly mean."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "config" / "application.yaml").exists():
            return candidate
    return Path.cwd()


class Settings:
    """Validated, typed view over the configurator."""

    def __init__(self, props: PropertiesConfigurator) -> None:
        self.props = props
        self.unknown_overrides: list[str] = []
        self._check_schema()
        self.environment = self._choice("app.environment", ENVIRONMENTS)
        self.dialect = self._choice("db.dialect", DIALECTS)
        self.auth_mode = self._choice("auth.mode", AUTH_MODES)
        self.storage_root = Path(props.require("storage.root")).expanduser()
        self.lake_root = self._lake_root()
        if self.environment == "prod" and self.dialect == "sqlite":
            raise ConfigurationError(
                "app.environment is prod but db.dialect is sqlite. SQLite is a "
                "single-node, small-team backend (spec §14.1); set "
                "db.dialect=postgresql for production.",
                key="db.dialect",
            )

    def _lake_root(self) -> Path:
        """Where the lake lives: the configured path, or under the storage root.

        A relative path is resolved against the project root rather than the working
        directory. The alternative reads well in a config file and behaves differently
        depending on where somebody happened to run the script from, which for a store of
        record is the wrong kind of surprise."""
        configured = (self.props.get("lake.root", "") or "").strip()
        if not configured:
            return self.storage_root / "lake"
        path = Path(configured).expanduser()
        return path if path.is_absolute() else (project_root() / path)

    def _check_schema(self) -> None:
        """Refuse an undeclared key from a file, report one from the command line, and
        validate the type and range of every value that is declared."""
        sources = self.props.get_all_sources()
        configured = self.props.get_all_properties()
        unknown = schema.unknown_keys(configured)
        schema.refuse_unknown(
            [k for k in unknown if sources.get(k) == "file"], where="a configuration file"
        )
        self.unknown_overrides = [k for k in unknown if sources.get(k) != "file"]
        if self.unknown_overrides:
            logger.warning(
                "%s command-line override(s) are not MAYA settings and were ignored: %s",
                len(self.unknown_overrides),
                ", ".join(self.unknown_overrides),
            )
        for key, value in configured.items():
            setting = schema.find(key)
            if setting is not None and value is not None and str(value).strip() != "":
                setting.validate(str(value))
        for key in schema.required_keys():
            self.props.require(key)

    def _choice(self, key: str, allowed: tuple[str, ...]) -> str:
        value = self.props.require(key).strip().lower()
        if value not in allowed:
            raise ConfigurationError(
                f"Setting '{key}' is '{value}'; expected one of {', '.join(allowed)}.",
                key=key,
                allowed=list(allowed),
            )
        return value

    # -- typed helpers ---------------------------------------------------
    def _declared(self, key: str, default: Any) -> Any:
        """The schema's default for an unset key, so a call site cannot invent a second
        one. A key the schema does not declare falls back to what the caller asked for."""
        declared = schema.find(key)
        return default if declared is None else declared.default

    def get(self, key: str, default: str | None = None) -> str | None:
        value = self.props.get(key)
        return self._declared(key, default) if value is None else value

    def int(self, key: str, default: int) -> int:
        value = self.props.get_int(key, self._as_int(key, default))
        return default if value is None else value

    def bool(self, key: str, default: bool = False) -> bool:
        declared = self._declared(key, None)
        fallback = default if declared is None else declared.strip().lower() in ("1", "true", "yes")
        value = self.props.get_bool(key, fallback)
        return fallback if value is None else value

    def _as_int(self, key: str, default: int) -> int:
        declared = self._declared(key, None)
        try:
            return default if declared is None else int(float(declared))
        except ValueError:
            return default

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
                key="app.secret_key",
            )
        path = self.storage_root / "keys" / "session.secret"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        return path.read_text(encoding="utf-8").strip()

    def effective(self) -> list[dict[str, Any]]:
        """Every setting with its source, type and description, secrets redacted (admin
        config page). A declared setting that is nowhere configured is listed with its
        schema default and the source ``default``, so the page shows what MAYA is
        actually using rather than only what a file happened to say."""
        rows = []
        sources = self.props.get_all_sources()
        configured = self.props.get_all_properties()
        for key, value in sorted(configured.items()):
            rows.append(self._row(key, value, sources.get(key, "file")))
        for setting in schema.SETTINGS:
            if setting.key not in configured and not setting.family:
                rows.append(self._row(setting.key, setting.default, "default"))
        return sorted(rows, key=lambda r: str(r["key"]))

    def _row(self, key: str, value: Any, source: str) -> dict[str, Any]:
        setting = schema.find(key)
        secret = (setting.secret if setting else False) or any(
            s in key for s in ("password", "secret", "token")
        )
        return {
            "key": key,
            "value": "••••••" if secret and value else value,
            "source": source,
            "kind": setting.kind if setting else "undeclared",
            "description": setting.description if setting else "Not a declared MAYA setting.",
        }


def load_settings(config_path: str | Path | None = None, *, fresh: bool = False) -> Settings:
    """Load (once) and validate the configuration."""
    if fresh:
        PropertiesConfigurator.reset_instance()
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {path}", path=str(path))
    return Settings(PropertiesConfigurator([str(path)]))
