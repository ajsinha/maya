"""
MAYA — shared route scaffolding.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Every route module needs the same four things: the services, the brand context
for a template, one place that turns a domain refusal into an HTTP status, and
the login check. They were written seven times; they are written once here.

The error mapping is the important part. Design rule DR-6 says no failure may be
unmapped, and DR-7 says a refusal must explain itself — which only holds if
there is a single table to check, rather than a try/except in each module that
drifts.
"""
from __future__ import annotations

import base64
import binascii
from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from core.assist import AssistError
from core.attachments import AttachmentError
from core.notify import NotifyError
from core.parameters import ParameterError
from core.policy import PolicyError
from core.telemetry import TelemetryError
from core.baseline import BaselineError
from core.regimes import RegimeError
from core.scheduler import SchedulerError
from core.authz import AuthzError
from core.execution import WarrantError
from core.features import AssemblyRejected, FeatureError
from core.docs import DocumentError
from core.lifecycle import LifecycleError
from core.monitoring import MonitorError
from core.overlays import OverlayError
from core.log import get_logger
from core.registry import RegistryError
from core.validation import FindingWorkflowError, ValidationError

API = "/api/v1"

# domain refusal -> HTTP status. One table, checked in one place.
logger = get_logger(__name__)

STATUS: Dict[str, int] = {
    "not_found": 404, "validation_failed": 422, "assembly_rejected": 422,
    "no_entitlement": 403, "use_not_approved": 403, "signature_invalid": 403,
    "registry_refused": 409, "feature_refused": 409, "restricted": 423,
    "validation_refused": 409,
    "revoked": 410, "expired": 410, "blocked": 423, "boundary_violation": 422, "no_runtime": 501,
    # authorisation
    "unauthenticated": 401, "forbidden": 403, "out_of_scope": 403,
    "segregation_of_duties": 403, "incompatible_roles": 409,
    "duplicate_principal": 409, "no_such_principal": 404, "unknown_role": 422,
    "unknown_permission": 422,
    # lifecycle
    "illegal_transition": 409, "record_frozen": 409, "nothing_to_approve": 409,
    "not_tiered": 409, "amendment_open": 409, "attestation_open": 409,
    "attestation_closed": 409, "already_signed": 409, "no_attestation_open": 409,
    "reason_required": 422, "unknown_decision": 422,
    "role_not_required": 403, "role_not_held": 403, "deletion_refused": 403,
    "no_attestation": 404, "no_amendment": 404,
    # monitoring
    "unknown_kind": 422, "test_not_admissible": 422, "threshold_required": 422,
    "label_delay_required": 422, "unknown_status": 422, "no_reference": 422,
    "cohort_immature": 409, "monitor_inactive": 409, "duplicate_monitor": 409,
    "no_monitor": 404, "unknown_severity": 422,
    # grammar
    "grammar_violation": 422,
    # documents
    "unknown_document_kind": 422, "no_document": 404,
    # attached documents
    "title_required": 422, "empty_document": 422,
    "document_too_large": 413, "bad_digest": 422,
    "self_review": 403, "already_reviewed": 409,
    "already_attached": 409, "already_superseded": 409,
    "no_version_to_attach_to": 409, "no_attachment": 404,
    "no_version_for_document": 404,
    "no_such_attachment": 404, "document_missing": 404,
    "document_corrupt": 500,
    # featuresets and the parameters a fit produces
    "unknown_provenance": 422, "no_such_version": 404,
    "nothing_to_fit": 422, "parameters_not_reachable": 422,
    "warrant_required": 422, "unknown_warrant": 404,
    "warrant_revoked": 410, "warrant_names_another_model": 409,
    "warrant_names_another_version": 409,
    "no_parameters": 422, "parameters_too_large": 413,
    "featureset_required": 422, "self_approval": 403,
    "no_parameter_set": 404, "no_approved_parameters": 409,
    "ambiguous_parameters": 409, "different_version": 409,
    "schema_not_satisfied": 409, "no_featureset_registry": 501,
    # version approval as a quorum
    # telemetry
    # notification
    # versioned gates
    "unknown_gate": 404, "empty_rule": 422, "unknown_fact": 422,
    "rule_does_not_parse": 422, "not_in_the_language": 422,
    "unknown_function": 422, "reserved_name": 422, "rule_failed": 422,
    "fact_not_supplied": 500, "too_few_cases": 422,
    "case_without_a_verdict": 422, "no_refusing_case": 422,
    "cases_do_not_pass": 409, "already_decided": 409, "no_policy": 404,
    # `reason_required` is shared with lifecycle above and mapped there. Three
    # subsystems refuse an unexplained act with the same code, which is the
    # right answer given the same remedy; repeating the key here silently
    # overwrote the earlier entry with an identical value and hid the sharing.
    "policy_refused": 403,
    # fitting a parameter object
    # A refusal here almost always names something the caller can put right in
    # the featureset or the warrant, so the status separates "you asked for
    # something incoherent" from "the data will not support it".
    "window_required": 422, "window_inverted": 422,
    "no_snapshot": 404, "snapshot_storage_missing": 410,
    "snapshot_not_from_a_featureset": 409, "snapshot_is_empty": 409,
    "snapshot_not_pit_verified": 409,
    "wrong_verb": 409, "unknown_family": 422, "fit_underspecified": 422,
    "target_is_a_regressor": 422, "no_rows": 422, "too_few_rows": 422,
    "column_missing": 422, "value_not_numeric": 422,
    "not_identified": 422, "collinear_regressors": 422,
    "series_is_constant": 422, "fit_did_not_converge": 422,
    # running at a point of P
    # `parameter_mismatch` is 409 and not 422: nothing about the request is
    # wrong. The numbers in the register stopped matching what was approved,
    # which is a conflict in the platform's own state and a security event.
    "parameter_mismatch": 409, "no_parameter_register": 501,
    "no_parameters_supplied": 409, "parameter_missing": 409,
    "no_features": 422, "state_required": 422, "state_not_a_variance": 422,
    # asking a model
    # `provider_unavailable` is 501 and not 503: it is not that the provider is
    # down, it is that this instance was never wired to one, which is a
    # deployment decision rather than a transient fault.
    "provider_unavailable": 501, "unknown_provider": 422,
    "nothing_to_ground": 422,
    # A directory login that resolves to nobody here, or to somebody it was
    # never linked to. 403 rather than 401: the credential was fine, the
    # identity is the problem, and retrying with it will not help.
    "identity_not_linked": 403, "already_linked": 409,
    # Asking for a credential in somebody else's name.
    "principal_not_self": 403, "verifier_not_self": 403,
    # single sign-on
    "sso_not_configured": 501, "discovery_incomplete": 502,
    "issuer_mismatch": 403, "audience_mismatch": 403,
    "state_mismatch": 403, "nonce_mismatch": 403,
    "login_expired": 403, "no_login_in_progress": 403,
    "token_expired": 403, "token_from_the_future": 403,
    "bad_signature": 403, "unsupported_algorithm": 403,
    "unknown_key": 403, "ambiguous_key": 403,
    "no_signing_keys": 502, "unsupported_key": 502,
    "weak_key": 502, "malformed_token": 502,
    "no_id_token": 502, "provider_unreachable": 503,
    "not_provisioned": 403, "no_roles_mapped": 403,
    "no_subject": 502,
    "unknown_channel": 422, "channel_not_built": 501,
    "channel_unavailable": 503,
    "unknown_stream": 422, "empty_batch": 422,
    "batch_too_large": 413, "bad_sample_rate": 422,
    "malformed_row": 422, "no_telemetry": 501,
    "no_telemetry_in_window": 404, "empty_reference_window": 422,
    "no_registry": 501, "monitor_has_no_version": 409,
    "quorum_required": 409, "no_quorum_required": 409,
    "approval_open": 409, "approval_closed": 409,
    "already_approved": 409, "no_approval": 404,
    "already_signed_personally": 409, "no_tier": 409,

    # --- the captive engine's own refusals -------------------------------
    # These reach a caller only through the convenience execute endpoint, but
    # they still deserve a status that says who has to act. A 502 says the
    # artifact behind the warrant is wrong or absent, which is the registrar's
    # problem; a 422 says the caller's inputs are; a 504 says it ran too long.
    "no_artifact": 502, "artifact_missing": 502,
    "artifact_mismatch": 502, "artifact_unverifiable": 502,
    "artifact_outside_root": 502, "no_artifact_root": 501,
    "pmml_malformed": 502, "pmml_unsupported": 501,
    "runtime_unavailable": 503,
    "missing_inputs": 422, "input_not_in_graph": 422,
    "execution_timeout": 504, "execution_limit": 507,
    "execution_failed": 502,
    # the quantlib runtime's own refusals
    "no_evaluation_date": 422, "no_curve": 422, "malformed_curve": 422,
    "malformed_date": 422, "malformed_fixing": 422, "missing_fixing": 422,
    "no_volatility": 422, "unknown_day_count": 422,
    "instrument_unsupported": 501, "pricing_engine_unsupported": 501,
    "valuation_failed": 422,
    # overlays
    "unknown_direction": 422, "rationale_required": 422,
    "window_too_long": 422, "unknown_closure": 422,
    # `self_approval` is shared with parameters above and mapped there.
    "self_renewal": 403,
    "not_proposed": 409, "not_active": 409, "already_measured": 409,
    "unmeasured": 409, "period_unmeasured": 409, "no_overlay": 404,
    # machine assistance
    "advisory_not_registrable": 422, "unknown_tier": 422,
    "oracle_required": 422, "unknown_oracle": 422, "unknown_autonomy": 422,
    "duplicate_capability": 409, "capability_inactive": 409,
    "oracle_failed": 422, "nothing_grounded": 422,
    # `already_decided` is shared with policy above and mapped there.
    "self_attestation": 403,
    "no_capability": 404, "no_generation": 404,
    # baseline import
    "unknown_gap": 422, "plan_required": 422, "nothing_to_import": 422,
    "already_recorded": 409, "already_registered": 409, "no_debt": 404,
    # regimes
    "no_regime": 404, "incomplete_translation": 422,
    "satisfaction_condition_failed": 422,
    # scheduler
    "unknown_job": 422,
    # the workflow around a finding
    "no_finding": 404, "finding_closed": 409, "owner_required": 422,
    "already_owned": 409, "not_the_owner": 403, "date_in_the_past": 422,
    "beyond_the_due_date": 422, "not_acknowledged": 409, "self_extension": 403,
    "not_an_extension": 422, "extension_too_long": 422,
}
REMEDY: Dict[type, str] = {
    RegistryError: "the refusal names the clause that failed; satisfy it and retry",
    FeatureError: "correct the feature definition or the view version and retry",
    AssemblyRejected: "bound the assembly on both valid time and transaction time",
    ValidationError: "the refusal names the rule that was not satisfied; satisfy it and retry",
}


