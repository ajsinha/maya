"""
Service wiring: constructs every service on the platform, registers job
handlers and the named workflow checks (§10.2), and provides the generic
transition dispatcher that campaigns and the review screen use.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import logging
from typing import Any

from maya.core.errors import ValidationFailed
from maya.security.authz import Principal


def wire(platform: Any) -> None:
    from maya.services.access import AccessService
    from maya.services.access_requests import AccessRequestService
    from maya.services.auth import AuthService
    from maya.services.catalog import CatalogService
    from maya.services.subscriptions import SubscriptionService
    from maya.services.retention import RetentionService
    from maya.services.tracking import TrackingService
    from maya.services.bundle import BundleService
    from maya.services.execution import ExecutionService
    from maya.services.feature_data import FeatureData
    from maya.services.governance import GovernanceService
    from maya.services.monitoring import MonitoringService
    from maya.services.inventory import InventoryService
    from maya.services.features import FeatureService
    from maya.services.featuresets import FeatureSetService
    from maya.services.models import ModelService
    from maya.services.ops import OpsService
    from maya.services.sso import SsoService
    from maya.services.workspaces import WorkspaceService
    from maya.services.sources import SourceService
    from maya.services.webhooks import WebhookService
    from maya.services.licensing import LicenceService
    from maya.services.custody import CustodyService
    from maya.services.assistant import AssistantService
    from maya.services.passkeys import PasskeyService
    from maya.services.warrants import WarrantService
    from maya.services.workflow_service import WorkflowService

    for name, cls in (
        ("auth", AuthService),
        ("access", AccessService),
        ("feature_data", FeatureData),
        ("features", FeatureService),
        ("featuresets", FeatureSetService),
        ("models", ModelService),
        ("warrants", WarrantService),
        ("execution", ExecutionService),
        ("bundles", BundleService),
        ("workflow_svc", WorkflowService),
        ("ops", OpsService),
        ("sso", SsoService),
        ("workspaces", WorkspaceService),
        ("sources", SourceService),
        ("webhooks", WebhookService),
        ("licences", LicenceService),
        ("custody", CustodyService),
        ("passkeys", PasskeyService),
        ("assistant", AssistantService),
        ("catalog", CatalogService),
        ("subscriptions", SubscriptionService),
        ("access_requests", AccessRequestService),
        ("retention", RetentionService),
        ("tracking", TrackingService),
        ("governance", GovernanceService),
        ("monitoring", MonitoringService),
        ("inventory", InventoryService),
    ):
        platform.register_service(name, cls(platform))
    _jobs(platform)
    _checks(platform)
    _collectors(platform)
    platform.workflow.principal_loader = platform.auth.build_principal
    platform.workflow.on_move(platform.assistant.on_move)
    # An approved version has consequences: dependants that track it are marked for
    # re-approval (§5.8, §8.7) and whoever follows the object is told (§5.7).
    platform.workflow.on_move(platform.tracking.on_move)
    platform.workflow.on_move(platform.subscriptions.on_move)
    from maya.jobs.scheduler import Scheduler

    platform.scheduler = Scheduler()
    platform.scheduler.every(
        "workflow.escalate_overdue", 3600, platform.workflow_svc.escalate_overdue
    )
    platform.scheduler.every("execution.expiry_notices", 3600, platform.execution.expire_sweep)
    platform.scheduler.every("notices.sweep", 3600, platform.subscriptions.notices)
    # an overdue periodic review suspends the model's live execution warrants
    platform.scheduler.every("governance.review_sweep", 3600, platform.governance.sweep)
    platform.scheduler.every(
        "tracking.revoked_members", 3600, platform.tracking.sweep_revoked_members
    )
    platform.scheduler.every(
        "lake.maintenance",
        platform.settings.int("lake.maintenance.interval_seconds", 86400),
        platform.ops.lake_maintenance,
    )
    platform.scheduler.every(
        "custody.anchor",
        platform.settings.int("custody.anchor.interval_seconds", 3600),
        platform.custody.anchor,
    )
    verify_every = platform.settings.int("integrity.verify.interval_seconds", 86400)
    if verify_every > 0:
        platform.scheduler.every(
            "integrity.verify", verify_every, platform.ops.schedule_integrity_verification
        )
    platform.dispatch_transition = lambda p, object_type, object_id, name, **kw: (
        dispatch_transition(platform, p, object_type, object_id, name, **kw)
    )


def _cancel_pin(uow: Any, table: str, params: dict[str, Any]) -> None:
    """A pin whose job is cancelled before it ran is failed, never left 'materializing':
    a stuck pin would block its name and date for good."""
    pin = uow.repo(table).get(params["pin_id"])
    if pin is not None and pin["state"] == "materializing":
        uow.repo(table).update(pin["id"], {"state": "failed", "failure": "cancelled before it ran"})


def _announcing(platform: Any, kind: str, run: Any) -> Any:
    """A pin job that also says what it did: subscribers hear about a sealed pin (§5.7)
    and the owner about one the quality contract blocked (§5.5). The announcement runs
    whether the job succeeded or failed, and never changes its outcome."""

    def wrapped(ctx: Any, params: dict[str, Any]) -> Any:
        try:
            return run(ctx, params)
        finally:
            try:
                platform.subscriptions.announce_pin(kind, params["pin_id"])
            except Exception:  # noqa: BLE001 - a notification never fails a pin
                logging.getLogger(__name__).exception("could not announce pin %s", params["pin_id"])

    return wrapped


def _jobs(platform: Any) -> None:
    q = platform.jobs
    q.register(
        "feature.pin",
        _announcing(platform, "feature", platform.features.run_pin_job),
        on_cancel=lambda uow, params: _cancel_pin(uow, "feature_pins", params),
    )
    q.register("assistant.challenge", platform.assistant.run_job)
    q.register(
        "featureset.pin",
        _announcing(platform, "featureset", platform.featuresets.run_pin_job),
        on_cancel=lambda uow, params: _cancel_pin(uow, "feature_set_pins", params),
    )
    q.register("model.validate_artifact", platform.models.run_validation_job)
    q.register("workspace.shadow_replay", platform.workspaces.run_replay_job)
    q.register(
        "integrity.verify",
        lambda ctx, params: platform.ops.verify_integrity(_system_principal(platform, ctx.actor)),
    )


def _collectors(platform: Any) -> None:
    """Gauges read at scrape time, so /metrics never reports a stale number."""
    from maya.core.backends import Backends
    from maya.core.version import BUILD_DATE, VERSION
    from maya.observability.metrics import METRICS
    from maya.core.clock import utcnow

    def state() -> list[tuple[str, dict[str, Any], float]]:
        out: list[tuple[str, dict[str, Any], float]] = []
        with platform.uow() as uow:
            for st in ("queued", "running", "failed", "dead_letter"):
                out.append(("maya_jobs", {"state": st}, uow.repo("jobs").count(state=st)))
            out.append(
                (
                    "maya_sessions_active",
                    {},
                    uow.repo("sessions").count(revoked_at__isnull=True, expires_at__gt=utcnow()),
                )
            )
            for st in ("pending", "dead"):
                out.append(
                    (
                        "maya_webhook_backlog",
                        {"state": st},
                        uow.repo("webhook_deliveries").count(state=st),
                    )
                )
        return out

    def static() -> list[tuple[str, dict[str, Any], float]]:
        from maya.security.sandbox import sandbox_tier

        out: list[tuple[str, dict[str, Any], float]] = [
            (
                "maya_build_info",
                {"version": VERSION, "build": BUILD_DATE, "dialect": platform.db.dialect},
                1.0,
            ),
            ("maya_sandbox_tier", {"tier": sandbox_tier()["tier"]}, 1.0),
        ]
        out += [
            ("maya_seam_backend", {"seam": c["seam"], "backend": c["selected"]}, 1.0)
            for c in Backends.report()
        ]
        return out

    from maya.observability import caches
    from maya.observability.collectors import Collectors

    gauges = Collectors(platform)
    METRICS._collectors.clear()  # one platform per process owns the scrape
    METRICS.collector(state)
    METRICS.collector(static)
    METRICS.collector(gauges.all)
    caches.seed()  # every registered cache reports its zeros before its first lookup


def _system_principal(platform: Any, username: str) -> Principal:
    """The principal a job runs as. A job the *scheduler* queued has no person behind it
    (owner ``system``), so it runs as techops rather than being attributed to whichever
    administrator happened to exist — the audit entry then says plainly that MAYA did it."""
    with platform.uow() as uow:
        user = uow.repo("users").find_one(username=username)
        if user is None:
            return Principal(
                user_id="system",
                username=username,
                roles=["techops"],
                capabilities={},
                principal_type="system",
                channel="scheduler",
            )
        return platform.auth.build_principal(uow, user["id"])


def _checks(platform: Any) -> None:
    w = platform.workflow
    features, fsets, models = platform.features, platform.featuresets, platform.models
    warrants, execution, wf = platform.warrants, platform.execution, platform.workflow_svc

    def definition_valid(uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        row = ctx["row"]
        if "feature_set_id" in row:
            errors = fsets.validate(row["definition"])
        else:
            from maya.services import catalog

            errors = catalog.blocking_errors(
                catalog.validate_feature_definition(
                    row["definition"], production=ctx["subject"].namespace.get("production")
                )
            )
        return (not errors, "; ".join(errors) or "definition is valid and typed")

    def quality_passes(uow: Any, ctx: dict[str, Any]) -> tuple[bool, str]:
        feature = ctx["feature"]
        ns = ctx["subject"].namespace
        from maya.resolution import quality
        from maya.services import catalog

        eff = catalog.effective_feature_definition(uow, ctx["row"]["definition"])
        if not eff.get("quality"):
            return True, "no quality contract declared"
        try:
            res = platform.feature_data.resolve_definition(ns["name"], feature["name"], eff)
        except Exception as exc:  # noqa: BLE001 - reported as the check's detail
            return False, f"could not resolve a sample: {exc}"
        results = quality.run_checks(res.df, eff["quality"], res.meta["index"])
        failed = [r for r in results if not r["passed"]]
        return (
            not failed,
            "; ".join(f"{r['check']}: {r['detail']}" for r in failed)
            or f"{len(results)} quality check(s) pass on current data",
        )

    for name, fn in {
        "definition_valid": definition_valid,
        "quality_passes": quality_passes,
        "members_approved": lambda uow, ctx: fsets.members_approved(uow, ctx["row"]),
        "no_open_blocking_comments": wf.check_no_blocking_comments,
        "formula_typechecks": models.check_formula,
        "spec_document_complete": models.check_spec,
        "code_artifact_validated": models.check_artifact,
        "code_matches_specification": models.check_conformance,
        "no_live_execution_warrant": models.check_no_live_warrant,
        "spec_true_build": models.check_true_build,
        "composite_members_mature": models.check_members,
        "contract_valid": warrants.check_contract,
        "leakage_certified": warrants.check_leakage,
        "parameters_within_bounds": warrants.check_bounds_ok,
        "data_verified_or_justified": warrants.check_data_verified,
        "parameters_approved": execution.check_params,
    }.items():
        w.register_check(name, fn)
    _ = features


def dispatch_transition(
    platform: Any,
    p: Principal,
    object_type: str,
    object_id: str,
    name: str,
    *,
    rationale: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Take a transition on any governed object, addressed by type and id."""
    from maya.services import refs

    with platform.uow() as uow:
        if object_type == "feature_version":
            v = uow.repo("feature_versions").require(object_id)
            f = uow.repo("features").require(v["feature_id"])
            ns = uow.repo("namespaces").require(f["namespace_id"])
            target = (
                "features",
                refs.object_ref("feature", ns["name"], f["name"]),
                v["version_no"],
            )
        elif object_type == "featureset_version":
            v = uow.repo("feature_set_versions").require(object_id)
            f = uow.repo("feature_sets").require(v["feature_set_id"])
            ns = uow.repo("namespaces").require(f["namespace_id"])
            target = (
                "featuresets",
                refs.object_ref("featureset", ns["name"], f["name"]),
                v["version_no"],
            )
        elif object_type == "model_version":
            v = uow.repo("model_versions").require(object_id)
            m = uow.repo("models").require(v["model_id"])
            ns = uow.repo("namespaces").require(m["namespace_id"])
            target = ("models", refs.object_ref("model", ns["name"], m["name"]), v["version_no"])
        else:
            target = None
    if target is not None:
        svc, ref, vno = target
        return getattr(platform, svc).transition(
            p, ref, vno, name, rationale=rationale, force=force
        )
    if object_type == "parameter_set":
        return platform.warrants.parameter_transition(
            p, object_id, name, rationale=rationale, force=force
        )
    if object_type == "training_warrant":
        return platform.warrants.transition(p, object_id, name, rationale=rationale, force=force)
    if object_type == "execution_warrant":
        return platform.execution.transition(p, object_id, name, rationale=rationale, force=force)
    raise ValidationFailed(f"Unknown object type '{object_type}'")
