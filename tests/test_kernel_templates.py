"""
The compute-kernel wizard's template library.

A library of examples that is not executed is a library of examples that has rotted. These
tests run every template through the same parser and the same generator the wizard uses, so
a template that stops working fails the build rather than failing a person.

One of them earns its place by having already caught something. MAYA's parser reads an
undeclared multi-letter name the way LaTeX does, as a product of single letters: `income`
is i·n·c·o·m·e unless somebody says otherwise. A template that does that still parses, still
generates code and is silently about the wrong thing -- which is the exact failure the
platform exists to prevent, committed in its own examples. So the declaration is a test
rather than a convention.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import ast

import pytest

from maya.formula.codegen import to_python_kernel
from maya.formula.ir import validate_ir
from maya.formula.parse import _normalise_name, parse_model
from maya.web.kernel_templates import GROUPS, TEMPLATES, for_ui

KEYS = [t["key"] for t in TEMPLATES]


def test_there_are_enough_of_them_to_be_worth_searching():
    assert len(TEMPLATES) >= 50
    assert len(set(KEYS)) == len(KEYS), "template keys are the identity; they must be unique"
    assert {t["group"] for t in TEMPLATES} <= set(GROUPS)
    for group in GROUPS:
        assert [t for t in TEMPLATES if t["group"] == group], f"{group} has no templates"


@pytest.mark.parametrize("t", TEMPLATES, ids=KEYS)
def test_every_template_parses_and_generates_a_kernel(t):
    ir = parse_model(t["formula"], roles=t["roles"])
    assert not validate_ir(ir)
    assert ir["outputs"][0]["name"]
    source = to_python_kernel(ir)
    tree = ast.parse(source)
    assert [type(n).__name__ for n in tree.body] == ["FunctionDef"]


@pytest.mark.parametrize("t", TEMPLATES, ids=KEYS)
def test_every_multi_letter_symbol_is_declared(t):
    """Otherwise the template means something other than what it says.

    An undeclared `income` is six features called i, n, c, o, m and e, and the formula that
    results parses, validates and computes a number. Nothing downstream can tell that it is
    not the model somebody meant to write, which is why this is asserted here and not left
    to whoever reads the example."""
    ir = parse_model(t["formula"], roles=t["roles"])
    declared = {_normalise_name(k.lstrip("\\")) for k in t["roles"]}
    loose = sorted(
        i["name"] for i in ir["inputs"] if len(i["name"]) > 1 and i["name"] not in declared
    )
    assert not loose, (
        f"{t['key']}: {loose} are multi-letter inputs nobody declared. Either declare them "
        "in the template's roles, or the parser has split a name into a product of letters."
    )


@pytest.mark.parametrize("t", TEMPLATES, ids=KEYS)
def test_every_declared_role_is_actually_used(t):
    """A role for a symbol the formula never mentions is a copy that has drifted."""
    ir = parse_model(t["formula"], roles=t["roles"])
    used = {i["name"] for i in ir["inputs"]} | {_normalise_name(n) for n in (ir.get("lets") or {})}
    stale = sorted(k for k in t["roles"] if _normalise_name(k.lstrip("\\")) not in used)
    assert not stale, f"{t['key']}: roles declared for symbols the formula does not use: {stale}"


def test_the_ui_form_carries_the_roles_as_the_box_expects_them():
    for t in for_ui():
        if t["roles"]:
            lines = t["roles_text"].splitlines()
            assert len(lines) == len(t["roles"])
            for line in lines:
                name, _, role = line.partition(": ")
                assert role in ("feature", "parameter", "constant"), line


def test_each_one_says_what_it_is_for():
    for t in TEMPLATES:
        assert t["title"] and t["note"], t["key"]
        assert len(t["note"]) > 40, f"{t['key']}: a note that says nothing is worse than none"
