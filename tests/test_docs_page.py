"""The interactive specification must render on an instance with headers on.

FastAPI's `/docs` and `/redoc` load Swagger UI and ReDoc from
`cdn.jsdelivr.net`. The Content-Security-Policy here is `script-src 'self'` —
deliberately, because every other asset in this interface is vendored so it
renders air-gapped — so both pages were blank on every instance with the headers
on, which is every instance. The page the API reference points people at was a
white screen, and nothing anywhere said so.
"""
from __future__ import annotations

import pathlib

VENDOR = pathlib.Path(__file__).resolve().parents[1] / "web" / "static" / "vendor"


class TestTheSpecificationPageRenders:

    def test_docs_loads_nothing_from_another_origin(self, client):
        body = client.get("/docs").text
        assert "swagger-ui" in body
        assert "cdn.jsdelivr.net" not in body, \
            "a CSP of script-src 'self' makes this a blank page"
        assert "/static/vendor/swagger-ui/swagger-ui-bundle.js" in body

    def test_every_asset_it_names_is_one_this_server_holds(self, client):
        import re

        body = client.get("/docs").text
        for url in re.findall(r'(?:src|href)="([^"]+)"', body):
            assert url.startswith("/"), f"{url} is not served from this origin"
            assert client.get(url).status_code == 200, f"{url} is a 404"

    def test_the_bundle_is_actually_vendored(self):
        for name in ("swagger-ui-bundle.js", "swagger-ui.css"):
            path = VENDOR / "swagger-ui" / name
            assert path.exists() and path.stat().st_size > 10_000, name
        assert (VENDOR / "swagger-ui" / "PROVENANCE.md").exists(), \
            "a vendored bundle with no provenance is a bundle nobody can update"

    def test_redoc_is_gone_rather_than_blank(self, client):
        """Two renderings of one specification is one more than anybody needs,
        and a page that renders nothing is worse than a page that is not there."""
        assert client.get("/redoc").status_code == 404

    def test_the_policy_is_still_strict(self, client):
        csp = client.get("/docs").headers["content-security-policy"]
        assert "script-src 'self' 'unsafe-inline'" in csp
        assert "cdn." not in csp, "no CDN exception was opened for this"
