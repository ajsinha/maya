"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A pytest plugin that records every refusal code the suite actually raises.

    pytest -p tools.qa.codeprobe tests/

Section D asks whether a mapped refusal code can be emitted at all. Reading the
source answers whether one *could be*; this answers whether one *was*.

Implemented by wrapping `BaseException.__init__`? No — that is both slow and
too broad. Every refusal in this codebase sets `self.code` in its own
`__init__`, so the probe subscribes to exception construction through
`sys.monitoring`-free means: it patches the small, known set of error classes
discovered by import, and each patched `__init__` records the first argument
before delegating.

Anything it cannot patch is simply not recorded, which makes the probe
**conservative** — it can under-report provocation and never over-report it.
An under-report shows up as UNPROVEN, which asks a human to look; the opposite
error would quietly certify a control nobody exercised.
"""
from __future__ import annotations

import importlib
import pathlib
import pkgutil
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEEN = ROOT / "docs" / "QA" / "results" / ".codes-seen.txt"
CODE_SHAPE = re.compile(r"[a-z][a-z0-9_]{2,}")

_seen: set = set()


def _error_classes():
    """Every `*Error` class in the codebase whose first argument is a code."""
    found = []
    for package in ("core", "routes", "db"):
        base = ROOT / package
        if not base.is_dir():
            continue
        for info in pkgutil.walk_packages([str(base)], prefix=f"{package}."):
            try:
                module = importlib.import_module(info.name)
            except Exception as exc:
                # A module that will not import cannot contribute a refusal
                # class, and this probe must not be able to fail the run it is
                # observing. Printed rather than logged: pytest captures it,
                # and a silent skip here would shrink the probe's reach with
                # no trace, which reads afterwards as "that code is unproven".
                print(f"codeprobe: skipped {info.name} ({exc})")
                continue
            for name in dir(module):
                obj = getattr(module, name, None)
                if (isinstance(obj, type) and issubclass(obj, BaseException)
                        and name.endswith("Error")
                        and obj.__module__ == info.name):
                    found.append(obj)
    return found


def pytest_configure(config):
    for cls in _error_classes():
        original = cls.__init__

        def patched(self, *args, __original=original, **kwargs):
            if args and isinstance(args[0], str) and CODE_SHAPE.fullmatch(args[0]):
                _seen.add(args[0])
            return __original(self, *args, **kwargs)

        try:
            cls.__init__ = patched
        except (AttributeError, TypeError):
            continue


def pytest_sessionfinish(session, exitstatus):
    SEEN.parent.mkdir(parents=True, exist_ok=True)
    existing = set()
    if SEEN.is_file():
        existing = {ln.strip() for ln in
                    SEEN.read_text(encoding="utf-8").splitlines() if ln.strip()}
    SEEN.write_text("\n".join(sorted(existing | _seen)) + "\n",
                    encoding="utf-8")
