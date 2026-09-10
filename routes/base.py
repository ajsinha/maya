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
from core.classification import ClassificationError
from core.estate.common import EstateError
from core.events.common import EventError
from core.discovery.common import DiscoveryError
from core.plugins.common import PluginError
from core.retention.common import RetentionError
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
from core.apikeys import ApiKeyError
from core.risk.designations import DesignationError
from core.risk.tiering import RiskError
from core.waivers import WaiverError
from core.references.index import ReferencedError
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
    # Same answer as `incompatible_roles`, asked of a role's permissions
    # rather than of a person's roles: nothing is wrong with the request,
    # the duties are.
    "incompatible_permissions": 409,
    "duplicate_principal": 409, "no_such_principal": 404, "unknown_role": 422,
    # Both 409: the request is well-formed, and the register is in a state
    # where granting it would leave nobody able to undo it.
    "self_suspension": 409, "last_administrator": 409,
    # 500, not 403: a model-scoped permission checked without a model is a
    # defect in the route, and the caller may well hold the permission. A 403
    # here would send somebody to ask for access they already have.
    "scope_insufficient": 403,
    "scope_not_checked": 500,
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
    "not_tiered": 409,
    # Asking what an unnamed move costs. 422 rather than 409: the record is in
    # no wrong state — the caller named a transition this machine does not
    # have, and the refusal names the ones it does.
    "unknown_transition": 422,
    # machine assistance budgets. All 422: the request named a number that is
    # not a budget, and the caller can fix it by naming a different one.
    "budget_not_positive": 422, "window_not_positive": 422,
    # data classification. 422 rather than 403: the caller may state this, they
    # just stated a value the lattice does not admit or one below the floor
    # their own model's inputs force.
    "unknown_classification": 422, "below_the_derived_floor": 422,
    # Idempotency and preconditions. 409 for both idempotency conflicts because
    # neither is a malformed request: one is a key already spent on something
    # else, the other a request still running. Mapped HERE and not beside the
    # middleware, because a second status map is the drift this table exists to
    # prevent.
    # Per-grant limits. 429 for all three: the caller did nothing wrong and
    # the answer is *later*, which is what 429 means and what 403 does not.
    # A conditional approval whose terms no longer hold. 409 rather than 403:
    # the caller is entitled, and the model is not — the record is in a state
    # that does not permit the act.
    "approval_condition_broken": 409, "unknown_condition": 422,
    "condition_incomplete": 422, "window_out_of_range": 422,
    "not_attested": 409, "no_condition": 404, "no_version": 404,
    # parallel runs
    "same_version": 422, "purpose_required": 422,
    "run_already_open": 409, "run_concluded": 409,
    "input_key_required": 422, "no_observation": 404,
    "unknown_conclusion": 422, "not_conclusive": 409,
    "no_run": 404,
    # portfolio views
    "unknown_dimension": 422, "same_dimension": 422,
    # retention and legal holds
    "matter_required": 422,
    # document retrieval
    "empty_query": 422,
    # extension points
    "unknown_axis": 422, "axis_closed": 403,
    # discovery
    "scanner_required": 422, "already_triaged": 409,
    # regulatory approvals and the tiering what-if
    "unknown_bom_format": 422, "unknown_predicate": 422,
    "digest_required": 422, "provenance_not_verified": 403,
    "unknown_approval_kind": 422, "regulator_required": 422,
    "not_in_force": 409, "candidate_not_callable": 422,
    "urn_required": 422, "no_candidate": 404,
    "scope_required": 422, "no_hold": 404,
    # the event stream and its subscribers
    "kinds_required": 422, "wildcard_refused": 422,
    "limit_out_of_range": 422, "no_subscription": 404,
    "delivery_refused": 502,
    # compute zones. 403: this is about authority over data, and the
    # answer is not *later* — it is *not from there*.
    "zone_may_not_hold_this_data": 403,
    "purpose_not_permitted_in_zone": 403,
    "rate_limit_reached": 429, "quota_limit_reached": 429,
    "cost_limit_reached": 429, "limit_not_positive": 422,
    "idempotency_key_reused": 409, "idempotency_in_flight": 409,
    "idempotency_key_too_long": 422,
    "precondition_failed": 412, "precondition_unevaluable": 428,
    # break-glass. `same_person` and `reviewed_by_the_user` are 403 because
    # they are refusals of *authority*: this person may not do this act,
    # whoever they are. The rest are 409 — a grant in the wrong state — or 422.
    "same_person": 403, "reviewed_by_the_user": 403,
    "review_outstanding": 409, "not_requested": 409, "not_open": 409,
    "still_open": 409,
    "not_unilateral": 422, "unknown_outcome": 422, "note_required": 422,
    "no_grant": 404,
    "nothing_to_set": 422, "budget_exhausted": 429,
    # A reassessment that re-runs the formula on last year's facts and
    # calls it a review. 422: the request is incomplete, not refused.
    "review_says_nothing": 422, "amendment_open": 409, "attestation_open": 409,
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
    # 422 and not 400: the request is well formed and names a purpose
    # class the estate has not configured, which is the caller's to
    # correct or the risk function's to add — a distinction a bare 400
    # erases.
    "unknown_purpose_class": 422,
    # Not the caller's mistake: the model was found and what is missing is
    # something it has not got yet — a version, and therefore a class. 422
    # rather than 404 for that reason. (`no_fibre` is mapped already, further
    # down, and mapping it twice would silently keep only the last one.)
    "no_class": 422,
    # The waiver register. Every one of these is the caller being told what a
    # waiver has to have before it is one — a bounded window, a reason, and
    # something being done instead — so they are 422 rather than 400, except
    # the two that are about the row's state and the one that is a lookup.
    "unknown_designation": 422,
    # Monitoring plans. `no_plan` is a 404 because the version was
    # found and the plan is what is missing; the other two are about
    # the state of a plan that exists.
    "no_plan": 404, "plan_exists": 409, "already_inherited": 409,
    "unknown_control": 422, "no_rationale": 422,
    "no_compensating_control": 422, "no_expiry": 422,
    "no_such_waiver": 404, "no_reason": 422,
    "proposer_may_not_approve": 409, "role_already_signed": 409,
    "already_closed": 409,
    "nothing_to_fit": 422, "parameters_not_reachable": 422,
    "not_obtained_from_data": 422,
    "warrant_required": 422, "unknown_warrant": 404,
    "warrant_revoked": 410, "warrant_names_another_model": 409,
    "warrant_names_another_version": 409,
    "no_parameters": 422, "parameters_too_large": 413,
    "featureset_required": 422, "self_approval": 403,
    "no_parameter_set": 404, "no_approved_parameters": 409,
    "ambiguous_parameters": 409, "different_version": 409,
    "schema_not_satisfied": 409, "input_schema_not_declared": 409,
    "no_featureset_registry": 501,
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
    # A delete refused because something still points at the thing. 409:
    # the request is well formed and the register is in a state that
    # forbids it, which is exactly what a conflict is.
    "still_referenced": 409,
    # An API key presented for something its scope excludes. 403,
    # not 401: the credential is valid and the act is not permitted
    # to it, which is a different thing from not being signed in.
    "outside_key_scope": 403,
    # A stored scope that is not a list. 500 rather than 403: nothing is
    # wrong with the request, and the platform cannot tell what this
    # credential is permitted to do.
    "key_scope_unreadable": 500,
    "principal_not_active": 409,
    "name_required": 422, "name_in_use": 409,
    "lifetime_refused": 422, "scope_exceeds_principal": 422,
    "no_such_key": 404, "already_revoked": 409,
    # A credential that IS ours and is no longer usable. 401 rather than
    # 403: the caller is not authenticated, and each says WHICH of the four
    # reasons it is — an expired key used to get the anonymous 401, whose
    # remediation told the caller to send the key it was already sending.
    "key_expired": 401, "key_revoked": 401, "key_principal_missing": 401,
    "key_principal_not_active": 401,
    # Roles, now that a bank can define them. 409 where the register is in a
    # state that forbids the act, 422 where the request itself is incomplete.
    "role_exists": 409, "role_in_use": 409, "built_in_role": 409,
    "role_awaited": 409,
    "role_name_required": 422, "role_description_required": 422,
    "role_grants_nothing": 422,
    "unknown_format": 422, "empty_artifact": 422, "malformed_digest": 422,
    "artifact_format_mismatch": 422,
    "artifact_digest_mismatch": 409, "artifact_too_large": 413,
    "artifact_not_stored": 404,
    # The store could not be READ, which is not the same as the artifact
    # not being there. 503: the request is fine and the platform cannot
    # answer it right now.
    "artifact_store_unreadable": 503,
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
    # a chain resolved as one unit, and an answer that must not be used
    "cyclic_composition": 409, "composition_too_deep": 422,
    # 409 and not 403: every node is individually authorised and the
    # composite is refused because of the STATE of one of them, which is
    # a conflict the caller can resolve rather than a permission it lacks.
    "composite_refused": 409,
    "share_out_of_range": 422, "mirrors_required": 422,
    "shadow_use_is_a_production_use": 409,
    # the run register, and the standing approval for a re-fit
    "unknown_verb": 422, "parent_closed": 409,
    "nesting_too_deep": 422, "run_closed": 409, "unknown_run": 404,
    "unknown_trigger": 422, "trigger_required": 422,
    "tier_not_eligible": 403, "author_may_not_approve": 403,
    # a round of asking, and what arrives before a model is a model
    "unknown_campaign_kind": 422, "campaign_already_open": 409,
    "empty_population": 422, "campaign_closed": 409,
    "unknown_response": 422, "not_in_this_campaign": 404,
    "unknown_campaign": 404, "description_required": 422,
    "proposal_already_recorded": 409, "unknown_sourcing": 422,
    "proposal_declined": 409, "not_triaged": 409,
    "unknown_proposal": 404,
    # an equivalence claim about two artifacts, measured elsewhere
    "same_artifact": 422, "ran_by_required": 422,
    "tolerance_required": 422,
    # proposing an encoding, and probes over a declared domain
    "text_too_short": 422, "no_declared_domain": 409,
    # asking in English, and the three things a validator is offered
    "question_required": 422,
    # A service this deployment was built without. 501 rather than 500:
    # nothing is broken, the capability was never wired.
    "no_document_search": 501, "no_findings": 501, "no_assumptions": 501,
    # the semantic layer, saved views and the extracts taken from them
    "unknown_entity": 422, "operator_not_admissible": 422,
    "value_not_a_list": 422, "view_already_saved": 409,
    "not_your_view": 403, "view_not_shared": 403, "unknown_view": 404,
    # A format MAYA declines on purpose, separated from one that does not
    # exist: the first is a decision with a reason and the second is a typo.
    "format_refused": 422, "unknown_return": 404,
    # champion against challenger, and numbers computed elsewhere
    "no_shared_monitor": 409, "unknown_version": 404,
    "two_versions_required": 422, "computed_by_required": 422,
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
    # The formula runtime. `parameter_overridden` is a 409 rather than a
    # 422 because the request is well formed and the conflict is with the
    # approved parameter set; `malformed_expression` is a 409 because the
    # version is immutable and the defect is in what was registered.
    "no_expression": 422, "parameter_overridden": 409,
    "malformed_expression": 409,
    "execution_timeout": 504, "execution_limit": 507,
    "execution_failed": 502,
    # 501: the warrant is valid and this DEPLOYMENT cannot honour it. A limit
    # the warrant states and the platform cannot enforce — POSIX resource
    # limits are unavailable on Windows — is a missing capability here rather
    # than a fault in the request, and the caller's remedy is a different
    # engine rather than a different warrant.
    "limit_not_enforceable": 501,
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
                RiskError, DesignationError, WaiverError,
                OverlayError, AssistError, BaselineError,
                RegimeError, SchedulerError, AttachmentError,
                ParameterError, TelemetryError, NotifyError,
                FindingWorkflowError, PolicyError,
                ArtifactError, ProfileError, ExportError,
                ReportingError, FibreError, RuleError,
                ReferencedError, ApiKeyError,
                ClassificationError, EstateError,
                EventError, RetentionError, PluginError,
                DiscoveryError) as exc:
            # A refusal is normal operation, not a fault — but it is the record of
            # a governance decision, so it is never translated without a trace.
            logger.warning("refused (%s): %s", exc.code, exc)
            raise HTTPException(STATUS.get(exc.code, 400), exc.as_problem()) from exc
        except (RegistryError, FeatureError, AssemblyRejected, ValidationError) as exc:
            # Looked up along the MRO rather than by EXACT type. `type(exc)`
            # was a KeyError the moment anything subclassed one of these, and
            # a KeyError inside the handler that maps refusals is a refusal
            # arriving as a 500 — which is precisely the unmapped failure DR-6
            # forbids, produced by the code that exists to prevent it.
            #
            # `SourceError` is a `FeatureError`, and every one of its refusals
            # 500'd: "a source may only read, and this starts with 'UPDATE'" —
            # a control working perfectly, reported as a crash.
            table = {RegistryError: "registry_refused",
                     FeatureError: "feature_refused",
                     AssemblyRejected: "assembly_rejected",
                     ValidationError: "validation_refused"}
            code = next((table[base] for base in type(exc).__mro__
                         if base in table), "feature_refused")
            logger.warning("refused (%s): %s", code, exc)
            raise HTTPException(STATUS[code], {
                # The refusal's OWN remediation when it carries one. The
                # per-type fallback is right for the common case — most of
                # these are about a definition — and wrong for the ones that
                # are not: "why can I not delete this featureset?" was answered
                # with "correct the feature definition or the view version and
                # retry", an instruction about a different object entirely.
                "error": code, "detail": str(exc),
                "remediation": (getattr(exc, "remediation", "")
                                or next((REMEDY[base] for base in type(exc).__mro__
                                         if base in REMEDY), ""))}) from exc

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
        # An API key, which is how a service authenticates without holding a
        # password. Tried after a session and after Basic because those name a
        # person and this names a credential; where both are present the person
        # is the more specific answer.
        if (row := self._api_key_principal(request)) is not None:
            _identify(request, row)
            return row
        raise HTTPException(401, {
            "error": "unauthenticated",
            "detail": "this endpoint requires an authenticated principal",
            "remediation": "sign in, present HTTP Basic credentials, or send "
                           "an API key as 'Authorization: Bearer maya_sk_…' "
                           "or 'X-API-Key'",
        }, headers={"WWW-Authenticate": 'Basic realm="MAYA"'})

    def _api_key_principal(self, request: Request) -> Optional[Dict[str, Any]]:
        """The principal a key acts as, or None.

        Two headers, because both are what people actually send: `Bearer` is
        what an HTTP client library defaults to, and `X-API-Key` is what a curl
        line somebody typed looks like. Accepting one and not the other buys
        nothing and costs an afternoon.
        """
        keys = self.ctx.get("api_keys")
        if keys is None:
            return None
        header = request.headers.get("authorization") or ""
        secret = ""
        if header.lower().startswith("bearer "):
            secret = header[7:].strip()
        secret = secret or (request.headers.get("x-api-key") or "").strip()
        if not secret:
            return None
        # `authenticate` returns None for a key that is unknown, expired,
        # revoked or whose principal is suspended -- all of which are "not
        # signed in". It RAISES only when the stored credential cannot be read
        # at all, which is not the same answer and must not be flattened into
        # one: a key whose scope column is corrupt would otherwise fall through
        # to the anonymous 401, and an operator would go looking for a key that
        # is present and valid.
        try:
            return keys.authenticate(secret)
        except ApiKeyError as exc:
            logger.error("API key '%s' could not be applied: %s", exc.code,
                         exc.detail)
            raise HTTPException(STATUS.get(exc.code, 500),
                                exc.as_problem()) from exc

    def authorise(self, request: Request, permission: str,
                  model: Optional[Dict[str, Any]] = None,
                  subject_id: Optional[str] = None,
                  about: Optional[str] = None,
                  estate_wide: Optional[str] = None) -> Dict[str, Any]:
        """Authenticate, then check permission, scope and segregation.

        ``subject_id`` is where the evidence lives; ``about`` narrows it to one
        thing when the subject carries evidence for many, as a model does for
        every finding raised against it.

        Returns the principal so the caller can attribute the act to them —
        every governance act is recorded against a real identity rather than
        against 'system'.
        """
        who = self.principal(request)
        # A key narrows what its principal may do, and never widens it. Checked
        # here rather than inside `authorise`, because the narrowing is a
        # property of the CREDENTIAL and authorisation is a property of the
        # identity: a key that carried its own permissions would be a second
        # place permissions come from.
        # Always a list by the time it gets here: `ApiKeyRegister.authenticate`
        # refuses a stored scope that is not one, because this check used to be
        # a SUBSTRING match when the JSON column failed to decode.
        scopes = who.get("api_key_scopes")
        if scopes and permission not in scopes:
            raise HTTPException(403, {
                "error": "outside_key_scope",
                "detail": f"the API key '{who.get('api_key_name')}' does not "
                          f"carry '{permission}', though "
                          f"{who.get('username')} does",
                "remediation": "use a key whose scope covers this, or issue "
                               "one that does — narrowing a key is how a "
                               "service is given only what it needs",
            })
        self.ctx["authz"].authorise(who, permission, model, subject_id, about,
                                    estate_wide)
        return who

    def model_of(self, model_id: str) -> Optional[Dict[str, Any]]:
        """The model a finding, validation or generation belongs to.

        These routes load the subject and have its `model_id`; what they did not
        do is turn it back into a model, so `authorise` had nothing to apply the
        legal-entity scope to. A principal refused READ access to a model could
        close its findings.
        """
        return self.ctx["registry"].catalogue.by_id(model_id)

    def model_behind(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """The model a warrant, monitor, overlay, parameter set, validation or
        attachment hangs off. Every one of those tables has `model_id NOT NULL`,
        so this is total wherever the row exists."""
        if not row:
            return None
        model_id = row.get("model_id")
        return self.model_of(model_id) if model_id else None

    def model_of_subject(self, subject_type: str,
                         subject_id: str) -> Optional[Dict[str, Any]]:
        """The model a generation is about, when its subject has one.

        An assist subject is not always a model — it may be a feature, a
        featureset version or a parameter set — so this returns None rather
        than refusing. What it stops is the case that was open: a UK-scoped
        principal generating and attesting claims about a US model.
        """
        registry = self.ctx["registry"]
        if subject_type == "model":
            return registry.catalogue.by_id(subject_id)
        if subject_type == "model_version":
            version = registry.version_by_id(subject_id)
            return registry.get(version["urn"]) if version else None
        return None

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
        row = self.ctx["principals"].get(username)
        # The same `status == "active"` test `principal()` applies. Without it
        # the two doors disagreed: suspending somebody closed the API and left
        # every PAGE open for the life of their cookie -- up to eight hours of
        # reading the model register, the evidence chains, the findings and the
        # principal list, from an account the administrator had just switched
        # off and reasonably believed was shut out. The screens even went on
        # rendering the Suspend and Set-password buttons, all of which 401.
        if row is None or row["status"] != "active":
            return None
        return row

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

    def page_gate(self, request: Request, permission: str):
        """Signed in, and holding the permission this screen's API needs.

        Returns a response to return, or None to carry on. The permission is the
        SAME one the endpoints behind the page ask for, never a page-only rule:
        two authorisation rules for one screen is exactly how a screen ends up
        rendering in full and then answering 403 to everything it does.
        """
        if (redirect := login_required(request)) is not None:
            return redirect
        who = self.page_principal(request)
        if who is None or not self.ctx["authz"].permits(who, permission):
            return self.refused_page(request, permission)
        return None

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
        brand = self.brand(request)
        # A page may not shadow a brand key.
        #
        # Three pages passed `version=` meaning *the model version* and shadowed
        # `brand()`'s `version`, which is the application's. The footer renders
        # `{{ version }}`, so every one of them printed the whole version record
        # — kernel, schemas and artifact digest — as the footer's text, on a
        # page nobody had opened. Nothing raised, because shadowing is what a
        # merged dict does.
        #
        # This is the same shape as the `status` collision documented above, and
        # the second instance is what makes it worth a check rather than a
        # comment. Refused rather than renamed: a page silently given a
        # different key than it asked for is the next version of this defect.
        if collisions := sorted(set(context) & set(brand)):
            raise RuntimeError(
                f"{template} passes {', '.join(collisions)}, which the brand "
                f"context already supplies. Rename the page's key to what it "
                f"holds — `model_version` rather than `version` — because "
                f"whichever wins, one of the two readers is getting the other's "
                f"value.")
        return self.templates.TemplateResponse(
            request, template, {**brand, **context},
            status_code=http_status)
