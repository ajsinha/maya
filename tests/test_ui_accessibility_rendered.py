"""The same rule, on the RENDERED page rather than the template.

A template scan cannot see a control assembled by a Jinja loop into markup that
does not look like a control in source, and it cannot see two loop iterations
colliding on one id. This walks the pages a signed-in person can open and checks
the HTML that actually reaches the browser.
"""
from __future__ import annotations

import re

import pytest

from tests.api_helpers import login

CONTROL = re.compile(r"<(input|select|textarea)\b([^>]*?)/?>", re.S)
UNNAMED_BY_NATURE = re.compile(r'type="(hidden|submit|button)"')

PAGES = ["/dashboard", "/models/new", "/features", "/featuresets", "/policies",
         "/notifications", "/board-pack", "/model-algebra", "/warrants",
         "/admin/principals", "/admin/regimes", "/login"]


@pytest.mark.parametrize("path", PAGES)
def test_every_rendered_control_is_named(registered, client, path):
    login(client)
    page = registered.get(path)
    assert page.status_code == 200, f"{path} -> {page.status_code}"
    body = page.text
    labelled = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', body))
    unnamed = []
    for match in CONTROL.finditer(body):
        attrs = match.group(2)
        if UNNAMED_BY_NATURE.search(attrs):
            continue
        ident = re.search(r'\bid="([^"]+)"', attrs)
        if "aria-label" in attrs or "aria-labelledby" in attrs:
            continue
        if ident and ident.group(1) in labelled:
            continue
        unnamed.append(attrs.strip()[:70])
    assert unnamed == [], f"{path}: " + "; ".join(unnamed)
