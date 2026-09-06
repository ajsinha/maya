"""
MAYA — the warrant and package screens.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Two screens that author rather than read, and are therefore tested by being
driven rather than by being scanned: a grant is issued, a fit warrant goes out,
the parameters come back and are approved by somebody else, a scoring warrant
names the point of `P` it runs at, and a pack is cut and opened.

Everything here runs against the real application over HTTP, through the session
cookie a browser would hold, with the CSRF token the page carries. That matters
more than usual on these pages: once a client holds a session its authority is
ambient, so the guard applies to every state-changing call and a test that
authenticated some other way would not be exercising what a user does.

The one thing deliberately not asserted is a *decision*. These screens compute
no governance answer, so there is nothing here of the form "the page correctly
allowed X" — only that the platform's answer, whichever it was, reached the
reader with its remediation attached.
"""
from __future__ import annotations

import io
import json
import pathlib
import re
import zipfile

import pytest
from fastapi.testclient import TestClient

from tests.api_helpers import approve_record, login as _login, quorum_approve as _quorum_approve
from tests.conftest import CONTRACT, KERNEL, NAME, URN

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "web" / "templates"
SCRIPTS = ROOT / "web" / "static" / "js"

#: The templates and scripts these screens own. Named rather than globbed so
#: that a file quietly renamed shows up as a missing asset instead of as one
#: fewer thing being checked.
OWNED_TEMPLATES = ("warrant_author.html", "package.html", "packages.html")
OWNED_SCRIPTS = ("warrant-author.js", "package.js")


def token_of(client) -> str:
    """The session's CSRF token, read off a page exactly as csrf.js reads it."""
    page = client.get("/warrants").text
    return re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)


@pytest.fixture
def signed_in(registered):
    """A browser session on a model already taken to approved and aliased."""
    _login(registered)
    return registered


@pytest.fixture
def csrf(signed_in):
    return {"X-MAYA-CSRF": token_of(signed_in)}


class TestThePagesRender:
    def test_the_warrant_page_redirects_when_anonymous(self, client):
        r = client.get("/warrants", follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]

    def test_the_package_pages_redirect_when_anonymous(self, client):
        for path in ("/packages", f"/packages/{NAME}"):
            r = client.get(path, follow_redirects=False)
            assert r.status_code == 303, path

    def test_the_warrant_page_renders_without_a_model(self, signed_in):
        """The grammar applies to every model, so it reads before one is chosen."""
        body = signed_in.get("/warrants").text
        assert "The fourteen admissibility laws" in body
        assert "Choose a model above" in body

    def test_all_fourteen_laws_are_listed_with_what_they_say(self, signed_in):
        body = signed_in.get("/warrants").text
        for n in range(14):
            assert f"L-W{n}" in body, f"L-W{n} is missing from the page"
        # Quoted from the implementation, not retyped here.
        assert "Fitting is a type error for T0 and T6" in body
        assert "A backtest without outcomes is a re-score" in body

    def test_the_page_says_where_a_law_is_enforced(self, signed_in):
        """L-W10 is not in the grammar and the validator will not report it, so
        a page that listed it beside the others without saying so would send
        somebody looking for it in the wrong place."""
        body = signed_in.get("/warrants").text
        assert "warrant resolution only" in body
        assert "schema_not_satisfied" in body

    def test_the_warrant_page_renders_for_a_model(self, signed_in):
        body = signed_in.get(f"/warrants?model={NAME}").text
        assert "The standing grant" in body
        assert "svc/origination" in body, "the fixture's grant should be listed"
        assert "no_entitlement" in body, "the refusal has to be explained here"

    def test_the_package_index_lists_models_in_scope(self, signed_in):
        body = signed_in.get("/packages").text
        assert "SB PD" in body and f"/packages/{NAME}" in body

    def test_the_package_page_shows_what_a_pack_would_hold(self, signed_in):
        body = signed_in.get(f"/packages/{NAME}").text
        assert "What this pack will contain" in body
        # The three decisions in pack.py that a reader should be able to see.
        assert "excludes the manifest" in body
        assert "gaps.md" in body
        assert "rendered, not compiled" in body.lower() or \
               "Documents are rendered, not compiled" in body

    def test_the_package_page_counts_the_record_it_will_carry(self, signed_in):
        body = signed_in.get(f"/packages/{NAME}").text
        assert "standing grant(s)" in body and "node(s)" in body

    def test_the_package_page_says_parameter_sets_have_no_member(self, signed_in):
        """They travel inside the dossier. Saying so is the difference between a
        reader finding them and concluding the pack dropped them."""
        body = signed_in.get(f"/packages/{NAME}").text
        assert "have no member of their own" in body

    def test_an_unknown_model_is_404_on_both_screens(self, signed_in):
        assert signed_in.get("/warrants?model=ghost").status_code == 404
        assert signed_in.get("/packages/ghost").status_code == 404


