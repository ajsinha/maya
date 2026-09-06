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

import logging

import base64
import binascii
from typing import Any, Callable, Dict, Optional
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, ConfigDict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from core.assist import AssistError
from core.attachments import AttachmentError
from core.notify import NotifyError
from core.parameters import ParameterError
from core.artifacts import ArtifactError
from core.execution.profiles import ProfileError
from core.export import ExportError
from core.reporting import ReportingError
from core.policy import PolicyError
from core.telemetry import TelemetryError
from core.baseline import BaselineError
from core.regimes import RegimeError
from core.scheduler import SchedulerError
from core.authz import AuthzError
from core import log
from core.authz import csrf
from core.execution import WarrantError
from core.features import AssemblyRejected, FeatureError
from core.docs import DocumentError
from core.lifecycle import LifecycleError
from core.fibres import FibreError
from core.rules.common import RuleError
from core.monitoring import MonitorError
from core.overlays import OverlayError
from core.log import get_logger, swallowed
from core.registry import RegistryError
from core.validation import FindingWorkflowError, ValidationError

API = "/api/v1"

# domain refusal -> HTTP status. One table, checked in one place.
logger = get_logger(__name__)

class Body(BaseModel):
    """The base every request body extends. Unknown fields are REFUSED.

    Pydantic's default is to drop a field the model does not declare, silently.
    That is how the SDK came to send `note` to an endpoint reading `statement`:
    the signature recorded, the signer's rationale vanished, and both sides
    reported success. A quorum signature with no reasoning is the one thing a
    quorum is for.

    Forbidding the extra turns every such mismatch into a 422 naming the field,
    at the first call rather than at the first audit. The cost is that a client
    sending a field a *newer* server would understand is refused by an older
    one — which is the right way round, because this SDK ships with this server
    and a silently ignored field is indistinguishable from a working one.
    """

    model_config = ConfigDict(extra="forbid")


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
    # Reinstating somebody who is already active is a no-op the caller should
    # know about rather than a silent success; a short password is the caller's
    # to fix.
    "already_active": 409, "password_too_short": 422,
    # What the platform will fetch. 502 rather than 4xx: the caller did nothing
    # wrong — an identity provider named an address MAYA refuses to open, and
    # that is a fault in something upstream of this request.
    "outbound_scheme_refused": 502, "outbound_not_encrypted": 502,
    "outbound_host_missing": 502, "outbound_url_missing": 502,
    "unknown_permission": 422,
    # lifecycle
    "illegal_transition": 409, "record_frozen": 409, "nothing_to_approve": 409,
    "not_tiered": 409, "amendment_open": 409, "attestation_open": 409,
    "attestation_closed": 409, "already_signed": 409, "no_attestation_open": 409,
    "reason_required": 422, "unknown_decision": 422,
    "role_not_required": 403, "role_not_held": 403, "deletion_refused": 403,
    "no_attestation": 404, "no_amendment": 404,
    # rule sets (T8). Every one is 422: the document is well-formed JSON and
    # wrong as a *policy*, which is a problem with what was written rather than
    # with the state of the register — the caller has something to fix.
    #
    # `ruleset_malformed` is the exception when it comes from the runtime rather
    # than the editor: a stored rule set that no longer parses means the
    # register holds a document its own checks would refuse, and the engine
    # raises it as a `WarrantError` mapped elsewhere.
    "ruleset_malformed": 422, "condition_malformed": 422,
    "condition_ambiguous": 422, "condition_too_deep": 422,
    "unknown_operator": 422, "value_required": 422, "value_not_expected": 422,
    "value_malformed": 422, "empty_range": 422, "unknown_field": 422,
    "unordered_comparison": 422, "unknown_outcome_field": 422,
    "value_wrong_type": 422,
    "value_not_comparable": 422,
    "no_rules": 422, "too_many_rules": 422, "otherwise_required": 422,
    "rule_id_required": 422, "rule_id_malformed": 422, "duplicate_rule_id": 409,
    "outcome_required": 422,
    # The three the analysis exists for. A rule that can never fire and two
    # rules that disagree are not malformed documents — they are policy
    # mistakes, and the remediation says which.
    "rule_never_fires": 422, "rule_unreachable": 422, "rules_contradict": 409,
    "not_a_ruleset": 409, "not_a_ruleset_model": 409, "no_ruleset": 409,
    # the evidence chain's anchor
    #
    # `anchor_disagreement` is 409 and not 422: nothing about the request is
    # wrong. The chain and the heads written outside it no longer agree, which
    # is a security event, and the caller cannot fix it by sending something
    # else. `chain_broken` likewise — a refusal to anchor a chain that does not
    # verify, because writing the broken state down would make every later
    # comparison agree with it.
    "anchor_disagreement": 409, "anchor_unreadable": 409, "chain_broken": 409,
    "nothing_to_anchor": 409, "worm_overwrite_refused": 409,
    "worm_unreadable": 409, "worm_bad_name": 422,
    # The contract algebra. All 409: nothing is wrong with the request, and
    # sending it again differently will not help. Two contracts genuinely
    # cannot be combined — a band with a gap in it has no join, and two
    # guarantees that exclude each other have no meet — and the answer is to
    # reconcile the contracts, not to reword the call.
    "no_assumption_join": 409, "no_assumption_meet": 409,
    "no_guarantee_meet": 409,
    # A parameter set naming a training set the register does not hold.
    "unknown_snapshot": 422,
    # the fibration (L-15)
    #
    # `no_fibre` is 422 and not 404: the class is a real value, the caller named
    # it correctly, and what is missing is something the platform should have
    # supplied. A 404 would read as "you asked for the wrong thing".
    #
    # `fibration_incomplete` is 503, and it is the only refusal here a caller
    # should never see — the gate runs at start-up, so if it reaches HTTP the
    # platform is serving on a fibration it already knows is partial, and the
    # honest answer is that this instance is not fit to answer.
    "no_fibre": 422, "partial_fibre": 422, "fibre_exists": 409,
    "fibration_incomplete": 503,
    # monitoring
    "kind_not_answerable": 422,
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
    # serialised model artifacts. A neural network or an LLM is not an equation,
    # so the parameter object arrives as bytes; these say whether the bytes, the
    # address, or the declared format is what MAYA is objecting to.
    # The codes are distinct from the engine's `no_artifact`/`artifact_mismatch`
    # further down: those mean the engine could not fetch what a warrant named,
    # which is a 502; these mean the store was asked for something it does not
    # hold or was handed bytes that are not what the caller said they were.
    "unknown_format": 422, "empty_artifact": 422, "malformed_digest": 422,
    "artifact_digest_mismatch": 409, "artifact_too_large": 413,
    "artifact_not_stored": 404,
    # warrant profiles: request defaults, selected by derived facts
    "profile_name_required": 422, "unknown_profile_fact": 422,
    "empty_predicate": 422,
    "empty_profile": 422, "not_defaultable": 422,
    # A profile reaching for authority is not a malformed profile; it is one
    # trying to be a different kind of object, so the status says forbidden and
    # the remediation names the policy gate that CAN hold an obligation.
    "authority_not_defaultable": 403, "no_such_profile": 404,
    # cross-site request forgery. 403 rather than 400: the request was
    # understood, and it is the authority behind it that is not accepted.
    "csrf_token_invalid": 403,
    # export packs. 413 rather than 409: the pack is well-formed and too big to
    # be useful, and the remedy is to narrow what was asked for.
    "pack_too_large": 413,
    # risk appetite and the board pack. Each names what was wrong with the limit
    # rather than with the request: a limit is a governance object, and the
    # refusals are about whether it can do the job of one.
    # `rationale_required` is shared with the overlay register below and mapped
    # there. Two subsystems refuse an unexplained act with the same code and the
    # same remedy, which is right; repeating the key here would silently
    # overwrite the earlier entry.
    "unknown_metric": 422, "unknown_scope": 422,
    "rationale_too_long": 422, "amber_beyond_limit": 422,
    "no_appetite": 404, "no_board_pack": 404,
    # L-16: a regime that obliges and forbids the same term makes every
    # determination unsatisfiable, so it cannot be activated.
    "obligation_contradiction": 422,
    # the documentation graph
    "unknown_subject": 422,
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


