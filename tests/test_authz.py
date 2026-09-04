"""
MAYA — authorisation: roles, scope and segregation of duties.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Three independent questions, and the tests are organised the same way. The ones
that matter most are in TestSegregation: the rule that the person who built a
version may not approve it is checked against the evidence chain, so it holds
however the roles are arranged — including for an administrator.
"""
import time

import pytest

from core.authz import (AuthorizationPolicy, AuthzError, PrincipalService, ROLES,
                        Scope, SegregationPolicy, conflicts, permissions_for)
from tests.conftest import URN


# ==================================================================== roles
class TestRoles:
    def test_every_role_grants_only_real_permissions(self):
        from core.authz.common import PERMISSIONS
        for name, granted in ROLES.items():
            unknown = granted - PERMISSIONS
            assert not unknown, f"role {name} grants unknown permissions: {unknown}"

    def test_roles_compose_by_union(self):
        both = permissions_for(["model_developer", "validator"])
        assert both >= ROLES["model_developer"] | ROLES["validator"]

    def test_an_unknown_role_is_refused_rather_than_ignored(self):
        with pytest.raises(AuthzError, match="not a recognised role"):
            permissions_for(["wizard"])

    def test_a_developer_cannot_approve_or_tier(self):
        granted = permissions_for(["model_developer"])
        assert "version:create" in granted
        assert "version:approve" not in granted
        assert "risk:assess" not in granted
        assert "alias:move" not in granted

    def test_a_validator_never_builds(self):
        granted = permissions_for(["validator"])
        assert "validation:conclude" in granted and "finding:close" in granted
        assert "version:create" not in granted
        assert "feature:materialise" not in granted

    def test_an_auditor_reads_and_raises_but_never_remediates(self):
        granted = permissions_for(["auditor"])
        assert "finding:raise" in granted and "model:read" in granted
        assert "finding:close" not in granted
        assert "version:approve" not in granted

    def test_an_operator_has_no_governance_authority(self):
        """It runs the monitoring batch. It decides nothing."""
        granted = permissions_for(["operator"])
        assert "monitor:evaluate" in granted, "the batch runner must be able to evaluate"
        governance = {"version:approve", "model:attest", "model:approve", "alias:move",
                      "finding:close", "validation:conclude", "risk:assess",
                      "model:register", "version:create", "monitor:define"}
        assert not (granted & governance)

    def test_admin_holds_everything(self):
        from core.authz.common import PERMISSIONS
        assert permissions_for(["admin"]) == PERMISSIONS

    def test_incompatible_role_pairs_are_detected(self):
        found = conflicts(["model_developer", "model_risk_manager"])
        assert found and "approving its own work" in found[0]

    def test_compatible_roles_report_no_conflict(self):
        assert conflicts(["model_developer", "model_owner"]) == []

    def test_admin_is_exempt_because_break_glass_is_a_conscious_choice(self):
        assert conflicts(["admin", "model_developer", "model_risk_manager"]) == []


# ==================================================================== scope
class TestScope:
    UK = {"legal_entity": "LE-UK-02", "domain": "credit", "urn": "maya://model/a"}
    US = {"legal_entity": "LE-US-01", "domain": "credit", "urn": "maya://model/b"}
    FC = {"legal_entity": "LE-UK-02", "domain": "financial_crime", "urn": "maya://model/c"}

    def test_an_empty_scope_reaches_everything(self):
        assert Scope().unrestricted
        assert Scope().permits(self.UK) and Scope().permits(self.US)

    def test_entity_scope_excludes_other_entities(self):
        scope = Scope(legal_entities=("LE-UK-02",))
        assert scope.permits(self.UK) and not scope.permits(self.US)

    def test_domain_scope_excludes_other_domains(self):
        scope = Scope(domains=("credit",))
        assert scope.permits(self.UK) and not scope.permits(self.FC)

    def test_both_dimensions_must_pass(self):
        scope = Scope(legal_entities=("LE-UK-02",), domains=("credit",))
        assert scope.permits(self.UK)
        assert not scope.permits(self.US) and not scope.permits(self.FC)

    def test_the_refusal_names_the_dimension_that_excluded_it(self):
        assert "legal entity" in Scope(legal_entities=("LE-UK-02",)).refusal(self.US)
        assert "domain" in Scope(domains=("credit",)).refusal(self.FC)

    def test_filtering_hides_rows_rather_than_only_blocking_them(self):
        """Out of scope must not be discoverable from a count that does not add up."""
        scope = Scope(legal_entities=("LE-UK-02",))
        assert [m["urn"] for m in scope.filter([self.UK, self.US, self.FC])] == \
               ["maya://model/a", "maya://model/c"]

    def test_scope_is_read_from_a_principal_row(self):
        scope = Scope.of({"legal_entities": ["LE-UK-02"], "domains": []})
        assert scope.legal_entities == ("LE-UK-02",) and scope.domains == ()


