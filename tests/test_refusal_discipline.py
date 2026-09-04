"""
MAYA — every coded refusal maps to a status that says who must act.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

A refusal is a governance decision, and a decision delivered as an unexplained
400 is one the caller cannot act on. Every ``SomethingError("code", ...)`` in
``core/`` must therefore appear in the route layer's status taxonomy.

This is enforced by walking the source rather than by review, because the
alternative is what happened: fifteen execution-layer codes accumulated over
three milestones, each surfacing as a bare 400, and nobody noticed because no
test exercised that path.
"""
from __future__ import annotations

import ast
import pathlib
import re

from routes.base import STATUS

ROOT = pathlib.Path(__file__).resolve().parent.parent
CODE_SHAPE = re.compile(r"[a-z][a-z0-9_]*$")

# A status that tells the caller nothing about who must act is not a mapping.
GENERIC = {400}


def _coded_refusals():
    """Every (code, file, line) raised as the first argument of an *Error."""
    found = []
    for path in sorted((ROOT / "core").rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
            if not name.endswith("Error") or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if CODE_SHAPE.fullmatch(first.value):
                    found.append((first.value, path.relative_to(ROOT), node.lineno))
    return found


def test_every_coded_refusal_has_a_status():
    refusals = _coded_refusals()
    assert refusals, "the walker found nothing, which means it is broken"

    unmapped = sorted({f"{code}  ({path}:{line})"
                       for code, path, line in refusals if code not in STATUS})
    assert not unmapped, (
        "these refusals carry a code the route layer does not map, so they reach "
        "a caller as a bare 400 with no indication of who must act:\n    "
        + "\n    ".join(unmapped))


def test_no_refusal_is_mapped_to_a_generic_status():
    """400 is the absence of a decision. Every code should say more than that:
    who has to act, and whether retrying could ever help."""
    generic = sorted(c for c in STATUS if STATUS[c] in GENERIC)
    assert not generic, (
        "these codes are mapped to a status that tells the caller nothing:\n    "
        + "\n    ".join(generic))


def test_the_taxonomy_has_no_codes_nothing_raises():
    """Rot in the other direction: a status for a refusal that no longer exists
    reads as a documented behaviour and is not one."""
    raised = {code for code, _, _ in _coded_refusals()}
    # Codes the route layer raises itself, rather than translating from core.
    ROUTE_OWNED = {
        "registry_refused", "feature_refused", "assembly_rejected",
        "validation_refused", "not_found", "forbidden", "unauthenticated",
        "blocked", "no_entitlement", "conflict", "grammar_violation",
    }
    orphans = sorted(set(STATUS) - raised - ROUTE_OWNED)
    assert not orphans, (
        "these codes are in the status taxonomy but nothing in core/ raises "
        "them:\n    " + "\n    ".join(orphans))
