"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Content.

Help and explanatory pages are markdown files under content/, rendered at
request time and cached on modification time. Split by responsibility: front
matter parsing, markdown rendering, and the library that discovers and groups
them.
"""
from core.content.frontmatter import split
from core.content.library import ContentLibrary, Topic
from core.content.renderer import MarkdownRenderer

__all__ = ["ContentLibrary", "MarkdownRenderer", "Topic", "split"]
