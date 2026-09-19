"""
The review experience (§10.3, §10.6): a semantic diff against the last approved
version rendered in words, the impact list of dependents with their owners, the
separation of duties in force, the approvals still outstanding and from whom,
and — the defect the specification audit named — the policy that actually
governs the item rather than the first active policy of its type.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import copy

import pytest

from maya.services import catalog
from tests.conftest import PASSWORD, PX_DEF, approved_feature, price_csv


@pytest.fixture(scope="module")
def reviewed(world):
    """A feature at v2 in review, with a feature set downstream of it."""
    w = world
    w.p.access.create_namespace(w.admin, name="rev", preset="regulated")
    approved_feature(w, "rv_px", price_csv(), ns="rev")
    # v2 changes the resolution policy and adds an attribute: a real semantic change
    w.p.features.new_draft(w.dana, "rev/rv_px")
    d = copy.deepcopy(PX_DEF)
    d["resolution"]["rules"]["close"] = "last_known_as_of(lag=1)"
    d["schema"] = d["schema"] + [{"name": "vol", "type": "float64"}]
    d["transform"] = [{"op": "derive", "name": "dbl", "expr": "close * 2"}]
    w.p.features.update_draft(w.dana, "rev/rv_px", d)
    w.p.features.transition(w.dana, "rev/rv_px", 2, "submit")
    # a feature set whose member reference is bare: it tracks the latest approved version
    w.p.featuresets.create(
        w.dana,
        namespace="rev",
        name="rv_panel",
        definition={
            "index": ["date", "symbol"],
            "index_types": {"date": "date", "symbol": "string"},
            "members": [
                {"attr": "close", "ref": "maya://feature/rev/rv_px", "source_attr": "close"}
            ],
            "alignment": {"mode": "inner"},
        },
    )
    w.p.featuresets.transition(w.dana, "rev/rv_panel", 1, "submit")
    w.p.featuresets.transition(w.mick, "rev/rv_panel", 1, "approve")
    with w.p.uow() as uow:
        feature = uow.repo("features").find_one(name="rv_px")
        v2 = uow.repo("feature_versions").find_one(feature_id=feature["id"], version_no=2)
    return w, v2["id"]


def test_the_diff_names_every_section_that_changed_in_words(reviewed):
    w, v2 = reviewed
    r = w.p.workflow_svc.review(w.mick, "feature_version", v2)
    assert r["diff"]["against"] == "v1"
    sections = {e["section"] for e in r["diff"]["entries"]}
    assert {"Schema", "Resolution", "Transform"} <= sections
    by_what = {e["what"]: e for e in r["diff"]["entries"]}
    # rendered, not raw JSON: the rule reads as the rule, the step as the step
    assert by_what["rule for close"]["was"] == "forward_fill(limit=3)"
    assert by_what["rule for close"]["now"] == "last_known_as_of(lag=1)"
    assert by_what["attribute vol"]["change"] == "added"
    assert by_what["attribute vol"]["now"].startswith("float64")
    assert by_what["step 1"]["now"] == "derive expr=close * 2, name=dbl"
    assert all("{" not in e["now"] and "{" not in e["was"] for e in r["diff"]["entries"])


def test_a_first_version_says_so_rather_than_diffing_against_nothing(world):
    w = world
    w.p.features.create(w.dana, namespace="eq", name="rv_first", definition=PX_DEF)
    w.p.features.transition(w.dana, "eq/rv_first", 1, "submit")
    with w.p.uow() as uow:
        f = uow.repo("features").find_one(name="rv_first")
        v1 = uow.repo("feature_versions").find_one(feature_id=f["id"], version_no=1)
    r = w.p.workflow_svc.review(w.mick, "feature_version", v1["id"])
    assert r["diff"]["entries"] == []
    assert "no approved version before this one" in r["diff"]["note"]


def test_the_impact_list_names_dependents_and_their_owners(reviewed):
    w, v2 = reviewed
    r = w.p.workflow_svc.review(w.mick, "feature_version", v2)
    refs = {d["ref"] for d in r["impact"]["items"]}
    assert any("rv_panel" in ref for ref in refs), r["impact"]
    panel = next(d for d in r["impact"]["items"] if "rv_panel" in d["ref"])
    assert panel["owner"] == "dana"
    assert panel["type"] == "featureset"
    assert panel["edge"] == "member_of"
    assert panel["url"] == "/catalog/featuresets/rev/rv_panel"


def test_a_dependent_the_reviewer_may_not_read_is_counted_never_named(world):
    """The read scoping the audit fixed for lineage holds for the impact list too."""
    w = world
    w.p.access.create_namespace(w.admin, name="rv_open", default_visibility="namespace_read")
    w.p.access.create_namespace(
        w.admin, name="rv_shut", default_visibility="private", preset="regulated"
    )
    approved_feature(w, "rv_base", price_csv(), ns="rv_open")
    w.p.featuresets.create(
        w.dana,
        namespace="rv_shut",
        name="rv_secret",
        definition={
            "index": ["date", "symbol"],
            "index_types": {"date": "date", "symbol": "string"},
            "members": [
                {"attr": "close", "ref": "maya://feature/rv_open/rv_base", "source_attr": "close"}
            ],
            "alignment": {"mode": "inner"},
        },
    )
    with w.p.uow() as uow:
        fs = uow.repo("feature_sets").find_one(name="rv_secret")
    w.p.access.grant(
        w.admin,
        kind="featureset",
        obj=fs,
        principal_type="user",
        principal_id="mick",
        level="approve",
    )
    w.p.featuresets.transition(w.dana, "rv_shut/rv_secret", 1, "submit")
    w.p.featuresets.transition(w.mick, "rv_shut/rv_secret", 1, "approve")
    seen = w.p.catalog.dependents(w.mona, "maya://feature/rv_open/rv_base")
    assert seen["hidden"] >= 1
    assert all("rv_secret" not in d["ref"] for d in seen["items"]), seen
    owner_sees = w.p.catalog.dependents(w.dana, "maya://feature/rv_open/rv_base")
    assert any("rv_secret" in d["ref"] for d in owner_sees["items"])


def test_separation_of_duties_is_named_and_says_whether_it_stops_you(reviewed):
    w, v2 = reviewed
    submitter = w.p.workflow_svc.review(w.dana, "feature_version", v2)
    assert submitter["sod"]["level"] == "strict"
    assert submitter["sod"]["blocks_you"] is True
    assert "you created, submitted or last modified" in submitter["sod"]["reason"]
    assert "dana" in submitter["sod"]["involved"]
    approver = w.p.workflow_svc.review(w.mick, "feature_version", v2)
    assert approver["sod"]["blocks_you"] is False
    assert approver["sod"]["reason"] is None


def test_a_transition_the_caller_cannot_take_carries_the_rule_that_would_refuse_it(reviewed):
    """§16.4: disabled with the reason, and the reason is the engine's own, not a guess."""
    w, v2 = reviewed
    r = w.p.workflow_svc.review(w.dana, "feature_version", v2)
    approve = next(t for t in r["transitions"] if t["name"] == "approve")
    assert approve["available"] is False
    assert "role ceiling: no 'A' on feature" in approve["reason"]
    ok = w.p.workflow_svc.review(w.mick, "feature_version", v2)
    assert next(t for t in ok["transitions"] if t["name"] == "approve")["available"] is True


