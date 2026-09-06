"""
MAYA — The administration screens, and the navigation that reaches them.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Six things about this platform — who may act, which rulebook is in force, what
runs unattended, whether the record is intact, what may execute — had an API and
no screen. These tests exist because the failure mode of a page like that is not
a crash: it is a page that renders `Undefined` where the answer should be, which
looks exactly like an answer of "nothing".

The navigation is tested with them, since a screen nobody can reach is the same
problem one step further on: eight pages built for this release were unreachable
from the bar until somebody went looking.
"""

import re

import pytest

from tests.api_helpers import login as _login


ADMIN_PAGES = ["/admin", "/admin/principals", "/admin/regimes",
               "/admin/scheduler", "/admin/evidence", "/admin/runtimes"]


def _nav(body: str) -> str:
    match = re.search(r"<nav.*?</nav>", body, re.S)
    assert match, "the page has no navigation at all"
    return match.group(0)


class TestAdminPages:
    @pytest.mark.parametrize("path", ADMIN_PAGES)
    def test_every_admin_page_renders_for_an_administrator(self, client, path):
        _login(client)
        r = client.get(path)
        assert r.status_code == 200
        # The tell-tale of a context key the route forgot to pass.
        assert "Undefined" not in r.text and "jinja2" not in r.text.lower()

    @pytest.mark.parametrize("path", ADMIN_PAGES)
    def test_every_admin_page_refuses_a_stranger(self, client, path):
        # Not a 200 with less on it: an unauthenticated caller is redirected to
        # sign in, which is what `login_required` does everywhere else.
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (302, 303, 307), path

    def test_people_and_roles_shows_the_effective_permission_count(self, client, people):
        _login(client)
        body = client.get("/admin/principals").text
        assert "d.raman" in body and "model_developer" in body
        assert "effective" in body
        # The pairs nobody may hold together are on the page, not only enforced.
        assert "Roles nobody may hold together" in body

    def test_people_and_roles_is_refused_without_principal_read(self, client, people):
        _login(client, "d.raman", "dev-pw")
        r = client.get("/admin/principals")
        assert r.status_code == 403

    def test_evidence_separates_self_verification_from_the_anchors(self, client):
        """The two checks are different claims and the page must not merge them.

        A chain rewritten from the first node passes `verify_chain`. Only the
        anchors — heads written outside the database — say anything about that.
        """
        _login(client)
        body = client.get("/admin/evidence").text
        assert "The chain against itself" in body
        assert "The chain against a second medium" in body

    def test_scheduler_reports_on_the_scheduler_itself(self, client):
        _login(client)
        body = client.get("/admin/scheduler").text
        # Health first: a batch that has never run is the failure this catches.
        assert "jobs have ever run" in body

    def test_runtimes_lists_the_fibration_and_its_gaps(self, client):
        _login(client)
        body = client.get("/admin/runtimes").text
        assert "The fibration" in body
        # L-15 holds at start-up, so there is nothing to report here.
        assert "Gaps in the fibration" not in body

    def test_regimes_says_whether_the_encoding_survives_translation(self, client):
        """The VERDICT, not the label above it.

        This asserted only that the question appeared on the page, and passed
        with the answer inverted: the template read a key the service does not
        return, so every regime — including the ones in force — rendered a red
        "No." while the API said `holds: true`. A test that checks the heading
        is a test of the heading.
        """
        _login(client)
        body = client.get("/admin/regimes").text
        assert "Does truth survive translation?" in body

        # What the service says, asked directly, one regime at a time.
        catalogue = client.get("/api/v1/regimes").json()["regimes"]
        assert catalogue, "no regimes are encoded, so this proves nothing"
        verdicts = {r["key"]: client.get(
            f"/api/v1/regimes/{r['key']}/satisfaction").json()["holds"]
            for r in catalogue}
        assert all(verdicts.values()), (
            f"the shipped regimes do not hold, so the page is right: {verdicts}")

        # And the page must agree with it. Every regime holds, so there is no
        # "No." on the page and nothing is counted as broken.
        assert ">No.<" not in body
        assert body.count(">Yes.<") == len(catalogue)
        assert "0</div>\n    <div class=\"stat-l\">whose encoding does not hold" \
            in body or ">0<" in body

    def test_the_regime_page_reads_the_key_the_service_returns(self, client):
        """The specific defect, held apart from the verdict above.

        `check()` returns `holds`, `failures` and `untranslated_terms`. A
        template reading anything else gets Jinja's Undefined, which is falsy —
        so the failure branch renders and nothing raises.
        """
        _login(client)
        answer = client.get("/api/v1/regimes").json()["regimes"][0]
        satisfaction = client.get(
            f"/api/v1/regimes/{answer['key']}/satisfaction").json()
        for key in ("holds", "failures", "untranslated_terms", "detail"):
            assert key in satisfaction, (
                f"the page renders '{key}'; the service no longer returns it")


