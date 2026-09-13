"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Section I — the shape of a refusal, across the whole codebase.

Every refusal in MAYA is `error` / `detail` / `remediation`: what was refused,
why, and what to do instead. That contract is the platform's main claim about
being usable, and it is a property of 773 raise sites rather than of any one
of them — so it is checked in bulk, the way `spec_lock` checks routes.
"""
from __future__ import annotations

import pathlib
import re

from routes.base import STATUS
from qa.regression_suite.scenarios.common import FAIL, PASS, Ctx, Result, case

#: `SomethingError("code", ...)` — the first positional argument of every
#: refusal the platform raises.
RAISE = re.compile(r'Error\(\s*\n?\s*"([a-z_]{3,})"')
#: The same, where the third argument is written as an empty string.
NO_REMEDY = re.compile(
    r'Error\(\s*"([a-z_]{3,})"\s*,\s*(?:f?"[^"]*"\s*)+,\s*""\s*\)')
#: Refusals where "what to do instead" is the refusal itself. Naming a thing
#: that does not exist has no remedy beyond naming one that does.
ABSENCE = ("no_", "unknown_", "not_found", "no_such", "missing")


def _sources():
    return sorted(pathlib.Path("core").rglob("*.py"))


@case("QA-PLT-2800", "Every refusal code the platform raises has a status")
def plt_2800(ctx: Ctx) -> Result:
    """`routes/base.py::STATUS` turns a code into an HTTP status. A code with
    no entry falls to the default, so a conflict and a bad request answer the
    same number and a client cannot tell retry-able from not.
    """
    raised = {}
    for path in _sources():
        for match in RAISE.finditer(path.read_text(encoding="utf-8")):
            raised.setdefault(match.group(1), set()).add(path.name)
    unmapped = sorted(c for c in raised if c not in STATUS)
    if unmapped:
        return FAIL, (f"{len(unmapped)} of {len(raised)} refusal codes have "
                      f"no status mapping, so each answers the default: "
                      + ", ".join(unmapped[:10]))
    return PASS, f"all {len(raised)} refusal codes are mapped to a status"


@case("QA-PLT-2801", "Every actionable refusal says what to do instead")
def plt_2801(ctx: Ctx) -> Result:
    """A refusal naming something that does not exist needs no remedy — the
    detail already is one. Every other refusal is a caller who did something
    they could have done differently, and an empty third argument leaves them
    to guess.
    """
    blank = []
    total = 0
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        total += len(RAISE.findall(text))
        for match in NO_REMEDY.finditer(text):
            code = match.group(1)
            if not any(code.startswith(a) or a in code for a in ABSENCE):
                blank.append(code)
    unique = sorted(set(blank))
    if unique:
        return FAIL, (
            f"{len(unique)} actionable refusal code(s) of {total} raise sites "
            f"carry an explicitly empty remediation, so a caller who did "
            f"something they could have done differently is told what and not "
            f"what instead: " + ", ".join(unique[:12]))
    return PASS, f"every actionable refusal of {total} names a remedy"


@case("QA-PLT-2802", "Every refusal type reaches HTTP as a refusal")
def plt_2802(ctx: Ctx) -> Result:
    """There are TWO refusal shapes here, and that is deliberate. Most
    subsystems raise an error carrying its own `code` and `as_problem`, and
    `guard` handles those duck-typed. Seven older ones carry only a message —
    `RegistryError`, `ValidationError`, `AuthzError`, `FeatureError`,
    `SourceError`, `AssemblyRejected`, `ConfigError` — and the route layer
    supplies the code and a generic remediation for them.

    The property that matters is not that they look alike. It is that no
    error class falls through BOTH paths, because one that did would leave a
    working control reporting as a 500 — which is exactly what happened once
    to `SourceError`, whose refusals all crashed while the control worked
    perfectly.
    """
    import importlib
    import inspect as _i
    import pkgutil

    import pathlib as _p

    import core
    from routes.base import REMEDY

    adapted = tuple(REMEDY)
    # A type may also be caught by name somewhere in routes/ — `AuthzError`
    # is handled inside `authorise` rather than inside `guard`, which is a
    # different path and not a gap. And a type raised only while reading
    # configuration at start-up never travels a request at all.
    caught = "\n".join(f.read_text(encoding="utf-8")
                        for f in _p.Path("routes").rglob("*.py"))
    startup_only = {"core.config.properties_configurator.ConfigError"}
    orphans, seen = [], set()
    for found in pkgutil.walk_packages(core.__path__, "core."):
        try:
            module = importlib.import_module(found.name)
        except Exception as exc:                 # an optional dependency
            orphans.append(f"{found.name} did not import: {exc}")
            continue
        for obj in vars(module).values():
            if not (_i.isclass(obj) and issubclass(obj, RuntimeError)
                    and obj is not RuntimeError
                    and obj.__module__.startswith("core.")):
                continue
            key = f"{obj.__module__}.{obj.__name__}"
            if key in seen:
                continue
            seen.add(key)
            duck = hasattr(obj, "code") or (
                hasattr(obj, "as_problem")
                and "code" in _i.signature(obj.__init__).parameters)
            if duck or issubclass(obj, adapted):
                continue
            if f"except {obj.__name__}" in caught or \
                    f"{obj.__name__} as exc" in caught or key in startup_only:
                continue
            orphans.append(key)
    if orphans:
        return FAIL, (
            f"{len(orphans)} of {len(seen)} refusal type(s) are neither "
            f"duck-typed with a code nor adapted by `guard`, so raising one "
            f"answers 500 and a working control reads as a crash: "
            + ", ".join(orphans[:8]))
    return PASS, (f"all {len(seen)} refusal types reach HTTP as refusals: "
                  f"duck-typed, adapted by `guard`, caught by name in a "
                  f"route, or raised only at start-up")


@case("QA-PLT-2803", "No refusal code is raised under two spellings")
def plt_2803(ctx: Ctx) -> Result:
    """A caller branches on the code. Two codes for one condition — or one
    code meaning two things in two subsystems — makes that branch wrong
    somewhere. Reported rather than asserted: sharing a code across
    subsystems is legitimate when the condition really is the same.
    """
    where = {}
    for path in _sources():
        for match in RAISE.finditer(path.read_text(encoding="utf-8")):
            where.setdefault(match.group(1), set()).add(str(path))
    shared = {c: s for c, s in where.items() if len(s) > 3}
    if not shared:
        return PASS, "no refusal code is raised from more than three modules"
    worst = sorted(shared.items(), key=lambda kv: -len(kv[1]))[:4]
    return PASS, ("codes raised from many modules, each a place the "
                  "condition must genuinely be the same: "
                  + ", ".join(f"{c} ({len(s)})" for c, s in worst))