class TestScopeIsCheckedOnThePageAndNotOnlyTheApi:
    OTHER = "maya://model/eu.capital.irb"
    OTHER_NAME = "eu.capital.irb"

    def _elsewhere_and_scoped(self, client, people):
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": self.OTHER, "name": "EU IRB", "model_class": "capital.irb",
            "domain": "capital", "owner": "person/j.okafor",
            "legal_entity": "LE-EU-01", "purpose": "IRB capital"})
        client.post("/api/v1/principals", json={
            "username": "uk.val", "display_name": "UK Validator",
            "roles": ["validator"], "password": "uk-pw",
            "legal_entities": ["LE-US-01"], "domains": ["credit"]})

    def test_the_warrant_page_refuses_a_model_out_of_scope(self, registered,
                                                           people):
        """A model's grants say who may run it and for what. That is not a thing
        to render for somebody the API refuses the model to."""
        self._elsewhere_and_scoped(registered, people)
        _login(registered, "uk.val", "uk-pw")
        page = registered.get(f"/warrants?model={self.OTHER_NAME}")
        assert page.status_code == 403
        assert "LE-EU-01" not in page.text

    def test_the_package_page_refuses_it_too(self, registered, people):
        """A pack is the most complete thing this platform produces about a
        model, so it is the largest scope leak available."""
        self._elsewhere_and_scoped(registered, people)
        _login(registered, "uk.val", "uk-pw")
        page = registered.get(f"/packages/{self.OTHER_NAME}")
        assert page.status_code == 403
        assert "IRB capital" not in page.text


class TestARefusalReachesTheReader:
    def test_the_csrf_guard_refuses_an_untokened_post(self, signed_in):
        """Not a defect to work around: once the session cookie is held the
        authority is ambient, and this is the control that says so."""
        r = signed_in.post("/api/v1/warrants", json={
            "urn": URN, "environment": "prod", "principal": "svc/x",
            "declared_use": "y"})
        assert r.status_code == 403
        assert r.json()["error"] == "csrf_token_invalid"

    def test_no_entitlement_arrives_with_its_remediation(self, signed_in, csrf):
        r = signed_in.post("/api/v1/resolve?verb=score", headers=csrf, json={
            "urn": URN, "environment": "prod", "principal": "svc/nobody",
            "declared_use": "origination_decision"})
        problem = r.json()
        assert r.status_code == 403 and problem["error"] == "no_entitlement"
        assert "holds no warrant" in problem["detail"]
        assert "request a warrant grant" in problem["remediation"]

    def test_a_use_that_was_not_approved_is_refused_by_name(self, signed_in, csrf):
        r = signed_in.post("/api/v1/resolve?verb=score", headers=csrf, json={
            "urn": URN, "environment": "prod", "principal": "svc/origination",
            "declared_use": "something_else"})
        assert r.status_code == 403 and r.json()["error"] == "use_not_approved"
        assert r.json()["remediation"]

    def test_the_validator_reports_every_problem_not_the_first(self, signed_in,
                                                               csrf):
        """The property an authoring screen is built around: fixing one error to
        be told about the next is the worst interface for a ten-section
        document."""
        r = signed_in.post("/api/v1/grammar/validate", headers=csrf,
                           json={"maya_warrant": "1.0"})
        report = r.json()
        assert r.status_code == 200 and report["valid"] is False
        assert report["problem_count"] >= 9, report
        assert {p["law"] for p in report["problems"]} == {"L-W0"}
        assert all(p["path"] and p["detail"] and p["remediation"]
                   for p in report["problems"])

    def test_a_law_names_the_path_and_what_to_do(self, signed_in, csrf):
        r = signed_in.post("/api/v1/grammar/validate", headers=csrf, json={
            "maya_warrant": "1.0", "subject": {"trainability_class": "T0"},
            "operation": {"verb": "fit"}, "parameters": {},
            "realisation": {"runtime": "onnx", "entry": {"graph": "g"}},
            "data": {"inputs": [{"binding": "featureset", "featureset": "f",
                                 "version": 1}],
                     "outputs": [{"sink": "response"}]},
            "io_contract": {}, "constraints": {}, "authority": {},
            "governance": {}, "signature": {}})
        laws = {p["law"] for p in r.json()["problems"]}
        assert "L-W1" in laws, r.json()
        assert "L-W4" in laws, "a fit must say where its parameters go"


