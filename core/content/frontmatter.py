"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

YAML front matter.

A content file is metadata and prose in one artifact, so the two travel
together: a topic cannot be reordered, retitled or moved between sections
without the change appearing in the same diff as the words it describes.

    ---
    title: Registering a model
    section: The register
    order: 20
    ---
    The body starts here.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple

import yaml

from core.log import get_logger, swallowed

logger = get_logger(__name__)

FENCE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def split(text: str, origin: str = "<string>") -> Tuple[Dict[str, Any], str]:
    """Return (metadata, body). A file with no front matter is all body.

    Malformed front matter is a content error, not a crash: the body is still
    served, and the failure is logged rather than swallowed. A help page that
    renders without its title is far better than a help page that 500s.
    """
    match = FENCE.match(text)
    if not match:
        return {}, text
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        swallowed(logger, exc, f"front matter in {origin} is not valid YAML",
                  detail="serving the body with no metadata")
        return {}, text[match.end():]
    if not isinstance(meta, dict):
        logger.warning("front matter in %s is %s, not a mapping; ignoring it",
                       origin, type(meta).__name__)
        return {}, text[match.end():]
    return meta, text[match.end():]
