"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A route that asks for a permission nobody defines is a route nobody can call.

Three endpoints shipped authorising on `"admin"`. That is a **role**, not a
permission, so `authorise` answered `unknown_permission` (422) to every caller
including an administrator — and the whole compaction subsystem, plan, sweep
and vacuum alike, was unreachable from the moment it was written.

It is the recurring shape of this codebase in a new costume: built, wired,
documented, and never callable. The two mechanisms that catch that shape did
not see this one. `tests/test_uncalled_controls.py` looks for controls with no
call site, and these had call sites — three routes. The QA run's section A
calls every operation and counts anything under 500 as a considered answer, so
a 422 naming a real refusal code looked like the platform working.

What found it was a hand-written case that asserted **which** refusal came
back. What stops it recurring is this: `authorise` is only ever handed a
string `core.authz.common.PERMISSIONS` knows.
"""
from __future__ import annotations

import pathlib
import re

from core.authz.common import PERMISSIONS

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _asked_for() -> list:
    """Every literal permission a route hands to `authorise`."""
    found = []
    for path in sorted((ROOT / "routes").glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(
                r'authorise\(\s*request,\s*"([a-z_:*]+)"', text):
            line = text.count("\n", 0, match.start()) + 1
            found.append((match.group(1), f"{path.name}:{line}"))
    return found


class TestEveryRouteAsksForARealPermission:
    def test_no_route_authorises_on_an_unknown_string(self):
        asked = _asked_for()
        assert asked, "the scan found no authorise() call; check the pattern"
        unknown = sorted({f"{name} ({where})" for name, where in asked
                          if name not in PERMISSIONS})
        assert not unknown, (
            f"these routes ask for something core.authz.common.PERMISSIONS "
            f"does not define, so every caller — administrators included — is "
            f"answered `unknown_permission` and the endpoint cannot be "
            f"reached at all: {unknown}")

    def test_no_route_authorises_on_a_role_name(self):
        """The specific mistake, named. A role is a bundle of permissions and
        is never the thing a route checks."""
        from core.authz.roles import ROLES
        asked = {name for name, _ in _asked_for()}
        overlap = sorted(asked & set(ROLES))
        assert not overlap, (
            f"these are role names, not permissions: {overlap}")

    def test_the_scan_reaches_a_realistic_number_of_routes(self):
        """A guard on the guard: a regex that matches nothing agrees with
        everything, which is how the original defect survived section A."""
        assert len(_asked_for()) > 200


class TestTheCompactionPermissionIsItsOwn:
    def test_it_exists(self):
        assert "storage:compact" in PERMISSIONS

    def test_only_the_administrator_holds_it(self):
        """A sweep is irreversible and estate-wide. It is deliberately not
        folded into `model:delete`: deleting one model is an act about that
        model and is refused while anything refers to it; a sweep is an act
        about the whole store."""
        from core.authz.roles import ROLES
        holders = sorted(r for r, granted in ROLES.items()
                         if "storage:compact" in granted)
        assert holders == ["admin"], f"also held by {holders}"
