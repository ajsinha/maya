"""
The workflow, role by role (§10): for each transition of the feature and model
state machines, every shipped role tries it on a fresh object in the right
state, and exactly the roles the policy and capability matrix name succeed.
Then separation of duties under each namespace preset, break-glass, and
delegation interplay.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import itertools

import pytest

from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed
from tests.conftest import PASSWORD, PX_DEF, World, build_platform, price_csv

# username -> role, from conftest.ROLES (plus the bootstrap admin)
PEOPLE = {
    "dana": "feature_designer",
    "mick": "feature_manager",
    "mona": "model_designer",
    "devi": "model_developer",
    "mgr": "model_manager",
    "owen": "model_owner",
    "tess": "techops",
    "admin2": "admin",
}
_seq = itertools.count()


@pytest.fixture(scope="module")
def w():
    platform = build_platform()
    world = World(platform)
    for ns, preset in (("std", "standard"), ("reg", "regulated"), ("small", "small_team")):
        platform.access.create_namespace(world.admin, name=ns, preset=preset)
    yield world
    platform.shutdown()


def _feature(w, state: str, ns: str = "std", owner: str = "dana") -> str:
    """A fresh feature whose version 1 is in ``state``."""
    ref = f"{ns}/f{next(_seq)}"
    p = w.p
    p.features.create(w.principal(owner), namespace=ns, name=ref.split("/")[1], definition=PX_DEF)
    p.features.ingest(w.principal(owner), ref, price_csv(3), fmt="csv")
    if state == "draft":
        return ref
    p.features.transition(w.principal(owner), ref, 1, "submit")
    if state == "in_review":
        return ref
    p.features.transition(w.mick, ref, 1, "approve")
    if state == "approved":
        return ref
    if state == "deprecated":
        p.features.transition(w.mick, ref, 1, "deprecate")
        return ref
    raise AssertionError(state)


# transition -> (source state, the roles that may take it)
FEATURE_MATRIX = {
    "submit": ("draft", {"feature_designer", "admin"}),
    "withdraw": ("in_review", {"feature_designer", "admin"}),
    "request_changes": ("in_review", {"feature_manager"}),
    "approve": ("in_review", {"feature_manager"}),
    "publish": ("approved", {"feature_manager"}),
    "deprecate": ("approved", {"feature_manager"}),
    "retire": ("deprecated", {"admin"}),
}


@pytest.mark.parametrize("transition", sorted(FEATURE_MATRIX))
def test_feature_transitions_by_role(w, transition):
    state, allowed = FEATURE_MATRIX[transition]
    wrong = []
    for user, role in PEOPLE.items():
        ref = _feature(w, state)
        try:
            out = w.p.features.transition(w.principal(user), ref, 1, transition)
            ok = out["moved"]
        except (PermissionDenied, NotApproved):
            ok = False
        if ok != (role in allowed):
            wrong.append((user, role, "moved" if ok else "refused"))
    assert not wrong, (transition, wrong)


def test_a_transition_from_the_wrong_state_names_the_allowed_states(w):
    ref = _feature(w, "draft")
    with pytest.raises(NotApproved, match="allowed from in_review"):
        w.p.features.transition(w.mick, ref, 1, "approve")
    with pytest.raises(ValidationFailed, match="not a transition"):
        w.p.features.transition(w.dana, ref, 1, "teleport")


def test_separation_of_duties_by_preset(w):
    """A person holding both roles: blocked from approving their own work under
    two_person and strict, allowed in a small_team namespace (sod none)."""
    w.p.access.create_user(
        w.admin, username="both", password=PASSWORD, roles=["feature_designer", "feature_manager"]
    )
    for ns, allowed in (("std", False), ("reg", False), ("small", True)):
        ref = _feature(w, "in_review", ns=ns, owner="both")
        if allowed:
            assert w.p.features.transition(w.principal("both"), ref, 1, "approve")["moved"]
        else:
            with pytest.raises(PermissionDenied):
                w.p.features.transition(w.principal("both"), ref, 1, "approve")
            assert w.p.features.transition(w.mick, ref, 1, "approve")["moved"]


def test_an_approved_object_cannot_be_approved_again(w):
    feature = _feature(w, "in_review")
    assert w.p.features.transition(w.mick, feature, 1, "approve")["moved"]
    with pytest.raises(NotApproved, match="Cannot approve from state 'approved'"):
        w.p.features.transition(w.mick, feature, 1, "approve")


def test_break_glass_is_admin_only_needs_a_reason_and_is_loud(w):
    ref = _feature(w, "in_review")
    with pytest.raises(PermissionDenied, match="reserved to administrators"):
        w.p.features.transition(
            w.mick, ref, 1, "approve", force=True, rationale="because I said so, loudly"
        )
    with pytest.raises(ValidationFailed, match="written reason"):
        w.p.features.transition(w.admin, ref, 1, "approve", force=True, rationale="now")
    out = w.p.features.transition(
        w.admin, ref, 1, "approve", force=True, rationale="regulator deadline; reviewer on leave"
    )
    assert out["moved"] and out["state"] == "approved"
    version = w.p.features.get(w.admin, ref)["versions"][0]
    assert version["force_approved"] is True
    with w.p.uow() as uow:
        assert uow.repo("audit_events").list(
            action="workflow.break_glass", object_ref__ilike=ref.split("/")[1]
        )
    report = w.p.workflow_svc.break_glass_report()
    assert any(r["object_id"] == version["id"] and r["actor"] == "admin" for r in report)
    dana_inbox = w.p.access.inbox(w.dana)
    assert any(n["kind"] == "break_glass" for n in dana_inbox)


def test_a_delegate_gains_only_what_the_delegator_could_do(w):
    """A designer given mick's approvals may approve a feature, but not submit someone
    else's draft (delegation lends approvals, not the delegator's other capabilities)."""
    w.p.access.create_user(
        w.admin, username="stand_in", password=PASSWORD, roles=["feature_designer"]
    )
    today = dt.date.today()
    w.p.workflow_svc.delegate(
        w.mick, to="stand_in", starts_on=today, ends_on=today, object_types=["feature_version"]
    )
    stand_in = w.principal("stand_in")
    ref = _feature(w, "in_review")
    out = w.p.features.transition(stand_in, ref, 1, "approve")
    assert out["moved"]
    approval = next(
        h
        for h in w.p.workflow_svc.history(
            "feature_version", w.p.features.get(w.admin, ref)["versions"][0]["id"]
        )
        if h["transition"] == "approval"
    )
    assert approval["on_behalf_of"] == "mick"
    other = _feature(w, "draft")
    with pytest.raises(PermissionDenied):
        w.p.features.transition(stand_in, other, 1, "submit")
    # a delegation for models lends nothing on features
    w.p.access.create_user(
        w.admin, username="model_stand_in", password=PASSWORD, roles=["feature_designer"]
    )
    w.p.workflow_svc.delegate(
        w.mick, to="model_stand_in", starts_on=today, ends_on=today, object_types=["model_version"]
    )
    with pytest.raises(PermissionDenied):
        w.p.features.transition(
            w.principal("model_stand_in"), _feature(w, "in_review"), 1, "approve"
        )


def test_comments_and_history_follow_read_access(w):
    ref = _feature(w, "in_review")
    vid = w.p.features.get(w.admin, ref)["versions"][0]["id"]
    w.p.access.create_user(w.admin, username="outsider", password=PASSWORD, roles=[])
    outsider = w.principal("outsider")
    for call in (
        lambda: w.p.workflow_svc.comment(
            outsider, "feature_version", vid, "blocked!", blocking=True
        ),
        lambda: w.p.workflow_svc.comments("feature_version", vid, outsider),
        lambda: w.p.workflow_svc.history("feature_version", vid, outsider),
    ):
        with pytest.raises(PermissionDenied):
            call()
    with pytest.raises(ValidationFailed, match="Unknown object type"):
        w.p.workflow_svc.comment(w.mick, "spaceship", vid, "hello")
    note = w.p.workflow_svc.comment(w.mick, "feature_version", vid, "units?", blocking=True)
    with pytest.raises(NotApproved, match="no_open_blocking_comments"):
        w.p.features.transition(w.mick, ref, 1, "approve")
    with pytest.raises(PermissionDenied, match="author"):
        w.p.workflow_svc.resolve_comment(w.dana, note["id"])
    w.p.workflow_svc.resolve_comment(w.mick, note["id"])
    assert w.p.features.transition(w.mick, ref, 1, "approve")["moved"]
    assert len(w.p.workflow_svc.comments("feature_version", vid, w.dana)) == 1


MODEL_FORMULA = "yhat = a*x + b"


def _model(w, submitted: bool) -> str:
    from tests.test_warrants import complete_spec

    name = f"m{next(_seq)}"
    w.p.models.create(
        w.mona,
        namespace="std",
        name=name,
        formula=MODEL_FORMULA,
        roles={"a": "parameter", "b": "parameter"},
    )
    w.p.models.update_draft(w.mona, f"std/{name}", spec_latex=complete_spec(name))
    if submitted:
        w.p.models.transition(w.mona, f"std/{name}", 1, "submit")
    return f"std/{name}"


@pytest.mark.parametrize(
    "transition,submitted,allowed",
    [
        ("submit", False, {"model_designer", "admin"}),
        # the owner holds 'A' on a model too (§10.2 asks them to sign off in production),
        # so they can also send it back; approving alone does not move it, because the
        # policy still wants the manager's approval
        ("approve", True, {"model_manager"}),
        ("request_changes", True, {"model_manager", "model_owner"}),
    ],
)
def test_model_transitions_by_role(w, transition, submitted, allowed):
    wrong = []
    for user, role in PEOPLE.items():
        ref = _model(w, submitted)
        try:
            ok = w.p.models.transition(w.principal(user), ref, 1, transition)["moved"]
        except (PermissionDenied, NotApproved):
            ok = False
        if ok != (role in allowed):
            wrong.append((user, role, "moved" if ok else "refused"))
    assert not wrong, (transition, wrong)


def test_a_pinned_parent_must_be_approved(w):
    """extends … binding: pinned is immune to parent change only if the parent cannot
    change; clone-and-extend binds the latest approved version, never an open draft."""
    parent = _feature(w, "approved")
    w.p.features.new_draft(w.dana, parent)  # v2, a draft
    child = f"std/child{next(_seq)}"
    w.p.features.clone(w.dana, parent, name=child.split("/")[1], extend=True)
    ext = w.p.features.get(w.dana, child)["versions"][0]["definition"]["extends"]
    assert ext["parent"].endswith(f"{parent}@v1") and ext["binding"] == "pinned"
    rogue = f"child{next(_seq)}"
    w.p.features.create(
        w.dana,
        namespace="std",
        name=rogue,
        definition={
            "extends": {
                "parent": f"maya://feature/{parent}@v2",
                "binding": "pinned",
                "override": {},
            }
        },
    )
    with pytest.raises(ValidationFailed, match="which is draft: a pinned parent must be"):
        w.p.features.transition(w.dana, f"std/{rogue}", 1, "submit")
    assert w.p.features.transition(w.dana, child, 1, "submit")["moved"]