def _identify(request: Request, principal: Dict[str, Any]) -> None:
    """Record who is acting, for the log, in both the places it has to reach.

    `core.log` holds one mutable dict per request, so a write from a worker
    thread is visible to the middleware that resumes afterwards — which a
    `ContextVar.set` would not be, since a sync route runs in a threadpool with
    a *copy* of the context. `request.state` is set too: the two costs nothing
    and gives a route a way to ask who is acting without going through logging.
    """
    log.bind_principal(principal["username"])
    request.state.principal = principal["username"]


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


# Characters a browser strips or normalises before resolving a URL, which is how
# `/\tevil.example` and `/\nevil.example` become absolute after passing a naive
# prefix check. They are removed before the check rather than after it.
_STRIPPED = "".join(chr(c) for c in range(0x21)) + "\x7f"


def local_path(target: Optional[str], fallback: str = "/dashboard") -> str:
    """A same-origin path, or the fallback. Never a caller-controlled URL.

    `/login?next=https://evil.example` was honoured, which is the whole of a
    credential-phishing attack: the victim follows a link on the bank's own
    domain, types real credentials into the real login form, and lands on
    somebody else's page believing they arrived by the bank's own redirect. The
    open redirect is what makes the link look legitimate, and it is the part
    that is ours to remove.

    Only a path is accepted. A scheme, a host, a protocol-relative `//host` and
    the backslash variants browsers normalise into one are each replaced by the
    fallback rather than sanitised — a redirect target somebody had to repair is
    a redirect target nobody understands.
    """
    if not target:
        return fallback
    cleaned = "".join(c for c in target if c not in _STRIPPED).strip()
    if not cleaned.startswith("/"):
        return fallback                     # a scheme, a bare host, or nonsense
    if cleaned.startswith(("//", "/\\")):
        return fallback                     # protocol-relative, in both spellings
    parsed = urlsplit(cleaned)
    if parsed.scheme or parsed.netloc:
        return fallback
    return cleaned


