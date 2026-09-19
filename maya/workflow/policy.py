"""
Workflow policy as data: loading, validation and the YAML projection (§10.2, §10.6).

A policy is validated when it is *edited*, not when it bites: an unknown
state, an unreachable state, a check nobody registered, a role that does not
exist, or an approval no role could ever satisfy are all refused with the
reason before the policy can be saved.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import yaml

from maya.core.errors import ValidationFailed

DEFAULTS_FILE = Path(__file__).parent / "default_policies.yaml"
OBJECT_TYPES = (
    "feature_version",
    "featureset_version",
    "model_version",
    "parameter_set",
    "training_warrant",
    "execution_warrant",
)
INITIAL_STATE = "draft"
LETTERS = set("CRUAPGQ")


def default_policies() -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(DEFAULTS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def validate(policy: dict[str, Any], *, checks: Iterable[str], roles: Iterable[str]) -> list[str]:
    """Every reason this policy cannot be saved. Empty means valid."""
    errors: list[str] = []
    checks, roles = set(checks), set(roles)
    states = policy.get("states") or []
    transitions = policy.get("transitions") or {}
    if INITIAL_STATE not in states:
        errors.append(f"the initial state '{INITIAL_STATE}' is missing")
    if not transitions:
        errors.append("the policy has no transitions")
    for name, t in transitions.items():
        errors += _validate_transition(name, t, set(states), checks, roles)
    unreachable = set(states) - _reachable(transitions)
    if unreachable:
        errors.append("unreachable state(s): " + ", ".join(sorted(unreachable)))
    if not any(t.get("to") == "approved" for t in transitions.values()):
        errors.append(
            "no transition reaches 'approved': every object would be permanently unapprovable"
        )
    return errors


def _validate_transition(  # noqa: C901 - a checklist
    name: str,
    t: dict[str, Any],
    states: set[str],
    checks: set[str],
    roles: set[str],
) -> list[str]:
    errors = []
    sources = t.get("from") or []
    if isinstance(sources, str):
        sources = [sources]
    for s in sources:
        if s not in states:
            errors.append(f"transition '{name}': unknown source state '{s}'")
    if t.get("to") not in states:
        errors.append(f"transition '{name}': unknown target state '{t.get('to')}'")
    for c in t.get("checks") or []:
        if c not in checks:
            errors.append(f"transition '{name}': check '{c}' does not exist")
    for r in t.get("roles") or []:
        if r not in roles:
            errors.append(f"transition '{name}': role '{r}' does not exist")
    cap = t.get("capability")
    if cap and cap not in LETTERS:
        errors.append(f"transition '{name}': capability '{cap}' is not one of C R U A P G Q")
    for a in t.get("approvals") or []:
        if a.get("role") not in roles:
            errors.append(
                f"transition '{name}': approval role '{a.get('role')}' does not exist,"
                " so the approval could never be satisfied"
            )
        if int(a.get("count", 1)) < 1:
            errors.append(f"transition '{name}': approval count must be at least 1")
    return errors


def _reachable(transitions: dict[str, Any]) -> set[str]:
    seen = {INITIAL_STATE}
    changed = True
    while changed:
        changed = False
        for t in transitions.values():
            sources = t.get("from") or []
            sources = [sources] if isinstance(sources, str) else sources
            if any(s in seen for s in sources) and t.get("to") not in seen:
                seen.add(t["to"])
                changed = True
    return seen


def to_yaml(policy: dict[str, Any]) -> str:
    """The canonical text projection. export → import → export is byte-identical."""
    return yaml.safe_dump(policy, sort_keys=True, default_flow_style=False, allow_unicode=True)


def from_yaml(text: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValidationFailed(f"Policy YAML does not parse: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationFailed("Policy YAML must be a mapping")
    return data


def transitions_from(policy: dict[str, Any], state: str) -> list[str]:
    out = []
    for name, t in (policy.get("transitions") or {}).items():
        sources = t.get("from") or []
        sources = [sources] if isinstance(sources, str) else sources
        if state in sources:
            out.append(name)
    return out
