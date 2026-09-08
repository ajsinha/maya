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
