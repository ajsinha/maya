"""
Service wiring: constructs every service on the platform, registers job
handlers and the named workflow checks (§10.2), and provides the generic
transition dispatcher that campaigns and the review screen use.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

from typing import Any

from maya.core.errors import ValidationFailed
from maya.security.authz import Principal


def wire(platform: Any) -> None:
    from maya.services.access import AccessService
    from maya.services.auth import AuthService
    from maya.services.bundle import BundleService
    from maya.services.execution import ExecutionService
    from maya.services.feature_data import FeatureData
    from maya.services.features import FeatureService
    from maya.services.featuresets import FeatureSetService
    from maya.services.models import ModelService
    from maya.services.ops import OpsService
    from maya.services.sso import SsoService
    from maya.services.warrants import WarrantService
    from maya.services.workflow_service import WorkflowService

    for name, cls in (("auth", AuthService), ("access", AccessService),
                      ("feature_data", FeatureData), ("features", FeatureService),
                      ("featuresets", FeatureSetService), ("models", ModelService),
                      ("warrants", WarrantService), ("execution", ExecutionService),
                      ("bundles", BundleService), ("workflow_svc", WorkflowService),
                      ("ops", OpsService), ("sso", SsoService)):
        platform.register_service(name, cls(platform))
    _jobs(platform)
    _checks(platform)
    platform.dispatch_transition = lambda p, object_type, object_id, name, **kw: \
        dispatch_transition(platform, p, object_type, object_id, name, **kw)


def _jobs(platform: Any) -> None:
    q = platform.jobs
    q.register("feature.pin", platform.features.run_pin_job)
    q.register("featureset.pin", platform.featuresets.run_pin_job)
    q.register("model.validate_artifact", platform.models.run_validation_job)
    q.register("integrity.verify", lambda ctx, params: platform.ops.verify_integrity(
        _system_principal(platform, ctx.actor)))


def _system_principal(platform: Any, username: str) -> Principal:
    with platform.uow() as uow:
        user = uow.repo("users").find_one(username=username)
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
            errors = catalog.blocking_errors(catalog.validate_feature_definition(
                row["definition"], production=ctx["subject"].namespace.get("production")))
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
        return (not failed, "; ".join(f"{r['check']}: {r['detail']}" for r in failed)
                or f"{len(results)} quality check(s) pass on current data")

    for name, fn in {
        "definition_valid": definition_valid,
        "quality_passes": quality_passes,
        "members_approved": lambda uow, ctx: fsets.members_approved(uow, ctx["row"]),
        "no_open_blocking_comments": wf.check_no_blocking_comments,
        "formula_typechecks": models.check_formula,
        "spec_document_complete": models.check_spec,
        "code_artifact_validated": models.check_artifact,
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


def dispatch_transition(platform: Any, p: Principal, object_type: str, object_id: str,
                        name: str, *, rationale: str | None = None,
                        force: bool = False) -> dict[str, Any]:
    """Take a transition on any governed object, addressed by type and id."""
    from maya.services import refs
    with platform.uow() as uow:
        if object_type == "feature_version":
            v = uow.repo("feature_versions").require(object_id)
            f = uow.repo("features").require(v["feature_id"])
            ns = uow.repo("namespaces").require(f["namespace_id"])
            target = ("features", refs.object_ref("feature", ns["name"], f["name"]), v["version_no"])
        elif object_type == "featureset_version":
            v = uow.repo("feature_set_versions").require(object_id)
            f = uow.repo("feature_sets").require(v["feature_set_id"])
            ns = uow.repo("namespaces").require(f["namespace_id"])
            target = ("featuresets", refs.object_ref("featureset", ns["name"], f["name"]),
                      v["version_no"])
        elif object_type == "model_version":
            v = uow.repo("model_versions").require(object_id)
            m = uow.repo("models").require(v["model_id"])
            ns = uow.repo("namespaces").require(m["namespace_id"])
            target = ("models", refs.object_ref("model", ns["name"], m["name"]), v["version_no"])
        else:
            target = None
    if target is not None:
        svc, ref, vno = target
        return getattr(platform, svc).transition(p, ref, vno, name, rationale=rationale,
                                                 force=force)
    if object_type == "parameter_set":
        return platform.warrants.parameter_transition(p, object_id, name, rationale=rationale,
                                                      force=force)
    if object_type == "training_warrant":
        return platform.warrants.transition(p, object_id, name, rationale=rationale, force=force)
    if object_type == "execution_warrant":
        return platform.execution.transition(p, object_id, name, rationale=rationale, force=force)
    raise ValidationFailed(f"Unknown object type '{object_type}'")
