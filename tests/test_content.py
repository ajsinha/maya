"""
MAYA — the content library.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Help pages are markdown on disk. That buys version control and review, and it
costs a rendering path that has to behave when the files are wrong — malformed
front matter, a missing directory, a file that vanishes mid-request. Those are
the cases tested hardest here, because they are the ones that would otherwise
take the help system down at exactly the moment somebody needed it.

The last class checks the shipped content itself: unique slugs, real summaries,
and internal links that resolve. A help system whose own links 404 is worse than
none.
"""
import pathlib

import pytest

from core.content import ContentLibrary, MarkdownRenderer, split

ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestFrontMatter:
    def test_metadata_and_body_are_separated(self):
        meta, body = split("---\ntitle: A\norder: 20\n---\nThe body.\n")
        assert meta == {"title": "A", "order": 20}
        assert body.strip() == "The body."

    def test_a_file_without_front_matter_is_all_body(self):
        meta, body = split("# Just a heading\n")
        assert meta == {} and body.startswith("# Just")

    def test_malformed_front_matter_still_serves_the_body(self):
        """A help page that renders without its title beats one that 500s."""
        meta, body = split("---\ntitle: [unclosed\n---\nThe body.\n", origin="bad.md")
        assert meta == {}
        assert "The body." in body

    def test_front_matter_that_is_not_a_mapping_is_ignored(self):
        meta, body = split("---\n- one\n- two\n---\nBody.\n", origin="list.md")
        assert meta == {} and "Body." in body

    def test_a_body_containing_a_rule_is_not_truncated(self):
        _, body = split("---\ntitle: A\n---\nBefore.\n\n---\n\nAfter.\n")
        assert "Before." in body and "After." in body


class TestRendering:
    @pytest.fixture
    def renderer(self):
        return MarkdownRenderer()

    def test_tables_render_as_tables(self, renderer):
        html, _ = renderer.render("| a | b |\n|---|---|\n| 1 | 2 |\n")
        assert "<table>" in html and "<td>1</td>" in html

    def test_fenced_code_is_highlighted(self, renderer):
        html, _ = renderer.render("```bash\nPOST /api/v1/models\n```")
        # codehilite tokenises, so the text is spread across spans; assert on the
        # structure and the tokens rather than on a contiguous string.
        assert 'class="highlight"' in html and "<pre" in html
        assert "POST" in html and "/api/v1/models" in html

    def test_headings_are_collected_with_anchors(self, renderer):
        _, headings = renderer.render("## First\n\ntext\n\n## Second\n")
        names = [h["name"] for h in headings]
        assert names == ["First", "Second"]
        assert all(h["id"] for h in headings), "each heading needs an anchor to link to"

    def test_state_does_not_leak_between_renders(self, renderer):
        """The library carries the toc between calls; a fresh instance per render
        is what stops one document's contents appearing in the next one."""
        renderer.render("## Alpha\n")
        _, headings = renderer.render("## Beta\n")
        assert [h["name"] for h in headings] == ["Beta"]


class TestLibrary:
    @pytest.fixture
    def library(self, tmp_path):
        area = tmp_path / "help"
        area.mkdir()
        (area / "20-second.md").write_text(
            "---\ntitle: Second\nsection: Basics\norder: 20\nsummary: s2\n---\n## H\ntext\n")
        (area / "10-first.md").write_text(
            "---\ntitle: First\nsection: Basics\norder: 10\nsummary: s1\n---\ntext\n")
        (area / "30-other.md").write_text(
            "---\ntitle: Other\nsection: Reference\norder: 30\n---\ntext\n")
        return ContentLibrary(tmp_path)

    def test_topics_are_ordered_by_their_declared_order(self, library):
        assert [t.title for t in library.topics("help")] == ["First", "Second", "Other"]

    def test_the_numeric_filename_prefix_is_not_in_the_slug(self, library):
        assert {t.slug for t in library.topics("help")} == {"first", "second", "other"}

    def test_sections_group_in_first_appearance_order(self, library):
        sections = library.sections("help")
        assert [name for name, _ in sections] == ["Basics", "Reference"]
        assert [t.title for t in sections[0][1]] == ["First", "Second"]

    def test_a_topic_is_fetched_by_slug(self, library):
        assert library.get("help", "second").title == "Second"

    def test_an_unknown_slug_returns_none(self, library):
        assert library.get("help", "nope") is None

    def test_a_missing_area_is_empty_rather_than_an_error(self, library):
        assert library.topics("does-not-exist") == []

    def test_editing_a_file_is_picked_up_without_a_restart(self, library, tmp_path):
        """Cached on modification time, so an edit shows on the next request."""
        first = library.get("help", "first")
        assert "text" in first.html
        path = tmp_path / "help" / "10-first.md"
        path.write_text("---\ntitle: First\nsection: Basics\norder: 10\n---\nrewritten\n")
        import os, time
        os.utime(path, (time.time() + 2, time.time() + 2))
        assert "rewritten" in library.get("help", "first").html

    def test_an_unchanged_file_is_not_re_rendered(self, library, tmp_path):
        a = library.get("help", "first")
        b = library.get("help", "first")
        assert a is b, "the cache should return the same object for an unchanged file"

    def test_a_topic_without_a_title_falls_back_to_its_slug(self, tmp_path):
        area = tmp_path / "help"; area.mkdir()
        (area / "99-untitled.md").write_text("Just a body.\n")
        assert ContentLibrary(tmp_path).get("help", "untitled").title == "Untitled"

    def test_anchors_are_second_level_headings_only(self, tmp_path):
        area = tmp_path / "help"; area.mkdir()
        (area / "01-a.md").write_text(
            "---\ntitle: A\n---\n# Page title\n\n## Section\n\n### Detail\n")
        anchors = ContentLibrary(tmp_path).get("help", "a").anchors
        assert [a["name"] for a in anchors] == ["Section"], \
            "an on-page contents list, not a full index"


class TestTheShippedContent:
    """The content that actually ships is checked like code, because it is."""

    @pytest.fixture
    def library(self):
        return ContentLibrary(ROOT / "content")

    def test_help_topics_exist(self, library):
        assert len(library.topics("help")) >= 12

    def test_every_topic_has_a_title_and_a_summary(self, library):
        for t in library.topics("help"):
            assert t.title and t.summary, f"{t.source} is missing title or summary"

    def test_slugs_are_unique(self, library):
        slugs = [t.slug for t in library.topics("help")]
        assert len(slugs) == len(set(slugs)), "two topics would answer to one URL"

    def test_every_topic_renders_to_html(self, library):
        for t in library.topics("help"):
            assert t.html.strip(), f"{t.source} rendered to nothing"

    def test_internal_help_links_resolve(self, library):
        """A help system whose own links 404 is worse than none."""
        import re
        slugs = {t.slug for t in library.topics("help")}
        broken = []
        for t in library.topics("help"):
            for target in re.findall(r'href="/help/([a-z0-9-]+)"', t.html):
                if target not in slugs:
                    broken.append(f"{t.source} -> /help/{target}")
        assert not broken, "broken internal links:\n  " + "\n  ".join(broken)

    def test_the_about_area_carries_the_competitive_analysis(self, library):
        titles = [t.title for t in library.topics("about")]
        assert "Competitive analysis" in titles
