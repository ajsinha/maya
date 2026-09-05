"""
MAYA — The rendered interface.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Public pages, sign-in, and every page a signed-in person can reach. A page
with no test is a page that renders Undefined and nobody notices, which is
how three of these were found.

The application, the four principals and a registered model come from
``conftest``; ``quorum_approve`` and ``login`` from ``api_helpers``. Everything
here runs against the real app over HTTP, because an interface tested through a
shortcut is an interface nobody has tested.
"""

import pytest
from fastapi.testclient import TestClient

from tests.api_helpers import login as _login
from tests.conftest import NAME, URN


class TestPublicPages:
    def test_landing_is_public_and_carries_the_slogan(self, client):
        r = client.get("/")
        assert r.status_code == 200 and "Evidence, not assertion." in r.text

    def test_landing_explains_the_name(self, client):
        assert "m\u0101y\u0101" in client.get("/").text or "maya" in client.get("/").text.lower()

    def test_about_is_public(self, client):
        r = client.get("/about")
        assert r.status_code == 200 and "does not execute models" in r.text

    def test_help_lists_topic_cards_from_the_content_directory(self, client):
        body = client.get("/help").text
        assert "Documentation" in body
        # Cards, not a hard-coded walkthrough: the topics come from markdown on disk.
        assert "/help/quickstart" in body and "/help/registering-a-model" in body
        assert "Getting started" in body and "Reference" in body

    def test_a_help_topic_renders_its_markdown(self, client):
        body = client.get("/help/features-and-two-clocks").text
        assert body.count("<h2") >= 2, "headings should be rendered, not escaped"
        assert "<table>" in body, "markdown tables should render as tables"
        assert "content/help/" in body, "the source file is cited on the page"

    def test_an_unknown_help_topic_is_404(self, client):
        assert client.get("/help/no-such-topic").status_code == 404

    def test_help_is_reachable_without_signing_in(self, client):
        assert client.get("/help").status_code == 200
        assert client.get("/help/glossary").status_code == 200

    def test_about_carries_the_competitive_analysis(self, client):
        body = client.get("/about").text
        assert "Competitive analysis" in body
        assert "OpenPages" in body and "MLflow" in body
        assert "Where MAYA is weaker today" in body, "positioning must state weaknesses too"

    def test_landing_offers_sign_in_when_anonymous(self, client):
        assert "/login" in client.get("/").text

class TestAuthentication:
    def test_login_page_renders(self, client):
        assert client.get("/login").status_code == 200

    def test_valid_credentials_redirect_to_the_dashboard(self, client):
        r = _login(client)
        assert r.status_code == 303 and r.headers["location"] == "/dashboard"

    def test_invalid_password_is_rejected(self, client):
        r = _login(client, password="wrong")
        assert r.status_code == 401 and "not recognised" in r.text

    def test_invalid_username_is_rejected(self, client):
        assert _login(client, username="nobody").status_code == 401

    def test_dashboard_redirects_when_anonymous(self, client):
        r = client.get("/dashboard", follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]

    def test_model_page_redirects_when_anonymous(self, client):
        r = client.get(f"/model/{NAME}", follow_redirects=False)
        assert r.status_code == 303

    def test_logout_clears_the_session(self, client):
        _login(client)
        client.get("/logout", follow_redirects=False)
        assert client.get("/dashboard", follow_redirects=False).status_code == 303