def test_the_approve_control_is_disabled_for_an_approver_who_submitted_it(world):
    """Somebody who may approve in general still may not approve their own work, and the
    screen says which of the two rules is stopping them."""
    w = world
    w.p.access.create_namespace(w.admin, name="rv_dual_ns", preset="regulated")
    w.p.access.create_role(
        w.admin,
        name="rv_designer_approver",
        capabilities={"feature": "CRUA", "feature_pin": "Q", "jobs": "R"},
        description="designs and approves features: exists so SoD has something to stop",
    )
    w.p.access.create_user(
        w.admin, username="rv_dual", password=PASSWORD, roles=["rv_designer_approver"]
    )
    dual = w.principal("rv_dual")
    w.p.features.create(dual, namespace="rv_dual_ns", name="rv_own", definition=PX_DEF)
    w.p.features.ingest(dual, "rv_dual_ns/rv_own", price_csv(), fmt="csv")
    w.p.features.transition(dual, "rv_dual_ns/rv_own", 1, "submit")
    with w.p.uow() as uow:
        f = uow.repo("features").find_one(name="rv_own")
        v1 = uow.repo("feature_versions").find_one(feature_id=f["id"], version_no=1)
    r = w.p.workflow_svc.review(dual, "feature_version", v1["id"])
    assert r["sod"]["level"] == "strict"
    approve = next(t for t in r["transitions"] if t["name"] == "approve")
    assert approve["available"] is False
    assert "segregation of duties (strict)" in approve["reason"]


