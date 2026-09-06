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
        _login(client)
        body = client.get("/admin/regimes").text
        assert "Does truth survive translation?" in body


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