class TestAuthenticatedInterface:
    @pytest.fixture
    def signed_in(self, registered):
        _login(registered)
        return registered

    def test_dashboard_lists_a_registered_model(self, signed_in):
        assert "SB PD" in signed_in.get("/dashboard").text

    def test_model_page_renders(self, signed_in):
        html = signed_in.get(f"/model/{NAME}").text
        assert "SB PD" in html and "3.2.1" in html and "TIER" in html

    def test_unknown_model_page_is_404(self, signed_in):
        assert signed_in.get("/model/ghost").status_code == 404

    def test_no_cdn_references_anywhere(self, signed_in):
        """Every asset must be vendored: the UI has to work air-gapped."""
        for path in ("/", "/about", "/help", "/login", "/dashboard", f"/model/{NAME}",
                     "/policies", "/notifications", "/telemetry",
                     f"/telemetry/3.2.1/{NAME}", f"/parameters/3.2.1/{NAME}"):
            html = signed_in.get(path).text
            for marker in ("cdn.", "//code.jquery", "googleapis", "jsdelivr", "unpkg"):
                assert marker not in html, f"{marker} referenced in {path}"

    def test_vendored_assets_are_served(self, client):
        for asset in ("/static/vendor/bootstrap/css/bootstrap.min.css",
                      "/static/vendor/jquery/jquery.min.js",
                      "/static/img/maya-mark-64.png"):
            assert client.get(asset).status_code == 200, asset

class TestTutorialsArea:
    def test_the_tutorials_index_renders_cards(self, client):
        body = client.get("/tutorials").text
        assert "Working through MAYA" in body
        assert "/tutorials/end-to-end" in body
        assert "/tutorials/warrants-and-training" in body

    def test_a_tutorial_renders_its_markdown(self, client):
        body = client.get("/tutorials/features").text
        assert "<table>" in body and body.count("<h2") >= 3

    def test_every_shipped_tutorial_renders(self, client):
        """Named individually rather than globbed, so deleting one is a test
        failure rather than a silently smaller loop."""
        for slug in ("defining-a-model", "features", "featuresets",
                     "warrants-and-training", "model-package", "end-to-end"):
            assert client.get(f"/tutorials/{slug}").status_code == 200, slug

    def test_an_unknown_tutorial_is_404(self, client):
        assert client.get("/tutorials/nope").status_code == 404

    def test_tutorials_are_public(self, client):
        anon = TestClient(client.app)
        assert anon.get("/tutorials").status_code == 200
        assert anon.get("/tutorials/end-to-end").status_code == 200

    def test_help_still_works_alongside_tutorials(self, client):
        assert client.get("/help").status_code == 200
        assert client.get("/help/warrants").status_code == 200

class TestDashboardEstate:
    def test_the_dashboard_shows_the_estate_and_your_own_work(self, registered,
                                                              people):
        registered.post("/login", data={"username": "admin", "password": "admin123",
                                        "next": "/dashboard"})
        body = registered.get("/dashboard").text
        assert "models registered" in body
        assert "blocking findings" in body and "open breaches" in body
        assert "Outstanding for you" in body

    def test_an_outstanding_signature_reaches_the_person_who_can_sign(
            self, registered, people):
        owner, mrm = people["j.okafor"], people["s.iqbal"]
        r1 = registered.post(f"/api/v1/models/{NAME}/submit", auth=owner, json={})
        assert r1.status_code == 200, r1.text
        r2 = registered.post(f"/api/v1/models/{NAME}/approve", auth=mrm, json={})
        assert r2.status_code == 200, r2.text

        client = TestClient(registered.app)
        client.post("/login", data={"username": owner[0], "password": owner[1],
                                    "next": "/dashboard"})
        body = client.get("/dashboard").text
        assert "Attestation outstanding: model_owner" in body
        assert "Attestation outstanding: model_risk_manager" not in body, \
            "the owner is not shown somebody else's signature"

    def test_the_worklist_explains_that_it_cannot_go_stale(self, registered,
                                                           people):
        owner = people["j.okafor"]
        registered.post(f"/api/v1/models/{NAME}/submit", auth=owner, json={})
        client = TestClient(registered.app)
        val = people["a.mehta"]
        client.post("/login", data={"username": val[0], "password": val[1],
                                    "next": "/dashboard"})
        body = client.get("/dashboard").text
        assert "computed from the register rather than assigned" in body

