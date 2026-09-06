"""
MAYA — the model algebra, on screen.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The model page reads a model. These screens are the operations *on* one:
creating a version and watching its class fall out, proposing a composition
edge, asking whether one version may replace another, moving a record through
its lifecycle, and approving a version by quorum.

Everything here runs against the real application over HTTP, because an
interface tested through a shortcut is an interface nobody has tested. Two rules
shape what is asserted:

* **The screen decides nothing.** So the tests assert that the *platform's*
  verdict reaches the user — the refusal text, the derived class, the named
  fields — rather than that the page drew something. A page that computed the
  same answer locally would pass a test that only looked at the HTML.
* **A refusal is the product.** Half of these tests are refusals, and each one
  checks that the reason survives the trip: `T6` short-circuiting, an edge that
  does not type-check naming the field it fails to provide, an attested record
  refusing a new version, one signature refused where a quorum applies.
"""

import pathlib

import pytest

from tests.api_helpers import login as _login

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "web" / "templates"
SCRIPTS = ROOT / "web" / "static" / "js"

PD = "credit.pd.smallbiz"
ECL = "credit.ecl.stack"
CURVE = "rates.curve.usd"
URN = "maya://model/{}".format

#: A model reading exactly what the PD model produces, so the wire type-checks.
PD_KERNEL = {"parameter_kind": "estimated_coefficients", "fit_procedure": "estimate",
             "input_schema": [{"name": "dscr", "dtype": "float",
                               "minimum": -5, "maximum": 20}],
             "output_schema": [{"name": "pd_12m", "dtype": "float"}]}
ECL_KERNEL = {"parameter_kind": "rule_set", "fit_procedure": "author",
              "input_schema": [{"name": "pd_12m", "dtype": "float"}],
              "output_schema": [{"name": "ecl", "dtype": "float"}]}
CURVE_KERNEL = {"parameter_kind": "calibration_set", "fit_procedure": "calibrate",
                "input_schema": [{"name": "tenor", "dtype": "float"}],
                "output_schema": [{"name": "discount", "dtype": "float"}]}
CONTRACT = {"assumptions": [{"key": "dscr", "minimum": -5, "maximum": 20}],
            "guarantees": [{"key": "gini", "minimum": 0.42}]}
#: The same model with a *narrower* assumption and a withdrawn guarantee: the
#: shape a replacement must not have, and the one L-7 and L-12 exist to catch.
NARROW_CONTRACT = {"assumptions": [{"key": "dscr", "minimum": 0, "maximum": 10}],
                   "guarantees": []}
NARROW_KERNEL = {**PD_KERNEL,
                 "input_schema": [{"name": "dscr", "dtype": "float",
                                   "minimum": 0, "maximum": 10}]}

PAGES = ("/model-algebra",
         f"/model-algebra/version/{PD}",
         "/model-algebra/composition",
         f"/model-algebra/refinement/{PD}",
         f"/model-algebra/lifecycle/{PD}",
         f"/model-algebra/quorum/{PD}",
         f"/model-algebra/risk/{PD}",
         f"/model-algebra/documents/{PD}")


def token(client) -> dict:
    """The session's CSRF token, read off a page as the browser's script reads it.

    Once the client holds a session cookie its authority is ambient, and the
    guard refuses an untokened state-changing request. That is the control
    working, so the tests send the token rather than reaching around it.
    """
    page = client.get("/model-algebra").text
    return {"X-MAYA-CSRF": page.split('name="csrf-token" content="')[1].split('"')[0]}