class TestNavigation:
    def test_the_bar_is_four_items(self, client):
        """Manage, Admin, Help, About — and nothing else.

        It carried eleven links and a sign-out, which is a list rather than a
        menu. The count is asserted because the failure is gradual: every new
        screen wants one more link in the bar.
        """
        _login(client)
        nav = _nav(client.get("/dashboard").text)
        labels = [t.strip() for t in
                  re.findall(r'class="nav-link[^"]*"[^>]*>([^<]*)', nav)]
        assert [l for l in labels if l] == ["Manage", "Admin", "Help", "About"]

    @pytest.mark.parametrize("href", [
        "/dashboard", "/models/new", "/model-algebra", "/model-algebra/composition",
        "/warrants", "/packages", "/telemetry", "/board-pack",
        "/features", "/features/new", "/features/load", "/features/point-in-time",
        "/featuresets", "/featuresets/author", "/featuresets/lattice"])
    def test_every_working_screen_is_reachable_from_manage(self, client, href):
        """Eight of these were built and then reachable only by typing the URL."""
        _login(client)
        nav = _nav(client.get("/dashboard").text)
        assert f'href="{href}"' in nav

    @pytest.mark.parametrize("href", ADMIN_PAGES[1:] + ["/policies"])
    def test_every_admin_screen_is_reachable_from_admin(self, client, href):
        _login(client)
        nav = _nav(client.get("/dashboard").text)
        assert f'href="{href}"' in nav

    def test_the_menu_never_offers_what_the_page_refuses(self, client, people):
        """A developer holds no `principal:read`, so the entry is absent.

        The point is not tidiness. A menu that lists screens which then answer
        403 teaches people that refusals are noise.
        """
        _login(client, "d.raman", "dev-pw")
        nav = _nav(client.get("/dashboard").text)
        assert 'href="/admin/principals"' not in nav
        assert 'href="/policies"' not in nav
        # And what they DO hold is still there.
        assert 'href="/admin/scheduler"' in nav

    def test_a_stranger_gets_neither_dropdown(self, client):
        nav = _nav(client.get("/").text)
        assert 'id="nav-manage"' not in nav and 'id="nav-admin"' not in nav
        assert 'href="/login"' in nav and 'href="/about"' in nav


class TestModelRegistrationTakesADocument:
    def test_the_form_offers_a_document(self, client):
        """The complaint that started this: no way to upload one on /models/new."""
        _login(client)
        body = client.get("/models/new").text
        assert 'name="document"' in body and 'name="doc_kind"' in body
        # The kinds come from the register's own vocabulary, not a second copy.
        assert "model_development_document" in body

    def test_a_document_can_be_filed_before_any_version_exists(self, client, people):
        """`model_level` is what makes this possible, and it is why the field is
        on the registration form rather than only on the version form.

        Registered here WITHOUT a version, which is the case the form is for:
        a methodology note is about the model whatever it goes on to run.
        """
        from tests.conftest import URN
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "12-month PD at origination"})
        r = client.post("/api/v1/attachments", auth=people["d.raman"],
                        data={"urn": URN, "kind": "model_development_document",
                              "title": "Methodology note", "model_level": "true"},
                        files={"file": ("note.txt", b"how it was built", "text/plain")})
        assert r.status_code == 201, r.text
        # Filed against the model, not a version — there is no version. A
        # model-level attachment hangs under no version at all, which is
        # exactly why it survives the model going on to v2.4.
        row = r.json()
        assert row["model_version_id"] is None
        assert row["subject_type"] == "model"