class TestFeatureAndFeaturesetPages:
    """Managing features through the interface, not only through curl."""

    def _catalogue(self, client, auth):
        for name, dtype in [("dscr", "numeric"), ("turnover", "numeric")]:
            client.post("/api/v1/features", auth=auth, json={
                "name": name, "entity": "borrower_id", "dtype": dtype,
                "description": f"SB {name}", "owner": "person/j.okafor"})

    def test_the_features_page_lists_the_catalogue(self, registered, people):
        self._catalogue(registered, people["d.raman"])
        registered.post("/api/v1/derived-features", auth=people["d.raman"], json={
            "name": "coverage", "expression": "turnover / dscr",
            "dtype": "numeric", "description": "turnover per unit of cover"})
        _login(registered)
        page = registered.get("/features").text
        assert "dscr" in page and "coverage" in page
        assert "turnover / dscr" in page, "a derived feature shows its expression"

    def test_the_featuresets_page_lists_declared_sets(self, registered, people):
        self._catalogue(registered, people["d.raman"])
        registered.post("/api/v1/featuresets", auth=people["d.raman"], json={
            "name": "sb_core", "entity": "borrower_id",
            "slots": {"dscr": "numeric"}})
        _login(registered)
        assert "sb_core" in registered.get("/featuresets").text

    def test_a_featureset_page_shows_its_schema_and_pins(self, registered, people):
        dev = people["d.raman"]
        self._catalogue(registered, dev)
        registered.post("/api/v1/feature-views", auth=dev, json={
            "name": "sb_credit", "entity": "borrower_id",
            "owner": "person/j.okafor", "features": ["dscr", "turnover"]})
        registered.post("/api/v1/feature-views/sb_credit/materialise", auth=dev,
                        json={"rows": [{"entity_id": "B1", "event_ts": 1.0,
                                        "ingest_ts": 1.0, "dscr": 1.4,
                                        "turnover": 250000.0}]})
        registered.post("/api/v1/featuresets", auth=dev, json={
            "name": "sb_core", "entity": "borrower_id",
            "slots": {"dscr": "numeric"}})
        registered.post("/api/v1/featuresets/sb_core/versions", auth=dev,
                        json={"bindings": {"dscr": "dscr"}})
        _login(registered)
        page = registered.get("/featureset/sb_core").text
        assert "features/borrower_id/sb_credit/v1" in page
        assert "delta v" in page, "the page shows the pin, not only the path"

    def test_a_feature_view_page_offers_the_bulk_formats(self, registered, people):
        dev = people["d.raman"]
        self._catalogue(registered, dev)
        registered.post("/api/v1/feature-views", auth=dev, json={
            "name": "sb_credit", "entity": "borrower_id",
            "owner": "person/j.okafor", "features": ["dscr"]})
        registered.post("/api/v1/feature-views/sb_credit/materialise", auth=dev,
                        json={"rows": [{"entity_id": "B1", "event_ts": 1.0,
                                        "ingest_ts": 1.0, "dscr": 1.4}]})
        _login(registered)
        page = registered.get("/feature-views/sb_credit").text
        assert "parquet" in page and "arrow" in page

    def test_the_new_model_page_offers_the_kernel_vocabulary(self, registered):
        _login(registered)
        page = registered.get("/models/new").text
        assert "estimated_coefficients" in page
        assert "descriptor_only" in page

