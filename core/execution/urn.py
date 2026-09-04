"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Model URNs.

A consumer holds a URN and nothing else. Artifact location, schemas, operating
boundaries and policy are all resolved at runtime from it, which is precisely
what lets a governed version move happen without a consumer redeploying.

    maya://model/<name>              the environment's champion
    maya://model/<name>@1.4.2        a pinned version
    maya://model/<name>#challenger   a named alias
"""
from __future__ import annotations

from typing import Optional, Tuple

from core.execution.errors import WarrantError

PREFIX = "maya://model/"
DEFAULT_ALIAS = "champion"


def build_urn(name: str, semver: Optional[str] = None,
              alias: Optional[str] = None) -> str:
    """The inverse of parse_urn. A pinned version and an alias are exclusive."""
    if semver and alias:
        raise WarrantError("validation_failed",
                        "a URN pins a version or names an alias, never both", "")
    return f"{PREFIX}{name}" + (f"@{semver}" if semver else "") + (f"#{alias}" if alias else "")


def model_urn(name: str) -> str:
    """The bare model URN, with any version or alias stripped."""
    return f"{PREFIX}{name}"


def parse_urn(urn: str) -> Tuple[str, Optional[str], Optional[str]]:
    """``maya://model/<name>[@<semver>][#<alias>]`` -> (name, semver, alias)."""
    if not urn.startswith(PREFIX):
        raise WarrantError("validation_failed", f"not a MAYA model URN: {urn}",
                        "expected maya://model/<name>[@<semver>|#<alias>]")
    body = urn[len(PREFIX):]
    aliasname = semver = None
    if "#" in body:
        body, aliasname = body.split("#", 1)
    if "@" in body:
        body, semver = body.split("@", 1)
    if not body:
        raise WarrantError("validation_failed", f"empty model name in {urn}", "")
    return body, semver, aliasname
