"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The content library.

Help and explanatory pages are markdown files on disk, rendered at request
time. They are not templates and not database rows, and both of those were
considered.

Not templates, because help text that lives inside markup can only be changed by
someone who can edit markup, which is the wrong constraint on the people who
actually know what the help should say. Not rows, because then it would need a
migration path, an editor, and a backup story to change a sentence — and it
would stop being reviewable in a pull request alongside the behaviour it
describes.

Files get the useful properties for free: version control, diff review, blame,
and a topic that cannot drift from the release it shipped with.

Rendered HTML is cached against the file's modification time, so editing a topic
shows up on the next request without a restart, and an unchanged topic is not
re-parsed on every page view.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.content.frontmatter import split
from core.content.renderer import MarkdownRenderer
from core.log import get_logger

logger = get_logger(__name__)


@dataclass
class Topic:
    """One rendered content file."""
    slug: str
    title: str
    summary: str = ""
    section: str = "General"
    order: int = 500
    icon: str = "file-text"
    audience: str = ""
    html: str = ""
    headings: List[Dict[str, Any]] = field(default_factory=list)
    source: str = ""

    @property
    def anchors(self) -> List[Dict[str, Any]]:
        """Second-level headings only — an on-page contents list, not an index."""
        return [h for h in self.headings if h["level"] == 2]


class ContentLibrary:
    """Loads a directory of markdown into Topics, cached on modification time."""

    def __init__(self, root: Path, renderer: Optional[MarkdownRenderer] = None):
        self.root = Path(root)
        self.renderer = renderer or MarkdownRenderer()
        self._cache: Dict[Path, Tuple[float, Topic]] = {}

    # ------------------------------------------------------------------ load
    def _load(self, path: Path) -> Optional[Topic]:
        try:
            stamp = path.stat().st_mtime
        except OSError as exc:
            logger.warning("content file vanished between listing and load: %s (%s)",
                           path, exc)
            return None
        cached = self._cache.get(path)
        if cached and cached[0] == stamp:
            return cached[1]

        meta, body = split(path.read_text(encoding="utf-8"), origin=str(path))
        html, headings = self.renderer.render(body)
        topic = Topic(
            slug=meta.get("slug") or self._slug(path),
            title=meta.get("title") or self._slug(path).replace("-", " ").capitalize(),
            summary=meta.get("summary", ""), section=meta.get("section", "General"),
            order=int(meta.get("order", 500)), icon=meta.get("icon", "file-text"),
            audience=meta.get("audience", ""), html=html, headings=headings,
            source=str(path.relative_to(self.root)) if self.root in path.parents
            else path.name)
        self._cache[path] = (stamp, topic)
        return topic

    @staticmethod
    def _slug(path: Path) -> str:
        """Filenames carry a numeric prefix for ordering; URLs should not."""
        stem = path.stem
        return stem.split("-", 1)[1] if stem[:2].isdigit() and "-" in stem else stem

    # ----------------------------------------------------------------- query
    def paths(self, area: str) -> List[Path]:
        directory = self.root / area
        return sorted(directory.glob("*.md")) if directory.is_dir() else []

    def topics(self, area: str) -> List[Topic]:
        """Every topic in an area, ordered by ``order`` then title."""
        found = [t for t in (self._load(p) for p in self.paths(area)) if t]
        return sorted(found, key=lambda t: (t.order, t.title))

    def get(self, area: str, slug: str) -> Optional[Topic]:
        return next((t for t in self.topics(area) if t.slug == slug), None)

    def sections(self, area: str) -> List[Tuple[str, List[Topic]]]:
        """Topics grouped into sections, each in the order the group first appears."""
        grouped: Dict[str, List[Topic]] = {}
        for topic in self.topics(area):
            grouped.setdefault(topic.section, []).append(topic)
        return list(grouped.items())

    def available(self) -> bool:
        return self.root.is_dir()
