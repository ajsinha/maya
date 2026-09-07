"""Every link in the documentation goes somewhere.

Sixteen links across four documents pointed at tutorials that had been deleted
two milestones earlier — eleven per-fibre walkthroughs, replaced by six written
by running them. `docs/02 §5` introduced its table with *"Eight fibres are
worked end to end, one tutorial each"* and then linked eight files that did not
exist, which is a worse failure than the missing tutorials: a reader following
it concludes the documentation is unmaintained, and stops trusting the parts
that are right.

Two kinds of link, checked two ways. A **relative** target is a file in this
repository and must exist on disk. An **absolute** target is a URL the running
application serves, so it is checked against the app's own routes — `/help/…`
and `/tutorials/…` resolve through a router, not through the filesystem, and a
scan that treated them as paths would report a hundred and fifty false
failures and be turned off within a week.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

DOCUMENTS = (sorted((ROOT / "docs").rglob("*.md"))
             + sorted((ROOT / "content").rglob("*.md"))
             + [ROOT / "README.md"])


def _links(path: pathlib.Path):
    for text, target in LINK.findall(path.read_text(encoding="utf-8")):
        yield text, target


def test_every_relative_link_points_at_a_file_that_exists() -> None:
    broken = []
    for path in DOCUMENTS:
        for text, target in _links(path):
            if target.startswith(("http://", "https://", "mailto:", "#", "/")):
                continue
            clean = target.split("#")[0]
            if not clean:
                continue
            if not (path.parent / clean).resolve().exists():
                broken.append(f"{path.relative_to(ROOT)}: [{text}]({target})")
    assert broken == [], (
        f"{len(broken)} link(s) point at files that do not exist:\n  "
        + "\n  ".join(broken))


def test_the_scan_can_see_a_broken_link(tmp_path) -> None:
    """A link checker that matches nothing passes on a documentation set made
    entirely of dead links."""
    doc = tmp_path / "x.md"
    doc.write_text("[gone](./nowhere.md) and [here](./x.md)")
    found = [t for _text, t in _links(doc)
             if not (doc.parent / t.split("#")[0]).exists()]
    assert found == ["./nowhere.md"]


class TestTheServedLinks:
    """`/help/quickstart` and `/tutorials/features` are routes, not paths."""

    @staticmethod
    def _served(path: pathlib.Path):
        for text, target in _links(path):
            if target.startswith("/") and not target.startswith("//"):
                yield text, target.split("#")[0]

    def test_every_absolute_link_is_a_route_this_app_answers(self, client):
        broken = []
        for path in DOCUMENTS:
            for text, target in self._served(path):
                if not target:
                    continue
                status = client.get(target, follow_redirects=False).status_code
                # 200 is served; 3xx is a redirect to sign-in, which means the
                # route exists. 404 means it does not.
                if status == 404:
                    broken.append(f"{path.relative_to(ROOT)}: [{text}]({target})")
        assert broken == [], (
            f"{len(broken)} link(s) point at URLs this application does not "
            "serve:\n  " + "\n  ".join(broken))

    def test_the_scan_actually_fetched_something(self, client):
        """Otherwise the test above passes because it found no links at all."""
        found = sum(1 for path in DOCUMENTS for _ in self._served(path))
        assert found > 50, f"only {found} served links found; the scan is broken"