class TestNoPageIsOrphaned:
    """Every screen with no parameters can be walked to from the front door.

    This is the test the release before this one needed. Eight pages were built,
    tested, and reachable only by typing the URL, because the person who built
    each one did not own the template holding the navigation. Nothing failed;
    the screens simply were not there as far as anybody using the product was
    concerned.

    Crawling is the only check that catches it. Asserting a list of links in
    `base.html` tests that the list matches itself.
    """

    #: `/logout` ends the session and `/login` is where an unauthenticated
    #: caller is sent, so neither is a destination to crawl into.
    #: `/docs/oauth2-redirect` is the callback Swagger's own OAuth flow posts
    #: back to — a landing point for a redirect, never a page anybody opens.
    NOT_DESTINATIONS = {"/logout", "/login", "/docs/oauth2-redirect"}

    @staticmethod
    def _static_page_routes(client):
        """Every page route that takes no parameters, from the app itself."""
        found = set()
        for route in client.app.routes:
            path = getattr(route, "path", "")
            methods = getattr(route, "methods", None) or set()
            if "GET" not in methods or "{" in path or path.startswith("/api"):
                continue
            if path.startswith(("/health", "/auth", "/static")):
                continue
            found.add(path)
        return found

    def _crawl(self, client, start="/dashboard"):
        seen, queue = set(), [start, "/"]
        while queue:
            path = queue.pop()
            if path in seen or path in self.NOT_DESTINATIONS:
                continue
            seen.add(path)
            r = client.get(path)
            if r.status_code != 200:
                continue
            for href in re.findall(r'href="(/[^"#?]*)', r.text):
                href = href.rstrip("/") or "/"
                if href not in seen and "{" not in href:
                    queue.append(href)
        return seen

    def test_every_parameterless_page_is_reachable_by_clicking(self, client):
        _login(client)
        reachable = self._crawl(client)
        expected = self._static_page_routes(client) - self.NOT_DESTINATIONS
        orphans = sorted(p for p in expected if p not in reachable)
        assert not orphans, (
            "these pages exist and nothing links to them, so nobody using the "
            f"product can get to them: {orphans}")


class TestTheFooterCarriesTheClaim:
    """The principle sits under every page, from one place.

    It is the sentence the whole platform is an argument for, and it was a
    string typed into two templates and a deck slide. Three copies of a sentence
    is three sentences waiting to happen.
    """

    LINE = ("A model is a representation of the world. "
            "Governance is knowing the difference.")

    @pytest.mark.parametrize("path", ["/", "/login", "/help", "/about"])
    def test_a_public_page_carries_it(self, client, path):
        assert self.LINE in client.get(path).text

    @pytest.mark.parametrize("path", ["/dashboard", "/models/new", "/admin/evidence"])
    def test_a_page_behind_a_session_carries_it(self, client, path):
        _login(client)
        assert self.LINE in client.get(path).text

    def test_it_comes_from_configuration_and_not_from_the_template(self, client):
        """Change the configured value; the page must change with it.

        Asserting that the sentence appears proves only that *a* copy of it
        exists somewhere — which is true of a template that hard-codes it, and
        was true of two templates that did. This substitutes a different
        sentence and reads it back, so a hard-coded copy fails here.
        """
        configured = client.app.state.ctx["config"].get("app.principle")
        assert configured == self.LINE, (
            "the shipped sentence and the configured one have drifted apart")

        different = "A test substituted this sentence."
        original = client.app.state.ctx["config"].get("app.principle")
        client.app.state.ctx["config"]._properties["app.principle"] = different
        try:
            body = client.get("/").text
            assert different in body, (
                "the footer ignored configuration, so a template holds its own "
                "copy of the sentence")
            assert self.LINE not in body
        finally:
            client.app.state.ctx["config"]._properties["app.principle"] = original

    def test_the_shipped_configuration_and_the_code_fallback_agree(self):
        """`brand()` carries a default for a deployment that sets nothing.

        A default that has drifted from the shipped configuration is worse than
        no default: it renders a *different* sentence on exactly the instances
        whose operator never looked, and nothing anywhere reports a difference.
        """
        import inspect
        from pathlib import Path

        import yaml

        from routes.base import Routes

        root = Path(__file__).resolve().parents[1]
        shipped = yaml.safe_load(
            (root / "config" / "application.yaml").read_text())["app"]["principle"]
        source = inspect.getsource(Routes.brand)
        assert shipped == self.LINE
        # The fallback is a wrapped string literal in the source; comparing the
        # joined literal is enough to catch a drift, and does not require
        # running with configuration removed.
        collapsed = " ".join(source.split()).replace('" "', "")
        assert self.LINE in collapsed, (
            "the fallback in Routes.brand no longer matches config/application.yaml")


