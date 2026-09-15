"""Every model-scoped permission is checked against a model.

The legal-entity scope was opt-in: `authorise(...)` applied it when a route
remembered to pass `model=`, and about a dozen write routes did not. A UK-scoped
validator, refused READ access to a US model, could still sign half its Tier 2
quorum, revoke its production warrant and close its blocking findings.

`authorise` now refuses at run time (`scope_not_checked`), which catches the
paths tests walk. This walks the source instead, so a route added tomorrow and
never exercised is caught too.
"""
from __future__ import annotations

import ast
import pathlib
from typing import List, Tuple

from core.authz.common import MODEL_SCOPED

ROUTES = pathlib.Path(__file__).resolve().parents[1] / "routes"

#: HTML page handlers that carry no permission gate. Each entry is a deliberate
#: decision with the reason written down, not a backlog: a page here must be
#: readable by anybody who is signed in, and its panels must be too.
UNGATED_PAGES = {
    "dashboard": "the landing page; every panel on it is already filtered by "
                 "`visible()`, and a signed-in principal with no permissions "
                 "would otherwise have nowhere to land",
    "telemetry_page": "filtered by `visible()` per model rather than gated as a "
                      "whole; `monitor:read` is held by every human role",
    "notifications_page": "your own digest needs nothing; the estate's delivery "
                          "history is gated inside the handler on "
                          "`principal:read`, matching its endpoint",
    "admin_index": "a directory of the admin screens and the permission each "
                   "needs; it holds no state, and the screens themselves gate",
    "algebra_index": "the vocabulary — relations, classes, states, quorum rules "
                     "— read from the code that enforces them. Rules, not data",
    "packages_index": "filtered by `visible()` rather than gated, because an "
                      "inventory of model names is itself the sensitive part",
}


def test_every_html_page_is_gated_or_listed() -> None:
    """A page handler either checks a permission or appears above with a reason.

    Four screens rendered in full for principals every panel on them refused.
    Adding a fifth should be a decision somebody writes down, not something that
    happens by forgetting.
    """
    ungated = []
    for path in sorted(ROUTES.glob("ui*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            decorators = "".join(ast.unparse(d) for d in node.decorator_list)
            if "HTMLResponse" not in decorators:
                continue
            body = ast.unparse(node)
            checked = any(k in body for k in
                          ("page_gate(", "_gate(", "may_view(", "gate(request",
                           "permits("))
            if not checked and node.name not in UNGATED_PAGES:
                ungated.append(f"{path.name}:{node.name}")
    assert ungated == [], (
        "these page handlers check no permission and are not listed in "
        f"UNGATED_PAGES with a reason: {', '.join(ungated)}")


def _unscoped_checks() -> List[Tuple[str, int, str]]:
    """Every `authorise(..., "<model-scoped>")` call with no `model=`."""
    offences: List[Tuple[str, int, str]] = []
    for path in sorted(ROUTES.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "authorise"):
                continue
            permission = next(
                (a.value for a in node.args
                 if isinstance(a, ast.Constant) and isinstance(a.value, str)
                 and ":" in a.value),
                None)
            if permission not in MODEL_SCOPED:
                continue
            # `estate_wide=` is the argued exception — it does not skip the
            # check, it demands an unrestricted principal instead.
            if not any(kw.arg in ("model", "estate_wide") for kw in node.keywords):
                offences.append((path.name, node.lineno, permission))
    return offences


def test_no_model_scoped_permission_is_checked_without_a_model() -> None:
    offences = _unscoped_checks()
    assert offences == [], (
        "these routes check a permission about one model without saying which, "
        "so the legal-entity scope is not applied: "
        + "; ".join(f"{f}:{line} {perm}" for f, line, perm in offences))


def test_the_scan_can_actually_see_an_offence() -> None:
    """The scanner above must fail on a planted breach, or it proves nothing.

    A previous discipline check in this repository reported success while
    matching nothing at all, so each one now demonstrates its own teeth.
    """
    source = (
        "class R:\n"
        "    def route(self, request):\n"
        "        self.authorise(request, 'version:sign')\n")
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "authorise"]
    assert len(calls) == 1
    permission = calls[0].args[1].value
    assert permission in MODEL_SCOPED
    assert not any(kw.arg in ("model", "estate_wide") for kw in calls[0].keywords)


class TestTheScopeActuallyBites:
    """The static scan proves `model=` is passed. This proves it refuses.

    A scan can only see that an argument is present; it cannot see that the
    argument reaches a check. This walks the HTTP surface as a UK-scoped
    principal who holds every permission the act needs, against a US model.

    One test rather than four because `registered` takes a model through the
    whole governed path and costs about a minute; the three acts below are the
    three shapes — a signature, a warrant, and estate-wide policy — and each
    assertion says which one it is.
    """

    def test_a_uk_scoped_principal_is_refused_every_write_act(
            self, registered, client, people):
        from tests.conftest import NAME, KERNEL, CONTRACT, URN

        # Two principals, not one holding both roles: `model_developer`/`owner`
        # and `validator` are an incompatible pair, so a single UK person
        # carrying the whole list is refused before any scope is reached.
        registered.post("/api/v1/principals", json={
            "username": "uk.validator", "display_name": "UK val",
            "roles": ["validator"],
            "password": "pw-long-enough-x", "legal_entities": ["LE-UK-02"]})
        registered.post("/api/v1/principals", json={
            "username": "uk.owner", "display_name": "UK owner",
            "roles": ["model_owner"],
            "password": "pw-long-enough-x", "legal_entities": ["LE-UK-02"]})
        uk_validator, uk = ("uk.validator", "pw-long-enough-x"), ("uk.owner", "pw-long-enough-x")

        # A signature on a quorum. `registered` already approved 3.2.1, so open
        # the quorum on a fresh version — the record is still in draft, which is
        # what makes adding one legal.
        registered.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                        json={"semver": "3.2.2", "kernel": KERNEL,
                              "contract": CONTRACT,
                              "artifact_digest": "sha256:" + "b" * 64})
        opened = registered.post("/api/v1/version-approvals", auth=people["s.iqbal"],
                                 json={"urn": URN, "semver": "3.2.2"})
        assert opened.status_code == 201, opened.text
        signed = registered.post(
            f"/api/v1/version-approvals/{opened.json()['id']}/sign",
            auth=uk_validator, json={"role": "validator"})
        assert signed.status_code == 403, signed.text
        assert signed.json()["error"] == "out_of_scope", \
            "half a Tier 2 quorum signed from outside the entity"

        # Production authority over a model they cannot read.
        issued = registered.post("/api/v1/warrants", auth=uk, json={
            "urn": URN, "environment": "production", "principal": "batch",
            "declared_use": "origination"})
        assert issued.status_code == 403, issued.text
        assert issued.json()["error"] == "out_of_scope", issued.text

        # Estate-wide policy is not model-scoped, so it demands the whole estate
        # rather than any one model.
        profile = registered.post("/api/v1/warrant-profiles", auth=uk, json={
            "name": "uk-wide", "when": {}, "defaults": {"ttl_days": 3650},
            "note": "reaches every model in every entity"})
        assert profile.status_code == 403, profile.text
        assert profile.json()["error"] == "scope_insufficient", profile.text
        assert "LE-UK-02" in profile.json()["detail"], \
            "say which scope was too narrow"