class TestThePolicyPage:
    """The point of the policy engine is that a gate can be changed by somebody
    who is not deploying code. That person is not going to use curl, so a gate
    with no page is a gate only engineers can move."""

    CASES = [{"name": "no blocking findings", "expect": "allow",
              "facts": {"blocking_findings": 0, "tier": 1}},
             {"name": "a blocking finding stops it", "expect": "refuse",
              "facts": {"blocking_findings": 1, "tier": 1}}]

    def _draft(self, client, people, **overrides):
        body = {"gate": "version:approve", "rule": "blocking_findings == 0",
                "reason": "as shipped, written down", "cases": self.CASES}
        body.update(overrides)
        return client.post("/api/v1/policies", auth=people["a.mehta"], json=body)

    def test_the_page_shows_the_rule_in_force_on_every_gate(self, registered):
        """A page naming the gates without quoting their rules would leave the
        reader to assume what is in force, which is the state of affairs the
        register exists to end."""
        _login(registered)
        page = registered.get("/policies").text
        assert "blocking_findings == 0 and tier is not None" in page
        for gate in ("version:approve", "alias:move", "model:mutate",
                     "warrant:resolve"):
            assert gate in page, gate
        assert "built in" in page, "an instance that has published nothing says so"

    def test_the_page_lists_the_facts_a_gate_may_read(self, registered):
        """A rule may read these and nothing else, so a person writing one needs
        the whole vocabulary in front of them rather than in the source."""
        _login(registered)
        page = registered.get("/policies").text
        assert "refinement_holds" in page
        assert "whether the new contract refines the incumbent" in page

    def test_the_page_carries_the_promise_that_a_policy_only_tightens(
            self, registered):
        """A mistyped rule that weakened the platform would look like a
        successful deployment, so the page says what a policy cannot do where
        somebody drafting one will read it."""
        _login(registered)
        page = registered.get("/policies").text
        assert "never instead of them" in page
        assert "add a condition" in page

    def test_a_published_rule_replaces_the_built_in_one_on_the_page(
            self, registered, people):
        drafted = self._draft(registered, people, gate="warrant:resolve",
                              rule="environment != 'prod'",
                              reason="prod is frozen during the change freeze",
                              cases=[{"name": "lab is fine", "expect": "allow",
                                      "facts": {"environment": "lab"}},
                                     {"name": "prod is not", "expect": "refuse",
                                      "facts": {"environment": "prod"}}]).json()
        registered.post(f"/api/v1/policies/{drafted['id']}/publish",
                        auth=people["s.iqbal"])
        _login(registered)
        page = registered.get("/policies").text
        assert "prod is frozen during the change freeze" in page
        assert "published v1" in page

    def test_a_draft_is_shown_as_not_in_force_and_offered_for_publication(
            self, registered, people):
        """Authoring and publishing are separate duties, so the person who did
        not write the rule has to be able to find it."""
        drafted = self._draft(registered, people).json()
        _login(registered)
        page = registered.get("/policies").text
        assert "as shipped, written down" in page
        assert 'data-id="%s"' % drafted["id"] in page
        assert "drafted, not in force" in page

    def test_the_history_keeps_the_version_a_publish_superseded(
            self, registered, people):
        """'Which rule was in force in March' is a question somebody will ask,
        and a page showing only the current rule could not answer it."""
        first = self._draft(registered, people).json()
        registered.post(f"/api/v1/policies/{first['id']}/publish",
                        auth=people["s.iqbal"])
        second = self._draft(
            registered, people, rule="blocking_findings == 0 and documents",
            reason="a version is not approved with nothing on file",
            cases=[{"name": "documented", "expect": "allow",
                    "facts": {"blocking_findings": 0, "documents": 1}},
                   {"name": "nothing on file", "expect": "refuse",
                    "facts": {"blocking_findings": 0, "documents": 0}}]).json()
        registered.post(f"/api/v1/policies/{second['id']}/publish",
                        auth=people["s.iqbal"])
        _login(registered)
        page = registered.get("/policies").text
        assert "superseded" in page
        assert "as shipped, written down" in page
        assert "a version is not approved with nothing on file" in page

    def test_a_publication_that_loosened_a_gate_says_so_afterwards(
            self, registered, people):
        """The drift report is returned to whoever published, and a report that
        existed only in that response would be a governance fact nobody could
        revisit. 'When did this gate get looser' is asked months later."""
        first = self._draft(registered, people).json()
        registered.post(f"/api/v1/policies/{first['id']}/publish",
                        auth=people["s.iqbal"])
        looser = self._draft(
            registered, people, rule="tier is not None",
            reason="deliberately looser",
            cases=[{"name": "tiered", "expect": "allow", "facts": {"tier": 1}},
                   {"name": "untiered", "expect": "refuse",
                    "facts": {"tier": None}}]).json()
        published = registered.post(f"/api/v1/policies/{looser['id']}/publish",
                                    auth=people["s.iqbal"]).json()
        assert published["drift"]["loosened"], "the publish itself reported it"
        _login(registered)
        page = registered.get("/policies").text
        assert "are now permitted" in page

    def test_the_first_policy_on_a_gate_says_there_was_nothing_to_compare(
            self, registered, people):
        drafted = self._draft(registered, people).json()
        registered.post(f"/api/v1/policies/{drafted['id']}/publish",
                        auth=people["s.iqbal"])
        _login(registered)
        page = registered.get("/policies").text
        assert "nothing was in force on this gate before" in page

    def test_the_cases_a_policy_carries_are_reported_on_the_page(
            self, registered, people):
        """A policy nobody has shown to refuse anything is a policy nobody has
        shown to be a gate, so the page reports its cases rather than its mere
        existence."""
        self._draft(registered, people)
        _login(registered)
        page = registered.get("/policies").text
        assert "all behave as declared" in page

    def test_the_page_publishes_the_language_a_rule_is_written_in(self, registered):
        _login(registered)
        page = registered.get("/policies").text
        assert "predicate, not a program" in page
        assert "vacuously true of nothing" in page

    def test_the_policy_page_redirects_when_anonymous(self, client):
        r = client.get("/policies", follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]