class TestTheBatchCannotStopQuietly:
    """Two ways the governance batch silently never runs.

    Expiry, staleness, cohort maturity, outstanding signatures and missing
    evidence are all DERIVED when somebody asks. The batch is what turns a
    derived condition into a recorded consequence. An instance whose batch
    never runs is therefore indistinguishable from an estate with nothing
    outstanding — to every screen, every health probe and every digest.
    """

    def test_the_documented_cron_call_needs_no_body(self, client):
        """`POST /api/v1/scheduler/run`, exactly as the configuration file
        recommends it.

        It returned 422. A cron entry written from that comment failed, mailed
        its error to a mailbox nobody reads, and the batch never ran while every
        other signal stayed green. This is the test for a documentation defect
        that presents as an operations one.
        """
        r = client.post("/api/v1/scheduler/run")
        assert r.status_code == 200, r.text
        assert r.json()["ran"] > 0

    def test_naming_jobs_still_runs_only_those(self, client):
        first = client.get("/api/v1/scheduler").json()["jobs"][0]["job"]
        r = client.post("/api/v1/scheduler/run", json={"jobs": [first]})
        assert r.status_code == 200 and r.json()["ran"] == 1

    def test_a_disabled_loop_is_announced_at_startup(self, tmp_path, monkeypatch):
        """At the volume of the secret warnings, because the failure it precedes
        is quieter than either of them.

        The warning is captured by intercepting the module's own logger rather
        than with `caplog`: `core.log.configure` calls `basicConfig(force=True)`,
        which removes pytest's handler, so a caplog assertion here passes or
        fails on handler ordering rather than on whether anything was said.
        """
        import run_maya_web
        from core.config import PropertiesConfigurator
        from run_maya_web import create_app

        said = []
        real = run_maya_web.logger.warning
        monkeypatch.setattr(run_maya_web.logger, "warning",
                            lambda msg, *a, **k: (said.append(msg % a if a else msg),
                                                  real(msg, *a, **k))[0])

        config = tmp_path / "application.yaml"
        config.write_text(f"""
app: {{name: MAYA, version: "0.1.0", tagline: t, slogan: s}}
database: {{url: "sqlite:///{tmp_path}/data/sqlite/maya.db"}}
data: {{dir: "{tmp_path}/data"}}
scheduler: {{loop: {{enabled: false}}}}
logging: {{level: WARNING}}
""")
        PropertiesConfigurator.reset()
        create_app(PropertiesConfigurator(str(config), reload_interval=0))
        spoken = " ".join(said)
        assert "scheduler loop is DISABLED" in spoken
        # And it must say what to do instead, or it is a warning nobody acts on.
        assert "scheduler/run" in spoken and "/admin/scheduler" in spoken