class TestAMissingSubjectIsFourOhFourAndNotFiveHundred:
    """`model_behind(None)` is None, and `authorise` refuses a model-scoped
    permission with no model as `scope_not_checked` — a 500, deliberately,
    because it means the ROUTE forgot.

    Eleven routes loaded their subject with `.get(id)`, which returns None for
    an id that does not exist. So asking to review an attachment that is not
    there produced a 500 blaming the route, when the honest answer is that the
    attachment is not there. Found by running tutorial 01, which reviews an
    attachment it had failed to create.
    """

    def test_reviewing_an_attachment_that_does_not_exist(self, registered,
                                                         people):
        r = registered.post("/api/v1/attachments/01a000000000000000000000/review",
                            auth=people["s.iqbal"],
                            json={"accept": True, "note": "n/a"})
        assert r.status_code == 404, r.text
        assert r.json()["error"] != "scope_not_checked"

    def test_the_same_for_every_subject_that_carries_a_model(self, registered,
                                                             people):
        absent = "01a000000000000000000000"
        for path, body in (
                (f"/api/v1/overlays/{absent}/approve", None),
                (f"/api/v1/monitors/{absent}/evaluate", {"rows": []}),
                (f"/api/v1/validations/{absent}/results",
                 {"test_key": "discrimination.auc", "left": [], "right": []})):
            r = (registered.post(path, auth=people["s.iqbal"], json=body)
                 if body is not None
                 else registered.post(path, auth=people["s.iqbal"]))
            # 404 or the service's own governed refusal — the register decides
            # how it says "no such thing". What none of them may say is 500.
            assert r.status_code < 500, f"{path} -> {r.status_code} {r.text}"
            assert r.json()["error"] != "scope_not_checked", path
            assert absent in r.json()["detail"], \
                f"{path}: the refusal must name the subject that is missing"