class TestTheWholeRoundTrip:
    """A grant, a fit warrant, the numbers back, a second person's approval, and
    a scoring warrant that names the point of `P` it runs at."""

    def _fittable(self, client, people):
        """A version MAYA can locate whose parameters live in the REGISTER.

        No artifact: with one, the warrant binds the artifact and the point of
        `P` is inside it. The seed is here because L-W5 requires it — a
        `python.callable` runs code MAYA cannot read, so a claim of determinism
        must be backed by something.
        """
        kernel = {**KERNEL, "runtime": "python.callable", "seed": 20260101,
                  "entry": {"module": "sb.estimators", "attr": "ols_fit"}}
        r = client.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                        json={"semver": "3.3.0", "kernel": kernel,
                              "contract": CONTRACT})
        assert r.status_code == 201, r.text
        _quorum_approve(client, people, "3.3.0")
        assert client.put(f"/api/v1/models/{NAME}/aliases", auth=people["s.iqbal"],
                          json={"environment": "prod", "alias": "challenger",
                                "semver": "3.3.0"}).status_code == 200

    def _featureset(self, client, people):
        dev = people["d.raman"]
        for name, dtype in (("dscr", "float"), ("turnover", "float")):
            client.post("/api/v1/features", auth=dev, json={
                "name": name, "entity": "borrower_id", "dtype": dtype,
                "description": name, "owner": "person/j.okafor"})
        client.post("/api/v1/feature-views", auth=dev, json={
            "name": "sb_credit", "entity": "borrower_id",
            "owner": "person/j.okafor", "features": ["dscr", "turnover"]})
        client.post("/api/v1/feature-views/sb_credit/materialise", auth=dev,
                    json={"rows": [{"entity_id": "B1", "event_ts": 1717200000.0,
                                    "ingest_ts": 1717200000.0, "dscr": 1.4,
                                    "turnover": 250000.0}]})
        client.post("/api/v1/featuresets", auth=dev, json={
            "name": "sb_set", "entity": "borrower_id", "slots": {"dscr": "float"}})
        r = client.post("/api/v1/featuresets/sb_set/versions", auth=dev,
                        json={"bindings": {"dscr": "dscr"}})
        assert r.status_code == 201, r.text

    @pytest.fixture
    def ready(self, registered, people):
        """Set up over HTTP Basic, BEFORE signing in: a client with no session
        carries no ambient authority and therefore needs no token.

        The record is put through the register at the END of this fixture, not
        the start: this loop resolves a warrant, and resolving now requires that
        somebody approved the model record and not only a version of it — but an
        approved record is frozen, so every version this fixture creates has to
        exist before that happens.
        """
        self._fittable(registered, people)
        self._featureset(registered, people)
        # AFTER the version work, because an approved record is frozen.
        approve_record(registered, people)
        _login(registered)
        return registered

    def test_a_grant_is_issued_from_the_screen(self, ready):
        headers = {"X-MAYA-CSRF": token_of(ready)}
        r = ready.post("/api/v1/warrants", headers=headers, json={
            "urn": f"{URN}#challenger", "environment": "prod",
            "principal": "svc/model-lab", "declared_use": "model_development"})
        assert r.status_code == 201, r.text
        grant = r.json()
        assert grant["ttl_seconds"] and grant["id"]
        # And it reaches the page, with the id the parameters will have to name.
        body = ready.get(f"/warrants?model={NAME}").text
        assert grant["id"] in body

    def test_the_whole_loop(self, ready):
        headers = {"X-MAYA-CSRF": token_of(ready)}
        ready.post("/api/v1/warrants", headers=headers, json={
            "urn": f"{URN}@3.3.0", "environment": "prod",
            "principal": "svc/model-lab", "declared_use": "model_development"})

        fit = ready.post("/api/v1/fit-warrants", headers=headers, json={
            "urn": f"{URN}@3.3.0", "environment": "prod",
            "principal": "svc/model-lab", "declared_use": "model_development",
            "featureset": "sb_set", "featureset_version": 1,
            "window": {"from": 1546300800.0, "to": 1735603200.0},
            "as_of": 1736899200.0})
        assert fit.status_code == 201, fit.text
        warrant = fit.json()
        assert warrant["operation"]["verb"] == "fit"
        assert warrant["parameters"]["source"]["binding"] == "to_be_fitted"
        assert warrant["data"]["inputs"][0]["featureset"] == "sb_set"
        # All ten sections, because a page that renders them sectioned needs
        # them all to be there.
        assert set(warrant) >= {"subject", "operation", "parameters",
                                "realisation", "data", "io_contract",
                                "constraints", "authority", "governance",
                                "signature"}

        # The trap the page exists to remove: the descriptor's own id is not
        # what takes delivery of parameters. It is minted per request and never
        # stored; the standing grant is what MAYA persists.
        body = ready.get(f"/warrants?model={NAME}").text
        grant_id = re.search(
            r'data-principal="svc/model-lab"[^>]*data-grant="([^"]+)"',
            body).group(1)
        refused = ready.post("/api/v1/parameters", headers=headers, json={
            "urn": URN, "semver": "3.3.0", "name": "sb-pd-2026q1",
            "kind": "estimated_coefficients", "provenance": "fitted",
            "values": {"intercept": -1.4, "dscr": 0.31},
            "warrant_id": warrant["warrant_id"], "featureset": "sb_set",
            "featureset_version": 1, "as_of": 1736899200.0})
        assert refused.status_code == 404
        assert refused.json()["error"] == "unknown_warrant"

        recorded = ready.post("/api/v1/parameters", headers=headers, json={
            "urn": URN, "semver": "3.3.0", "name": "sb-pd-2026q1",
            "kind": "estimated_coefficients", "provenance": "fitted",
            "values": {"intercept": -1.4, "dscr": 0.31},
            "diagnostics": {"r2": 0.41}, "warrant_id": grant_id,
            "featureset": "sb_set", "featureset_version": 1,
            "as_of": 1736899200.0})
        assert recorded.status_code == 201, recorded.text
        pset = recorded.json()
        assert pset["state"] == "proposed", "a fit is not self-certifying"

        mine = ready.post(f"/api/v1/parameter-sets/{pset['id']}/review",
                          headers=headers, json={"accept": True, "note": "mine"})
        assert mine.status_code == 403
        assert mine.json()["error"] == "self_approval"

        # A second client, with no session of its own: once this one is signed
        # in, `principal()` resolves from the cookie and a Basic header on the
        # same client is ignored.
        with TestClient(ready.app) as other:
            approved = other.post(
                f"/api/v1/parameter-sets/{pset['id']}/review",
                auth=("a.mehta", "val-pw"),
                json={"accept": True, "note": "checked"})
        assert approved.status_code == 200, approved.text

        scored = ready.post("/api/v1/resolve?verb=score", headers=headers, json={
            "urn": f"{URN}#challenger", "environment": "prod",
            "principal": "svc/model-lab", "declared_use": "model_development"})
        assert scored.status_code == 200, scored.text
        source = scored.json()["parameters"]["source"]
        assert source["binding"] == "parameter_set"
        assert source["parameter_set"] == pset["id"]
        assert source["digest"] == pset["digest"]
        # `age_seconds` is what the page renders as "N days old", and it comes
        # from the platform rather than from a subtraction in the browser.
        assert source["as_of"] == 1736899200.0
        assert source["age_seconds"] > 0

        page = ready.get(f"/warrants?model={NAME}").text
        assert "sb-pd-2026q1" in page and "approved" in page

    def test_a_revocation_bumps_the_epoch_and_stops_resolution(self, ready):
        headers = {"X-MAYA-CSRF": token_of(ready)}
        r = ready.post("/api/v1/warrants/revoke", headers=headers,
                       json={"urn": URN, "reason": "model withdrawn"})
        assert r.status_code == 200, r.text
        assert r.json()["revoked"] >= 1 and r.json()["epoch"] >= 1
        again = ready.post("/api/v1/resolve?verb=score", headers=headers, json={
            "urn": URN, "environment": "prod", "principal": "svc/origination",
            "declared_use": "origination_decision"})
        assert again.status_code == 410
        assert again.json()["error"] == "revoked"
        assert "do not retry" in again.json()["remediation"]

    def test_the_page_states_what_grace_does_not_extend(self, ready):
        body = ready.get(f"/warrants?model={NAME}").text
        assert "when the platform is unreachable" in body
        assert "ignorant of a withdrawal" in body