class TestADraftRecordCannotReachProduction:
    """The model risk manager's path, walked again and refused.

    Registered, tiered, versioned, quorum-approved, aliased to prod/champion and
    warranted — with the model RECORD never submitted and never approved. It
    returned a signed execution credential whose own body read
    `"model_status": "draft"`.

    This is the platform's central claim: MAYA authorises execution. It
    authorised a model nothing had approved.
    """

    def _to_the_edge_of_production(self, client, people):
        """Everything the reviewer did, stopping before the resolve."""
        from tests.api_helpers import quorum_approve
        from tests.conftest import KERNEL, CONTRACT, NAME, URN

        owner, dev, mrm = people["j.okafor"], people["d.raman"], people["s.iqbal"]
        client.post("/api/v1/models", auth=owner, json={
            "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "12-month PD at origination"})
        client.post(f"/api/v1/models/{NAME}/assess", auth=owner,
                    json={"exposure": 2e9, "purpose_class": "regulatory_capital"})
        client.post(f"/api/v1/models/{NAME}/versions", auth=dev,
                    json={"semver": "3.2.1", "kernel": KERNEL, "contract": CONTRACT,
                          "artifact_digest": "sha256:" + "a" * 64})
        quorum_approve(client, people)
        client.put(f"/api/v1/models/{NAME}/aliases", auth=mrm,
                   json={"environment": "prod", "alias": "champion",
                         "semver": "3.2.1"})
        client.post("/api/v1/warrants", auth=owner, json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination",
            "declared_use": "origination_decision"})
        return owner, mrm

    def test_the_record_is_still_a_draft_at_that_point(self, client, people):
        """Stated, so the next test is unambiguous about what it refuses."""
        from tests.conftest import NAME
        self._to_the_edge_of_production(client, people)
        body = client.get(f"/api/v1/models/{NAME}", auth=people["j.okafor"]).json()
        assert body["model"]["status"] == "draft"

    def test_resolving_against_it_is_refused(self, client, people):
        from tests.conftest import URN
        self._to_the_edge_of_production(client, people)
        r = client.post("/api/v1/resolve", auth=("admin", "admin123"), json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination",
            "declared_use": "origination_decision"})
        assert r.status_code == 403, r.text
        assert "draft" in r.text

    def test_it_resolves_once_the_record_has_been_through_the_register(
            self, client, people):
        """Two acts, by two different people, and then it runs.

        The fix is not that production became harder to reach. It is that
        reaching it now requires the thing everybody assumed had happened.
        """
        from tests.conftest import NAME, URN
        owner, mrm = self._to_the_edge_of_production(client, people)
        assert client.post(f"/api/v1/models/{NAME}/submit", auth=owner,
                           json={"note": "ready"}).status_code in (200, 201)
        assert client.post(f"/api/v1/models/{NAME}/approve", auth=mrm,
                           json={"note": "approved"}).status_code in (200, 201)
        r = client.post("/api/v1/resolve", auth=("admin", "admin123"), json={
            "urn": f"{URN}#champion", "environment": "prod",
            "principal": "svc/origination",
            "declared_use": "origination_decision"})
        assert r.status_code == 200, r.text
        # The descriptor prints the record's state; it used to print "draft"
        # and sign it anyway.
        assert "draft" not in r.text