# ---------------------------------------------------------------------------
# An API key narrows what its principal may do — on the routes that ask for a
# permission.
#
# The scope check lives in `Routes.authorise`, so a route that only
# AUTHENTICATES never reaches it and an `api_key_scopes` list narrows nothing
# there. That is defensible exactly while every such route answers a
# VOCABULARY — what a document kind is, what a fibre is, which verbs exist —
# or filters its own answer by `visible()`. It stops being defensible the
# moment somebody adds one that returns estate data, and the failure is
# silent: a key issued for one narrow read would reach it.
#
# So the boundary is written down rather than trusted. A route that
# authenticates without authorising must be listed here, and the list is
# the statement that somebody checked: every one of the parameterless GETs
# below was driven as an UNPRIVILEGED principal against an estate holding a
# marked model and a marked finding, and none of them returned either.
# Adding a route is then a decision — the build fails until somebody puts
# the name here, which is the moment to ask whether it carries an estate.
# ---------------------------------------------------------------------------
AUTHENTICATED_NOT_AUTHORISED = {
    "approval_routes.py::quorum", "artifact_routes.py::formats",
    "assist_routes.py::assist_metrics", "assist_routes.py::list_providers",
    "assist_routes.py::tiers", "attachment_routes.py::kinds",
    "auth_routes.py::login_submit", "baseline_routes.py::gap_catalogue",
    "document_routes.py::kinds", "document_routes.py::subjects",
    "export_routes.py::describe", "feature_routes.py::screening_posture",
    "featureset_routes.py::language", "featureset_routes.py::provenance",
    "featureset_routes.py::retrieval", "finding_routes.py::acts",
    "finding_routes.py::root_posture", "grammar_routes.py::check",
    "grammar_routes.py::conventions_", "grammar_routes.py::deprecations_",
    "grammar_routes.py::fibre", "grammar_routes.py::fibres",
    "grammar_routes.py::grammar", "grammar_routes.py::schema",
    "lifecycle_routes.py::authority_posture",
    "lifecycle_routes.py::condition_kinds", "lifecycle_routes.py::machine",
    "lifecycle_routes.py::profile", "lifecycle_routes.py::profiles",
    "lifecycle_routes.py::stalled", "model_routes.py::assumption_kinds",
    "model_routes.py::classification_levels",
    "model_routes.py::designations",
    "model_routes.py::fact_sourcing_posture",
    "model_routes.py::limitation_kinds", "model_routes.py::relations",
    "model_routes.py::retier_posture",
    "model_routes.py::waivable_controls",
    "monitoring_routes.py::distributed_posture",
    "monitoring_routes.py::kinds", "notification_routes.py::preview",
    "notification_routes.py::status", "overlay_routes.py::kinds",
    "policy_routes.py::facts", "policy_routes.py::gates",
    "principal_routes.py::close_break_glass", "principal_routes.py::me",
    "principal_routes.py::recertification_posture",
    "principal_routes.py::request_break_glass",
    "principal_routes.py::roles", "profile_routes.py::listing",
    "profile_routes.py::preview", "profile_routes.py::vocabulary",
    "reporting_routes.py::cost_posture", "reporting_routes.py::history",
    "reporting_routes.py::in_force", "reporting_routes.py::metrics",
    "reporting_routes.py::portfolio_dimensions",
    "rule_routes.py::extension_points", "rule_routes.py::import_formats",
    "rule_routes.py::vocabulary", "sso_routes.py::callback",
    "telemetry_routes.py::streams", "transfer_routes.py::formats",
    "ui_routes.py::dashboard", "ui_routes.py::document_search_page",
    "ui_routes.py::notifications_page", "ui_routes.py::parameters_page",
    "ui_routes.py::policies_page", "ui_routes.py::query_page",
    "ui_routes.py::telemetry_page", "validation_routes.py::tier_verdicts",
    "validation_routes.py::vendor_checklist",
    "warrant_routes.py::engine_boundary",
    "warrant_routes.py::signing_posture",
}


def _authenticated_not_authorised() -> List[Tuple[str, str]]:
    """Every route handler that calls `principal()` and never `authorise()`."""
    found: List[Tuple[str, str]] = []
    for path in sorted(ROUTES.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                       and d.func.attr in ("get", "post", "put", "delete", "patch")
                       for d in node.decorator_list):
                continue
            body = ast.dump(node)
            if "'authorise'" in body:
                continue
            if "'principal'" not in body:
                continue
            found.append((path.name, node.name))
    return found


def test_a_route_that_only_authenticates_is_a_declared_one() -> None:
    """Adding one is a decision somebody makes, not a default they inherit."""
    undeclared = [f"{f}::{n}" for f, n in _authenticated_not_authorised()
                  if f"{f}::{n}" not in AUTHENTICATED_NOT_AUTHORISED]
    assert undeclared == [], (
        f"{len(undeclared)} route(s) authenticate without asking for a "
        f"permission and are not declared:\n  " + "\n  ".join(undeclared)
        + "\n\nAn API key's scope is applied in `authorise`, so a key narrows "
          "nothing on these. That is safe for a closed vocabulary and for a "
          "handler that filters by `visible()` itself; it is not safe for "
          "anything else. Add the permission, or add the name above with the "
          "reason it carries no estate.")


def test_the_declaration_does_not_outlive_its_routes() -> None:
    """A name left behind after its route was gated reads as a live exemption."""
    live = {f"{f}::{n}" for f, n in _authenticated_not_authorised()}
    stale = sorted(AUTHENTICATED_NOT_AUTHORISED - live)
    assert stale == [], (
        f"{len(stale)} declared exemption(s) name a route that no longer "
        f"exists or now authorises: {stale}. An exemption list nobody prunes "
        f"is one nobody reads.")