class TestWarrantProfiles:
    def test_a_profile_is_registered_and_reaches_the_page(self, signed_in, csrf):
        r = signed_in.post("/api/v1/warrant-profiles", headers=csrf, json={
            "name": "scored_in_prod", "when": {"environment": ["prod"]},
            "defaults": {"verb": "score", "max_seconds": 5},
            "note": "the ordinary prod score"})
        assert r.status_code == 201, r.text
        assert "scored_in_prod" in signed_in.get(f"/warrants?model={NAME}").text

    def test_a_profile_reaching_for_authority_is_refused(self, signed_in, csrf):
        r = signed_in.post("/api/v1/warrant-profiles", headers=csrf, json={
            "name": "sneaky", "when": {},
            "defaults": {"principal": "svc/anything"}})
        assert r.status_code == 403
        assert r.json()["error"] == "authority_not_defaultable"
        assert "policy" in r.json()["remediation"]

    def test_the_preview_names_where_each_value_came_from(self, signed_in, csrf):
        signed_in.post("/api/v1/warrant-profiles", headers=csrf, json={
            "name": "scored_in_prod", "when": {"environment": ["prod"]},
            "defaults": {"verb": "score"}})
        # The bare NAME, not the urn: the endpoint prefixes what it is given.
        r = signed_in.post("/api/v1/warrant-profiles/preview", headers=csrf,
                           json={"urn": NAME, "environment": "prod",
                                 "request": {}})
        assert r.status_code == 200, r.text
        assert r.json()["applied"]["verb"].startswith("scored_in_prod@")

    def test_the_page_publishes_what_a_profile_may_and_may_not_touch(self,
                                                                     signed_in):
        body = signed_in.get(f"/warrants?model={NAME}").text
        assert "trainability_class" in body and "max_seconds" in body
        assert "declared_use" in body, "the never-defaultable keys are published"