class TestTheEstateWideFindingsQuestion:
    """"What is outstanding anywhere?" had no answer in the product.

    `open_for` takes one model and `GET /api/v1/findings` demanded a `urn`, so a
    second line could not list what was open across the register by any route —
    while a worklist could still report "nothing is outstanding for you" over an
    unacknowledged finding.
    """

    def _raise_one(self, client, people, severity="High", blocking=False):
        from tests.conftest import URN
        r = client.post("/api/v1/findings", auth=people["a.mehta"], json={
            "urn": URN, "severity": severity, "title": f"A {severity} thing",
            "owner": "person/j.okafor", "blocking": blocking,
            "description": "raised by the review"})
        assert r.status_code in (200, 201), r.text
        return r.json()

    def test_the_endpoint_answers_without_naming_a_model(self, registered, people):
        self._raise_one(registered, people)
        r = registered.get("/api/v1/open-findings", auth=people["s.iqbal"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["open"] == 1 and body["models"] == 1
        # Each row names the model, so the list is readable on its own.
        assert body["findings"][0]["urn"] and body["findings"][0]["model_name"]

    def test_the_screen_renders_them_worst_first(self, registered, people):
        self._raise_one(registered, people, "Observation")
        self._raise_one(registered, people, "Critical")
        _login(registered, "s.iqbal", "mrm-pw")
        body = registered.get("/findings").text
        assert body.index("Critical") < body.index("Observation"), (
            "a list sorted by when things were raised buries the Critical one")

    def test_it_is_scoped_to_what_the_caller_may_see(self, registered, people):
        """Not a way around the visibility rules: the model ids come from what
        this principal is already permitted to list."""
        self._raise_one(registered, people)
        r = registered.get("/api/v1/open-findings", auth=people["d.raman"])
        assert r.status_code == 200
        seen = {f["urn"] for f in r.json()["findings"]}
        listed = {m["urn"] for m in
                  registered.get("/api/v1/models", auth=people["d.raman"]).json()["models"]}
        assert seen <= listed

    def test_an_empty_answer_says_what_it_is_an_answer_about(self, registered, people):
        """"Nothing open" is a claim about a scope, and the page says whose."""
        _login(registered, "s.iqbal", "mrm-pw")
        body = registered.get("/findings").text
        assert "not about the estate" in body or "your scope" in body

    def test_a_stranger_is_redirected_and_a_developer_may_read(self, registered, people):
        assert registered.get("/findings", follow_redirects=False).status_code in (
            302, 303, 307)
        _login(registered, "d.raman", "dev-pw")
        assert registered.get("/findings").status_code == 200


class TestAccountAdministrationIsNotOneWay:
    """Create, set roles, suspend — and nothing else.

    A suspension made in error, or for a fortnight's leave, could only be undone
    with an UPDATE against the database, which is the thing this platform exists
    to make unnecessary. A forgotten password meant a new account, and an
    evidence chain whose actors are `j.okafor` and `j.okafor.2` is one nobody
    can read.
    """

    def test_a_suspended_principal_can_be_reinstated(self, client, people):
        admin = ("admin", "admin123")
        assert client.post("/api/v1/principals/d.raman/suspend",
                           auth=admin).status_code == 200
        # Suspended means suspended: the credential stops working.
        assert client.get("/api/v1/me", auth=people["d.raman"]).status_code == 401

        back = client.post("/api/v1/principals/d.raman/reinstate", auth=admin)
        assert back.status_code == 200, back.text
        assert back.json()["status"] == "active"
        assert client.get("/api/v1/me", auth=people["d.raman"]).status_code == 200

    def test_reinstating_an_active_principal_is_refused_rather_than_ignored(
            self, client, people):
        r = client.post("/api/v1/principals/d.raman/reinstate",
                        auth=("admin", "admin123"))
        assert r.status_code == 409 and r.json()["error"] == "already_active"

    def test_both_acts_are_on_the_evidence_chain(self, client, people):
        """A suspension and its reversal read as a pair, with who did each."""
        admin = ("admin", "admin123")
        client.post("/api/v1/principals/d.raman/suspend", auth=admin)
        client.post("/api/v1/principals/d.raman/reinstate", auth=admin)
        # Read from the service rather than an endpoint, because the chain is
        # published as a verification rather than as a feed.
        chain = client.app.state.ctx["evidence"].repo.many()
        kinds = [n["kind"] for n in chain]
        assert "principal_suspended" in kinds and "principal_reinstated" in kinds

    def test_a_password_can_be_set_without_making_a_second_account(
            self, client, people):
        admin = ("admin", "admin123")
        r = client.post("/api/v1/principals/d.raman/password", auth=admin,
                        json={"password": "a-much-longer-secret"})
        assert r.status_code == 200, r.text
        assert client.get("/api/v1/me", auth=("d.raman", "dev-pw")).status_code == 401
        assert client.get("/api/v1/me",
                          auth=("d.raman", "a-much-longer-secret")).status_code == 200

    def test_a_short_password_is_refused(self, client, people):
        r = client.post("/api/v1/principals/d.raman/password",
                        auth=("admin", "admin123"), json={"password": "short"})
        assert r.status_code == 422 and r.json()["error"] == "password_too_short"

    def test_the_password_itself_never_reaches_the_evidence_chain(self, client, people):
        """The FACT is recorded; the secret is not."""
        admin = ("admin", "admin123")
        client.post("/api/v1/principals/d.raman/password", auth=admin,
                    json={"password": "a-much-longer-secret"})
        import json

        nodes = client.app.state.ctx["evidence"].repo.many()
        assert any(n["kind"] == "principal_password_set" for n in nodes)
        assert "a-much-longer-secret" not in json.dumps(nodes, default=str)


class TestAFormOffersOnlyWhatTheCallerMayDo:
    """A form rendered to somebody who cannot submit it teaches them the product
    is broken.

    `/models/new` and `/warrants` rendered in full for a model developer, who
    holds neither `model:register` nor `warrant:issue` — and the refusal that
    followed said "ask an administrator for a role that carries this
    permission", when the right answer is "ask the model owner". Naming the
    wrong person is worse than naming none: it sends somebody to the one team
    that cannot help, and a permission granted to fix it is a change to who is
    accountable rather than a configuration change.
    """

    def test_a_developer_is_told_who_to_ask_to_register(self, client, people):
        _login(client, "d.raman", "dev-pw")
        body = client.get("/models/new").text
        assert "model:register" in body
        assert "owner" in body.lower()
        assert "ask an administrator" not in body.lower()

    def test_an_owner_is_not_told_anything_they_do_not_need(self, client, people):
        _login(client, "j.okafor", "owner-pw")
        body = client.get("/models/new").text
        assert "which your account does not hold" not in body

    def test_a_developer_is_told_who_to_ask_for_a_warrant(self, client, people):
        _login(client, "d.raman", "dev-pw")
        body = client.get("/warrants").text
        assert "warrant:issue" in body and "model owner" in body

    def test_the_page_still_reads_for_somebody_who_may_not_act(self, client, people):
        """The refusal hides the control, not the explanation. Everything a
        developer needs in order to ask for the right warrant is still there."""
        _login(client, "d.raman", "dev-pw")
        body = client.get("/warrants").text
        assert "still reads" in body
        assert body.count("<form") >= 1


class TestTheMinorFindingsFromTheReview:
    """The nineteen the reviewers ranked below serious, and why each mattered."""

    def test_a_page_may_not_shadow_a_brand_key(self, client, people):
        """Three pages passed `version=` meaning the MODEL version and shadowed
        the application's, so the footer — which renders `{{ version }}` —
        printed the whole version record, kernel and artifact digest included,
        as its text. Nothing raised, because shadowing is what a merged dict
        does. The second instance of this shape is what makes it a check."""
        from routes.base import Routes

        class Probe(Routes):
            def register(self):
                pass

        with pytest.raises(RuntimeError, match="version"):
            Probe(client.app, client.app.state.ctx, None).page(
                _FakeRequest(), "x.html", version={"semver": "1.0.0"})

    def test_the_upload_control_takes_what_every_example_uploads(self, client,
                                                                 people, registered):
        """The control offered four suffixes and the API reads six — including
        CSV, which is what both tutorials and the SDK's own `load` use. The
        screen refused the file the documentation tells you to bring."""
        from core.features.transfer import accept_attribute
        assert ".csv" in accept_attribute()
        _login(client)
        for path in ("/features/load",):
            body = client.get(path).text
            assert ".csv" in body, path

    def test_both_feature_forms_offer_the_same_types(self, client, people):
        """`/features` offered `boolean` and `/features/new` did not, so whether
        a feature could be one depended on which screen you opened. The register
        constrains neither — which makes them suggestions, and a suggestion is
        still a vocabulary."""
        _login(client)
        from core.features.common import SUGGESTED_DTYPES
        for path in ("/features", "/features/new"):
            body = client.get(path).text
            for dtype in SUGGESTED_DTYPES:
                assert f">{dtype}<" in body, f"{path} does not offer {dtype}"

    def test_both_version_forms_can_express_a_full_kernel(self, client, people,
                                                          registered):
        """One had the derived-class preview and no way to say what runs; the
        other could say what runs and showed no class. So the screen tutorial 01
        sends you to could not create a version that executes."""
        from tests.conftest import NAME
        _login(client)
        for path in ("/models/new", f"/model-algebra/version/{NAME}"):
            body = client.get(path).text
            for field in ("runtime", "entry", "adaptive", "deterministic"):
                assert f'name="{field}"' in body, f"{path} cannot set {field}"

    def test_an_unknown_enum_names_the_field_and_the_vocabulary(self, client,
                                                                people, registered):
        """`ParameterKind('not_a_kind')` raised a bare ValueError, which reached
        the caller as a 500 with an empty body. A typo in a closed vocabulary is
        the most ordinary mistake here and it was the one refusal that said
        nothing."""
        from tests.conftest import NAME
        r = client.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                        json={"semver": "7.7.7",
                              "kernel": {"parameter_kind": "not_a_kind",
                                         "fit_procedure": "none"}})
        assert r.status_code == 409, r.text
        detail = r.json()["detail"]
        assert "parameter_kind" in detail and "estimated_coefficients" in detail

    @pytest.mark.parametrize("header,expected", [
        ("content-security-policy", "frame-ancestors 'none'"),
        ("x-frame-options", "DENY"),
        ("x-content-type-options", "nosniff"),
        ("referrer-policy", "same-origin"),
    ])
    def test_every_response_carries_the_security_headers(self, client, header,
                                                         expected):
        """There were none. The interface is entirely self-hosted, which makes a
        strict policy cheap to state and expensive to omit: an injected
        `<script src>` had nothing stopping it, on pages that render model
        names, findings and document titles people supplied."""
        assert expected in client.get("/").headers.get(header, "")

    def test_the_policy_forbids_calling_out(self, client):
        """A governance platform that can be made to fetch from somewhere else
        is one somebody can exfiltrate through."""
        policy = client.get("/").headers["content-security-policy"]
        assert "connect-src 'self'" in policy
        assert "default-src 'self'" in policy


class _FakeRequest:
    """Enough of a request for `brand()` — it reads a session and a cookie."""
    session: dict = {}
    cookies: dict = {}
    headers: dict = {}
    url = None
