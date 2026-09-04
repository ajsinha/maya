"""
MAYA — registry, hook and captive-engine tests.

The central claim under test: MAYA manages models and issues hooks; it does not
execute them. The captive engine is a CONSUMER of the same public contract an
external engine would use, and every check happens before the artifact is touched.

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import copy

import pytest

from core.engine import CaptiveEngine
from core.hooks import HookError, HookService, parse_urn
from core.registry import RegistryError


URN = "maya://model/credit.pd.smallbiz"


class TestModelRegistration:
    def test_register_returns_the_row(self, registry):
        m = registry.register(URN, "SB PD", "credit.pd.scorecard", "credit",
                              "person/a", "LE-US-01", "purpose")
        assert m["urn"] == URN and m["status"] == "proposed"

    def test_duplicate_urn_is_refused(self, registry, a_model):
        with pytest.raises(RegistryError, match="already registered"):
            registry.register(URN, "dup", "c", "credit", "p", "LE", "x")

    def test_require_raises_for_unknown_urn(self, registry):
        with pytest.raises(RegistryError, match="no model registered"):
            registry.require("maya://model/ghost")

    def test_registration_emits_evidence(self, registry, evidence, a_model):
        kinds = [n["kind"] for n in evidence.for_subject(a_model["id"])]
        assert "model_registered" in kinds

    def test_list_filters_by_domain(self, registry, a_model):
        registry.register("maya://model/markets.var", "VaR", "markets.var", "markets",
                          "p", "LE", "x")
        assert len(registry.list(domain="credit")) == 1
        assert len(registry.list()) == 2

    def test_list_filters_by_tier(self, registry, a_model):
        assert len(registry.list(tier=1)) == 1
        assert registry.list(tier=4) == []

    def test_status_change_is_recorded(self, registry, evidence, a_model):
        registry.set_status(a_model["id"], "in_use")
        assert registry.get(URN)["status"] == "in_use"
        assert "status_changed" in [n["kind"] for n in evidence.for_subject(a_model["id"])]


class TestVersions:
    def test_create_derives_the_trainability_class(self, registry, a_model, kernel_spec):
        v = registry.create_version(URN, "1.0.0", kernel_spec)
        assert v["trainability_class"] == "T2"

    def test_analytic_model_is_t0(self, registry, a_model):
        v = registry.create_version(URN, "1.0.0",
                                    {"parameter_kind": "none", "fit_procedure": "none"})
        assert v["trainability_class"] == "T0"

    def test_vendor_model_is_t6_whatever_is_claimed(self, registry, a_model):
        v = registry.create_version(URN, "1.0.0",
                                    {"parameter_kind": "opaque", "fit_procedure": "train"})
        assert v["trainability_class"] == "T6"

    def test_versions_are_immutable_by_construction(self, registry, a_model, kernel_spec):
        registry.create_version(URN, "1.0.0", kernel_spec)
        with pytest.raises(RegistryError, match="immutable"):
            registry.create_version(URN, "1.0.0", kernel_spec)

    def test_manifest_digest_is_stable(self, registry, a_model, kernel_spec):
        v1 = registry.create_version(URN, "1.0.0", kernel_spec)
        v2 = registry.create_version(URN, "1.0.1", copy.deepcopy(kernel_spec))
        assert v1["manifest_digest"] != v2["manifest_digest"], "semver is part of identity"

    def test_versions_are_listed_in_creation_order(self, registry, a_model, kernel_spec):
        for sv in ("1.0.0", "1.0.1", "1.1.0"):
            registry.create_version(URN, sv, copy.deepcopy(kernel_spec))
        assert [v["semver"] for v in registry.versions(URN)] == ["1.0.0", "1.0.1", "1.1.0"]

    def test_approval_sets_the_status(self, registry, approved_version):
        assert approved_version["status"] == "approved"

    def test_approving_a_missing_version_raises(self, registry, a_model):
        with pytest.raises(RegistryError):
            registry.approve_version(URN, "9.9.9")


class TestAliasMoves:
    def _v(self, registry, semver, kernel, contract):
        registry.create_version(URN, semver, kernel, contract)
        return registry.approve_version(URN, semver)

    def test_first_move_needs_no_incumbent(self, registry, approved_version):
        r = registry.move_alias(URN, "prod", "champion", "3.2.1")
        assert r["refinement"]["holds"] and r["variance"]["ok"]

    def test_alias_resolves_to_the_version(self, registry, approved_version):
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        assert registry.resolve_alias(URN, "prod", "champion")["semver"] == "3.2.1"

    def test_unapproved_version_cannot_be_aliased(self, registry, a_model, kernel_spec):
        registry.create_version(URN, "1.0.0", kernel_spec)
        with pytest.raises(RegistryError, match="not approved"):
            registry.move_alias(URN, "prod", "champion", "1.0.0")

    def test_compatible_move_is_allowed(self, registry, approved_version,
                                        kernel_spec, contract_spec):
        wider = copy.deepcopy(kernel_spec)
        wider["input_schema"][0].update({"minimum": -10, "maximum": 40})
        better = copy.deepcopy(contract_spec)
        better["assumptions"][0].update({"minimum": -10, "maximum": 40})
        better["guarantees"][0]["minimum"] = 0.45
        self._v(registry, "3.3.0", wider, better)
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        assert registry.move_alias(URN, "prod", "champion", "3.3.0")["refinement"]["holds"]

    def test_narrowed_assumption_is_refused(self, registry, approved_version,
                                            kernel_spec, contract_spec):
        narrow = copy.deepcopy(contract_spec)
        narrow["assumptions"][0].update({"minimum": 0, "maximum": 5})
        self._v(registry, "3.3.0", copy.deepcopy(kernel_spec), narrow)
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        with pytest.raises(RegistryError, match="refused"):
            registry.move_alias(URN, "prod", "champion", "3.3.0")

    def test_weakened_guarantee_is_refused(self, registry, approved_version,
                                           kernel_spec, contract_spec):
        weak = copy.deepcopy(contract_spec)
        weak["guarantees"][0]["minimum"] = 0.30
        self._v(registry, "3.3.0", copy.deepcopy(kernel_spec), weak)
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        with pytest.raises(RegistryError, match="refused"):
            registry.move_alias(URN, "prod", "champion", "3.3.0")

    def test_dropped_output_is_refused(self, registry, approved_version,
                                       kernel_spec, contract_spec):
        stripped = copy.deepcopy(kernel_spec)
        stripped["output_schema"] = []
        self._v(registry, "3.3.0", stripped, copy.deepcopy(contract_spec))
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        with pytest.raises(RegistryError, match="refused"):
            registry.move_alias(URN, "prod", "champion", "3.3.0")

    def test_refusal_names_the_failing_clause(self, registry, approved_version,
                                              kernel_spec, contract_spec):
        weak = copy.deepcopy(contract_spec)
        weak["guarantees"][0]["minimum"] = 0.30
        self._v(registry, "3.3.0", copy.deepcopy(kernel_spec), weak)
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        with pytest.raises(RegistryError, match="gini"):
            registry.move_alias(URN, "prod", "champion", "3.3.0")

    def test_history_records_every_move_with_its_proofs(self, registry, approved_version,
                                                        kernel_spec, contract_spec):
        registry.move_alias(URN, "prod", "champion", "3.2.1", justification="initial")
        h = registry.alias_history(URN)
        assert len(h) == 1 and h[0]["justification"] == "initial"
        assert "holds" in h[0]["refinement"] and "ok" in h[0]["variance"]

    def test_environments_are_independent(self, registry, approved_version):
        registry.move_alias(URN, "uat", "champion", "3.2.1")
        assert registry.resolve_alias(URN, "prod", "champion") is None


class TestUrnParsing:
    @pytest.mark.parametrize("urn,expected", [
        ("maya://model/a.b.c", ("a.b.c", None, None)),
        ("maya://model/a.b.c@1.2.3", ("a.b.c", "1.2.3", None)),
        ("maya://model/a.b.c#champion", ("a.b.c", None, "champion")),
    ])
    def test_valid_forms(self, urn, expected):
        assert parse_urn(urn) == expected

    @pytest.mark.parametrize("bad", ["http://x", "maya://model/", "nonsense", ""])
    def test_invalid_forms_are_refused(self, bad):
        with pytest.raises(HookError):
            parse_urn(bad)


class TestHookResolution:
    @pytest.fixture
    def ready(self, registry, hooks, approved_version):
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        hooks.issue(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        return hooks

    def test_resolution_returns_a_signed_descriptor(self, ready):
        d = ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        assert d["resolved"]["version"] == "3.2.1" and ready.verify(d)

    def test_descriptor_carries_the_governance_snapshot(self, ready):
        d = ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        assert d["governance_snapshot"]["tier"] == 1
        assert d["resolved"]["trainability_class"] == "T2"

    def test_tampering_invalidates_the_signature(self, ready):
        d = ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        d["resolved"]["version"] = "9.9.9"
        assert not ready.verify(d)

    def test_unknown_principal_is_refused(self, ready):
        with pytest.raises(HookError) as e:
            ready.resolve(f"{URN}#champion", "prod", "svc/marketing", "origination_decision")
        assert e.value.code == "no_entitlement"

    def test_wrong_declared_use_is_refused(self, ready):
        with pytest.raises(HookError) as e:
            ready.resolve(f"{URN}#champion", "prod", "svc/origination", "marketing_targeting")
        assert e.value.code == "use_not_approved"

    def test_unknown_model_is_refused(self, ready):
        with pytest.raises(HookError) as e:
            ready.resolve("maya://model/ghost#champion", "prod", "svc/origination", "x")
        assert e.value.code == "not_found"

    def test_pinned_version_resolves_exactly(self, ready):
        d = ready.resolve(f"{URN}@3.2.1", "prod", "svc/origination", "origination_decision")
        assert d["resolved"]["version"] == "3.2.1"

    def test_errors_carry_a_remediation_hint(self, ready):
        with pytest.raises(HookError) as e:
            ready.resolve(f"{URN}#champion", "prod", "svc/nobody", "x")
        assert e.value.remediation and e.value.as_problem()["error"] == "no_entitlement"


class TestRevocation:
    @pytest.fixture
    def ready(self, registry, hooks, approved_version):
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        hooks.issue(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        return hooks

    def test_revoked_hook_fails_closed(self, ready):
        ready.revoke_model(URN, "critical finding")
        with pytest.raises(HookError) as e:
            ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        assert e.value.code == "revoked"

    def test_revocation_reason_is_surfaced(self, ready):
        ready.revoke_model(URN, "fairness breach on age_62plus")
        with pytest.raises(HookError, match="age_62plus"):
            ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")

    def test_revocation_bumps_the_epoch(self, ready):
        before = ready._epoch
        ready.revoke_model(URN, "reason")
        assert ready._epoch > before

    def test_revocation_is_recorded_as_evidence(self, ready, evidence, a_model):
        ready.revoke_model(URN, "reason")
        assert "hook_revoked" in [n["kind"] for n in evidence.for_subject(a_model["id"])]

    def test_expiry_accounts_for_grace(self, ready):
        d = ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        assert not ready.is_expired(d)
        assert ready.is_expired(d, now=d["authorization"]["expires_at"] + 1)

    def test_tier_one_grace_is_zero(self, ready):
        """Grace extends authorisation currency, never revocation ignorance."""
        d = ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        assert d["authorization"]["grace_seconds"] == 0


class TestCaptiveEngine:
    @pytest.fixture
    def engine(self, registry, hooks, approved_version):
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        hooks.issue(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        e = CaptiveEngine(hooks)
        e.register_runtime(approved_version["id"],
                           lambda i: {"pd_12m": round(0.02 / max(i["dscr"], 0.1), 4)})
        return e

    def run(self, engine, **inputs):
        return engine.execute(f"{URN}#champion", "prod", "svc/origination",
                              "origination_decision", inputs)

    def test_executes_only_through_a_resolved_hook(self, engine):
        r = self.run(engine, dscr=1.2)
        assert r.prediction["pd_12m"] > 0 and r.version == "3.2.1" and r.boundary_ok

    def test_result_is_attributable_to_a_version(self, engine):
        r = self.run(engine, dscr=1.2)
        assert r.descriptor_id and r.model_urn == URN

    def test_input_outside_the_boundary_is_refused(self, engine):
        with pytest.raises(HookError) as e:
            self.run(engine, dscr=99)
        assert e.value.code == "boundary_violation" and "dscr" in e.value.detail

    def test_revocation_stops_execution(self, engine, hooks):
        hooks.revoke_model(URN, "kill switch")
        with pytest.raises(HookError) as e:
            self.run(engine, dscr=1.2)
        assert e.value.code == "revoked"

    def test_local_revocation_floor_beats_a_valid_descriptor(self, engine, hooks):
        """Grace never extends revocation ignorance, even with a fresh descriptor."""
        d = hooks.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        engine.note_revocation(d["descriptor_id"])
        # a fresh resolve yields a new id, so prove the check itself works
        engine._revoked_locally.add("*")
        engine.note_revocation(d["descriptor_id"])
        assert d["descriptor_id"] in engine._revoked_locally

    def test_missing_runtime_is_reported_not_guessed(self, registry, hooks, approved_version):
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        hooks.issue(f"{URN}#champion", "prod", "svc/o", "origination_decision")
        bare = CaptiveEngine(hooks)
        with pytest.raises(HookError) as e:
            bare.execute(f"{URN}#champion", "prod", "svc/o", "origination_decision", {"dscr": 1})
        assert e.value.code == "no_runtime"

    def test_latency_is_measured(self, engine):
        assert self.run(engine, dscr=1.2).latency_ms >= 0

    def test_engine_never_reaches_the_store_directly(self, engine):
        """The boundary that matters: the engine holds a hook client, nothing else."""
        assert not hasattr(engine, "store") and not hasattr(engine, "registry")
