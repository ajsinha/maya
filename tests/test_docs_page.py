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


class TestTheHeadersAreDocumented:
    """Six headers were added and described nowhere. A control nobody can read
    about is a control the next person removes because they cannot see what it
    was for — and this one costs something visible (`/docs` went blank), which
    makes it exactly the kind somebody switches off.
    """

    SECURITY_DOC = (pathlib.Path(__file__).resolve().parents[1]
                    / "docs" / "09-security-compliance.md")

    def test_every_header_the_app_sends_is_named_in_the_document(self, client):
        from run_maya_web import SECURITY_HEADERS

        prose = self.SECURITY_DOC.read_text(encoding="utf-8")
        missing = [name for name in SECURITY_HEADERS if name not in prose]
        assert missing == [], (
            "these headers are sent on every response and appear in no design "
            "document: " + ", ".join(missing))

    def test_the_document_names_no_header_the_app_does_not_send(self, client):
        """The other direction, which is the one that rots: a document
        describing a control that was removed."""
        from run_maya_web import SECURITY_HEADERS

        sent = {name.lower() for name in SECURITY_HEADERS}
        actual = {k.lower() for k in client.get("/login").headers}
        assert sent <= actual, sorted(sent - actual)

    def test_the_unsafe_inline_decision_is_written_down(self):
        prose = self.SECURITY_DOC.read_text(encoding="utf-8")
        assert "'unsafe-inline'" in prose and "decision, not an oversight" in prose

    def test_the_headers_reach_the_api_as_well_as_the_pages(self, client):
        for path in ("/login", "/api/v1/openapi.json"):
            headers = client.get(path).headers
            assert "content-security-policy" in headers, path
