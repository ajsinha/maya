"""
What every case study shares: a MAYA to talk to, and a way to narrate what happens.

A case study is a sequence of separate scripts — set up the features, compose the
feature set, register the model, draw the warrant, fit it, take it live — and each one
can be run on its own, in its own process, in front of people. ``run.py`` runs them in
order for an unattended pass; running them one at a time is the demonstration, because
between two steps you can open the web UI and show what the last one actually created.

That only works if MAYA outlives the process, so every study uses the project's own
estate -- the one ``config/application.yaml`` configures, under ``data/`` -- rather than a
temporary directory. The first script to ask for it builds it -- database, blob store,
Delta lake, signer, every service, one user per built-in role -- each study adds its own
namespace, and every script after that opens the same one (``maya.testing``, which is a supported part of the platform
and not a test fixture smuggled into a demo). ``--reset`` starts again from nothing.

Everything a study then does goes through ``maya.sdk.Client`` as a named user with that
user's roles, because that is what a person integrating with MAYA would write, and
because a demo that reaches past the SDK proves nothing about the SDK. The two
exceptions are ``maya.drain()``, which runs the queued jobs a deployment's workers
would run, and ``maya.platform``, which the studies do not use.

Flags, on every script:

``--reset``   delete the shared demonstration estate and build it again from nothing.
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
    """This script's own flags, and any MAYA setting the caller wants to override.

    A study reads ``config/application.yaml`` -- the same file the web application reads,
    with nothing overridden -- so that what a study builds is what the application serves.
    Anything else here is a `--key=value` setting, passed through to the configuration
    loader exactly as it would be on the application's own command line:

        run.py --lake.root=/tmp/demo-lake     one study somewhere else
        run.py --storage.root=/tmp/demo       a whole estate somewhere else

    which is why unknown arguments are kept rather than refused.
    """
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument(
        "--reset",
        action="store_true",
        help="delete the shared demonstration estate and build it again from nothing",
    )
    ap.add_argument("--quiet", action="store_true", help="results only, no narration")
    args, rest = ap.parse_known_args()
    # `load_settings` reads sys.argv itself, so leaving the settings there is how they
    # reach it -- the same path the application's own flags take.
    sys.argv = [sys.argv[0]] + rest
    return args


def open_study(
    namespace: str,
    *,
    reset: bool = False,
    fresh: bool = False,
    extra_users: dict[str, list[str]] | None = None,
    settings: dict[str, str] | None = None,
) -> Any:
    """The project's MAYA, as ``config/application.yaml`` configures it.

    Every study shares one instance: one database, one lake, one set of users, and one web
    application that serves all of them. That is not a convenience -- it is the arrangement
    MAYA is deployed in, and a demonstration whose objects lived somewhere the application
    would not look would be demonstrating something nobody runs. Studies stay apart by
    namespace, which is what namespaces are for.

    ``extra_users`` adds people beyond the seeded seven, which a study needs whenever a
    policy asks for two holders of one role: an execution warrant submitted by a model
    manager wants a *second* model manager to approve it, and one person cannot be both,
    which is the point of the rule.
    """
    from maya.config import load_settings
    from maya.services.platform import Platform
    from maya.testing import DEFAULT_USERS, Maya
    from maya.testing.kit import default_config

    if reset:
        _reset_everything()
    config = load_settings(default_config(), fresh=True)
    if settings:  # a study that needs a setting of its own re-reads with it applied
        config = _with(default_config(), settings)
    home = config.storage_root
    home.mkdir(parents=True, exist_ok=True)
    platform = Platform.build(config, start_workers=False)
    users = {**DEFAULT_USERS, **(extra_users or {})}
    maya = Maya(platform, home, namespace, users, keep=True)
    seed(maya, users)
    if fresh and _already_run(maya, namespace):
        maya.close()
        raise SystemExit(
            f"    The '{namespace}' namespace is already in this estate, so a full pass would\n"
            "    try to create objects that exist. MAYA does not delete governed objects, so\n"
            "    there is no resetting one study out of a shared estate. Either:\n"
            "      --reset   rebuild the whole demonstration estate, every study in it\n"
            "      or run the step scripts, which continue the study that is already there."
        )
    return maya


def _already_run(maya: Any, namespace: str) -> bool:
    """Has a study already put objects in this namespace?"""
    admin = maya.client("admin")
    return bool(admin.features.list(namespace=namespace) or admin.models.list(namespace=namespace))


def _with(config_path: Path, overrides: dict[str, str]) -> Any:
    """The same configuration with a few keys overridden, as the command line would."""
    import sys

    from maya.config import load_settings

    saved = sys.argv
    sys.argv = ["case-study"] + [f"--{k}={v}" for k, v in overrides.items()]
    try:
        return load_settings(config_path, fresh=True)
    finally:
        sys.argv = saved


def _reset_everything() -> None:
    """Delete the shared demonstration instance and build it again from nothing.

    There is one instance, so there is no resetting one study out of it: MAYA does not
    delete governed objects, and a reset that removed a namespace's rows from underneath an
    audit chain would be teaching the wrong lesson about what a register is. So ``--reset``
    is honest about its scope -- it removes the whole demonstration estate, every study in
    it -- and says so before it does."""
    from maya.config import load_settings
    from maya.testing.kit import default_config

    config = load_settings(default_config(), fresh=True)
    root, lake = config.storage_root, config.lake_root
    print(f"    --reset: deleting the shared demonstration estate at {root}")
    print(f"             and its lake at {lake}. Every study goes with it.")
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(lake, ignore_errors=True)


def seed(maya: Any, users: dict[str, list[str]]) -> None:
    """One user per role and the study's namespace — through the SDK, as an admin would.

    Each user then changes their own password, because an administrator-set one must be
    changed at first sign-in (§12) and that is the right rule: without this the first thing a
    demonstration shows in the browser is a change-password form, which reads as a broken
    install rather than as a control working. So the study walks each account through the step
    a person would, and the password in ``browse_hint`` is then the one that actually works.
    """
    from maya.sdk import Client

    from maya.core.errors import ConflictError

    admin = maya.client("admin")
    have = {u["username"] for u in admin.admin.users()}
    for username, roles in users.items():
        if username in have:
            continue  # an earlier study in this estate already created them
        admin.admin.create_user(username, password=SETUP_PASSWORD, roles=list(roles))
        with Client(app=maya.app) as anonymous:
            token = anonymous.auth.login(username, SETUP_PASSWORD)["token"]
        with Client(app=maya.app, token=token) as fresh:
            fresh.auth.change_password(SETUP_PASSWORD, PASSWORD)
    try:
        admin.namespaces.create(maya.namespace, preset="standard")
    except ConflictError:
        pass  # this study has been run before in this estate


def browse_hint(maya: Any) -> None:
    """How to open the web UI on what the studies have built so far."""
    print(
        f"\n    This is the project's MAYA at {maya.home}, shared by every study.\n"
        f"    Browse it:  .venv/bin/python run_maya_web.py\n"
        f"    Then open http://127.0.0.1:{PORT} and sign in as any of "
        f"{', '.join(sorted(maya.users))}\n"
        f"    with the password '{PASSWORD}'. This study is the '{maya.namespace}' namespace."
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