def current_user(request: Request) -> Optional[str]:
    return request.session.get("username")


def authz_problem(exc: AuthzError) -> HTTPException:
    """One translation of an authorisation refusal into HTTP."""
    return HTTPException(STATUS.get(exc.code, 403), {
        "error": exc.code, "detail": exc.detail, "remediation": exc.remediation})


def basic_credentials(request: Request) -> Optional[tuple]:
    """Username and password from an HTTP Basic header, or None.

    Services and scripts need a way in that is not a browser session. Basic over
    the same principal table keeps one identity store rather than two, and a
    malformed header is treated as absent rather than as an error — the caller
    is then told plainly that authentication is required.
    """
    header = request.headers.get("authorization", "")
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return None
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        logger.info("ignoring a malformed Basic authorization header: %s", exc)
        return None
    username, sep, password = decoded.partition(":")
    return (username, password) if sep else None


def login_required(request: Request) -> Optional[RedirectResponse]:
    """A redirect when the caller is anonymous, otherwise None."""
    if current_user(request) is None:
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)
    return None


class Routes:
    """Base for every route module. Subclasses implement ``register``."""

    def __init__(self, app: FastAPI, ctx: Dict[str, Any],
                 templates: Optional[Jinja2Templates] = None):
        self.app, self.ctx, self.templates = app, ctx, templates
        self.api = API
        self.register()

    def register(self) -> None:                                # pragma: no cover
        raise NotImplementedError

    # ----------------------------------------------------------------- domain
    def guard(self, fn: Callable[[], Any]) -> Any:
        """Run a service call, mapping any domain refusal onto the taxonomy."""
        try:
            return fn()
        # FindingWorkflowError is a ValidationError, and it is caught HERE
        # rather than below because it carries a code of its own. Catching it
        # with the uncoded validation refusals would flatten eleven refusals
        # that each name a different thing to do into one 409.
        except (WarrantError, LifecycleError, MonitorError, DocumentError,
                OverlayError, AssistError, BaselineError,
                RegimeError, SchedulerError, AttachmentError,
                ParameterError, TelemetryError, NotifyError,
                FindingWorkflowError, PolicyError) as exc:
            # A refusal is normal operation, not a fault — but it is the record of
            # a governance decision, so it is never translated without a trace.
            logger.warning("refused (%s): %s", exc.code, exc)
            raise HTTPException(STATUS.get(exc.code, 400), exc.as_problem()) from exc
        except (RegistryError, FeatureError, AssemblyRejected, ValidationError) as exc:
            code = {RegistryError: "registry_refused", FeatureError: "feature_refused",
                    AssemblyRejected: "assembly_rejected",
                    ValidationError: "validation_refused"}[type(exc)]
            logger.warning("refused (%s): %s", code, exc)
            raise HTTPException(STATUS[code], {
                "error": code, "detail": str(exc), "remediation": REMEDY[type(exc)]}) from exc

    # ---------------------------------------------------------- authorisation
    def principal(self, request: Request) -> Dict[str, Any]:
        """The acting principal, from the session or from Basic credentials.

        Raises 401 rather than returning None: every caller of this wants an
        identity, and an Optional here would eventually be used without checking.
        """
        people = self.ctx["principals"]
        if (username := current_user(request)) is not None:
            if (row := people.get(username)) and row["status"] == "active":
                return row
        if (creds := basic_credentials(request)) is not None:
            if (row := people.authenticate(*creds)) is not None:
                return row
        raise HTTPException(401, {
            "error": "unauthenticated",
            "detail": "this endpoint requires an authenticated principal",
            "remediation": "sign in, or present HTTP Basic credentials",
        }, headers={"WWW-Authenticate": 'Basic realm="MAYA"'})

    def authorise(self, request: Request, permission: str,
                  model: Optional[Dict[str, Any]] = None,
                  subject_id: Optional[str] = None,
                  about: Optional[str] = None) -> Dict[str, Any]:
        """Authenticate, then check permission, scope and segregation.

        ``subject_id`` is where the evidence lives; ``about`` narrows it to one
        thing when the subject carries evidence for many, as a model does for
        every finding raised against it.

        Returns the principal so the caller can attribute the act to them —
        every governance act is recorded against a real identity rather than
        against 'system'.
        """
        who = self.principal(request)
        self.ctx["authz"].authorise(who, permission, model, subject_id, about)
        return who

    @staticmethod
    def actor(principal: Dict[str, Any]) -> str:
        return principal.get("username", "system")

    @staticmethod
    def not_found(detail: str) -> HTTPException:
        return HTTPException(404, {"error": "not_found", "detail": detail})

    # ------------------------------------------------------------------- view
    def brand(self, request: Optional[Request] = None) -> Dict[str, Any]:
        c = self.ctx["config"]
        return {"app_name": c.get("app.name", "MAYA"), "tagline": c.get("app.tagline", ""),
                "slogan": c.get("app.slogan", ""), "version": c.get("app.version", ""),
                "user": current_user(request) if request is not None else None}

    def page(self, request: Request, template: str, *, http_status: int = 200,
             **context):
        """Render a template. Every other keyword reaches the template.

        The HTTP code is spelled `http_status` and is keyword-only on purpose.
        It was once called `status`, which is the most natural name a page has
        for a model's status, a finding's status or a version's status -- so a
        caller passing one got a silently empty variable in the template and a
        response code taken from a domain word. Nothing raised; the page simply
        rendered nothing where the status should have been.
        """
        return self.templates.TemplateResponse(
            request, template, {**self.brand(request), **context},
            status_code=http_status)
