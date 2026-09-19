"""
Workflow policy as data: loading, validation and the YAML projection (§10.2, §10.6).

A policy is validated when it is *edited*, not when it bites: an unknown
state, an unreachable state, a check nobody registered, a role that does not
exist, or an approval no role could ever satisfy are all refused with the
reason before the policy can be saved.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import re
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
# the authorization kind each governed object type is approved as (§11's matrix)
APPROVAL_KINDS = {
    "feature_version": "feature",
    "featureset_version": "featureset",
    "model_version": "model",
    "parameter_set": "parameter_set",
    "training_warrant": "training_warrant",
    "execution_warrant": "execution_warrant",
}
LETTERS = set("CRUAPGQ")

# An approval's `when` condition (§10.2). Deliberately tiny: an approval requirement is
# either always in force, or in force by the namespace's environment. A namespace marked
# `production` is env 'prod', every other is 'nonprod'. Anything else is refused when the
# policy is saved rather than read as "always", which is how a condition nobody noticed
# would quietly add an approver — or, worse, drop one.
ENVIRONMENTS = ("prod", "nonprod")
_WHEN_RE = re.compile(r"^env\s*(?P<op>==|!=)\s*['\"](?P<value>[a-z]+)['\"]$")
WHEN_FORMS = "prod, env == 'prod', env != 'prod', env == 'nonprod', env != 'nonprod'"


def when_problem(when: Any) -> str | None:
    """Why this `when` cannot be read, or None. ``None``/empty means "always"."""
    if when is None or when == "":
        return None
    if not isinstance(when, str):
        return f"approval condition must be text, not {type(when).__name__}"
    text = when.strip()
    if text == "prod":  # the shorthand, kept
        return None
    m = _WHEN_RE.match(text)
    if m is None:
        return f"approval condition '{when}' is not one of: {WHEN_FORMS}"
    if m["value"] not in ENVIRONMENTS:
        return f"approval condition '{when}': environment must be one of " + ", ".join(ENVIRONMENTS)
    return None


def when_applies(when: Any, namespace: dict[str, Any]) -> bool:
    """Whether an approval carrying ``when`` is required in ``namespace``. An unreadable
    condition is required, never skipped: saving it was refused, so a stored one is data
    from another version, and the safe reading of a condition MAYA cannot judge is "ask
    for the approval"."""
    if when is None or when == "" or not isinstance(when, str):
        return True
    text = when.strip()
    env = "prod" if namespace.get("production") else "nonprod"
    if text == "prod":
        return env == "prod"
    m = _WHEN_RE.match(text)
    if m is None or m["value"] not in ENVIRONMENTS:
        return True
    return (env == m["value"]) if m["op"] == "==" else (env != m["value"])


def default_policies() -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(DEFAULTS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def validate(
    policy: dict[str, Any],
    *,
    checks: Iterable[str],
    roles: Iterable[str],
    object_type: str | None = None,
) -> list[str]:
    """Every reason this policy cannot be saved. Empty means valid. With ``object_type``,
    an approval is also checked against the role ceiling (§11): a role that cannot approve
    that kind of object would leave everything it governs permanently in review."""
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
        errors += _validate_approvers(name, t, object_type)
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
        problem = when_problem(a.get("when"))
        if problem:
            errors.append(f"transition '{name}': {problem}")
    return errors


def _validate_approvers(name: str, t: dict[str, Any], object_type: str | None) -> list[str]:
    """An approval role must be able to approve this kind of object. §10.2's own example
    asks `model_owner` to approve a model version, and §11's matrix gives that role no 'A'
    on models: such a policy is accepted, and then nothing it governs can ever leave
    review. Only the built-in roles are checked here; a role defined at runtime carries
    its capabilities in the database, which this function does not read."""
    if object_type is None:
        return []
    from maya.security.roles import MATRIX

    kind = APPROVAL_KINDS.get(object_type)
    if kind is None:
        return []
    out = []
    for a in t.get("approvals") or []:
        role = a.get("role")
        caps = MATRIX.get(role)
        if caps is not None and "A" not in caps.get(kind, ""):
            out.append(
                f"transition '{name}': role '{role}' cannot approve a {kind} "
                f"(§11 gives it '{caps.get(kind, '')}'), so the approval could never be "
                "satisfied"
            )
    return out


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