class TestTheNotificationsPage:
    """Silence about a failed send is how somebody concludes they were never
    told. The page is where that record becomes legible."""

    def _finding(self, client, people):
        return client.post("/api/v1/findings", auth=people["s.iqbal"], json={
            "urn": URN, "severity": "Critical", "title": "Leakage",
            "owner": "person/j.okafor"})

    def test_the_page_says_which_channels_are_usable_and_why_the_others_are_not(
            self, registered):
        """An instance that quietly needed an SMTP relay in order to tell anybody
        anything would fail in a way nobody could diagnose from outside."""
        _login(registered)
        page = registered.get("/notifications").text
        assert "notifications.email.host" in page
        assert "notifications.webhook.url" in page
        assert "written to the platform log" in page

    def test_the_page_previews_what_the_signed_in_person_would_receive(
            self, registered, people):
        """The same derivation the dashboard reads and the same one a run would
        send, so nobody has to send a message to find out what it says."""
        self._finding(registered, people)
        _login(registered)
        page = registered.get("/notifications").text
        assert "Leakage" in page
        assert "Critical finding" in page

    def test_a_suppression_is_kept_in_the_record_with_its_reason(
            self, registered, people):
        """A message repeating yesterday's is one somebody filters. The
        suppression is shown, so quiet is distinguishable from broken."""
        self._finding(registered, people)
        registered.post("/api/v1/notifications/run", json={})
        registered.post("/api/v1/notifications/run", json={})
        _login(registered)
        page = registered.get("/notifications").text
        assert "suppressed" in page
        assert "the same outstanding work was notified" in page

    def test_a_delivery_that_reached_somebody_names_them(self, registered, people):
        self._finding(registered, people)
        registered.post("/api/v1/notifications/run", json={})
        _login(registered)
        page = registered.get("/notifications").text
        assert "j.okafor" in page
        assert "written to the platform log" in page

    def test_the_empty_state_teaches_rather_than_saying_no_data(self, registered):
        _login(registered)
        page = registered.get("/notifications").text
        assert "Nothing has been sent from this instance" in page
        assert "without looking" in page

    def test_the_notifications_page_redirects_when_anonymous(self, client):
        r = client.get("/notifications", follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]

