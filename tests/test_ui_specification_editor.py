"""
MAYA — the model specification editor.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Writing the mathematics down, in the interface, without creating a second
description of the model.

The design decision this file pins is the one that matters. `/api/v1/mathematics`
derives the equation from the syntax tree the platform evaluates and stores
NOTHING, precisely so the equation, the code and the answer cannot disagree — a
`latex` field on the version would be exactly the second description that
argument is against.

So a specification is a different artifact: prose ABOUT the model, filed as a
document, with an author and somebody else's acceptance. The way the two are
kept honest is that the prose QUOTES what MAYA derives rather than restating it,
which is what "Insert the derived equation" does.
"""
from __future__ import annotations

import pathlib
import re


from tests.api_helpers import login as _login
from tests.conftest import KERNEL, NAME, URN

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / "web" / "static" / "vendor" / "katex"
SCRIPT = ROOT / "web" / "static" / "js" / "model-specification.js"
TEMPLATE = ROOT / "web" / "templates" / "model_specification.html"


class TestTheRendererIsVendored:
    """`script-src 'self'` forbids a CDN, and a governance platform that can be
    made to fetch from somewhere else is one somebody can exfiltrate through.
    The interface must also render air-gapped."""

    def test_katex_is_served_from_disk(self, client):
        for asset in ("katex.min.js", "katex.min.css"):
            assert (VENDOR / asset).exists(), asset
            assert client.get(f"/static/vendor/katex/{asset}").status_code == 200

    def test_its_fonts_are_here_too(self, client):
        fonts = sorted(VENDOR.glob("fonts/*.woff2"))
        assert fonts, "no fonts vendored; the mathematics renders in a fallback"
        served = client.get(f"/static/vendor/katex/fonts/{fonts[0].name}")
        assert served.status_code == 200

    def test_the_stylesheet_asks_for_nothing_we_did_not_ship(self):
        """Only woff2 is shipped, so the CSS must not reference woff or ttf —
        a browser requesting a font that is not there is a 404 per glyph run."""
        css = (VENDOR / "katex.min.css").read_text(encoding="utf-8")
        assert ".woff2" in css
        assert not re.search(r"url\([^)]*\.(woff|ttf)\)", css)

    def test_nothing_on_the_page_calls_out(self):
        page = TEMPLATE.read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        for marker in ("//cdn.", "http://", "https://", "jsdelivr", "unpkg"):
            assert marker not in page, f"{marker} in the template"
            assert marker not in script, f"{marker} in the script"


class TestThePageOpens:
    def test_it_renders_for_somebody_who_may_file_documents(self, registered,
                                                            client):
        _login(client)
        page = registered.get(f"/model/{NAME}/specification")
        assert page.status_code == 200
        assert "Undefined" not in page.text
        assert "model-specification.js" in page.text
        assert "katex.min.js" in page.text

    def test_it_redirects_a_stranger(self, registered):
        r = registered.get(f"/model/{NAME}/specification", follow_redirects=False)
        assert r.status_code in (302, 303, 307)

    def test_an_unknown_model_is_404(self, client):
        _login(client)
        assert client.get("/model/ghost/specification").status_code == 404

    def test_the_scripts_load_after_jquery(self):
        """A page script in the content block runs BEFORE jQuery, which is
        loaded at the end of base.html — the editor was silently dead until it
        moved into the `scripts` block."""
        page = TEMPLATE.read_text(encoding="utf-8")
        assert "{% block scripts %}" in page
        head, tail = page.split("{% block scripts %}", 1)
        assert "model-specification.js" in tail
        assert "model-specification.js" not in head

    def test_it_opens_with_something_to_write_in_rather_than_a_blank_box(
            self, registered, client):
        _login(client)
        body = registered.get(f"/model/{NAME}/specification").text
        for heading in ("What the model does", "The mathematics",
                        "Assumptions", "Limitations"):
            assert heading in body, heading