# ============================================================== segregation
class TestSegregation:
    def test_the_creator_of_a_version_may_not_approve_it(self, segregation, evidence):
        evidence.append("version_created", "version", "v-1", {}, actor="d.raman")
        with pytest.raises(AuthzError) as exc:
            segregation.check("d.raman", "version:approve", "v-1")
        assert exc.value.code == "segregation_of_duties"
        assert "may not approve it" in exc.value.detail
        assert "evidence #" in exc.value.detail, "cite the record that disqualifies them"

    def test_somebody_else_may_approve_it(self, segregation, evidence):
        evidence.append("version_created", "version", "v-1", {}, actor="d.raman")
        segregation.check("s.iqbal", "version:approve", "v-1")     # no raise

    def test_the_creator_may_not_promote_their_own_build(self, segregation, evidence):
        evidence.append("version_created", "version", "v-1", {}, actor="d.raman")
        with pytest.raises(AuthzError, match="may not promote"):
            segregation.check("d.raman", "alias:move", "v-1")

    def test_the_creator_may_not_conclude_its_validation(self, segregation, evidence):
        evidence.append("version_created", "version", "v-1", {}, actor="d.raman")
        with pytest.raises(AuthzError, match="may not conclude"):
            segregation.check("d.raman", "validation:conclude", "v-1")

    def test_the_raiser_of_a_finding_may_not_close_it(self, segregation, evidence):
        evidence.append("finding_raised", "model", "f-1", {}, actor="a.mehta")
        with pytest.raises(AuthzError, match="may not close it"):
            segregation.check("a.mehta", "finding:close", "f-1")

    def test_acts_on_other_subjects_do_not_disqualify(self, segregation, evidence):
        evidence.append("version_created", "version", "v-1", {}, actor="d.raman")
        segregation.check("d.raman", "version:approve", "v-2")     # a different version

    def test_an_act_with_no_rule_is_never_refused(self, segregation, evidence):
        evidence.append("version_created", "version", "v-1", {}, actor="d.raman")
        segregation.check("d.raman", "model:read", "v-1")

    def test_the_conflict_is_reported_before_it_is_raised(self, segregation, evidence):
        evidence.append("version_created", "version", "v-1", {}, actor="d.raman")
        found = segregation.conflict("d.raman", "version:approve", "v-1")
        assert found["conflicting_kind"] == "version_created"
        assert found["remediation"]

    def test_the_rule_table_is_inspectable(self, segregation):
        """'Who could have approved this?' is an examiner's question."""
        described = segregation.describe()
        assert {r["act"] for r in described} >= {"version:approve", "alias:move"}
        assert all(r["reason"] and r["remediation"] for r in described)