class TestTheTelemetryPages:
    """A model that has stopped sending is the thing worth noticing, and a list
    sorted by name buries it under the ones that are fine."""

    OLD = 1700000000.0          # comfortably in the past, whenever this runs

    def _scores(self, client, count=3, at=OLD, rate=1.0, semver="3.2.1"):
        return client.post("/api/v1/telemetry", json={
            "urn": URN, "semver": semver, "stream": "scores",
            "sample_rate": rate, "source": "origination",
            "rows": [{"entity_id": f"B{i}", "scored_at": at + i,
                      "score": 0.1 + i / 100} for i in range(count)]})

    def _outcomes(self, client, count=1, at=OLD, semver="3.2.1"):
        return client.post("/api/v1/telemetry", json={
            "urn": URN, "semver": semver, "stream": "outcomes",
            "rows": [{"entity_id": f"B{i}", "label": 1, "label_ts": at + 100 + i}
                     for i in range(count)]})

    def test_telemetry_can_be_delivered_over_the_api_at_all(self, registered):
        """The ingestion endpoint asked for a permission that did not exist, so
        every delivery was refused as unknown_permission — for everybody,
        an administrator included. Nothing could ever be ingested, and no test
        reached the endpoint to notice."""
        assert self._scores(registered).status_code == 201

    def test_a_version_that_has_stopped_sending_leads_the_page(self, registered):
        self._scores(registered)
        _login(registered)
        page = registered.get("/telemetry").text
        assert "have stopped sending" in page
        assert "since anything was scored" in page
        assert "SB PD v3.2.1" in page
        assert "nothing scored for" in page

    def test_a_version_that_has_never_sent_says_so(self, registered):
        """Silence and never having started are different facts, and only one of
        them means somebody switched a collector off."""
        _login(registered)
        page = registered.get("/telemetry").text
        assert "never sent" in page
        assert "have never sent anything" in page
        assert "cannot be evaluated from storage" in page

    def test_a_sampled_stream_says_what_it_speaks_for(self, registered):
        self._scores(registered, rate=0.1)
        _login(registered)
        page = registered.get("/telemetry").text
        assert "speaks for the sample" in page
        assert "10.0%" in page

    def test_the_version_page_keeps_the_unlabelled_rows(self, registered):
        """A join that dropped them would show a cohort that looks complete and
        is not, which is the exact mistake the delayed-label discipline exists
        to prevent."""
        self._scores(registered, count=3)
        self._outcomes(registered, count=1)
        _login(registered)
        page = registered.get(f"/telemetry/3.2.1/{NAME}").text
        assert "B0" in page and "B2" in page
        assert "not known yet" in page
        assert "1 of 3 rows have an outcome" in page

    def test_the_version_page_names_the_two_streams_and_their_counts(
            self, registered):
        self._scores(registered, count=3)
        _login(registered)
        page = registered.get(f"/telemetry/3.2.1/{NAME}").text
        assert "what the model produced, when it produced it" in page
        assert "what actually happened, learned afterwards" in page
        assert "3 rows" in page

    def test_an_unknown_version_is_404_rather_than_an_empty_page(self, registered):
        """An empty shell for a version that does not exist reads as a version
        with nothing recorded against it."""
        _login(registered)
        assert registered.get(f"/telemetry/9.9.9/{NAME}").status_code == 404

    def test_the_telemetry_page_redirects_when_anonymous(self, client):
        r = client.get("/telemetry", follow_redirects=False)
        assert r.status_code == 303 and "/login" in r.headers["location"]

