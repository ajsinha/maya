"""
An approval's ``when`` condition (§10.2). The specification writes it
``when: "env == 'prod'"``; MAYA read only the bare word ``prod`` and treated
everything else as "always required" — including the specification's own form, and
including a typo. Now the condition is read, a form MAYA cannot read is refused when the
policy is saved, and a stored one it cannot read asks for the approval rather than
dropping it.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import copy

import pytest

from maya.core.errors import ValidationFailed
from maya.workflow import policy as policy_mod
from tests.conftest import PX_DEF, price_csv  # noqa: F401 - fixtures import chain


def _global(w, object_type="feature_version"):
    """The active global policy for an object type."""
    return next(
        p
        for p in w.p.workflow_svc.policies()
        if p["object_type"] == object_type and p["state"] == "active" and p["scope"] == "*"
    )["policy"]


PROD = {"production": True}
DEV = {"production": False}


@pytest.mark.parametrize(
    "when,in_prod,elsewhere",
    [
        (None, True, True),
        ("", True, True),
        ("prod", True, False),
        ("env == 'prod'", True, False),
        ('env == "prod"', True, False),
        ("env != 'prod'", False, True),
        ("env == 'nonprod'", False, True),
        ("env != 'nonprod'", True, False),
        ("  env  ==  'prod'  ", True, False),
    ],
)
def test_every_readable_condition(when, in_prod, elsewhere):
    assert policy_mod.when_problem(when) is None
    assert policy_mod.when_applies(when, PROD) is in_prod
    assert policy_mod.when_applies(when, DEV) is elsewhere


@pytest.mark.parametrize(
    "when", ["env == 'staging'", "env = prod", "production", "env == prod", "1 == 1", 7]
)
def test_a_condition_maya_cannot_read_is_refused_and_meanwhile_requires_the_approval(when):
    assert policy_mod.when_problem(when) is not None
    # a stored unreadable condition (written by another version) errs towards asking
    assert policy_mod.when_applies(when, PROD) and policy_mod.when_applies(when, DEV)


def test_a_policy_with_an_unreadable_condition_cannot_be_saved(world):
    base = copy.deepcopy(_global(world, "model_version"))
    base["transitions"]["approve"]["approvals"] = [
        {"role": "model_manager", "count": 1},
        {"role": "model_owner", "count": 1, "when": "env == 'staging'"},
    ]
    with pytest.raises(ValidationFailed, match="environment must be one of"):
        world.p.workflow_svc.draft_policy(world.admin, "model_version", base)


def test_an_approver_who_could_never_approve_is_named(world):
    """§10.2's example asked `model_owner` to approve a model version while §11's matrix
    gave that role no 'A' on models: the policy saved, and nothing it governed could ever
    leave review. The matrix now grants it (see maya/security/roles.py); a role that still
    cannot approve is reported."""
    base = copy.deepcopy(_global(world, "model_version"))
    base["transitions"]["approve"]["approvals"] = [{"role": "feature_designer", "count": 1}]
    errors = policy_mod.validate(
        base,
        checks=world.p.workflow.checks.keys(),
        roles=[r for r in ["feature_designer", "model_manager", "model_owner", "admin"]],
        object_type="model_version",
    )
    assert any("could never be satisfied" in e and "feature_designer" in e for e in errors)
    ok = copy.deepcopy(base)
    ok["transitions"]["approve"]["approvals"] = [
        {"role": "model_manager", "count": 1},
        {"role": "model_owner", "count": 1, "when": "env == 'prod'"},
    ]
    assert (
        policy_mod.validate(
            ok,
            checks=world.p.workflow.checks.keys(),
            roles=["model_manager", "model_owner", "admin"],
            object_type="model_version",
        )
        == []
    )


def test_the_shipped_policies_can_all_be_satisfied():
    """Every default policy, against the role ceiling: the execution-warrant policy asks
    the owner to approve in production, which the matrix must allow."""
    from maya.security.roles import MATRIX

    for object_type, policy in policy_mod.default_policies().items():
        checks = [c for t in policy["transitions"].values() for c in t.get("checks", [])]
        errors = policy_mod.validate(
            policy, checks=checks, roles=list(MATRIX), object_type=object_type
        )
        assert [e for e in errors if "could never be satisfied" in e] == [], object_type


def test_the_spec_form_asks_for_the_extra_approval_only_in_a_production_namespace(world):
    """§10.2's own example: the owner signs off in a production namespace, and nowhere
    else. Two namespaces, one policy shape, two outcomes."""
    w = world
    from tests.test_warrants import complete_spec

    w.p.access.create_namespace(w.admin, name="cond_prod", production=True)
    w.p.access.create_namespace(w.admin, name="cond_dev")
    base = copy.deepcopy(_global(w, "model_version"))
    base["transitions"]["approve"]["approvals"] = [
        {"role": "model_manager", "count": 1},
        {"role": "model_owner", "count": 1, "when": "env == 'prod'"},
    ]
    for ns in ("cond_prod", "cond_dev"):
        draft = w.p.workflow_svc.draft_policy(
            w.admin, "model_version", base, scope=ns, note="the owner signs off in production"
        )
        w.p.workflow_svc.activate(w.admin2, draft["id"])
    outcome = {}
    for ns in ("cond_prod", "cond_dev"):
        ref = f"{ns}/cmod"
        w.p.models.create(w.mona, namespace=ns, name="cmod", formula="y = 2*x")
        w.p.models.update_draft(w.mona, ref, spec_latex=complete_spec("cmod"))
        w.p.models.transition(w.mona, ref, 1, "submit")
        outcome[ns] = w.p.models.transition(w.mgr, ref, 1, "approve")
    assert outcome["cond_dev"]["moved"] is True, "no owner sign-off outside production"
    assert outcome["cond_prod"]["moved"] is False
    assert "model_owner" in outcome["cond_prod"]["message"]
    assert w.p.models.transition(w.owen, "cond_prod/cmod", 1, "approve")["moved"] is True
