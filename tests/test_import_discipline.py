"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The layering rule, made mechanical.

`docs/12 §5` stated it as **"The rule, enforced in CI"** and printed an
`.importlinter` configuration to show how. For as long as that sentence existed
there was no CI of any kind here, so the rule was enforced by nobody — a control
described in a tense it had not earned, which is the fourth of the ways a
control reports success while doing nothing (`docs/11 §3`).

There is CI now, and this file runs in it. That does not make the walker
redundant: the pipeline decides *when* the rule is checked, and this decides
*what* the rule is. There is still no `.importlinter`, no `ruff` and no `mypy`,
so the rule holds because of what is written below rather than because of
anything installed.

The boundaries turned out to be held anyway, which is the good news and also the
reason it went unnoticed: a rule everybody happens to keep is indistinguishable
from a rule that is enforced, right up until somebody does not.

So this walks the imports instead. It needs no tooling, no configuration file
and no pipeline, and it fails in the same suite as everything else.

## The one permitted crossing

`core.log` is imported by `core/domain/` and by `db/`, and that is deliberate.
The platform rule is that no exception may be swallowed and everything must be
logged through the standardised logger; a layer forbidden from importing the
logger would have to either invent a second one or stay silent, and both are
worse than the dependency. It is named here so it stays a decision rather than
becoming a precedent.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Infrastructure every layer may reach for. Keep this list at one entry for as
#: long as possible: each addition is a boundary that no longer holds.
UNIVERSAL = {"core.log"}


def _imports(path: pathlib.Path) -> set:
    """Every absolute module this file imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def _files(package: str):
    return sorted((ROOT / package).rglob("*.py"))


def _crossings(path: pathlib.Path, forbidden_roots: set, own_prefix: str = "") -> list:
    out = []
    for module in _imports(path):
        if module in UNIVERSAL or any(module.startswith(u + ".") for u in UNIVERSAL):
            continue
        if own_prefix and module.startswith(own_prefix):
            continue
        if module.split(".")[0] in forbidden_roots:
            out.append(module)
    return sorted(out)


class TestTheLayeringRuleIsMechanical:

    def test_the_domain_depends_on_nothing_in_maya(self):
        """`core/domain/` is the algebra: kernels, schemas, the lattice, the
        trainability derivation. It is the one layer that must be readable, and
        checkable, without the platform around it — a proof that reads the
        database is not a proof."""
        wrong = {str(p.relative_to(ROOT)): bad
                 for p in _files("core/domain")
                 if (bad := _crossings(p, {"core", "routes", "db", "web", "sdk",
                                           "tools", "fastapi", "starlette",
                                           "pydantic", "sqlalchemy"},
                                       own_prefix="core.domain"))}
        assert not wrong, (
            "core/domain must not depend on the platform:\n    "
            + "\n    ".join(f"{k} imports {', '.join(v)}" for k, v in wrong.items()))

    def test_core_never_imports_the_web_layer(self):
        """The direction that matters. `routes/` and `web/` import core; core
        importing back is what turns a layered system into a ball of mud, and it
        is also how a governance decision ends up being made in a view."""
        wrong = {str(p.relative_to(ROOT)): bad
                 for p in _files("core")
                 if (bad := _crossings(p, {"routes", "web"}))}
        assert not wrong, (
            "core must not import the web layer:\n    "
            + "\n    ".join(f"{k} imports {', '.join(v)}" for k, v in wrong.items()))

    def test_the_persistence_layer_does_not_import_the_domain(self):
        """`db/` holds repositories and the Delta store. If it reached into
        `core/`, the schema would start encoding governance rules and there
        would be two places to change one of them."""
        wrong = {str(p.relative_to(ROOT)): bad
                 for p in _files("db")
                 if (bad := _crossings(p, {"core", "routes", "web"}))}
        assert not wrong, (
            "db must not import core:\n    "
            + "\n    ".join(f"{k} imports {', '.join(v)}" for k, v in wrong.items()))

    def test_the_sdk_carries_no_dependencies(self):
        """`docs/12` claims standard library only, on the argument that an SDK
        with a dependency tree moves the air-gap problem into the client's build
        rather than solving it. Asserted here rather than asserted in prose."""
        import sys
        stdlib = set(sys.stdlib_module_names)
        wrong = {}
        for p in _files("sdk/python"):
            outside = {m for m in _imports(p)
                       if m.split(".")[0] not in stdlib
                       and not m.startswith("maya_sdk")}
            if outside:
                wrong[str(p.relative_to(ROOT))] = sorted(outside)
        assert not wrong, (
            "the SDK must import the standard library only:\n    "
            + "\n    ".join(f"{k} imports {', '.join(v)}" for k, v in wrong.items()))

    @pytest.mark.parametrize("permitted", sorted(UNIVERSAL))
    def test_the_permitted_crossing_is_still_the_logger(self, permitted):
        """A named exception that nobody re-reads becomes a general permission.

        `core.log` is reachable from every layer because the platform rule is
        that no exception is swallowed and everything is logged through one
        logger — a layer forbidden from importing it would have to invent a
        second logger or stay silent. This pins what the exception is *for*, so
        that widening `UNIVERSAL` is a visible decision.
        """
        assert permitted == "core.log"
        module = ROOT / (permitted.replace(".", "/") + ".py")
        assert module.exists(), "the permitted crossing no longer exists"
        assert "def swallowed" in module.read_text(encoding="utf-8"), (
            "core.log is permitted everywhere because it carries the "
            "swallowed-exception discipline; if that has moved, the exemption "
            "needs re-arguing rather than inheriting")