class TestTheParametersPage:
    """A parameter set changes what the model does. Approving one from a card
    that shows neither its values nor its diagnostics is approving numbers
    nobody has seen."""

    def _record(self, client, auth, **kw):
        body = {"urn": URN, "semver": "3.2.1", "name": "sb-pd-2025q1",
                "kind": "estimated_coefficients",
                "values": {"intercept": -1.4, "turnover": 0.31},
                "diagnostics": {"gini": 0.62, "observations": 40218},
                "provenance": "declared", "note": "carried over from the pilot"}
        body.update(kw)
        return client.post("/api/v1/parameters", auth=auth, json=body)

    def test_the_page_shows_the_values_a_reviewer_has_to_judge(
            self, registered, people):
        self._record(registered, people["d.raman"])
        _login(registered)
        page = registered.get(f"/parameters/3.2.1/{NAME}").text
        assert "intercept" in page and "-1.4" in page
        assert "turnover" in page and "0.31" in page

    def test_the_page_shows_the_diagnostics_the_fit_reported(
            self, registered, people):
        """An approver deciding without them is approving numbers they have no
        way to challenge."""
        self._record(registered, people["d.raman"])
        _login(registered)
        page = registered.get(f"/parameters/3.2.1/{NAME}").text
        assert "gini" in page and "0.62" in page
        assert "observations" in page and "40218" in page

    def test_the_page_says_the_version_cannot_run_until_something_is_approved(
            self, registered):
        _login(registered)
        page = registered.get(f"/parameters/3.2.1/{NAME}").text
        assert "cannot be run until it has some" in page
        assert "not ready" in page

    def test_an_unapproved_set_is_shown_as_awaiting_somebody_else(
            self, registered, people):
        self._record(registered, people["d.raman"])
        _login(registered)
        page = registered.get(f"/parameters/3.2.1/{NAME}").text
        assert "awaiting approval" in page
        assert "carried over from the pilot" in page
        assert "Reject" in page, "a reviewer needs both answers, not only one"

    def test_an_approved_set_names_who_approved_it_and_what_runs(
            self, registered, people):
        recorded = self._record(registered, people["d.raman"]).json()
        registered.post(f"/api/v1/parameter-sets/{recorded['id']}/review",
                        auth=people["a.mehta"],
                        json={"accept": True, "note": "residuals reviewed"})
        _login(registered)
        page = registered.get(f"/parameters/3.2.1/{NAME}").text
        assert "approved by a.mehta" in page
        assert "residuals reviewed" in page
        assert "running on" in page

    def test_the_provenance_of_a_set_is_explained_not_merely_labelled(
            self, registered, people):
        self._record(registered, people["d.raman"])
        _login(registered)
        page = registered.get(f"/parameters/3.2.1/{NAME}").text
        assert "asserted by a person" in page
        assert "under a fit warrant MAYA issued" in page

    def test_a_fitted_set_names_the_featureset_version_it_came_from(
            self, registered, people):
        """The coefficients mean nothing without the columns they belong to, and
        the row holds an id, which is not something a reviewer can read."""
        dev = people["d.raman"]
        for name, dtype in [("living_area_sqft", "numeric"), ("bedrooms", "integer")]:
            registered.post("/api/v1/features", auth=dev, json={
                "name": name, "entity": "property_id", "dtype": dtype,
                "description": name, "owner": "person/j.okafor"})
        registered.post("/api/v1/feature-views", auth=dev, json={
            "name": "nj_characteristics", "entity": "property_id",
            "owner": "person/j.okafor",
            "features": ["living_area_sqft", "bedrooms"]})
        registered.post("/api/v1/feature-views/nj_characteristics/materialise",
                        auth=dev, json={"rows": [
                            {"entity_id": "P1", "event_ts": 1717200000.0,
                             "ingest_ts": 1717200000.0,
                             "living_area_sqft": 1800.0, "bedrooms": 3}]})
        registered.post("/api/v1/featuresets", auth=dev, json={
            "name": "nj_home_core", "entity": "property_id",
            "slots": {"living_area_sqft": "numeric", "bedrooms": "integer"}})
        registered.post("/api/v1/featuresets/nj_home_core/versions", auth=dev,
                        json={"bindings": {"living_area_sqft": "living_area_sqft",
                                           "bedrooms": "bedrooms"}})
        grant = registered.post("/api/v1/warrants", auth=people["j.okafor"], json={
            "urn": URN, "environment": "lab", "principal": "svc/model-lab",
            "declared_use": "model_development"}).json()
        r = self._record(registered, dev, provenance="fitted",
                         warrant_id=grant["id"], featureset="nj_home_core",
                         featureset_version=1)
        assert r.status_code == 201, r.text
        _login(registered)
        page = registered.get(f"/parameters/3.2.1/{NAME}").text
        assert "nj_home_core@v1" in page
        assert grant["id"] in page, "the warrant it was produced under is named"

    def test_the_empty_state_explains_what_a_parameter_set_is_for(self, registered):
        _login(registered)
        page = registered.get(f"/parameters/3.2.1/{NAME}").text
        assert "No parameter sets are recorded against this version" in page
        assert "terminal" in page

    def test_the_model_page_links_to_the_fuller_parameter_page(self, registered):
        """The card on the model page says what runs; it has nowhere to put the
        values, and a reviewer needs them."""
        _login(registered)
        assert f"/parameters/3.2.1/{NAME}" in registered.get(f"/model/{NAME}").text

    def test_an_unknown_version_is_404(self, registered):
        _login(registered)
        assert registered.get(f"/parameters/9.9.9/{NAME}").status_code == 404