@pytest.fixture
def estate(client, people):
    """Three models, versioned and tiered, set up over HTTP Basic.

    Basic on purpose, and before anybody signs in: a service credential is not
    ambient authority and needs no token, which keeps the setup out of the way
    of what these tests are actually about.
    """
    owner, dev = people["j.okafor"], people["d.raman"]
    for name, title, kernel, contract in (
            (PD, "SB PD", PD_KERNEL, CONTRACT),
            (ECL, "ECL stack", ECL_KERNEL, {}),
            (CURVE, "USD curve", CURVE_KERNEL, {})):
        r = client.post("/api/v1/models", auth=owner, json={
            "urn": URN(name), "name": title, "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "a worked example"})
        assert r.status_code == 201, r.text
        r = client.post(f"/api/v1/models/{name}/versions", auth=dev,
                        json={"semver": "1.0.0", "kernel": kernel,
                              "contract": contract})
        assert r.status_code == 201, r.text
        r = client.post(f"/api/v1/models/{name}/assess", auth=owner,
                        json={"exposure": 2e9, "purpose_class": "regulatory_capital",
                              "feature_count": 12,
                              "uses_alternative_data": False,
                              "interpretable": True})
        assert r.status_code == 200, r.text
    # The replacement that regresses, created here rather than in each test:
    # once a session exists the acting principal is read from it, so a version
    # created "as the developer" from a signed-in client is not created by the
    # developer at all.
    r = client.post(f"/api/v1/models/{PD}/versions", auth=dev,
                    json={"semver": "1.1.0", "kernel": NARROW_KERNEL,
                          "contract": NARROW_CONTRACT})
    assert r.status_code == 201, r.text
    return client


@pytest.fixture
def signed_in(estate):
    _login(estate)
    return estate


class TestThePagesRender:
    def test_every_screen_renders(self, signed_in):
        for path in PAGES:
            r = signed_in.get(path)
            assert r.status_code == 200, f"{path}: {r.text[:300]}"

    def test_every_screen_redirects_when_anonymous(self, estate):
        for path in PAGES:
            r = estate.get(path, follow_redirects=False)
            assert r.status_code == 303 and "/login" in r.headers["location"], path

    def test_an_unknown_model_is_404_rather_than_an_empty_shell(self, signed_in):
        for path in ("/model-algebra/version/ghost",
                     "/model-algebra/lifecycle/ghost",
                     "/model-algebra/risk/ghost"):
            assert signed_in.get(path).status_code == 404, path

    def test_the_index_publishes_the_whole_base_of_the_fibration(self, signed_in):
        body = signed_in.get("/model-algebra").text
        for name in (f"T{n}" for n in range(9)):
            assert name in body, f"{name} missing from the class table"

    def test_the_index_says_which_relations_compose_and_which_record(self, signed_in):
        body = signed_in.get("/model-algebra").text
        assert "input_to" in body and "challenger_of" in body
        assert "calibrated_by" in body and "benchmark_for" in body
        assert "type-checked" in body.lower()

    def test_the_index_publishes_the_seven_states(self, signed_in):
        body = signed_in.get("/model-algebra").text
        for state in ("draft", "baselined", "submitted", "approved", "attested",
                      "amending", "retired"):
            assert state in body, state


class TestTheTrainabilityDerivation:
    """The class is derived, never declared — and the screen shows the derivation."""

    KERNELS = (
        ({"parameter_kind": "none", "fit_procedure": "none"}, "T0"),
        ({"parameter_kind": "calibration_set", "fit_procedure": "calibrate"}, "T1"),
        ({"parameter_kind": "estimated_coefficients", "fit_procedure": "estimate"}, "T2"),
        ({"parameter_kind": "learned_weights", "fit_procedure": "train"}, "T3"),
        ({"parameter_kind": "learned_weights", "fit_procedure": "train",
          "adaptive": 1}, "T4"),
        ({"parameter_kind": "llm_configuration", "fit_procedure": "configure"}, "T5"),
        ({"parameter_kind": "opaque", "fit_procedure": "train"}, "T6"),
        ({"parameter_kind": "elicited_weights", "fit_procedure": "elicit"}, "T7"),
        ({"parameter_kind": "rule_set", "fit_procedure": "author"}, "T8"),
    )

    def test_each_kernel_derives_its_class(self, signed_in):
        headers = token(signed_in)
        for spec, expected in self.KERNELS:
            r = signed_in.post("/api/v1/model-algebra/kernel", json=spec,
                               headers=headers)
            assert r.status_code == 200, r.text
            assert r.json()["trainability_class"] == expected, spec

    def test_a_terminal_p_is_t0_and_the_fit_procedure_is_not_read(self, signed_in):
        r = signed_in.post("/api/v1/model-algebra/kernel", headers=token(signed_in),
                           json={"parameter_kind": "none", "fit_procedure": "train"})
        out = r.json()
        assert out["trainability_class"] == "T0"
        assert out["requires_fitting_evidence"] == 0
        assert "nothing to fit" in out["derivation"][-1]["says"]

    def test_opaque_short_circuits_before_the_fit_procedure(self, signed_in):
        """T6 is reached without reading anything else, and the page says so."""
        r = signed_in.post("/api/v1/model-algebra/kernel", headers=token(signed_in),
                           json={"parameter_kind": "opaque", "fit_procedure": "estimate"})
        out = r.json()
        assert out["trainability_class"] == "T6"
        assert len(out["derivation"]) == 1, "nothing after opaque may be read"
        assert "short-circuits" in out["derivation"][0]["says"]
        assert out["requires_fitting_evidence"] == 0

    def test_adaptive_separates_t4_from_t3(self, signed_in):
        headers = token(signed_in)
        base = {"parameter_kind": "learned_weights", "fit_procedure": "train"}
        assert signed_in.post("/api/v1/model-algebra/kernel", json=base,
                              headers=headers).json()["trainability_class"] == "T3"
        adaptive = signed_in.post("/api/v1/model-algebra/kernel",
                                  json={**base, "adaptive": 1}, headers=headers)
        assert adaptive.json()["trainability_class"] == "T4"
        assert any("adaptive" in step["reads"]
                   for step in adaptive.json()["derivation"])

    def test_parameters_with_no_fit_procedure_are_refused_on_the_form(self, signed_in):
        """Both halves of the contradiction, in the platform's own words."""
        r = signed_in.post("/api/v1/model-algebra/kernel", headers=token(signed_in),
                           json={"parameter_kind": "learned_weights",
                                 "fit_procedure": "none"})
        out = r.json()
        assert out["ok"] == 0
        assert "has parameters" in out["refusal"]
        assert "nothing produced them" in out["refusal"]

    def test_the_form_shows_the_refusal_the_create_call_would_raise(self, signed_in):
        """Parity. A check that said something different from the write would be
        worse than no check."""
        body = {"parameter_kind": "learned_weights", "fit_procedure": "none"}
        headers = token(signed_in)
        checked = signed_in.post("/api/v1/model-algebra/kernel", json=body,
                                 headers=headers).json()["refusal"]
        written = signed_in.post(f"/api/v1/models/{CURVE}/versions", headers=headers,
                                 json={"semver": "9.9.9", "kernel": body})
        assert written.status_code == 409
        assert written.json()["detail"] == checked

    def test_an_unknown_word_is_refused_rather_than_raised(self, signed_in):
        r = signed_in.post("/api/v1/model-algebra/kernel", headers=token(signed_in),
                           json={"parameter_kind": "nonsense", "fit_procedure": "none"})
        assert r.status_code == 409
        assert "not a parameter kind" in r.json()["detail"]
        assert "learned_weights" in r.json()["detail"], "name the whole vocabulary"

    def test_the_check_says_what_it_did_not_check(self, signed_in):
        r = signed_in.post("/api/v1/model-algebra/kernel", headers=token(signed_in),
                           json={"parameter_kind": "none", "fit_procedure": "none"})
        assert r.json()["not_checked"], "a clean check must not imply a clean write"

    def test_the_derived_class_carries_its_fibre(self, signed_in):
        r = signed_in.post("/api/v1/model-algebra/kernel", headers=token(signed_in),
                           json={"parameter_kind": "learned_weights",
                                 "fit_procedure": "train"})
        fibre = r.json()["fibre"]
        assert fibre["trainability_class"] == "T3"
        assert fibre["evidence"] and fibre["metrics"] and fibre["templates"]

    def test_the_version_page_shows_the_class_of_what_is_on_file(self, signed_in):
        body = signed_in.get(f"/model-algebra/version/{PD}").text
        assert "T2" in body and "estimated_coefficients" in body
        assert "derivation-steps" in body, "the derivation table has to be there"

    def test_a_version_can_be_created_from_the_screen(self, signed_in):
        r = signed_in.post(f"/api/v1/models/{PD}/versions", headers=token(signed_in),
                           json={"semver": "1.2.0", "kernel": PD_KERNEL,
                                 "contract": CONTRACT})
        assert r.status_code == 201, r.text
        assert r.json()["trainability_class"] == "T2"
        assert "1.2.0" in signed_in.get(f"/model-algebra/version/{PD}").text


class TestTypedComposition:
    def test_an_edge_that_type_checks_is_recorded(self, signed_in):
        r = signed_in.post("/api/v1/model-relations", headers=token(signed_in),
                           json={"from_urn": URN(PD), "to_urn": URN(ECL),
                                 "kind": "input_to", "note": "PD into the ECL stack"})
        assert r.status_code == 201, r.text
        assert r.json()["kind"] == "input_to"

    def test_an_edge_that_does_not_type_check_is_refused_naming_the_field(
            self, signed_in):
        """The user is told which field is missing, not that it is 'incompatible'."""
        r = signed_in.post("/api/v1/model-relations", headers=token(signed_in),
                           json={"from_urn": URN(CURVE), "to_urn": URN(ECL),
                                 "kind": "input_to"})
        assert r.status_code == 409
        detail = r.json()["detail"]
        assert "does not compose" in detail
        assert "pd_12m" in detail, "the offending field must be named"
        assert "wire to nowhere" in detail

    def test_a_relation_that_only_records_is_not_type_checked(self, signed_in):
        """The same two ends the `input_to` edge was refused for."""
        r = signed_in.post("/api/v1/model-relations", headers=token(signed_in),
                           json={"from_urn": URN(CURVE), "to_urn": URN(ECL),
                                 "kind": "challenger_of"})
        assert r.status_code == 201, r.text

    def test_the_composite_schema_is_derived_from_the_ends(self, signed_in):
        signed_in.post("/api/v1/model-relations", headers=token(signed_in),
                       json={"from_urn": URN(PD), "to_urn": URN(ECL),
                             "kind": "input_to"})
        r = signed_in.get("/api/v1/model-algebra/composite",
                          params={"from_urn": URN(PD), "to_urn": URN(ECL)})
        assert r.status_code == 200, r.text
        out = r.json()
        assert [f["name"] for f in out["input_schema"]] == ["dscr"]
        assert [f["name"] for f in out["output_schema"]] == ["ecl"]

    def test_a_recorded_edge_reaches_the_page(self, signed_in):
        signed_in.post("/api/v1/model-relations", headers=token(signed_in),
                       json={"from_urn": URN(PD), "to_urn": URN(ECL),
                             "kind": "input_to", "note": "PD into the ECL stack"})
        body = signed_in.get(f"/model-algebra/composition?urn={URN(ECL)}").text
        assert "PD into the ECL stack" in body
        assert "upstream" in body

    def test_the_blast_radius_follows_only_what_propagates(self, signed_in):
        headers = token(signed_in)
        signed_in.post("/api/v1/model-relations", headers=headers,
                       json={"from_urn": URN(PD), "to_urn": URN(ECL),
                             "kind": "input_to"})
        signed_in.post("/api/v1/model-relations", headers=headers,
                       json={"from_urn": URN(CURVE), "to_urn": URN(ECL),
                             "kind": "challenger_of"})
        reached = signed_in.post("/api/v1/blast-radius", headers=headers,
                                 json={"urn": URN(PD)}).json()
        assert reached["count"] == 1
        assert signed_in.post("/api/v1/blast-radius", headers=headers,
                              json={"urn": URN(CURVE)}).json()["count"] == 0


class TestRefinementBetweenVersions:
    def test_a_narrower_replacement_is_refused_and_both_clauses_are_named(
            self, signed_in):
        r = signed_in.post("/api/v1/model-algebra/substitution", headers=token(signed_in),
                           json={"urn": URN(PD), "incumbent": "1.0.0",
                                 "replacement": "1.1.0"})
        out = r.json()
        assert out["ok"] == 0
        assert out["refinement"]["holds"] is False
        assert "dscr" in out["refinement"]["reason"]
        assert "gini" in out["refinement"]["reason"], "a withdrawn guarantee counts"
        assert "dscr" in out["variance"]["reason"]

    def test_the_widening_direction_holds(self, signed_in):
        r = signed_in.post("/api/v1/model-algebra/substitution", headers=token(signed_in),
                           json={"urn": URN(PD), "incumbent": "1.1.0",
                                 "replacement": "1.0.0"})
        assert r.json()["ok"] == 1
        assert "alias move discharges" in r.json()["detail"]

    def test_an_alias_may_only_point_at_an_approved_version(self, signed_in):
        r = signed_in.put(f"/api/v1/models/{PD}/aliases", headers=token(signed_in),
                          json={"environment": "prod", "alias": "champion",
                                "semver": "1.0.0"})
        assert r.status_code == 409
        assert "not approved" in r.json()["detail"]


class TestTheLifecycleMachine:
    def test_the_page_shows_the_machine_and_where_this_record_is(self, signed_in):
        body = signed_in.get(f"/model-algebra/lifecycle/{PD}").text
        assert "draft" in body and "amending" in body
        assert "model:submit" in body, "the permission each move needs"
        assert "baselined" in body

    def test_an_illegal_transition_reaches_the_user_naming_what_is_legal(
            self, estate, people):
        owner = people["j.okafor"]
        assert estate.post(f"/api/v1/models/{PD}/submit", auth=owner,
                           json={"note": ""}).status_code == 200
        r = estate.post(f"/api/v1/models/{PD}/submit", auth=owner, json={"note": ""})
        assert r.status_code == 409
        assert r.json()["error"] == "illegal_transition"
        assert "from here you may" in r.json()["detail"]

    def test_submission_is_refused_without_a_tier(self, client, people):
        """The depth of control depends on the tier, so there is nothing to
        submit into."""
        owner, dev = people["j.okafor"], people["d.raman"]
        client.post("/api/v1/models", auth=owner, json={
            "urn": URN("untiered"), "name": "Untiered", "model_class": "x",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "no tier"})
        client.post("/api/v1/models/untiered/versions", auth=dev,
                    json={"semver": "1.0.0", "kernel": PD_KERNEL})
        r = client.post("/api/v1/models/untiered/submit", auth=owner, json={"note": ""})
        assert r.status_code == 409 and r.json()["error"] == "not_tiered"

    def test_an_attested_record_refuses_a_field_change_and_a_new_version(
            self, estate, people):
        """No session here: attestation is a quorum of people holding roles, and
        one signed-in client is one principal however many credentials it sends."""
        owner, mrm, dev = people["j.okafor"], people["s.iqbal"], people["d.raman"]
        attest(estate, owner, mrm)
        changed = estate.patch(f"/api/v1/models/{PD}", auth=owner,
                               json={"fields": {"purpose": "something else"}})
        assert changed.status_code == 409
        assert "immutable" in changed.json()["detail"]
        added = estate.post(f"/api/v1/models/{PD}/versions", auth=dev,
                            json={"semver": "2.0.0", "kernel": PD_KERNEL})
        assert added.status_code == 409
        assert "amendment" in added.json()["detail"], (
            "the refusal has to name the only route out of immutability")
        _login(estate)
        assert "FROZEN" in estate.get(f"/model-algebra/lifecycle/{PD}").text

    def test_an_amendment_is_that_route(self, estate, people):
        owner, mrm, dev = people["j.okafor"], people["s.iqbal"], people["d.raman"]
        attest(estate, owner, mrm)
        opened = estate.post(f"/api/v1/models/{PD}/amend", auth=owner,
                             json={"reason": "recalibration", "scope": ["kernel"]})
        assert opened.status_code == 200, opened.text
        added = estate.post(f"/api/v1/models/{PD}/versions", auth=dev,
                            json={"semver": "2.0.0", "kernel": PD_KERNEL})
        assert added.status_code == 201, added.text


class TestApprovalAsAQuorum:
    def test_one_signature_is_refused_where_a_quorum_applies(self, signed_in):
        r = signed_in.post(f"/api/v1/models/{PD}/versions/1.0.0/approve",
                           headers=token(signed_in), json={})
        assert r.status_code == 409
        assert r.json()["error"] == "quorum_required"
        assert "not by one signature" in r.json()["detail"]
        assert "/version-approvals" in r.json()["remediation"], (
            "a refusal must name the endpoint that does the right thing")

    def test_the_quorum_a_version_needs_is_shown_on_the_page(self, signed_in):
        body = signed_in.get(f"/model-algebra/quorum/{PD}").text
        assert "model_risk_manager" in body and "validator" in body
        assert "Approve with one signature" in body, (
            "the button is offered on purpose: the refusal is the lesson")

    def test_a_quorum_is_people_rather_than_hats(self, estate, people):
        mrm = people["s.iqbal"]
        opened = estate.post("/api/v1/version-approvals", auth=mrm,
                             json={"urn": URN(PD), "semver": "1.0.0"})
        assert opened.status_code == 201, opened.text
        approval = opened.json()["id"]
        first = estate.post(f"/api/v1/version-approvals/{approval}/sign", auth=mrm,
                            json={"role": "model_risk_manager"})
        assert first.status_code == 200
        again = estate.post(f"/api/v1/version-approvals/{approval}/sign", auth=mrm,
                            json={"role": "validator"})
        assert again.status_code in (403, 409)
        assert again.json()["error"] in ("role_not_held", "already_signed_personally")

    def test_a_completed_quorum_approves_the_version(self, estate, people):
        approve_by_quorum(estate, people)
        _login(estate)
        body = estate.get(f"/model-algebra/quorum/{PD}").text
        assert "approved by 2 signatures" in body


class TestRiskAndTheFibre:
    def test_the_page_shows_the_map_and_the_class_it_reads(self, signed_in):
        body = signed_in.get(f"/model-algebra/risk/{PD}").text
        assert "negligible" in body and "advanced" in body, "the tau grid"
        assert "T2" in body, "the latest version's class is what is read"
        assert "independent_validation" in body, "the controls a tier requires"

    def test_assessing_before_a_version_exists_tiers_an_empty_model(
            self, client, people):
        """Stated on the screen rather than discovered afterwards."""
        owner = people["j.okafor"]
        client.post("/api/v1/models", auth=owner, json={
            "urn": URN("empty"), "name": "Empty", "model_class": "x",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "no versions yet"})
        _login(client)
        body = client.get("/model-algebra/risk/empty").text
        assert "has no versions" in body
        assert "T0" in body
        r = client.post("/api/v1/models/empty/assess", headers=token(client),
                        json={"exposure": 0, "purpose_class": "commercial"})
        assert "class T0" in r.json()["rationale"]

    def test_the_index_shows_what_each_class_owes(self, signed_in):
        body = signed_in.get("/model-algebra").text
        assert "Evidence it owes" in body and "Documents that compile" in body


class TestDocuments:
    def test_the_page_publishes_what_a_document_can_be_about(self, signed_in):
        body = signed_in.get(f"/model-algebra/documents/{PD}").text
        for subject in ("model_version", "parameter_set", "featureset_version",
                        "feature", "validation"):
            assert subject in body, subject

    def test_a_filed_document_reaches_the_page(self, signed_in):
        r = signed_in.post("/api/v1/attachments", headers=token(signed_in),
                           files={"file": ("mdd.md", b"# MDD", "text/markdown")},
                           data={"urn": URN(PD), "kind": "model_development_document",
                                 "title": "MDD for 1.0.0", "semver": "1.0.0"})
        assert r.status_code == 201, r.text
        assert "MDD for 1.0.0" in signed_in.get(f"/model-algebra/documents/{PD}").text

    def test_the_page_says_what_the_register_cannot_answer(self, signed_in):
        """A screen that implied a control it does not have is worse than none."""
        body = signed_in.get(f"/model-algebra/documents/{PD}").text
        assert "subject id names anything" in body


class TestNothingIsExternal:
    """No CDN. An instance that cannot be deployed air-gapped is one somebody
    works around."""

    MARKERS = ("cdn.", "//code.jquery", "googleapis", "jsdelivr", "unpkg",
               "http://", "https://")

    def test_no_screen_references_an_external_asset(self, signed_in):
        for path in PAGES:
            body = signed_in.get(path).text
            for marker in ("cdn.", "//code.jquery", "googleapis", "jsdelivr",
                           "unpkg"):
                assert marker not in body, f"{marker} referenced in {path}"

    def test_the_templates_and_scripts_hold_no_external_reference(self):
        files = (list(TEMPLATES.glob("model_algebra*.html"))
                 + list(SCRIPTS.glob("model-algebra*.js")))
        assert len(files) >= 12, "the walk found nothing, which means it is broken"
        for path in files:
            body = path.read_text(encoding="utf-8")
            for marker in self.MARKERS:
                assert marker not in body, f"{marker} in {path.name}"

    def test_the_screens_are_served_from_disk(self, signed_in):
        for script in sorted(SCRIPTS.glob("model-algebra*.js")):
            r = signed_in.get(f"/static/js/{script.name}")
            assert r.status_code == 200, script.name

    def test_the_screens_add_no_library(self):
        """The whole client stack is Bootstrap, its icons and jQuery. A screen
        that needed a fourth would be a screen doing something in the browser
        that belongs on the server."""
        vendored = {p.name for p in (ROOT / "web" / "static" / "vendor").iterdir()}
        assert vendored == {"bootstrap", "bootstrap-icons", "jquery"}, vendored
        for path in TEMPLATES.glob("model_algebra*.html"):
            body = path.read_text(encoding="utf-8")
            for tag in body.split("<script src=\"")[1:]:
                source = tag.split('"')[0]
                assert source.startswith("/static/js/"), source

    def test_every_table_on_these_screens_has_a_header(self):
        """The rule is enforced across the whole interface elsewhere; asserted
        here too, because these screens are mostly tables."""
        for path in TEMPLATES.glob("model_algebra*.html"):
            body = path.read_text(encoding="utf-8")
            for number, chunk in enumerate(body.split("<table")[1:], 1):
                assert "<thead" in chunk.split("</table>")[0], f"{path.name} #{number}"


# --------------------------------------------------------------------- helpers
def approve_by_quorum(client, people, semver="1.0.0", name=PD):
    """Take a version through the quorum its tier requires, as two people."""
    opened = client.post("/api/v1/version-approvals", auth=people["s.iqbal"],
                         json={"urn": URN(name), "semver": semver})
    assert opened.status_code == 201, opened.text
    approval = opened.json()["id"]
    for who, role in ((people["s.iqbal"], "model_risk_manager"),
                      (people["a.mehta"], "validator")):
        r = client.post(f"/api/v1/version-approvals/{approval}/sign", auth=who,
                        json={"role": role})
        assert r.status_code == 200, r.text
    return approval


def attest(client, owner, mrm, name=PD):
    """Submit, approve and attest, by the people entitled to each act.

    One account cannot walk this path, and that is the point: the owner submits
    and signs the owner's half, the second line approves and signs the other.
    """
    assert client.post(f"/api/v1/models/{name}/submit", auth=owner,
                       json={"note": "ready"}).status_code == 200
    assert client.post(f"/api/v1/models/{name}/approve", auth=mrm,
                       json={"note": "sound"}).status_code == 200
    for who, role in ((owner, "model_owner"), (mrm, "model_risk_manager")):
        r = client.post(f"/api/v1/models/{name}/attest", auth=who,
                        json={"role": role, "decision": "attest"})
        assert r.status_code == 200, r.text
