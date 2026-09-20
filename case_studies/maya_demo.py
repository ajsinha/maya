"""
The few lines every case study shares: a MAYA to talk to, and a way to narrate.

Each case study is a script a person runs in front of other people. What it must not
be is a script that needs a running server, a database, an API key and a namespace
prepared by hand before it will say anything — by the time that is arranged the room
has moved on. So the default is a complete MAYA built in a temporary directory in a
couple of seconds: real database, real lake, real permissions, real workflow, real
signer, no server and no network (``maya.testing.Maya``, which is a supported part of
the platform and not a test fixture smuggled into a demo).

Everything the studies then do goes through ``maya.sdk.Client`` as a named user with
that user's roles, because that is what a person integrating with MAYA would write,
and because a demo that reaches past the SDK proves nothing about the SDK. The only
exceptions are ``maya.drain()``, which runs the queued jobs that a deployment's
workers would run, and ``maya.platform``, which the studies do not use.

Two flags, on every study:

``--keep``  leave the directory on disk and print it, so the objects the script made
            can be browsed in the web UI afterwards (the command is printed too).
``--quiet`` print the headline results without the narration.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RULE = "─" * 78


class Narrator:
    """Prints the story as it happens: steps, findings, and what MAYA refused."""

    def __init__(self, title: str, quiet: bool = False) -> None:
        self.quiet = quiet
        self.step_no = 0
        self.started = time.perf_counter()
        if not quiet:
            print(f"\n{RULE}\n{title}\n{RULE}")

    def step(self, text: str) -> None:
        self.step_no += 1
        if not self.quiet:
            print(f"\n[{self.step_no}] {text}")

    def say(self, text: str) -> None:
        if not self.quiet:
            print(f"    {text}")

    def fact(self, label: str, value: Any) -> None:
        """A result worth reading even in --quiet: the evidence the study is about."""
        print(f"    {label + ':':<34} {value}")

    def refused(self, what: str, error: Exception) -> None:
        """A refusal is a result. Every study shows at least one on purpose."""
        message = getattr(error, "message", None) or str(error)
        print(f"    refused — {what}\n      {type(error).__name__}: {message}")

    def done(self) -> None:
        print(f"\n{RULE}\ndone in {time.perf_counter() - self.started:.1f}s\n{RULE}")


def arguments(description: str) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument(
        "--keep",
        action="store_true",
        help="leave the MAYA directory on disk so the UI can be pointed at it",
    )
    ap.add_argument("--quiet", action="store_true", help="results only, no narration")
    return ap.parse_args()


def start(
    namespace: str,
    keep: bool = False,
    extra_users: dict[str, list[str]] | None = None,
    **settings: str,
) -> Any:
    """A throwaway MAYA with this study's namespace and one user per built-in role.

    ``extra_users`` adds people beyond the seeded seven. A study needs this whenever a
    policy asks for two holders of the same role — an execution warrant submitted by a
    model manager wants a *second* model manager to approve it, and one person cannot be
    both, which is the point of the rule."""
    from maya.testing import DEFAULT_USERS, Maya

    if keep:
        # A kept MAYA is one a person will open in the browser afterwards, so it goes
        # somewhere findable and out of /tmp, which on a developer machine is both
        # size-limited and swept.
        runs = Path(__file__).resolve().parent / "runs"
        runs.mkdir(exist_ok=True)
        tempfile.tempdir = str(runs)  # process-local; os.environ is not touched
    return Maya.start(
        namespace=namespace,
        keep=keep,
        users={**DEFAULT_USERS, **(extra_users or {})},
        settings=settings or None,
    )


def browse_hint(maya: Any, narrator: Narrator) -> None:
    """With --keep, how to open the web UI on what this study just built."""
    if not maya.keep:
        return
    print(
        f"\n    The MAYA this study built is at {maya.home}\n"
        f"    Browse it:  .venv/bin/python run_maya_web.py \\\n"
        f"                  --storage.root={maya.home} \\\n"
        f"                  --db.sqlite.path={maya.home}/maya.db\n"
        f"    Then open http://127.0.0.1:8600 and sign in as any of "
        f"{', '.join(sorted(maya.users))}\n"
        f"    with the password 'Maya-testing-pass-1'."
    )