class TestThePagesAuthoriseAndNotOnlyAuthenticate:
    """A validator scoped to one legal entity got 403 from the API and the
    dashboard correctly hid the model — then loaded the detail page directly and
    received its versions, alias history, warrant grants and full evidence
    chain. Listings filtered; directly-addressable pages did not.
    """

    OTHER = "maya://model/eu.capital.irb"
    OTHER_NAME = "eu.capital.irb"

    def _elsewhere(self, client, people):
        """A model in a legal entity our scoped principal cannot see."""
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": self.OTHER, "name": "EU IRB", "model_class": "capital.irb",
            "domain": "capital", "owner": "person/j.okafor",
            "legal_entity": "LE-EU-01", "purpose": "IRB capital"})

    def _scoped(self, client):
        client.post("/api/v1/principals", json={
            "username": "uk.val", "display_name": "UK Validator",
            "roles": ["validator"], "password": "uk-pw",
            "legal_entities": ["LE-US-01"], "domains": ["credit"]})
        return ("uk.val", "uk-pw")

    def test_the_api_refuses_an_out_of_scope_model(self, registered, people):
        self._elsewhere(registered, people)
        who = self._scoped(registered)
        r = registered.get(f"/api/v1/models/{self.OTHER_NAME}", auth=who)
        assert r.status_code == 403, r.text

    def test_the_page_refuses_it_too(self, registered, people, client):
        """The point. One authorisation policy, asked from two places — if a
        page showed what the API refuses, the page would be the one telling
        somebody what they are not cleared for."""
        self._elsewhere(registered, people)
        self._scoped(registered)
        _login(registered, "uk.val", "uk-pw")
        page = registered.get(f"/model/{self.OTHER_NAME}")
        assert page.status_code == 403
        assert "outside your scope" in page.text

    def test_the_page_does_not_leak_the_record_in_its_body(self, registered,
                                                           people):
        self._elsewhere(registered, people)
        self._scoped(registered)
        _login(registered, "uk.val", "uk-pw")
        body = registered.get(f"/model/{self.OTHER_NAME}").text
        assert "LE-EU-01" not in body and "IRB capital" not in body

    def test_somebody_in_scope_still_sees_their_own_model(self, registered,
                                                          people):
        _login(registered, "s.iqbal", "mrm-pw")
        page = registered.get(f"/model/{NAME}")
        assert page.status_code == 200 and "SB PD" in page.text


class TestTheTableEnhancerIsActuallyServed:
    """Structural tests prove the templates are shaped for it; this proves the
    browser can reach it."""

    def test_the_script_is_served(self, client):
        r = client.get("/static/js/tables.js")
        assert r.status_code == 200
        assert "mayaEnhanceTables" in r.text

    def test_every_page_loads_it(self, registered):
        _login(registered)
        for path in ("/dashboard", f"/model/{NAME}", "/features", "/featuresets",
                     "/policies", "/notifications", "/telemetry"):
            body = registered.get(path).text
            assert "/static/js/tables.js" in body, path

    def test_the_evidence_table_carries_its_header_when_rendered(self, registered):
        """The one that grows without bound, and previously sat header-less in a
        fixed-height scroll box."""
        _login(registered)
        body = registered.get(f"/model/{NAME}").text
        assert "<th>Event</th>" in body and "<th>Sequence</th>" in body