def test_outstanding_approvals_say_who_can_give_them(reviewed):
    w, v2 = reviewed
    r = w.p.workflow_svc.review(w.mick, "feature_version", v2)
    outstanding = {o["role"]: o for o in r["outstanding"]}
    assert "feature_manager" in outstanding
    assert outstanding["feature_manager"]["remaining"] == 1
    assert "mick" in outstanding["feature_manager"]["who"]
    assert outstanding["feature_manager"]["given"] == []


def test_an_approval_already_recorded_leaves_nothing_outstanding(world):
    w = world
    ref = approved_feature(w, "rv_done", price_csv(), ns="eq")
    with w.p.uow() as uow:
        f = uow.repo("features").find_one(name="rv_done")
        v1 = uow.repo("feature_versions").find_one(feature_id=f["id"], version_no=1)
    r = w.p.workflow_svc.review(w.mick, "feature_version", v1["id"])
    assert r["outstanding"] == []
    assert r["state"] == "approved"
    assert ref


def test_the_policy_shown_is_the_one_that_governs_this_namespace(reviewed):
    """The audit's bug: the screen picked the first active policy of the object type
    whatever its scope, so a policy scoped to another namespace could be described as
    the rule in force. The policy shown must be the one ``active_policy`` will use."""
    w, v2 = reviewed
    with w.p.uow() as uow:
        global_policy = w.p.workflow.active_policy(uow, "feature_version", "*")["policy"]
    other = copy.deepcopy(global_policy)
    other["transitions"]["approve"]["approvals"] = [{"role": "admin", "count": 2}]
    # twice, so the elsewhere-scoped policy carries the highest version_no of its object
    # type: that is exactly the ordering the old screen sorted by and picked from.
    for note in ("scoped elsewhere", "scoped elsewhere, again"):
        drafted = w.p.workflow_svc.draft_policy(
            w.admin, "feature_version", other, scope="somewhere_else", note=note
        )
        w.p.workflow_svc.activate(w.admin2, drafted["id"])
    active = [
        p
        for p in w.p.workflow_svc.policies()
        if p["object_type"] == "feature_version" and p["state"] == "active"
    ]
    assert active[0]["scope"] == "somewhere_else", "the ordering the bug depended on"
    r = w.p.workflow_svc.review(w.mick, "feature_version", v2)
    assert r["policy"]["scope"] == "*"
    assert {o["role"] for o in r["outstanding"]} == {"feature_manager"}


def test_a_namespace_scoped_policy_is_the_one_shown_for_its_own_namespace(world):
    w = world
    w.p.access.create_namespace(w.admin, name="rv_scoped", preset="standard")
    ref = approved_feature(w, "rv_sc", price_csv(), ns="rv_scoped")
    with w.p.uow() as uow:
        base = w.p.workflow.active_policy(uow, "feature_version", "*")["policy"]
    tight = copy.deepcopy(base)
    tight["transitions"]["approve"]["approvals"] = [
        {"role": "feature_manager", "count": 1},
        {"role": "admin", "count": 1},
    ]
    drafted = w.p.workflow_svc.draft_policy(
        w.admin, "feature_version", tight, scope="rv_scoped", note="tighter here"
    )
    w.p.workflow_svc.activate(w.admin2, drafted["id"])
    bumped = copy.deepcopy(PX_DEF)
    bumped["schema"] = bumped["schema"] + [{"name": "vol", "type": "float64"}]
    w.p.features.new_draft(w.dana, ref)
    w.p.features.update_draft(w.dana, ref, bumped)
    w.p.features.transition(w.dana, ref, 2, "submit")
    with w.p.uow() as uow:
        f = uow.repo("features").find_one(name="rv_sc")
        v2 = uow.repo("feature_versions").find_one(feature_id=f["id"], version_no=2)
    r = w.p.workflow_svc.review(w.mick, "feature_version", v2["id"])
    assert r["policy"]["scope"] == "rv_scoped"
    assert {o["role"] for o in r["outstanding"]} == {"feature_manager", "admin"}