class TestThePackage:
    def test_the_preview_carries_the_manifest_and_the_named_gaps(self, signed_in):
        r = signed_in.get(f"/packages/{NAME}/preview?documents=&attachments=1")
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["content_digest"].startswith("sha256:")
        assert out["files"] and all(f["digest"].startswith("sha256:")
                                    for f in out["files"])
        # The property that distinguishes an honest export: the gaps are the
        # packer's own words, not a second opinion assembled by the page.
        assert out["gaps_markdown"].startswith("# Gaps")
        assert out["gaps"] == 0 or "| `" in out["gaps_markdown"]

    def test_the_manifest_is_not_in_its_own_file_list(self, signed_in):
        out = signed_in.get(f"/packages/{NAME}/preview").json()
        assert all(f["name"] != "manifest.json" for f in out["files"])

    def test_the_pack_downloads_as_an_attachment_and_the_zip_opens(self,
                                                                   signed_in,
                                                                   csrf):
        r = signed_in.post(f"/packages/{NAME}?documents=&attachments=1",
                           headers=csrf)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"
        assert 'attachment; filename="maya-export-' in \
               r.headers["content-disposition"]
        assert r.headers["x-pack-content-digest"].startswith("sha256:")
        archive = zipfile.ZipFile(io.BytesIO(r.content))
        assert archive.testzip() is None
        members = set(archive.namelist())
        assert {"manifest.json", "README.md", "gaps.md", "model.json",
                "versions.json", "evidence/chain.json"} <= members

    def test_the_members_are_what_the_page_said_they_would_be(self, signed_in,
                                                              csrf):
        """The whole point of a preview. The manifest is the one member absent
        from its own list, and the page says so."""
        preview = signed_in.get(f"/packages/{NAME}/preview").json()
        cut = signed_in.post(f"/packages/{NAME}", headers=csrf)
        members = set(zipfile.ZipFile(io.BytesIO(cut.content)).namelist())
        assert {f["name"] for f in preview["files"]} | {"manifest.json"} == members

    def test_a_form_post_with_the_token_in_the_body_downloads(self, signed_in):
        """A form carries no headers, so csrf.js stamps a hidden field. This is
        the path the page's own download button takes."""
        token = token_of(signed_in)
        r = signed_in.post(f"/packages/{NAME}?documents=model_card&attachments=0",
                           data={"csrf_token": token})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"

    def test_narrowing_the_documents_narrows_the_pack(self, signed_in, csrf):
        r = signed_in.post(f"/packages/{NAME}?documents=model_card&attachments=0",
                           headers=csrf)
        members = set(zipfile.ZipFile(io.BytesIO(r.content)).namelist())
        assert "documents/model_card.md" in members
        assert not any(m.startswith("attachments/") for m in members)
        assert "documents/annex_iv.md" not in members

    def test_cutting_one_is_recorded_and_previewing_one_is_not(self, signed_in,
                                                               csrf):
        """Evidence of an export is evidence of a copy being TAKEN. A reader who
        looked at what one would contain has not taken one."""
        def length():
            r = signed_in.get("/api/v1/evidence/chain")
            assert r.status_code == 200, r.text
            return r.json()["length"]

        before = length()
        signed_in.get(f"/packages/{NAME}/preview")
        assert length() == before, "a preview must leave no trace"
        signed_in.post(f"/packages/{NAME}", headers=csrf)
        assert length() == before + 1, "cutting one is a governance act"


