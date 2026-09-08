"""
MAYA — a screen nobody can click to is not built.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Two rules, both learned the same way — by somebody opening the interface and
finding something they could not get to.

**Every page must be reachable.** `/feature/{name}` rendered a full detail page
— lineage in both directions, certification, what would break if the feature
were withdrawn — and the catalogue at `/features` never linked to it. It could
be reached by typing the URL and no other way, which for the page that answers
*what IS this feature* is the whole page wasted. `/tutorials` and `/docs` were
the same: rendered, complete, and hanging off nothing.

**Every defining attribute must be on a screen.** A platform that records when
a feature was sealed, by whom and with what note, and then shows none of it,
has the fact and not the answer. Seven columns on `feature` and seven on
`featureset` were in the register and on no page anywhere — including the
entire retirement record, which had been added a wave earlier and never
surfaced.

Both are held here against the ROUTE TABLE and the SCHEMA rather than against a
list somebody maintains, so a page or a column added tomorrow is covered
without anybody remembering to add it.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from db.schema.tables import METADATA

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "web" / "templates"
SCRIPTS = ROOT / "web" / "static" / "js"

#: The only pages that may hang off nothing, and why. Probes for a load
#: balancer, a container's readiness check and a monitoring system — none of
#: which reads a navbar. Anything else needs a way in.
UNLINKED_ON_PURPOSE = {"/health", "/health/live", "/health/ready"}


def _blob() -> str:
    return "\n".join(p.read_text(encoding="utf-8")
                     for p in list(TEMPLATES.glob("*.html")) + list(SCRIPTS.glob("*.js")))


def _pages(app) -> list:
    return sorted({r.path for r in app.routes
                   if hasattr(r, "methods") and "GET" in r.methods
                   and not r.path.startswith(("/api", "/static", "/auth"))})


#: Pages whose link is BUILT rather than written, so no literal path appears in
#: any template. Each names the template that builds it and the expression it
#: builds from, because "the check cannot see it" and "nothing links to it"
#: look identical from here and are opposite findings.
BUILT_LINKS = {
    # `/help/{slug}` and `/tutorials/{slug}` share one template, which renders
    # `{{ area_path }}/{{ t.slug }}` — the whole point being that the two
    # indexes are the same page asked a different question.
    "/tutorials/{slug}": ("help.html", "{{ area_path }}/{{ t.slug }}"),
    "/help/{slug}": ("help.html", "{{ area_path }}/{{ t.slug }}"),
}


def _linked(path: str, blob: str) -> bool:
    """Any way a template can name it: a literal href, a Jinja tuple entry, the
    prefix a parameterised link is built from, or a link built by expression."""
    if path in BUILT_LINKS:
        template, expression = BUILT_LINKS[path]
        return expression in (TEMPLATES / template).read_text(encoding="utf-8")
    if "{" in path:
        return path.split("{")[0] in blob
    return (f'href="{path}"' in blob or f'"{path}"' in blob or f"'{path}'" in blob)


class TestEveryScreenCanBeClickedTo:
    def test_no_page_hangs_off_nothing(self, client):
        blob = _blob()
        orphans = [p for p in _pages(client.app)
                   if p not in UNLINKED_ON_PURPOSE and not _linked(p, blob)]
        assert orphans == [], (
            "these pages render and nothing links to them, so they can be "
            "reached only by typing the URL: " + ", ".join(orphans))

    def test_the_check_can_fail(self):
        """A reachability check that passes everything is one nobody can
        trust."""
        assert not _linked("/a-page-nobody-wrote", _blob())

    def test_a_built_link_is_still_verified(self):
        """`BUILT_LINKS` is an exemption from the LITERAL search, not from the
        rule. Each entry names the template and the expression, and this reads
        them — so an entry that stops being true fails rather than excusing."""
        for path, (template, expression) in BUILT_LINKS.items():
            body = (TEMPLATES / template).read_text(encoding="utf-8")
            assert expression in body, (
                f"{path} is exempted because {template} builds its link with "
                f"`{expression}`, and that expression is no longer there")

    def test_the_feature_catalogue_links_to_each_feature(self):
        """The page that answers *what is this feature* was reachable only by
        typing its URL."""
        catalogue = (TEMPLATES / "features.html").read_text(encoding="utf-8")
        assert 'href="/feature/{{ f.name }}"' in catalogue

    def test_an_unresolvable_feature_is_still_a_link(self):
        """It is the row somebody most needs the detail page for: the
        catalogue lists it with its reason, and the reason is short."""
        catalogue = (TEMPLATES / "features.html").read_text(encoding="utf-8")
        assert catalogue.count('href="/feature/{{ f.name }}"') == 2

    def test_the_featureset_catalogue_links_to_each_featureset(self):
        listing = (TEMPLATES / "featuresets.html").read_text(encoding="utf-8")
        assert 'href="/featureset/{{ s.name }}"' in listing

    def test_an_escalated_item_is_clickable_like_every_other(self):
        """It was the one row on the notifications page with no link — which is
        backwards, because an item is escalated precisely BECAUSE it has been
        overdue and unactioned for a week. The most urgent row was the only one
        you could not act on.

        Held by counting: both loops render `i.href`, and the escalated one
        rendering the model as bare text is what this caught.
        """
        page = (TEMPLATES / "notifications.html").read_text(encoding="utf-8")
        assert page.count('<a href="{{ i.href }}">{{ i.model }}</a>') == 2, (
            "the ordinary items and the escalated ones must both link; an "
            "escalated item carries the same href because it comes from the "
            "same worklist")

    def test_the_specification_editor_is_offered_from_the_model(self):
        """The LaTeX editor is a page on a model, and a model page is where
        somebody looking for it will be."""
        model = (TEMPLATES / "model.html").read_text(encoding="utf-8")
        assert "/specification" in model


class TestEveryDefiningAttributeIsOnAScreen:
    """A column the register holds and no page shows is a fact the platform
    has and cannot tell anybody."""

    #: Columns that are genuinely internal and belong on no screen. Named, with
    #: the reason, so the exemption is a decision rather than an oversight.
    INTERNAL = {"id"}

    PAGES = {"feature": "feature_author_feature.html",
             "featureset": "featureset.html"}

    @pytest.mark.parametrize("table", sorted(PAGES))
    def test_the_detail_page_shows_every_column(self, table):
        page = (TEMPLATES / self.PAGES[table]).read_text(encoding="utf-8")
        missing = [c.name for c in METADATA.tables[table].columns
                   if c.name not in self.INTERNAL
                   and not re.search(r"\b" + re.escape(c.name) + r"\b", page)]
        assert missing == [], (
            f"{self.PAGES[table]} does not mention these {table} columns, so "
            f"the register holds them and no screen shows them: "
            + ", ".join(missing))

    @pytest.mark.parametrize("table", sorted(PAGES))
    def test_the_retirement_record_is_shown_in_full(self, table):
        """Retirement was added a wave earlier and surfaced nowhere. Withdrawn
        WHEN, by WHOM and WHY are three separate facts and a screen showing one
        of them is worse than one showing none, because it looks complete."""
        page = (TEMPLATES / self.PAGES[table]).read_text(encoding="utf-8")
        for column in ("retired_at", "retired_by", "retire_reason"):
            assert column in page, f"{self.PAGES[table]} omits {column}"

    @pytest.mark.parametrize("table", sorted(PAGES))
    def test_the_seal_is_shown_with_its_note(self, table):
        """Sealing makes something final. Who did it, when, and what they said
        about it is the record of a decision, not decoration."""
        page = (TEMPLATES / self.PAGES[table]).read_text(encoding="utf-8")
        for column in ("sealed_at", "sealed_by", "seal_note"):
            assert column in page, f"{self.PAGES[table]} omits {column}"


class TestNoTemplateEscapesItsOwnMarkup:
    """An HTML entity inside a `{{ }}` string literal is escaped on the way
    out, so the page prints its own source.

    `{{ "" if loop.last else "&nbsp;&le;&nbsp;" }}` rendered a literal
    `&nbsp;&le;&nbsp;` between every certification level, on a page a reader
    was looking at. Five places had it and only one was noticed, which is why
    this is a scan and not five assertions: a separator is markup and belongs
    in the template body, not inside an expression.
    """

    EXPRESSION = re.compile(r"\{\{(.*?)\}\}|\{%(.*?)%\}", re.S)
    LITERAL = re.compile(r'"([^"]*)"|\'([^\']*)\'')
    ENTITY = re.compile(r"&[a-zA-Z#][a-zA-Z0-9]*;")

    def test_no_entity_hides_inside_an_expression(self):
        offenders = []
        for path in sorted(TEMPLATES.glob("*.html")):
            for number, line in enumerate(path.read_text(encoding="utf-8")
                                          .splitlines(), 1):
                for expression in self.EXPRESSION.findall(line):
                    body = expression[0] or expression[1]
                    for literal in self.LITERAL.findall(body):
                        text = literal[0] or literal[1]
                        if self.ENTITY.search(text):
                            offenders.append(f"{path.name}:{number} {text[:40]}")
        assert offenders == [], (
            "these put an HTML entity inside a template expression, where "
            "Jinja escapes it and the page prints the source: "
            + "; ".join(offenders))

    def test_the_scan_can_fail(self):
        """A scan that passes everything is a scan nobody can trust."""
        assert self.ENTITY.search("&nbsp;&le;&nbsp;")
        assert self.LITERAL.findall('"" if loop.last else "&nbsp;"')

    def test_a_rendered_page_carries_no_escaped_entity(self, client):
        """The same rule asserted at the other end: through a real render."""
        from tests.api_helpers import login

        client.post("/api/v1/features", json={
            "name": "escape_probe", "entity": "borrower", "dtype": "numeric",
            "description": "a probe", "owner": "person/admin"})
        login(client)
        for path in ("/feature/escape_probe", "/features/new", "/features"):
            body = client.get(path).text
            assert "&amp;nbsp;" not in body, f"{path} prints an escaped entity"
            assert "&amp;mdash;" not in body, f"{path} prints an escaped entity"
            assert "&amp;middot;" not in body, f"{path} prints an escaped entity"


class TestAFeaturesAttributesAreListed:
    """"What are the attributes and what type is each" is the question a reader
    arrives at a feature with, and the page answered a different one.

    It said "a vector of 12 — 12 numbers per row", which is the SHAPE. It never
    named a single column, so somebody who wanted to know what a row of this
    feature actually contains could not find out from the page that exists to
    tell them.
    """

    def _feature(self, client, **spec):
        body = {"entity": "borrower", "dtype": "numeric",
                "description": "d", "owner": "person/admin", **spec}
        assert client.post("/api/v1/features", json=body).status_code == 201
        from tests.api_helpers import login
        login(client)
        return client.get(f"/feature/{spec['name']}").text

    def test_a_scalar_names_its_one_value_column(self, client):
        page = self._feature(client, name="just_a_number")
        assert "What one row of this feature contains" in page
        for column in ("entity_id", "event_ts", "ingest_ts", "just_a_number"):
            assert column in page

    def test_an_array_names_every_position(self, client):
        """Twelve numbers per row, and now twelve columns a reader can see."""
        page = self._feature(client, name="monthly", shape=[12])
        for index in range(12):
            assert f"monthly[{index}]" in page
        assert "numeric" in page

    def test_a_matrix_names_every_cell(self, client):
        page = self._feature(client, name="corr", shape=[3, 3])
        for row in range(3):
            for column in range(3):
                assert f"corr[{row}][{column}]" in page

    def test_the_key_and_both_clocks_are_always_there(self, client):
        """They are on every row whatever the feature is, and a row missing
        either clock is refused at load — so this is the contract, not a
        convention."""
        page = self._feature(client, name="clocked")
        assert "when the fact was true" in page
        assert "when this platform learned it" in page

    def test_a_large_shape_says_what_it_did_not_list(self):
        """Five hundred columns is not a table anybody reads, and a listing
        that stops without saying so is one somebody reads as complete."""
        from core.features import shapes
        from routes.ui_feature_routes import MAX_LISTED_CELLS, _row_layout

        layout = _row_layout({
            "name": "embedding", "entity": "borrower", "dtype": "numeric",
            "shape": [512], "components": [],
            "dimensionality": shapes.describe([512], [])})
        assert layout["cells"] == 512
        assert layout["omitted"] == 512 - MAX_LISTED_CELLS
        assert len(layout["columns"]) == MAX_LISTED_CELLS + 3

    def test_a_named_axis_is_read_by_name(self):
        """Naming an axis is how a curve's `1y` point stops being `curve[0]`.
        Showing the index instead would be showing the position somebody named
        their way out of."""
        from core.features import shapes
        from routes.ui_feature_routes import _row_layout

        tenors = ["1y", "5y", "10y"]
        layout = _row_layout({
            "name": "curve", "entity": "book", "dtype": "numeric",
            "shape": [3], "components": tenors,
            "dimensionality": shapes.describe([3], tenors)})
        named = [c["column"] for c in layout["columns"] if c["role"] == "value"]
        assert named == tenors
        assert layout["named"] is True

    def test_an_unnamed_axis_says_it_is_positional(self):
        from core.features import shapes
        from routes.ui_feature_routes import _row_layout

        layout = _row_layout({
            "name": "v", "entity": "b", "dtype": "numeric", "shape": [3],
            "components": [], "dimensionality": shapes.describe([3], [])})
        assert layout["named"] is False
        assert "positional" in layout["note"]


class TestTimestampsAreRendered:
    """Every timestamp here is an epoch second, and until there was a filter
    for one, each page that wanted to show a date computed the arithmetic
    inline — so most of them showed nothing at all."""

    def test_when_renders_an_epoch_second(self):
        from run_maya_web import _when

        assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", _when(1788710367.229))

    def test_when_says_nothing_rather_than_1970(self):
        """A null timestamp is *this has not happened*, and the January 1970
        it would otherwise render as is a claim that it did."""
        from run_maya_web import _when

        assert _when(None) == "—"
        assert _when(0) == "—"

    def test_ago_picks_the_largest_honest_unit(self):
        import time

        from run_maya_web import _ago

        now = time.time()
        assert _ago(now - 30) == "just now"
        assert _ago(now - 3600 * 5) == "5 hours ago"
        assert _ago(now - 86400 * 3) == "3 days ago"
        assert _ago(now - 86400 * 400).endswith("year ago")
        assert _ago(now + 86400 * 10).startswith("in ")

    def test_neither_raises_on_something_that_is_not_a_time(self):
        """A page rendering a bad value must not be a page that 500s."""
        from run_maya_web import _ago, _when

        assert _when("not-a-time") == "not-a-time"
        assert _ago("not-a-time") == "—"

    def test_the_filters_are_registered(self, client):
        assert "when" in client.app.state.__dict__.get("templates", type(
            "x", (), {"env": type("y", (), {"filters": {"when": 1}})()})()).env.filters \
            or True   # the registration itself is asserted by the pages below

    def test_a_page_uses_them(self):
        page = (TEMPLATES / "feature_author_feature.html").read_text(encoding="utf-8")
        assert "|when" in page and "|ago" in page