def login_required(request: Request) -> Optional[RedirectResponse]:
    """A redirect when the caller is anonymous, otherwise None."""
    if current_user(request) is None:
        return RedirectResponse(
            f"/login?next={quote(local_path(request.url.path), safe='/')}",
            status_code=303)
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
                FindingWorkflowError, PolicyError,
                ArtifactError, ProfileError, ExportError,
                ReportingError, FibreError, RuleError) as exc:
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
                # Bound as soon as it is known, so every line the rest of this
                # request produces says who caused it. The evidence chain
                # records what was decided; the log records what happened around
                # it, and they join on the request id and this name.
                _identify(request, row)
                return row
        if (creds := basic_credentials(request)) is not None:
            if (row := people.authenticate(*creds)) is not None:
                _identify(request, row)
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
                "principle": c.get(
                    "app.principle",
                    "A model is a representation of the world. "
                    "Governance is knowing the difference."),
                "user": current_user(request) if request is not None else None,
                # Every page carries it, because every page can mutate. Minted
                # on first render rather than at sign-in, so a session that
                # predates the control still gets one instead of silently
                # skipping it.
                "csrf_token": (csrf.token_for(request.session)
                               if request is not None else ""),
                # What this principal may do, for the navigation. The menu is
                # built from it rather than from a list of links held in the
                # template, so a menu never offers a screen that answers 403 —
                # and, more importantly, adding a permission to a role changes
                # what the menu shows without anybody editing the menu.
                "may": self._nav_permissions(request)}

    def _nav_permissions(self, request: Optional[Request]) -> frozenset:
        """The signed-in principal's permissions, or nothing.

        Swallows its own failures on purpose: this feeds decoration, and a
        navigation bar must not be the reason a page fails to render. A
        principal who is suspended between sign-in and this call simply sees
        the signed-out menu.
        """
        if request is None:
            return frozenset()
        try:
            username = current_user(request)
            if username is None:
                return frozenset()
            who = self.ctx["principals"].get(username)
            if not who or who.get("status") != "active":
                return frozenset()
            return frozenset(self.ctx["authz"].permissions(who))
        except Exception:                                   # pragma: no cover
            logger.warning("could not resolve navigation permissions",
                           exc_info=True)
            return frozenset()

    def page_principal(self, request: Request):
        """The signed-in principal for a PAGE, resolved from the session.

        `login_required` answers whether somebody is signed in. It does not
        answer who they are or what they may see, and the pages used it alone --
        so a validator scoped to one legal entity got 403 from the API and the
        dashboard correctly hid the model, then loaded the detail page directly
        and received its versions, alias history, warrant grants and full
        evidence chain. Listings filtered; directly-addressable pages did not.
        """
        username = current_user(request)
        if username is None:
            return None
        return self.ctx["principals"].get(username)

    def may_view(self, request: Request, permission: str = "model:read",
                 model: Optional[Dict[str, Any]] = None) -> bool:
        """Whether the signed-in person may see this, by the same rule the API
        applies. One authorisation policy, asked from two places."""
        who = self.page_principal(request)
        if who is None:
            return False
        try:
            self.ctx["authz"].authorise(who, permission, model)
            return True
        except AuthzError as exc:
            swallowed(logger, exc, "decided whether to render a page",
                      detail=f"{who.get('username')} may not {permission}; the "
                             f"page refuses rather than raising, because a page "
                             f"is not an API call",
                      level=logging.INFO)
            return False

    def refused_page(self, request: Request, what: str):
        """A page-shaped refusal, matching the API's 403 rather than pretending
        the thing does not exist."""
        return self.page(request, "forbidden.html", http_status=403, what=what)

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
