"""
Extension points, and the plugins registered at each (§25).

§25 promises that "every axis of variation is a registered plugin implementing a declared
protocol, discovered by entry point, configured by name", and that adding one never edits
core code. MAYA had the *variation* — seven source drivers, eight resolution rules, six
export formats, three auth providers, a dozen calendars — but no registry, so none of it
was discoverable, nothing could be listed on a screen, and a third party could not add one
without editing MAYA.

This is that registry, and it is deliberately modest:

* **Ten extension points**, each with the protocol §25 names and the built-ins MAYA ships.
  What is registered here is what actually exists — nothing is listed to make the table
  look full.
* **Discovery by entry point** (`maya.source_driver`, `maya.notifier`, …), read once at
  startup from the installed distributions.
* **An allowlist, and this is the safety story.** An entry-point plugin runs in this
  process with MAYA's own privileges: it can read the database and the signing key. §25 says
  untrusted plugins run under the sandbox rules for user Python, and that is not true of
  something imported into the server, so MAYA refuses to load a third-party plugin unless
  `plugins.allow` names it. A refusal is recorded and shown, not swallowed: an operator who
  installed a plugin and did not allow it should be able to see why it is not there.
* **A status per plugin** — built-in, allowed, refused (with the reason), or failed (with
  the error) — because "it is installed" and "it is in use" are different claims.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maya.core.version import VERSION

GROUP = "maya"

# point -> (the protocol §25 declares, what MAYA itself ships at that point)
POINTS: dict[str, tuple[str, str]] = {
    "source_driver": (
        "SourceDriver.schema() / read(plan)",
        "sql, csv, parquet, json, delta, derived, python",
    ),
    "resolution_rule": (
        "ResolutionRule.apply(col, grid, ctx)",
        "ffill, bfill, linear, spline, constant, zero, window mean, as-of",
    ),
    "lake_store": ("LakeStore / BlobStore", "Delta on the local filesystem, through maya_delta"),
    "exporter": ("Exporter.write(table, opts)", "arrow, parquet, csv, json, ndjson, xlsx"),
    "auth_provider": ("AuthProvider.authenticate()", "db, oidc, saml2"),
    "workflow_check": ("Check.evaluate(object, ctx)", "the checks the workflow engine registers"),
    "notifier": ("Notifier.send(event, recipients)", "inbox, webhook, email, slack, teams"),
    "model_runtime": (
        "ModelRuntime.predict(...)",
        "the formula IR evaluator; blind scoring only (ADR-007)",
    ),
    "calendar": (
        "Calendar.business_days(range)",
        "NYSE, LSE, TARGET, ISO business days, natural days",
    ),
    "search_index": ("SearchIndex", "MAYA's own inverted index (ADR-019)"),
    "llm_provider": (
        "LlmProvider.complete(system, messages, max_tokens, temperature)",
        "anthropic, openai (and compatible servers), azure_openai, ollama, bedrock, stub, none",
    ),
}


@dataclass
class Plugin:
    """One registered implementation, and how it got here."""

    point: str
    name: str
    version: str
    origin: str  # "built-in" or the distribution that provides it
    status: str  # "active" | "refused" | "failed"
    detail: str = ""
    capabilities: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    factory: Any = None

    def as_row(self) -> dict[str, Any]:
        return {
            "point": self.point,
            "name": self.name,
            "version": self.version,
            "origin": self.origin,
            "status": self.status,
            "detail": self.detail,
            "capabilities": list(self.capabilities),
            "config_schema": dict(self.config_schema),
        }


class Registry:
    """What is registered at each extension point, and what was refused."""

    def __init__(self) -> None:
        self._plugins: list[Plugin] = []
        self._discovered = False

    # -- registration ------------------------------------------------------------
    def register(
        self,
        point: str,
        name: str,
        *,
        version: str = VERSION,
        origin: str = "built-in",
        factory: Any = None,
        capabilities: list[str] | None = None,
        config_schema: dict[str, Any] | None = None,
        status: str = "active",
        detail: str = "",
    ) -> Plugin:
        if point not in POINTS:
            raise ValueError(f"unknown extension point '{point}'; points are {sorted(POINTS)}")
        plugin = Plugin(
            point=point,
            name=name,
            version=version,
            origin=origin,
            status=status,
            detail=detail,
            capabilities=list(capabilities or []),
            config_schema=dict(config_schema or {}),
            factory=factory,
        )
        self._plugins = [p for p in self._plugins if not (p.point == point and p.name == name)]
        self._plugins.append(plugin)
        return plugin

    def at(self, point: str) -> list[Plugin]:
        return [p for p in self._plugins if p.point == point and p.status == "active"]

    def get(self, point: str, name: str) -> Plugin | None:
        return next(
            (
                p
                for p in self._plugins
                if p.point == point and p.name == name and p.status == "active"
            ),
            None,
        )

    def rows(self) -> list[dict[str, Any]]:
        """Every plugin, built-in and installed, in the order a screen should show them."""
        order = list(POINTS)
        return [
            p.as_row()
            for p in sorted(
                self._plugins, key=lambda p: (order.index(p.point), p.origin != "built-in", p.name)
            )
        ]

    def report(self) -> dict[str, Any]:
        rows = self.rows()
        return {
            "points": [
                {
                    "point": point,
                    "protocol": protocol,
                    "ships_with": ships,
                    "registered": [r["name"] for r in rows if r["point"] == point],
                }
                for point, (protocol, ships) in POINTS.items()
            ],
            "plugins": rows,
            "refused": [r for r in rows if r["status"] != "active"],
            "note": "An entry-point plugin runs in this process with MAYA's privileges, so a "
            "third-party one loads only when plugins.allow names it. §25's sandbox rule "
            "covers user Python in a model artifact, not code imported into the server.",
        }

    # -- discovery ---------------------------------------------------------------
    def discover(self, settings: Any = None) -> list[Plugin]:
        """Read installed entry points once: `maya.<point>` groups, allowlist enforced."""
        if self._discovered:
            return self._plugins
        self._discovered = True
        allowed = _allowlist(settings)
        from importlib.metadata import entry_points

        for point in POINTS:
            for entry in entry_points(group=f"{GROUP}.{point}"):
                origin = getattr(getattr(entry, "dist", None), "name", None) or "installed"
                if entry.name not in allowed:
                    self.register(
                        point,
                        entry.name,
                        origin=origin,
                        status="refused",
                        detail=(
                            f"installed by {origin} and not in plugins.allow. A plugin runs "
                            "with MAYA's privileges, so it is opt-in by name."
                        ),
                    )
                    continue
                try:
                    factory = entry.load()
                except Exception as exc:  # noqa: BLE001 - one bad plugin must not stop MAYA
                    self.register(
                        point,
                        entry.name,
                        origin=origin,
                        status="failed",
                        detail=f"{type(exc).__name__}: {exc}",
                    )
                    continue
                declared = getattr(factory, "maya_plugin", {}) or {}
                self.register(
                    point,
                    entry.name,
                    version=str(declared.get("version") or "unknown"),
                    origin=origin,
                    factory=factory,
                    capabilities=list(declared.get("capabilities") or []),
                    config_schema=dict(declared.get("config_schema") or {}),
                )
        return self._plugins


def _allowlist(settings: Any) -> set[str]:
    if settings is None:
        return set()
    raw = settings.get("plugins.allow", "") or ""
    return {name.strip() for name in raw.split(",") if name.strip()}


def built_ins(registry: Registry, platform: Any = None) -> Registry:
    """Register what MAYA itself ships, so the table on the screen is the truth.

    With a ``platform``, the workflow checks it registered are listed too — they are
    registered at runtime by the services, so there is no static list to read.
    """
    from maya.resolution.rules import PARAMS
    from maya.services.catalog import SUPPORTED_SOURCES

    for name in SUPPORTED_SOURCES:
        registry.register("source_driver", name)
    for name in sorted(PARAMS):
        registry.register("resolution_rule", name)
    registry.register("lake_store", "maya_delta", capabilities=["local filesystem"])
    for name in ("arrow", "parquet", "csv", "json", "ndjson", "xlsx"):
        registry.register("exporter", name)
    for name in ("db", "oidc", "saml2"):
        registry.register("auth_provider", name)
    registry.register("model_runtime", "formula_ir", detail="blind scoring only (ADR-007)")
    from maya.core.calendars import CALENDARS

    for name in sorted(CALENDARS):
        registry.register("calendar", name)
    registry.register("search_index", "inverted_index", detail="ADR-019")
    from maya.llm.providers import BUILT_IN

    for name, provider in BUILT_IN.items():
        registry.register("llm_provider", name, factory=provider.from_settings)
    if platform is not None:
        for name in sorted(platform.workflow.checks):
            registry.register("workflow_check", name)
    from maya.notifiers import CHANNELS

    for name, channel in CHANNELS.items():
        registry.register(
            "notifier",
            name,
            factory=channel,
            capabilities=list(getattr(channel, "maya_plugin", {}).get("capabilities", [])),
            config_schema=dict(getattr(channel, "maya_plugin", {}).get("config_schema", {})),
        )
    return registry


__all__ = ["GROUP", "POINTS", "Plugin", "Registry", "built_ins"]