# ================================================================ principals
class TestPrincipals:
    def test_a_principal_is_created_with_roles_and_scope(self, principals):
        p = principals.create("a.mehta", "A Mehta", ["validator"], "pw",
                              legal_entities=["LE-UK-02"], domains=["credit"])
        assert p["roles"] == ["validator"]
        assert p["legal_entities"] == ["LE-UK-02"]

    def test_credentials_never_leave_the_service(self, principals):
        p = principals.create("a.mehta", "A Mehta", ["validator"], "pw")
        assert "password_hash" not in p and "password_salt" not in p
        assert all("password_hash" not in row for row in principals.list())

    def test_a_duplicate_username_is_refused(self, principals):
        principals.create("a.mehta", "A", ["validator"], "pw")
        with pytest.raises(AuthzError, match="already exists"):
            principals.create("a.mehta", "A", ["validator"], "pw")

    def test_incompatible_roles_are_refused(self, principals):
        with pytest.raises(AuthzError) as exc:
            principals.create("x", "X", ["model_developer", "model_risk_manager"], "pw")
        assert exc.value.code == "incompatible_roles"
        assert "allow_conflicts" in exc.value.remediation, "name the deliberate route"

    def test_a_documented_exception_can_be_granted_explicitly(self, principals):
        p = principals.create("x", "X", ["model_developer", "model_risk_manager"],
                              "pw", allow_conflicts=True)
        assert len(p["roles"]) == 2

    def test_authentication_succeeds_with_the_right_password(self, principals):
        principals.create("a.mehta", "A", ["validator"], "pw")
        assert principals.authenticate("a.mehta", "pw")["username"] == "a.mehta"

    def test_authentication_fails_with_the_wrong_password(self, principals):
        principals.create("a.mehta", "A", ["validator"], "pw")
        assert principals.authenticate("a.mehta", "nope") is None

    def test_an_unknown_username_fails_the_same_way(self, principals):
        assert principals.authenticate("ghost", "pw") is None

    def test_a_service_principal_has_no_password_and_cannot_sign_in(self, principals):
        principals.create("svc/pricing", "Pricing", ["service"], kind="service")
        assert principals.authenticate("svc/pricing", "") is None

    def test_a_suspended_principal_cannot_authenticate(self, principals):
        principals.create("a.mehta", "A", ["validator"], "pw")
        principals.suspend("a.mehta")
        assert principals.authenticate("a.mehta", "pw") is None

    def test_suspension_takes_effect_immediately_despite_the_cache(self, principals):
        """The cache shortens the key derivation, never the decision."""
        principals.create("a.mehta", "A", ["validator"], "pw")
        assert principals.authenticate("a.mehta", "pw") is not None   # warms the cache
        principals.suspend("a.mehta")
        assert principals.authenticate("a.mehta", "pw") is None

    def test_roles_can_be_changed_and_the_change_is_recorded(self, principals, evidence):
        principals.create("a.mehta", "A", ["validator"], "pw")
        updated = principals.set_roles("a.mehta", ["auditor"])
        assert updated["roles"] == ["auditor"]
        kinds = [n["kind"] for n in evidence.repo.many()]
        assert "principal_roles_changed" in kinds

    def test_bootstrap_creates_the_first_administrator(self, principals):
        created = principals.bootstrap("admin", "admin123")
        assert created["roles"] == ["admin"]

    def test_bootstrap_does_nothing_once_principals_exist(self, principals):
        principals.create("a.mehta", "A", ["validator"], "pw")
        assert principals.bootstrap("admin", "admin123") is None, \
            "restarting a live deployment must not resurrect a development password"


# ==================================================================== policy
class TestPolicy:
    def test_permission_is_checked_first(self, authz, staff):
        with pytest.raises(AuthzError) as exc:
            authz.authorise(staff["d.raman"], "version:approve")
        assert exc.value.code == "forbidden"
        assert "model_developer" in exc.value.detail, "name the roles they hold"

    def test_scope_is_checked_after_permission(self, authz, principals):
        scoped = principals.create("uk.mrm", "UK", ["model_risk_manager"], "pw",
                                   legal_entities=["LE-UK-02"])
        row = principals.get("uk.mrm")
        with pytest.raises(AuthzError) as exc:
            authz.authorise(row, "version:approve",
                            model={"legal_entity": "LE-US-01", "domain": "credit"})
        assert exc.value.code == "out_of_scope"

    def test_segregation_is_checked_last(self, authz, staff, evidence):
        evidence.append("version_created", "version", "v-1", {}, actor="s.iqbal")
        with pytest.raises(AuthzError) as exc:
            authz.authorise(staff["s.iqbal"], "version:approve",
                            model={"legal_entity": "LE-US-01", "domain": "credit"},
                            subject_id="v-1")
        assert exc.value.code == "segregation_of_duties"

    def test_a_permitted_in_scope_independent_act_passes(self, authz, staff, evidence):
        evidence.append("version_created", "version", "v-1", {}, actor="d.raman")
        authz.authorise(staff["s.iqbal"], "version:approve",
                        model={"legal_entity": "LE-US-01", "domain": "credit"},
                        subject_id="v-1")

    def test_explain_reports_what_a_principal_may_do(self, authz, staff):
        described = authz.explain(staff["a.mehta"])
        assert described["roles"] == ["validator"]
        assert "validation:conclude" in described["permissions"]
        assert described["scope"] == "all entities, all domains"

    def test_visible_filters_an_inventory(self, authz, principals):
        principals.create("uk", "UK", ["auditor"], "pw", legal_entities=["LE-UK-02"])
        row = principals.get("uk")
        models = [{"urn": "a", "legal_entity": "LE-UK-02", "domain": "credit"},
                  {"urn": "b", "legal_entity": "LE-US-01", "domain": "credit"}]
        assert [m["urn"] for m in authz.visible(row, models)] == ["a"]

    def test_an_unknown_permission_is_refused_rather_than_denied_silently(self, authz, staff):
        with pytest.raises(AuthzError, match="not a recognised permission"):
            authz.permits(staff["a.mehta"], "model:teleport")