def test_a_feature_set_version_diffs_its_members(reviewed):
    w, _ = reviewed
    w.p.featuresets.new_draft(w.dana, "rev/rv_panel")
    w.p.featuresets.update_draft(
        w.dana,
        "rev/rv_panel",
        {
            "index": ["date", "symbol"],
            "index_types": {"date": "date", "symbol": "string"},
            "members": [
                {
                    "attr": "close",
                    "ref": "maya://feature/rev/rv_px",
                    "source_attr": "close",
                    "cast": "float64",
                }
            ],
            "alignment": {"mode": "outer"},
        },
    )
    w.p.featuresets.transition(w.dana, "rev/rv_panel", 2, "submit")
    with w.p.uow() as uow:
        fs = uow.repo("feature_sets").find_one(name="rv_panel")
        v2 = uow.repo("feature_set_versions").find_one(feature_set_id=fs["id"], version_no=2)
    r = w.p.workflow_svc.review(w.mick, "featureset_version", v2["id"])
    sections = {e["section"] for e in r["diff"]["entries"]}
    assert {"Members", "Alignment"} <= sections
    member = next(e for e in r["diff"]["entries"] if e["section"] == "Members")
    assert "cast float64" in member["now"]


def test_a_reviewer_who_may_not_read_the_object_is_refused_the_review(world):
    from maya.core.errors import PermissionDenied

    w = world
    w.p.access.create_namespace(w.admin, name="rv_private", default_visibility="private")
    w.p.features.create(w.dana, namespace="rv_private", name="rv_hidden", definition=PX_DEF)
    w.p.features.transition(w.dana, "rv_private/rv_hidden", 1, "submit")
    with w.p.uow() as uow:
        f = uow.repo("features").find_one(name="rv_hidden")
        v1 = uow.repo("feature_versions").find_one(feature_id=f["id"], version_no=1)
    with pytest.raises(PermissionDenied):
        w.p.workflow_svc.review(w.mona, "feature_version", v1["id"])


def test_two_identical_definitions_diff_to_nothing():
    assert catalog.definition_diff("feature", PX_DEF, PX_DEF) == []


def test_a_derived_feature_set_diffs_its_algebra(reviewed):
    """A set built by §6.8 algebra has a derivation where a mapped one has members, and
    the diff shows the expression rather than a dictionary."""
    w, _ = reviewed
    base = {
        "index": ["date", "symbol"],
        "index_types": {"date": "date", "symbol": "string"},
        "derivation": {
            "operator": "union",
            "operands": ["maya://featureset/rev/a", "maya://featureset/rev/b"],
            "options": {},
        },
    }
    wider = copy.deepcopy(base)
    wider["derivation"]["operands"] = [
        "maya://featureset/rev/a",
        "maya://featureset/rev/c",
    ]
    wider["derivation"]["options"] = {"collision": "prefer_left"}
    entries = catalog.definition_diff("featureset", base, wider)
    algebra = next(e for e in entries if e["section"] == "Algebra")
    assert algebra["was"] == "union(maya://featureset/rev/a, maya://featureset/rev/b)"
    assert algebra["now"] == (
        "union(maya://featureset/rev/a, maya://featureset/rev/c) [collision prefer_left]"
    )
    assert algebra["change"] == "changed"
    assert catalog.definition_diff("featureset", base, base) == []
    assert w


def test_an_object_with_no_definition_says_so_rather_than_showing_an_empty_diff(world):
    """A warrant carries no definition; the screen says which, rather than rendering an
    empty diff that reads as 'nothing changed'."""
    w = world
    with w.p.uow("system") as uow:
        ns = uow.repo("namespaces").find_one(name="eq")
        model = uow.repo("models").add(
            {
                "namespace_id": ns["id"],
                "name": "rv_warrant_model",
                "owner_id": w.mona.user_id,
                "kind": "formula",
            }
        )
        mv = uow.repo("model_versions").add(
            {"model_id": model["id"], "version_no": 1, "state": "approved"}
        )
        warrant = uow.repo("training_warrants").add(
            {
                "namespace_id": ns["id"],
                "name": "rv_warrant",
                "version_no": 1,
                "state": "in_review",
                "owner_id": w.devi.user_id,
                "model_version_id": mv["id"],
                "featureset_ref": "maya://featureset/eq/none",
                "spec": {},
            }
        )
    r = w.p.workflow_svc.review(w.admin, "training_warrant", warrant["id"])
    assert r["diff"]["entries"] == []
    assert "carries no definition to diff" in r["diff"]["note"]
    assert r["namespace"] == "eq"
