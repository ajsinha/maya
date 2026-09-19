"""
The platform container: everything a service needs, built once at startup.

``Platform.build(settings)`` resolves the dependency seams, opens the
database for the configured dialect and verifies its schema identity, opens
the blob store and the lake, loads the signer, starts the job queue and wires
every service. The API layer holds one ``Platform``; nothing else constructs
these objects.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import logging
from functools import cached_property
from pathlib import Path
from typing import Any

from maya.config import Settings
from maya.core.backends import Backends, pins_from_config
from maya.core.chunker import ChunkParams
from maya.core.errors import CapabilityRefused
from maya.persistence.engine import Database, database_from_settings
from maya.persistence.session import UnitOfWork
from maya.storage.blobs import LocalBlobStore
from maya.storage.lake import LakeStore

logger = logging.getLogger(__name__)


class Platform:
    """Holds settings, stores and services for one running MAYA."""

    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db
        root = settings.storage_root
        root.mkdir(parents=True, exist_ok=True)
        self.root: Path = root
        self.blobs = LocalBlobStore(root)
        self.lake = LakeStore(root, backend=settings.get("lake.backend", "auto") or "auto",
                              chunk=ChunkParams(settings.int("lake.fragment.target_rows", 512),
                                                settings.int("lake.fragment.min_rows", 32),
                                                settings.int("lake.fragment.max_rows", 8192)))
        from maya.jobs.queue import JobQueue
        self.jobs = JobQueue(self.uow, workers=settings.int("jobs.workers", 2),
                             max_attempts=settings.int("jobs.max_attempts", 3))
        from maya.workflow.engine import WorkflowEngine
        self.workflow = WorkflowEngine(
            allow_self_approval=settings.bool("workflow.allow_self_approval", False),
            environment=settings.environment)
        self._services: dict[str, Any] = {}
        self.primary = True        # False in an extra web process (see ``build``)

    # -- construction ------------------------------------------------------
    @classmethod
    def build(cls, settings: Settings, *, init_if_empty: bool = True,
              start_workers: bool = True, primary: bool = True) -> "Platform":
        """A running MAYA. ``primary=False`` is an extra web process (``server.workers``
        above 1): it serves requests over the database the primary prepared — no schema
        creation, seeding, job reaping, job workers, webhooks or scheduler of its own."""
        Backends.resolve(pins_from_config(settings.props))
        db = database_from_settings(settings)
        if primary and not db.is_initialized():
            if not init_if_empty:
                db.verify_schema()
            db.init_schema()
        db.verify_schema()
        platform = cls(settings, db)
        platform.primary = primary
        if primary:
            platform.ensure_search_index()
        from maya.observability import tracing
        tracing.configure(settings.get("observability.otlp.endpoint") or None)
        platform.wire()
        if primary:
            from maya.services.seed import seed
            seed(platform)
        platform.startup_checks()
        if primary:
            platform.jobs.reap()
        if start_workers and primary:
            platform.jobs.start()
            platform.webhooks.start()
            platform.scheduler.start()
        return platform

    def uow(self, actor: str | None = None) -> UnitOfWork:
        return UnitOfWork(self.db, actor)

    @cached_property
    def signer(self) -> Any:
        from maya.core.crypto import Signer
        return Signer(self.root / "keys")

    def ensure_search_index(self) -> None:
        """Rebuild the derived search index when it is empty but the catalog is not."""
        with self.uow("system") as uow:
            uow.repo("search").ensure_current()

    def signer_or_none(self) -> Any:
        try:
            return self.signer
        except CapabilityRefused:
            return None

    def wire(self) -> None:
        """Construct every service and register job handlers and workflow checks."""
        from maya.services import registry
        registry.wire(self)

    def service(self, name: str) -> Any:
        return self._services[name]

    def register_service(self, name: str, svc: Any) -> None:
        self._services[name] = svc

    def __getattr__(self, name: str) -> Any:
        services = self.__dict__.get("_services", {})
        if name in services:
            return services[name]
        raise AttributeError(name)

    def startup_checks(self) -> None:
        """Refusals that must happen at startup, never at first use (§12, §17.2)."""
        from maya.security.sandbox import sandbox_tier, tier_at_least
        env = self.settings.environment
        self.service("sso").check_startup()
        tier = sandbox_tier()
        minimum = self.settings.get("sandbox.min_tier", "strong") or "strong"
        if env != "dev" and not tier_at_least(tier["tier"], minimum):
            raise CapabilityRefused(
                f"Sandbox tier is '{tier['tier']}' but sandbox.min_tier is '{minimum}' "
                f"in a {env} environment: {tier['reason']}", tier=tier["tier"])
        if env != "dev" and not self.settings.bool("app.allow_default_admin_password"):
            if self.service("auth").default_admin_password_active():
                raise CapabilityRefused(
                    "The bootstrap admin still has the default password in a non-dev "
                    "environment. Change it, or set app.allow_default_admin_password: true.")

    def shutdown(self) -> None:
        self.jobs.stop()
        self.service("webhooks").stop()
        if getattr(self, "scheduler", None) is not None:
            self.scheduler.stop()
        self.db.dispose()
