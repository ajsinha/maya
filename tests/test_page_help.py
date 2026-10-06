"""
Every page ends with "About this page": what it is for, the idea behind it, and where Help
explains it in full. A new page cannot be added without saying what it is.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from maya.web import page_help
from maya.web.help_catalog import SUBJECTS
from tests.test_web import env  # noqa: F401 - the web fixture, reused


def _page_routes() -> set[str]:
    """Every GET route the web tier serves, read from the routers mount_web includes."""
    import importlib
    import pkgutil

    import maya.web.routes as routes

    out = set()
    for mod in pkgutil.iter_modules(routes.__path__):
        router = getattr(importlib.import_module(f"maya.web.routes.{mod.name}"), "router", None)
        for route in getattr(router, "routes", []):
            if "GET" in (getattr(route, "methods", None) or set()) and not page_help.exempt(
                route.path
            ):
                out.add(route.path)
    return out


def test_every_page_has_its_help_and_every_entry_is_a_page(env):  # noqa: F811
    pages = _page_routes()
    missing = sorted(pages - set(page_help.PAGES))
    assert missing == [], f"pages with no 'About this page': {missing}"
    stale = sorted(set(page_help.PAGES) - pages)
    assert stale == [], f"help for pages that do not exist: {stale}"
    for template, (what, points, subject) in page_help.PAGES.items():
        assert what.strip(), template
        for point in points:
            heading, icon, text = point  # each point is a tile: a heading, an icon and the words
            assert heading.strip() and text.strip() and icon.replace("-", "").isalnum(), (
                template,
                point,
            )
        assert subject is None or subject.split("#")[0] in SUBJECTS, (template, subject)


def test_the_help_is_shown_at_the_foot_of_a_page(env):  # noqa: F811
    from starlette.testclient import TestClient

    _, app, _, _ = env
    page = TestClient(app).get("/login").text  # public, so no sign-in is needed here
    assert 'id="page-help"' in page and "About this page" in page
    assert 'href="/help/security"' in page
    # signed out, it is a quiet note under the card, not the panel of tiles
    assert 'class="page-help-note"' in page and "single sign-on configured" in page
    assert 'class="ph-tile"' not in page
    from tests.test_web import _login

    signed_in = TestClient(app)
    _login(signed_in)
    models = signed_in.get("/models").text
    assert 'href="#page-help"' in models  # the ? in the top bar that jumps to it
    assert 'class="ph-tile"' in models  # signed in, its points are tiles


def test_the_logo_leads_to_the_landing_page_and_the_house_leads_back(env):  # noqa: F811
    from starlette.testclient import TestClient

    from tests.test_web import _login

    _, app, _, _ = env
    visitor = TestClient(app)
    assert 'href="/welcome"' in visitor.get("/help").text  # the public bar's logo
    landing = visitor.get("/welcome").text
    assert 'href="/login"' in landing and "Go to your dashboard" not in landing
    member = TestClient(app)
    _login(member)
    page = member.get("/welcome")
    assert page.status_code == 200 and "Go to your dashboard" in page.text
    assert 'class="navbar-brand maya-brand" href="/welcome"' in page.text
    assert 'aria-label="Your dashboard"' in page.text  # the house in the top bar
    assert 'id="page-help"' not in page.text  # the landing page is its own explanation
    assert 'id="page-help"' not in visitor.get("/").text  # signed out, / is the landing too


def test_a_literal_page_is_not_mistaken_for_a_pattern():
    assert page_help.for_path("/warrants/training/new")["what"].startswith("Draw up a training")
    assert page_help.for_path("/warrants/execution/new")["what"].startswith("Issue an execution")
    assert page_help.for_path("/warrants/training/abc123")["what"].startswith("One training")
    assert page_help.for_path("/models/new")["what"].startswith("Define a model")