class TestTheDerivedEquationIsQuotedNotRetyped:
    """The whole point. A specification that restates the mathematics is a
    second description, and the one nobody executes drifts first."""

    FORMULA = {**KERNEL, "runtime": "formula",
               "entry": {"expression": "intercept + beta * dscr",
                         "target": "pd_12m"},
               "input_schema": [
                   {"name": "dscr", "dtype": "numeric",
                    "symbol": r"\mathrm{DSCR}"},
                   {"name": "intercept", "dtype": "numeric"},
                   {"name": "beta", "dtype": "numeric"}],
               "output_schema": [{"name": "pd_12m", "dtype": "numeric"}]}

    def _with_a_formula(self, client, people):
        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": "maya://model/spec.formula", "name": "Spec formula",
            "model_class": "c", "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "a closed form"})
        r = client.post("/api/v1/models/spec.formula/versions",
                        auth=people["d.raman"],
                        json={"semver": "1.0.0", "kernel": self.FORMULA})
        assert r.status_code == 201, r.text
        return client

    def test_the_button_carries_what_maya_derives(self, client, people):
        self._with_a_formula(client, people)
        _login(client)
        body = client.get("/model/spec.formula/specification").text
        assert 'id="insert-derived"' in body
        # The LaTeX on the button is what /api/v1/mathematics returns, not a
        # second rendering written for this page.
        from core.features.rendering import to_latex
        expected = to_latex("intercept + beta * dscr",
                            {"dscr": r"\mathrm{DSCR}"})
        assert expected.replace("&", "&amp;") in body or expected in body

    def test_a_kernel_with_no_expression_offers_no_button(self, registered,
                                                          client):
        """Every other runtime names an artifact MAYA does not read, and
        inventing an equation for one would be the invented description this
        page exists to avoid."""
        _login(client)
        body = registered.get(f"/model/{NAME}/specification").text
        # The BUTTON, not the phrase — the page's own prose explains what the
        # button is for, so matching the words finds the explanation.
        assert 'id="insert-derived"' not in body

    def test_the_inserted_block_says_where_it_came_from(self):
        """A reader has to be able to tell which half of the document MAYA
        computed and which half a person wrote."""
        script = SCRIPT.read_text(encoding="utf-8")
        assert "Derived by MAYA from the version's kernel" in script
        assert "second description of one model" in script


class TestWhatIsSavedIsADocument:
    """Not a field on the version. A specification has an author, a digest and
    somebody else's acceptance — which is what makes it worth reading."""

    def test_it_files_through_the_attachment_register(self, registered, people):
        filed = registered.post(
            "/api/v1/attachments", auth=people["j.okafor"],
            files={"file": ("spec.tex", b"\\section{X}\n$$y = mx + c$$\n",
                            "text/x-tex")},
            data={"urn": URN, "kind": "model_development_document",
                  "title": "Specification", "semver": "3.2.1"})
        assert filed.status_code == 201, filed.text
        body = filed.json()
        assert body["filename"] == "spec.tex"
        assert body["digest"].startswith("sha256:")
        assert body["state"] == "attached", "it lands awaiting review"

    def test_it_reads_back_byte_for_byte(self, registered, people):
        source = "\\section{X}\n$$y = mx + c$$\n"
        filed = registered.post(
            "/api/v1/attachments", auth=people["j.okafor"],
            files={"file": ("spec.tex", source.encode(), "text/x-tex")},
            data={"urn": URN, "kind": "model_development_document",
                  "title": "Specification", "semver": "3.2.1"}).json()
        got = registered.get(f"/api/v1/attachments/{filed['id']}/content",
                             auth=people["j.okafor"])
        assert got.status_code == 200
        assert got.text == source, "'Open in the editor' must return what was saved"

    def test_the_page_says_somebody_else_accepts_it(self, registered, client):
        _login(client)
        body = registered.get(f"/model/{NAME}/specification").text
        assert "Somebody other than you accepts it" in body


class TestTheHonestyAboutPdf:
    """MAYA ships no TeX toolchain. Saying so is the difference between a
    limitation and a surprise."""

    def test_the_page_does_not_promise_a_pdf_it_cannot_produce(self, registered,
                                                               client):
        _login(client)
        body = registered.get(f"/model/{NAME}/specification").text
        assert "MAYA ships no TeX toolchain" in body
        assert "Download the .tex" in body

    def test_the_preview_does_not_claim_to_be_a_tex_engine(self):
        script = SCRIPT.read_text(encoding="utf-8")
        assert "Not a TeX engine and not pretending to be one" in script
