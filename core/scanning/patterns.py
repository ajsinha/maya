"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The credential shapes, in one place.

`tools/ci/scan_secrets.py` has looked for these since the repository had a CI
gate, and the platform needs the same list at upload. Two copies of a pattern
list is two answers to *is this a secret*, and the copy that goes stale is
always the one somebody is relying on — so the tool imports this rather than the
other way round, and neither owns it.

**Shapes, not entropy.** An entropy scanner on a repository full of sha256
digests, ULIDs and canonical hashes cries wolf, and a check people learn to
override is worse than no check because it also reports success.
"""
from __future__ import annotations

import re
from typing import Pattern, Tuple

#: Each pattern, and what it is. The name travels with the hit, because "line
#: 41 matches a regex" is not something anybody can act on.
PATTERNS: Tuple[Tuple[str, str, Pattern], ...] = (
    ("private key", "a PEM private key block",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("aws access key", "an AWS access key id",
     re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("aws secret", "an AWS secret access key assignment",
     re.compile(r"aws_secret_access_key\s*[=:]\s*['\"][A-Za-z0-9/+=]{40}['\"]",
                re.IGNORECASE)),
    ("github token", "a GitHub token",
     re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack token", "a Slack token",
     re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("google api key", "a Google API key",
     re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("credentials in a url", "a username and password inside a URL",
     re.compile(r"\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:[^/\s:@]+@")),
    ("jwt", "a signed JSON Web Token",
     re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b")),
    ("bearer literal", "a hard-coded bearer token",
     re.compile(r"Authorization\s*[=:]\s*['\"]Bearer\s+[A-Za-z0-9._\-]{20,}['\"]")),
)


def find(text: str) -> list:
    """Every credential-shaped span, with what each one is."""
    out = []
    for name, means, pattern in PATTERNS:
        for match in pattern.finditer(text or ""):
            out.append({"pattern": name, "means": means,
                        "at": match.start(),
                        # The match is NOT quoted. A finding that carries the
                        # secret is a second copy of it, in a table more people
                        # can read than the file it came from.
                        "length": len(match.group(0))})
    return out
