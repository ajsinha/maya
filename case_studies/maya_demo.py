"""
What every case study shares: a MAYA to talk to, and a way to narrate what happens.

A case study is a sequence of separate scripts — set up the features, compose the
feature set, register the model, draw the warrant, fit it, take it live — and each one
can be run on its own, in its own process, in front of people. ``run.py`` runs them in
order for an unattended pass; running them one at a time is the demonstration, because
between two steps you can open the web UI and show what the last one actually created.

That only works if MAYA outlives the process, so a study's MAYA lives at
``case_studies/runs/<namespace>/`` rather than in a temporary directory. The first
script to ask for it builds it — database, blob store, Delta lake, signer, every
service, one user per built-in role, the study's namespace — and every script after
that opens the same one (``maya.testing``, which is a supported part of the platform
and not a test fixture smuggled into a demo). ``--reset`` starts again from nothing.

Everything a study then does goes through ``maya.sdk.Client`` as a named user with that
user's roles, because that is what a person integrating with MAYA would write, and
because a demo that reaches past the SDK proves nothing about the SDK. The two
exceptions are ``maya.drain()``, which runs the queued jobs a deployment's workers
would run, and ``maya.platform``, which the studies do not use.

Flags, on every script:

``--reset``   delete this study's MAYA and build it again from nothing.
``--quiet``   print the headline results without the narration.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RULE = "─" * 78
RUNS = Path(__file__).resolve().parent / "runs"
PASSWORD = "Maya-testing-pass-1"  # maya.testing's seeded password, printed for the demo
SETUP_PASSWORD = "Maya-setup-pass-0"  # what the administrator sets; each user then changes it
PORT = 8600


class Narrator:
    """Prints the story as it happens: steps, findings, and what MAYA refused."""

    def __init__(self, title: str, quiet: bool = False) -> None:
        self.quiet = quiet
        self.step_no = 0
        self.started = time.perf_counter()
        if title and not quiet:
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

    def done(self, label: str = "done") -> None:
        print(f"\n{RULE}\n{label} in {time.perf_counter() - self.started:.1f}s\n{RULE}")


def arguments(description: str) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument(
        "--reset",
        action="store_true",
        help="delete this study's MAYA and build it again from nothing",
    )
    ap.add_argument("--quiet", action="store_true", help="results only, no narration")
    return ap.parse_args()


def open_study(
    namespace: str,
    *,
    reset: bool = False,
    extra_users: dict[str, list[str]] | None = None,
    settings: dict[str, str] | None = None,
) -> Any:
    """This study's MAYA at ``runs/<namespace>``, built on first use and reopened after.

    ``extra_users`` adds people beyond the seeded seven, which a study needs whenever a
    policy asks for two holders of one role: an execution warrant submitted by a model
    manager wants a *second* model manager to approve it, and one person cannot be both,
    which is the point of the rule.
    """
    from maya.services.platform import Platform
    from maya.testing import DEFAULT_USERS, Maya, load_test_settings

    from maya.config import project_root

    home = RUNS / namespace
    # The study's data goes in the project's own lake rather than under the study folder,
    # because that is where the rest of MAYA keeps it and a demonstration should not have
    # its data somewhere the application would not look. One directory per study, so a
    # study can still be reset on its own.
    lake = project_root() / "data" / "maya-deltalake"
    if reset:
        shutil.rmtree(home, ignore_errors=True)
        _forget(lake, namespace)
    building = not (home / "maya.db").exists()
    home.mkdir(parents=True, exist_ok=True)
    platform = Platform.build(
        load_test_settings(home, {"lake.root": str(lake), **(settings or {})}),
        start_workers=False,
    )
    users = {**DEFAULT_USERS, **(extra_users or {})}
    maya = Maya(platform, home, namespace, users, keep=True)
    if building:
        seed(maya, users)
    return maya


def _forget(lake: Path, namespace: str) -> None:
    """Remove one study's tables from the shared lake, and nothing else.

    Every study writes into the same lake, because that is how MAYA is deployed and a
    demonstration that invented its own arrangement would be demonstrating the wrong thing.
    A lake table is ``<kind>/<namespace>/<name>``, so a study's data is exactly the
    namespace directory under each kind -- which is what ``--reset`` may delete, and the
    whole lake is what it may not."""
    if not lake.exists():
        return
    for kind in lake.iterdir():
        if kind.is_dir():
            shutil.rmtree(kind / namespace, ignore_errors=True)


def seed(maya: Any, users: dict[str, list[str]]) -> None:
    """One user per role and the study's namespace — through the SDK, as an admin would.

    Each user then changes their own password, because an administrator-set one must be
    changed at first sign-in (§12) and that is the right rule: without this the first thing a
    demonstration shows in the browser is a change-password form, which reads as a broken
    install rather than as a control working. So the study walks each account through the step
    a person would, and the password in ``browse_hint`` is then the one that actually works.
    """
    from maya.sdk import Client

    admin = maya.client("admin")
    for username, roles in users.items():
        admin.admin.create_user(username, password=SETUP_PASSWORD, roles=list(roles))
        with Client(app=maya.app) as anonymous:
            token = anonymous.auth.login(username, SETUP_PASSWORD)["token"]
        with Client(app=maya.app, token=token) as fresh:
            fresh.auth.change_password(SETUP_PASSWORD, PASSWORD)
    admin.namespaces.create(maya.namespace, preset="standard")


def browse_hint(maya: Any) -> None:
    """How to open the web UI on what the study has built so far."""
    print(
        f"\n    This study's MAYA is at {maya.home}\n"
        f"    Browse it:  .venv/bin/python run_maya_web.py \\\n"
        f"                  --storage.root={maya.home} \\\n"
        f"                  --db.sqlite.path={maya.home}/maya.db\n"
        f"    Then open http://127.0.0.1:{PORT} and sign in as any of "
        f"{', '.join(sorted(maya.users))}\n"
        f"    with the password '{PASSWORD}'."
    )


def step_script(
    title: str, namespace: str, work: Any, *, extra_users: dict[str, list[str]] | None = None
) -> int:
    """Run one step of a study as a standalone script: open MAYA, narrate, close.

    ``work(maya, cast_or_none, narrator)`` is the step itself. Every step script ends with
    ``sys.exit(step_script(...))``, so the steps can be run one at a time in front of an
    audience, and ``run.py`` can call the same functions in one process for a full pass.
    """
    args = arguments(title)
    n = Narrator(title, args.quiet)
    maya = open_study(namespace, reset=args.reset, extra_users=extra_users)
    try:
        work(maya, n)
        n.done()
        return 0
    finally:
        maya.close()
