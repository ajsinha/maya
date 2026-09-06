"""
MAYA — a secret committed by accident.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Written rather than vendored, for the reason the table script is: this needs to
run in a bank's own CI with no network and no third-party action, and the whole
job is a dozen patterns over the tracked files.

It looks for the shapes that are unambiguous — a private key header, an AWS
access key id, a bearer token in a URL — rather than for entropy. An entropy
scanner on a repository full of sha256 digests, ULIDs and canonical hashes is a
scanner that cries wolf, and a check people learn to override is worse than no
check because it also reports success.

    python tools/ci/scan_secrets.py [--all]
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[2]

#: Each pattern, and what it is. The name is printed with the hit, because
#: "line 41 matches a regex" is not something anybody can act on.
PATTERNS: Tuple[Tuple[str, str, "re.Pattern[str]"], ...] = (
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

#: Files that legitimately contain something shaped like a credential.
#:
#: The published session secret and the demo signing key are the two the
#: platform warns about at start-up, loudly, every time. They are in the
#: repository deliberately so an instance runs out of the box, and the warnings
#: are how somebody is told to change them — so a scanner that failed the build
#: on them would be arguing with a decision that was already made and
#: documented.
ALLOWED = {
    "tools/ci/scan_secrets.py",         # the patterns themselves
    "config/application.yaml",          # the published defaults, warned about at boot
    "docs/09-security-compliance.md",   # which explains exactly that
    # A connection string with the password elided as `...`, shown so a reader
    # knows the shape. Nothing here is a credential.
    "content/help/14-api-reference.md",
    # The throwaway password of an ephemeral local PostgreSQL container, named
    # in the docstring that tells somebody how to start it. It grants access to
    # a database created and dropped by the test run.
    "tests/test_postgres_dialect.py",
    # The scanner's own tests, which must contain one example per pattern or
    # they are testing nothing. Excusing the test rather than weakening a
    # pattern is the right way round: the patterns are the product here.
    "tests/test_secret_scanner.py",
}

SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "web/static/vendor",
             "data", "htmlcov"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".pptx",
                 ".parquet", ".db", ".woff", ".woff2", ".ttf", ".zip"}


def tracked() -> List[Path]:
    """The files git is tracking. Untracked working files are not shipped."""
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True,
                             capture_output=True, text=True).stdout
        return [ROOT / line for line in out.splitlines() if line]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return [p for p in ROOT.rglob("*") if p.is_file()]


def scan() -> List[str]:
    hits: List[str] = []
    for path in tracked():
        relative = path.relative_to(ROOT).as_posix()
        if relative in ALLOWED or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        # `any(part in SKIP_DIRS for part in SKIP_DIRS)` is True for every
        # file, because it asks whether each member of a set is in that set.
        # This scanner shipped with that line, reported "no secrets found in
        # 551 tracked files", and had read none of them — a control reporting
        # success while doing nothing, in the tool written to catch a different
        # one. Caught by planting a private key and watching it pass.
        if set(Path(relative).parts) & SKIP_DIRS:
            continue
        if any(relative.startswith(prefix) for prefix in SKIP_DIRS):
            continue
        try:
            text = path.read_text(errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for name, what, pattern in PATTERNS:
                if pattern.search(line):
                    hits.append(f"{relative}:{number}: {what} ({name})")
    return hits


def main() -> int:
    hits = scan()
    if not hits:
        print(f"no secrets found in {len(tracked())} tracked files")
        return 0
    print("possible secrets committed to this repository:\n")
    for hit in hits:
        print(f"    {hit}")
    print("\nIf one of these is deliberate — a published default the platform "
          "warns about at start-up — add the file to ALLOWED in this script "
          "with a comment saying why. Do not delete the pattern.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