class TestNothingIsFetchedFromTheInternet:
    """No CDN. An instance that cannot be deployed air-gapped is one somebody
    works around, and the working-around is what leaves the building."""

    MARKERS = ("cdn.", "//code.jquery", "googleapis", "jsdelivr", "unpkg",
               "http://", "https://")

    def test_the_owned_assets_reference_no_external_host(self):
        for name in OWNED_TEMPLATES:
            body = (TEMPLATES / name).read_text(encoding="utf-8")
            for marker in self.MARKERS:
                assert marker not in body, f"{marker} in {name}"
        for name in OWNED_SCRIPTS:
            body = (SCRIPTS / name).read_text(encoding="utf-8")
            for marker in self.MARKERS:
                assert marker not in body, f"{marker} in {name}"

    def test_the_rendered_pages_reference_no_external_host(self, signed_in):
        for path in ("/warrants", f"/warrants?model={NAME}", "/packages",
                     f"/packages/{NAME}"):
            body = signed_in.get(path).text
            for marker in ("cdn.", "//code.jquery", "googleapis", "jsdelivr",
                           "unpkg"):
                assert marker not in body, f"{marker} referenced in {path}"

    def test_the_scripts_are_served_from_disk(self, client):
        for name in OWNED_SCRIPTS:
            r = client.get(f"/static/js/{name}")
            assert r.status_code == 200, name

    def test_the_pages_load_the_shared_client_stack_and_add_nothing(self,
                                                                    signed_in):
        """csrf.js and tables.js come from the base template. These pages add
        one script each and no library."""
        body = signed_in.get(f"/warrants?model={NAME}").text
        assert "/static/js/csrf.js" in body and "/static/js/tables.js" in body
        assert body.count("<script src=") == 5, "jquery, bootstrap, csrf, tables, ours"


class TestTheMarkupIsWhatTheHouseRulesRequire:
    def test_every_table_this_screen_builds_in_the_browser_has_a_header(self):
        """The template scan in `test_ui_tables` cannot see a table assembled by
        script, and a header-less one is exactly as unusable either way."""
        for name in OWNED_SCRIPTS:
            body = (SCRIPTS / name).read_text(encoding="utf-8")
            assert body.count("<table") == body.count("<thead"), name

    def test_the_owned_templates_have_a_header_on_every_table(self):
        for name in OWNED_TEMPLATES:
            body = (TEMPLATES / name).read_text(encoding="utf-8")
            assert body.count("<table") == body.count("<thead"), name

    def test_no_boolean_is_sent_over_the_wire_by_these_screens(self):
        """0 and 1, in both dialects, in Delta, and in a query string."""
        body = (SCRIPTS / "package.js").read_text(encoding="utf-8")
        assert "attachments=" in body and "true" not in body
