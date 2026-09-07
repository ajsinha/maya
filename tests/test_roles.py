"""Roles in the register rather than in the source.

They were a Python dictionary. That is fine for the eight this platform ships
and wrong for everything a bank actually has — a *Model Validation Team Lead*, a
*Regional MRM*, a *Quant Developer with production read* — each of which meant
editing `core/authz/roles.py` and redeploying. **Administration that requires a
release is not administration.**

The hard part was not storage. It was that the incompatible-roles check compared
role NAMES, which works exactly as long as the only roles are the ones that were
named: the moment somebody can define a role, they can define one holding
`version:create` and `version:approve` together, and a name check sees a single
unfamiliar name and passes it.
"""
from __future__ import annotations

import itertools

import pytest

from core.authz.common import AuthzError
from core.authz.roles import ROLES, conflicts as by_role_name
from core.authz.rolestore import INCOMPATIBLE_PERMISSIONS, RoleStore
from db import RoleRepository


@pytest.fixture
def store(db, evidence):
    return RoleStore(RoleRepository(db), evidence)


class TestTheShippedRolesAreSeededAndProtected:

    def test_all_eight_are_in_the_register(self, store):
        seeded = {r["name"] for r in store.all()}
        assert seeded == set(ROLES), seeded ^ set(ROLES)
        assert all(r["built_in"] for r in store.all())

    def test_they_grant_exactly_what_the_source_says(self, store):
        for name, permissions in ROLES.items():
            assert set(store.require(name)["permissions"]) == set(permissions)

    def test_seeding_twice_changes_nothing(self, db, evidence):
        first = RoleStore(RoleRepository(db), evidence).all()
        second = RoleStore(RoleRepository(db), evidence).all()
        assert len(first) == len(second) == len(ROLES)

    def test_a_built_in_may_not_be_edited(self, store):
        with pytest.raises(AuthzError) as refusal:
            store.amend("validator", permissions=["model:read"])
        assert refusal.value.code == "built_in_role"
        assert "every document, tutorial and test" in str(refusal.value)

    def test_a_built_in_may_not_be_removed(self, store):
        with pytest.raises(AuthzError, match="cannot be removed"):
            store.remove("auditor")


class TestDefiningOne:

    def test_a_bank_can_define_its_own(self, store):
        role = store.create(
            "model_validation_lead",
            "Runs the validation team: everything a validator does, plus the "
            "board reporting the team owns",
            ["model:read", "validation:read", "validation:conclude",
             "finding:close", "report:read"],
            actor="person/admin")
        assert not role["built_in"]
        assert store.permissions_for(["model_validation_lead"]) >= {"report:read"}

    def test_a_permission_nothing_checks_is_refused(self, store):
        with pytest.raises(AuthzError, match="unknown_permission|not a "):
            store.create("invented", "grants something imaginary",
                         ["model:bless"])

    def test_a_role_granting_nothing_is_refused(self, store):
        """Somebody holding it could sign in and do nothing, which reads as a
        permissions fault rather than as the empty grant it is."""
        with pytest.raises(AuthzError) as refusal:
            store.create("hollow", "grants nothing at all", [])
        assert refusal.value.code == "role_grants_nothing"

    def test_a_role_needs_a_description(self, store):
        with pytest.raises(AuthzError, match="role_description_required|needs a "):
            store.create("terse", "  ", ["model:read"])

    def test_a_name_is_used_once(self, store):
        store.create("regional_mrm", "MRM for one region", ["model:read"])
        with pytest.raises(AuthzError, match="already a role"):
            store.create("regional_mrm", "again", ["model:read"])

    def test_a_role_somebody_holds_may_not_be_removed(self, store):
        """The reference rule, one layer up: their next request would resolve
        permissions against a name that is not there."""
        store.create("temp", "temporary", ["model:read"])
        with pytest.raises(AuthzError) as refusal:
            store.remove("temp", holders=["a.mehta"])
        assert refusal.value.code == "role_in_use"
        assert "a.mehta" in str(refusal.value)

    def test_one_nobody_holds_is_removed(self, store):
        store.create("temp", "temporary", ["model:read"])
        assert store.remove("temp", holders=[])["removed"]


class TestBothConflictChecksAreNeeded:
    """Neither catches what the other does, and running the pair against every
    combination of shipped roles is how that was established rather than
    assumed."""

    def test_a_custom_role_cannot_smuggle_a_capability_conflict(self, store):
        """The whole reason the permission pairs exist. A name check sees one
        unfamiliar role and passes it."""
        store.create("builder_approver",
                     "builds versions and approves them, which is the thing",
                     ["model:read", "version:create", "version:approve"])
        found = store.conflicts(["builder_approver"])
        assert found, "one role, both halves of a pair, and no familiar name"
        assert "first line approving its own work" in found[0]

    def test_a_permission_check_cannot_see_an_independence_conflict(self, store):
        """`auditor + model_developer` has no permission collision at all —
        an auditor holds reads and `finding:raise`. The conflict is about which
        LINE somebody is in, and a line is not a capability."""
        granted = store.permissions_for(["auditor", "model_developer"])
        collisions = [(a, b) for a, b, _ in INCOMPATIBLE_PERMISSIONS
                      if a in granted and b in granted]
        assert collisions == [], "there is nothing here for permissions to catch"
        assert store.conflicts(["auditor", "model_developer"]), \
            "and the role pair catches it"

    def test_the_combined_check_changes_no_shipped_answer(self, store):
        """Adding the permission pairs must not start refusing a combination
        that was legal, or this is a behaviour change wearing a fix's clothes."""
        names = sorted(ROLES)
        for size in (1, 2):
            for combo in itertools.combinations(names, size):
                assert bool(store.conflicts(combo)) == bool(by_role_name(combo)), \
                    f"{combo} changed answer"

    def test_admin_is_still_the_conscious_exception(self, store):
        assert store.conflicts(["admin", "model_developer", "validator"]) == []


class TestOverTheApi:

    def test_the_catalogue_publishes_both_kinds_of_conflict(self, client, people):
        body = client.get("/api/v1/roles", auth=people["a.mehta"]).json()
        assert body["incompatible"], "the role pairs"
        assert body["incompatible_permissions"], "the permission pairs"
        assert all(r["built_in"] for r in body["roles"]), \
            "a fresh instance has only the shipped ones"
        assert "model:read" in body["permissions"]

    def test_an_administrator_defines_one_and_grants_it(self, client):
        made = client.post("/api/v1/roles", json={
            "name": "regional_mrm", "description": "MRM for one region",
            "permissions": ["model:read", "finding:read", "report:read"]})
        assert made.status_code == 201, made.text
        r = client.post("/api/v1/principals", json={
            "username": "r.mrm", "display_name": "Regional", "password": "pw",
            "roles": ["regional_mrm"]})
        assert r.status_code == 201, r.text
        who = client.get("/api/v1/me", auth=("r.mrm", "pw")).json()
        assert "report:read" in who["permissions"]

    def test_defining_one_needs_the_permission(self, client, people):
        r = client.post("/api/v1/roles", auth=people["a.mehta"], json={
            "name": "x", "description": "y", "permissions": ["model:read"]})
        assert r.status_code == 403

    def test_a_conflicting_custom_role_is_refused_on_the_principal(self, client):
        client.post("/api/v1/roles", json={
            "name": "builder_approver",
            "description": "builds and approves, which is the thing",
            "permissions": ["model:read", "version:create", "version:approve"]})
        r = client.post("/api/v1/principals", json={
            "username": "sneaky", "display_name": "Sneaky", "password": "pw",
            "roles": ["builder_approver"]})
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "incompatible_roles"
