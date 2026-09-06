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
                          "artifact_digest": "sha256:abc"})
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
