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
        unfamiliar role and passes it.

        The refusal now lands at DEFINITION rather than at assignment. It used
        to land only when somebody was given the role — so a conflicted role sat
        in the catalogue as an ordinary row and the person who defined it found
        out on the first colleague they tried to grant it to. Both are refused;
        this is the earlier of the two.
        """
        from core.authz.common import AuthzError

        with pytest.raises(AuthzError) as caught:
            store.create("builder_approver",
                         "builds versions and approves them, which is the thing",
                         ["model:read", "version:create", "version:approve"])
        assert caught.value.code == "incompatible_permissions"
        assert "somebody other than the builder" in caught.value.detail

    def test_a_conflicted_role_that_predates_the_check_is_still_caught(self, store):
        """Written straight to the repository, because a role defined before
        the definition-time check existed is exactly the case assignment-time
        checking is still there for."""
        import time

        store.repo.add({"name": "legacy_builder_approver",
                        "description": "defined before the check existed",
                        "permissions": ["model:read", "version:create",
                                        "version:approve"],
                        "built_in": 0, "created_at": time.time(),
                        "created_by": "test"})
        found = store.conflicts(["legacy_builder_approver"])
        assert found, "one role, both halves of a pair, and no familiar name"
        assert "somebody other than the builder" in found[0]

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

    #: The shipped role combinations the permission pairs refuse and the role
    #: names do not. Enumerated rather than tolerated: each one is a deliberate
    #: separation the name list could not express, and a combination appearing
    #: here that nobody argued for is a behaviour change wearing a fix's
    #: clothes.
    NEWLY_REFUSED = {
        # `service` records what a model did; `model_owner` and `operator`
        # decide whether that record was acceptable. One principal holding both
        # can produce the observations and then pass its own evaluation. No
        # single shipped role grants the pair, and nothing said a person could
        # not hold two roles that do.
        ("model_owner", "service"),
        ("operator", "service"),
    }

    def test_the_combined_check_changes_only_the_answers_it_means_to(self, store):
        names = sorted(ROLES)
        changed = set()
        for size in (1, 2):
            for combo in itertools.combinations(names, size):
                if bool(store.conflicts(combo)) != bool(by_role_name(combo)):
                    changed.add(combo)
        assert changed == self.NEWLY_REFUSED, \
            f"unexpected: {changed - self.NEWLY_REFUSED}; " \
            f"no longer refused: {self.NEWLY_REFUSED - changed}"

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
            "username": "r.mrm", "display_name": "Regional", "password": "pw-long-enough-x",
            "roles": ["regional_mrm"]})
        assert r.status_code == 201, r.text
        who = client.get("/api/v1/me", auth=("r.mrm", "pw-long-enough-x")).json()
        assert "report:read" in who["permissions"]

    def test_defining_one_needs_the_permission(self, client, people):
        r = client.post("/api/v1/roles", auth=people["a.mehta"], json={
            "name": "x", "description": "y", "permissions": ["model:read"]})
        assert r.status_code == 403

    def test_a_conflicting_custom_role_is_refused_where_it_is_defined(self, client):
        """It used to be accepted here and refused on the first person somebody
        tried to give it to — so the conflicted role sat in the catalogue as an
        ordinary row, and the administrator who defined it found out later, in
        a refusal about somebody else."""
        r = client.post("/api/v1/roles", json={
            "name": "builder_approver",
            "description": "builds and approves, which is the thing",
            "permissions": ["model:read", "version:create", "version:approve"]})
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "incompatible_permissions"
        assert client.get("/api/v1/roles").json()["roles"], "catalogue still reads"
        assert not any(row["name"] == "builder_approver"
                       for row in client.get("/api/v1/roles").json()["roles"])

    def test_two_roles_that_conflict_only_together_are_refused_on_the_principal(self, client):
        """Each role is legal alone; the person holding both is not. That is
        the case only the assignment-time check can see."""
        for name, permission in (("halfone", "version:create"),
                                 ("halftwo", "version:approve")):
            assert client.post("/api/v1/roles", json={
                "name": name, "description": "one half of a separated duty",
                "permissions": ["model:read", permission]}).status_code in (200, 201)
        r = client.post("/api/v1/principals", json={
            "username": "sneaky", "display_name": "Sneaky", "password": "pw-long-enough-x",
            "roles": ["halfone", "halftwo"]})
        assert r.status_code == 409, r.text
        assert r.json()["error"] == "incompatible_roles"


class TestTheSeparationsCoverWhatTheRolesSeparate:
    """Six pairs, written by hand, covering two of the two dozen separations the
    shipped roles actually make.

    The gaps were not visible by reading them. A role called `solo` holding
    `model:register`, `risk:assess`, `model:submit` and `version:approve`
    collided with none of the six, so one person registered a model, set the
    tier that decides every control on it, submitted it and approved it — the
    whole first half of the lifecycle, alone, with the platform's own
    segregation check returning nothing.
    """

    def test_no_shipped_role_holds_a_pair_it_declares_incompatible(self):
        """The derivation's own guard. A separation broad enough to make a
        shipped role illegal is a separation that is wrong — `finding:raise`
        with `finding:close` was exactly that, and both lines of defence
        legitimately do both."""
        from core.authz.roles import ROLES
        from core.authz.rolestore import INCOMPATIBLE_PERMISSIONS

        for role, permissions in ROLES.items():
            if role == "admin":
                continue          # break-glass is a conscious exception
            held = set(permissions)
            for a, b, why in INCOMPATIBLE_PERMISSIONS:
                assert not (a in held and b in held), \
                    f"the shipped role '{role}' holds {a} and {b}: {why}"

    def test_every_separated_permission_is_a_real_one(self):
        from core.authz.common import PERMISSIONS
        from core.authz.rolestore import FIRST_LINE, SECOND_LINE

        assert not (FIRST_LINE | SECOND_LINE) - set(PERMISSIONS)

    def test_the_six_that_were_written_by_hand_are_all_still_refused(self):
        from core.authz.rolestore import INCOMPATIBLE_PERMISSIONS

        derived = {(a, b) for a, b, _ in INCOMPATIBLE_PERMISSIONS}
        for pair in (("version:create", "version:approve"),
                     ("version:create", "version:sign"),
                     ("version:create", "validation:conclude"),
                     ("model:register", "version:approve"),
                     ("model:register", "version:sign"),
                     ("model:register", "validation:conclude")):
            assert pair in derived, pair

    def test_the_role_that_did_the_whole_first_half_alone(self, store):
        from core.authz.common import AuthzError

        with pytest.raises(AuthzError) as caught:
            store.create("solo", "one person, the whole lifecycle",
                         ["model:register", "risk:assess", "model:submit",
                          "version:approve"])
        assert caught.value.code == "incompatible_permissions"

    def test_recording_what_a_model_did_is_not_judging_it(self, store):
        """`service` observes and `operator` evaluates, and nothing said one
        principal may not hold both — no custom role was even needed."""
        from core.authz.common import AuthzError

        with pytest.raises(AuthzError):
            store.create("watcher", "records and judges its own record",
                         ["monitor:observe", "monitor:evaluate"])


class TestAmendingARoleCannotSmuggleAConflictPast:
    """Every conflict check ran at the moment a role was GIVEN to somebody, and
    a role's permissions are mutable afterwards.

    So the check was avoidable in two steps that were each individually
    allowed: define a harmless role, have it assigned, then amend it to hold
    both halves of a separated duty. The direct path returns 409. This one
    returned 200, and every holder silently acquired the pair.
    """

    def test_a_role_cannot_be_amended_into_a_conflict(self, store):
        from core.authz.common import AuthzError

        store.create("harmless", "reads things", ["model:read"])
        with pytest.raises(AuthzError) as caught:
            store.amend("harmless",
                        permissions=["version:create", "version:approve"])
        assert caught.value.code == "incompatible_permissions"

    def test_the_refusal_names_the_people_it_would_affect(self, db, evidence):
        from core.authz.common import AuthzError
        from core.authz.principals import PrincipalService
        from db import PrincipalRepository, RoleRepository

        people = PrincipalRepository(db)
        store = RoleStore(RoleRepository(db), evidence, principals=people)
        principals = PrincipalService(people, evidence)
        principals.roles = store

        store.create("stepone", "harmless today", ["model:read"])
        store.create("steptwo", "the other half", ["version:approve"])
        principals.create("c.hale", "C Hale", ["stepone", "steptwo"])

        with pytest.raises(AuthzError) as caught:
            store.amend("stepone", permissions=["model:read", "version:create"])
        assert caught.value.code == "incompatible_permissions"
        assert "c.hale" in caught.value.detail

    def test_an_amendment_that_conflicts_with_nobody_still_goes_through(self, store):
        store.create("readers", "reads more things", ["model:read"])
        after = store.amend("readers",
                            permissions=["model:read", "evidence:read"])
        assert sorted(after["permissions"]) == ["evidence:read", "model:read"]
