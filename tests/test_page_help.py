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
