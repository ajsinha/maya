"""
MAYA — registry, warrant and captive-engine tests.

The central claim under test: MAYA manages models and issues warrants; it does not
execute them. The captive engine is a CONSUMER of the same public contract an
external engine would use, and every check happens before the artifact is touched.

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
"""
import copy

import pytest

from core.execution import CaptiveEngine
from core.execution import WarrantError, parse_urn
from core.registry import RegistryError


URN = "maya://model/credit.pd.smallbiz"


class TestModelRegistration:
    def test_register_returns_the_row(self, registry):
        m = registry.register(URN, "SB PD", "credit.pd.scorecard", "credit",
                              "person/a", "LE-US-01", "purpose")
        assert m["urn"] == URN and m["status"] == "draft"

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
        with pytest.raises(WarrantError):
            parse_urn(bad)


class TestWarrantResolution:
    @pytest.fixture
    def ready(self, registry, warrants, approved_version):
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        warrants.issue(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        return warrants

    def test_resolution_returns_a_signed_descriptor(self, ready):
        d = ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        assert d["subject"]["version"] == "3.2.1" and ready.verify(d)

    def test_descriptor_carries_the_governance_snapshot(self, ready):
        d = ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        assert d["governance"]["tier"] == 1
        assert d["subject"]["trainability_class"] == "T2"

    def test_tampering_invalidates_the_signature(self, ready):
        d = ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        d["subject"]["version"] = "9.9.9"
        assert not ready.verify(d)

    def test_unknown_principal_is_refused(self, ready):
        with pytest.raises(WarrantError) as e:
            ready.resolve(f"{URN}#champion", "prod", "svc/marketing", "origination_decision")
        assert e.value.code == "no_entitlement"

    def test_wrong_declared_use_is_refused(self, ready):
        with pytest.raises(WarrantError) as e:
            ready.resolve(f"{URN}#champion", "prod", "svc/origination", "marketing_targeting")
        assert e.value.code == "use_not_approved"

    def test_unknown_model_is_refused(self, ready):
        with pytest.raises(WarrantError) as e:
            ready.resolve("maya://model/ghost#champion", "prod", "svc/origination", "x")
        assert e.value.code == "not_found"

    def test_pinned_version_resolves_exactly(self, ready):
        d = ready.resolve(f"{URN}@3.2.1", "prod", "svc/origination", "origination_decision")
        assert d["subject"]["version"] == "3.2.1"

    def test_errors_carry_a_remediation_hint(self, ready):
        with pytest.raises(WarrantError) as e:
            ready.resolve(f"{URN}#champion", "prod", "svc/nobody", "x")
        assert e.value.remediation and e.value.as_problem()["error"] == "no_entitlement"


class TestRevocation:
    @pytest.fixture
    def ready(self, registry, warrants, approved_version):
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        warrants.issue(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        return warrants

    def test_revoked_warrant_fails_closed(self, ready):
        ready.revoke_model(URN, "critical finding")
        with pytest.raises(WarrantError) as e:
            ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        assert e.value.code == "revoked"

    def test_revocation_reason_is_surfaced(self, ready):
        ready.revoke_model(URN, "fairness breach on age_62plus")
        with pytest.raises(WarrantError, match="age_62plus"):
            ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")

    def test_revocation_bumps_the_epoch(self, ready):
        before = ready.epoch
        ready.revoke_model(URN, "reason")
        assert ready.epoch > before

    def test_revocation_is_recorded_as_evidence(self, ready, evidence, a_model):
        ready.revoke_model(URN, "reason")
        assert "warrant_revoked" in [n["kind"] for n in evidence.for_subject(a_model["id"])]

    def test_expiry_accounts_for_grace(self, ready):
        d = ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        assert not ready.is_expired(d)
        assert ready.is_expired(d, now=d["authority"]["expires_at"] + 1)

    def test_tier_one_grace_is_zero(self, ready):
        """Grace extends authorisation currency, never revocation ignorance."""
        d = ready.resolve(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        assert d["authority"]["grace_seconds"] == 0


class TestCaptiveEngine:
    @pytest.fixture
    def engine(self, registry, warrants, approved_version):
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        warrants.issue(f"{URN}#champion", "prod", "svc/origination", "origination_decision")
        e = CaptiveEngine(warrants)
        e.register_runtime(approved_version["id"],
                           lambda i: {"pd_12m": round(0.02 / max(i["dscr"], 0.1), 4)})
        return e

    def run(self, engine, **inputs):
        return engine.execute(f"{URN}#champion", "prod", "svc/origination",
                              "origination_decision", inputs)

    def test_executes_only_through_a_resolved_warrant(self, engine):
        r = self.run(engine, dscr=1.2)
        assert r.prediction["pd_12m"] > 0 and r.version == "3.2.1" and r.boundary_ok

    def test_result_is_attributable_to_a_version(self, engine):
        r = self.run(engine, dscr=1.2)
        assert r.descriptor_id and r.model_urn == URN

    def test_input_outside_the_boundary_is_refused(self, engine):
        with pytest.raises(WarrantError) as e:
            self.run(engine, dscr=99)
        assert e.value.code == "boundary_violation" and "dscr" in e.value.detail

    def test_revocation_stops_execution(self, engine, warrants):
        warrants.revoke_model(URN, "kill switch")
        with pytest.raises(WarrantError) as e:
            self.run(engine, dscr=1.2)
        assert e.value.code == "revoked"

    def test_local_revocation_floor_beats_a_valid_descriptor(self, engine, warrants):
        """Grace never extends revocation ignorance, even with a fresh descriptor.

        This test used to read:

            engine.note_revocation(d["warrant_id"])
            # a fresh resolve yields a new id, so prove the check itself works
            engine._revoked_locally.add("*")
            assert d["warrant_id"] in engine._revoked_locally

        which asserts that a set contains what was just added to it. It never
        called `execute` and never observed a refusal, and the floor it was named
        for could not fire: `execute` re-resolves, every build mints a fresh
        `warrant_id`, and the noted id therefore never matched the checked one.

        The comment in the middle is the tell. It states the exact reason the
        mechanism was broken and treats it as an inconvenience to the test.
        """
        engine.note_revocation(URN)
        with pytest.raises(WarrantError) as e:
            self.run(engine, dscr=1.2)
        assert e.value.code == "revoked"
        assert URN in e.value.detail

    def test_the_floor_survives_a_re_resolve(self, engine, warrants):
        """The whole point. The engine is told to stop, then obtains a brand new,
        perfectly valid, correctly signed descriptor — and still refuses."""
        engine.note_revocation(URN)
        fresh = warrants.resolve(f"{URN}#champion", "prod", "svc/origination",
                                 "origination_decision")
        assert warrants.verify(fresh), "the descriptor is genuinely valid"
        with pytest.raises(WarrantError) as e:
            self.run(engine, dscr=1.2)
        assert e.value.code == "revoked"

    def test_a_model_that_was_not_revoked_still_runs(self, engine, warrants):
        """A floor that refuses everything is not a floor."""
        engine.note_revocation("maya://model/some.other.thing")
        assert self.run(engine, dscr=1.2) is not None

    def test_missing_runtime_is_reported_not_guessed(self, registry, warrants, approved_version):
        registry.move_alias(URN, "prod", "champion", "3.2.1")
        warrants.issue(f"{URN}#champion", "prod", "svc/o", "origination_decision")
        bare = CaptiveEngine(warrants)
        with pytest.raises(WarrantError) as e:
            bare.execute(f"{URN}#champion", "prod", "svc/o", "origination_decision", {"dscr": 1})
        assert e.value.code == "no_runtime"

    def test_latency_is_measured(self, engine):
        assert self.run(engine, dscr=1.2).latency_ms >= 0

    def test_engine_never_reaches_the_store_directly(self, engine):
        """The boundary that matters: the engine holds a warrant client, nothing else."""
        assert not hasattr(engine, "store") and not hasattr(engine, "registry")


# ===================================== a refusal must survive the layer above
class TestARefusalToGuessIsNotRecoveredFrom:
    """`ParameterRegister.resolve` refuses `ambiguous_parameters` when a version
    has several approved sets and none was named, and its own comment says why:
    *choosing for the caller is how a model quietly runs on last quarter's
    coefficients.*

    `WarrantService._point_of_p` caught bare `Exception` and returned `None`.
    So the refusal did the opposite of its purpose one layer up — it vanished
    into a DEBUG line and the warrant was issued naming no point of `P`.

    The existing test asserted that `resolve` refuses, which was never the
    question. Nothing asserted the refusal reached anybody. That is the shape to
    watch for: a control tested where it is *raised* and never where it is
    *caught*.
    """

    class _Port:
        """Stands in for the parameter register, which is an injected port."""

        def __init__(self, code):
            self.code = code

        def resolve(self, urn, semver, name=None):
            raise self._Refusal(self.code)

        class _Refusal(RuntimeError):
            def __init__(self, code):
                super().__init__(code)
                self.code = code

    def _service(self, port):
        from core.execution.warrants import WarrantService
        service = WarrantService.__new__(WarrantService)
        service.parameters = port
        return service

    VERSION = {"semver": "3.2.1", "artifact_uri": None}

    def test_no_approved_parameters_is_recovered_from(self):
        """The case the recovery was written for: nothing approved yet, and the
        run fails for a better reason further on."""
        service = self._service(self._Port("no_approved_parameters"))
        assert service._point_of_p("maya://model/x", self.VERSION) is None

    def test_ambiguous_parameters_travels(self):
        service = self._service(self._Port("ambiguous_parameters"))
        with pytest.raises(Exception) as exc:
            service._point_of_p("maya://model/x", self.VERSION)
        assert exc.value.code == "ambiguous_parameters"

    def test_an_unrecognised_failure_travels_too(self):
        """A recovery that cannot name what it is recovering from is not a
        recovery. Anything but the one known-recoverable code is re-raised,
        including a failure with no code at all."""
        class _Broken:
            def resolve(self, urn, semver, name=None):
                raise KeyError("the register is not answering")

        with pytest.raises(KeyError):
            self._service(_Broken())._point_of_p("maya://model/x", self.VERSION)


class TestTheOperatingBoundaryReachesNestedInputs:
    """`check_inputs` skipped any assumption whose key was not in the top level
    of the input dict.

    The estimator reads `inputs["features"]`, so an assumption on `turnover`
    found no `turnover` at the top level, and the "absent key passes" clause let
    it through. A signed operating boundary was therefore **unenforced for every
    runtime that nests its inputs** — silently, with `boundary_ok: true` on the
    response, which is the shape of a control that reports success.
    """

    @staticmethod
    def _contract():
        from core.domain.contracts import Bound, Contract
        return Contract(assumptions=(Bound("turnover", minimum=0, maximum=2000),))

    def test_a_top_level_value_outside_the_band_is_caught(self):
        assert self._contract().check_inputs({"turnover": 9000}) == ["turnover"]

    def test_a_nested_value_outside_the_band_is_caught(self):
        """The case that was not."""
        assert self._contract().check_inputs(
            {"features": {"turnover": 9000}}) == ["turnover"]

    def test_a_nested_value_inside_the_band_passes(self):
        assert self._contract().check_inputs({"features": {"turnover": 500}}) == []

    def test_an_absent_assumption_is_not_a_violation_but_is_reported(self):
        """An assumption constrains a value that was supplied; a caller who
        supplied nothing has not violated a band. But 'the boundary held' and
        'the boundary never applied' must be answerable separately."""
        contract = self._contract()
        assert contract.check_inputs({"unrelated": 1}) == []
        assert contract.unchecked_inputs({"unrelated": 1}) == ["turnover"]

    def test_the_top_level_wins_a_name_collision(self):
        """Where the caller addressed it wins. A deep walk would start matching
        an assumption against a value that happens to share a name several
        objects down, and a boundary firing on the wrong field is worse than one
        that does not fire."""
        assert self._contract().check_inputs(
            {"turnover": 500, "features": {"turnover": 9000}}) == []

    def test_it_does_not_walk_deeper_than_one_level(self):
        contract = self._contract()
        deep = {"a": {"b": {"turnover": 9000}}}
        assert contract.check_inputs(deep) == []
        assert contract.unchecked_inputs(deep) == ["turnover"]


class TestTheRevocationEpochSurvivesARestart:
    """The epoch is bumped by every revocation and stamped onto each grant, so a
    descriptor carrying a stale one was issued before somebody withdrew
    authority.

    It lived only in the process and started at zero. Revoke three times,
    restart, and the next grant is stamped epoch 0 — indistinguishable from a
    grant predating every one of those revocations. **A restart silently undid
    the effect of revoking**, which is the one act that most needs to survive
    one. The column has been on `warrant` the whole time; nothing read it back.
    """

    def test_a_fresh_service_resumes_where_the_register_left_off(
            self, repos, registry, evidence, a_model, approved_version):
        from core.execution.grants import WarrantGrants

        grants = WarrantGrants(repos["warrants"], registry, evidence)
        grants.issue(URN, "prod", "svc/origination", "origination_decision")
        for _ in range(3):
            grants.revoke_model(URN, "kill switch")
        assert grants.epoch == 3

        # A restart: a new object over the same database.
        restarted = WarrantGrants(repos["warrants"], registry, evidence)
        assert restarted.epoch == 3, (
            "the epoch reset, so a grant issued after the restart would look "
            "older than three revocations that have already happened")

    def test_it_starts_at_zero_when_nothing_has_been_revoked(
            self, repos, registry, evidence):
        from core.execution.grants import WarrantGrants
        assert WarrantGrants(repos["warrants"], registry, evidence).epoch == 0

    def test_a_grant_issued_after_a_restart_carries_the_resumed_epoch(
            self, repos, registry, evidence, a_model, approved_version):
        from core.execution.grants import WarrantGrants
        grants = WarrantGrants(repos["warrants"], registry, evidence)
        grants.issue(URN, "prod", "svc/origination", "origination_decision")
        grants.revoke_model(URN, "kill switch")

        restarted = WarrantGrants(repos["warrants"], registry, evidence)
        fresh = restarted.issue(URN, "prod", "svc/origination",
                                "origination_decision")
        assert fresh["epoch"] == 1


class TestAnUndeclaredInputSchemaIsNotAnEmptyOne:
    """`input_schema` defaults to `[]`, and `[]` means "reads nothing".

    Every input-side control then passes vacuously while reporting success:
    L-W10 resolves to "does this featureset provide the empty set", which any
    featureset does, and L-12's contravariance is checked over no fields at all.
    So the version that skipped the cheapest declaration a developer makes was
    the version exempt from the checks — and each of them said it had passed.
    """

    def test_a_fit_warrant_refuses_a_version_that_declares_no_inputs(
            self, repos, registry, evidence, full_features):
        import pytest

        from core.execution import WarrantService
        from core.execution.warrants import WarrantError

        warrants = WarrantService(repos["warrants"], registry, evidence,
                                  jitter_pct=0, featuresets=full_features)
        urn = "maya://model/credit.undeclared"
        registry.register(urn, "Undeclared", "credit", "retail", "person/o",
                          "LE-US-01", "reads nothing, apparently")
        registry.create_version(urn, "1.0.0", {
            "parameter_kind": "estimated_coefficients",
            "fit_procedure": "estimate",
            "output_schema": [{"name": "pd", "dtype": "numeric"}]})
        version = registry.versions(urn)[-1]
        with pytest.raises(WarrantError) as refusal:
            warrants._check_schema(version, "anything", 1)
        assert refusal.value.code == "input_schema_not_declared"
        assert "any featureset" in str(refusal.value)

    def test_the_variance_proof_refuses_to_be_discharged_over_nothing(self):
        from core.registry.aliases import AliasService

        blank = {"input_schema": [], "output_schema": [], "contract": {}}
        proof = AliasService.obligations(dict(blank), dict(blank))
        assert not proof["variance"]["ok"], \
            "L-12 held between two versions that declare nothing"
        assert "no input schema" in proof["variance"]["reason"]

    def test_two_declared_versions_are_still_compared_normally(self):
        """So the refusal is about silence, not about the check itself."""
        from core.registry.aliases import AliasService

        schema = [{"name": "dscr", "dtype": "numeric"}]
        out = [{"name": "pd", "dtype": "numeric"}]
        same = {"input_schema": schema, "output_schema": out, "contract": {}}
        assert AliasService.obligations(dict(same), dict(same))["variance"]["ok"]

    def test_the_rule_validator_already_failed_closed(self):
        """Recorded because it is the one that got this right: an empty input
        schema refuses every rule that reads a field, rather than accepting
        them all. Worth a test so a later 'simplification' cannot invert it."""
        import pytest

        from core.rules.conditions import Condition
        from core.rules.common import RuleError

        with pytest.raises(RuleError, match="does not declare"):
            Condition.parse({"field": "dscr", "op": "gt", "value": 1.0}) \
                     .conforms({}, path="rule 'r1'")


class TestAContractThatPinsNothing:
    """`contract_of` and `bounds_of` read every key with `.get`.

    So every spelling mistake produced a VALID, EMPTY contract — digested into
    the manifest, carried into the fit warrant, and used to gate alias
    promotion. A version whose contract says `dscr` is constrained to [0, 20]
    and whose stored contract constrains nothing reads as governed and is not:
    L-7 refinement between two empty contracts holds, and a boundary check with
    no bounds never fires.
    """

    KERNEL = {"parameter_kind": "estimated_coefficients",
              "fit_procedure": "estimate",
              "input_schema": [{"name": "dscr", "dtype": "numeric"}],
              "output_schema": [{"name": "pd", "dtype": "numeric"}]}

    @staticmethod
    def _model(registry, name):
        urn = f"maya://model/{name}"
        registry.register(urn, name, "credit", "retail", "person/o",
                          "LE-US-01", "contract validation")
        return urn

    def _create(self, registry, name, contract):
        import pytest

        from core.registry.common import RegistryError

        urn = self._model(registry, name)
        with pytest.raises(RegistryError) as refusal:
            registry.create_version(urn, "1.0.0", dict(self.KERNEL), contract)
        return str(refusal.value)

    def test_a_misspelled_bound_is_refused_rather_than_silently_unbounded(
            self, registry):
        detail = self._create(registry, "c.minmax", {
            "assumptions": [{"key": "dscr", "min": 0, "max": 20}]})
        assert "min" in detail and "minimum" in detail
        assert "UNBOUNDED" in detail, "say what the mistake actually costs"

    def test_a_misspelled_section_is_refused_rather_than_dropped(self, registry):
        detail = self._create(registry, "c.section", {
            "assumption": [{"key": "dscr", "minimum": 0, "maximum": 20}]})
        assert "assumption" in detail and "assumptions" in detail

    def test_an_inverted_band_is_refused(self, registry):
        detail = self._create(registry, "c.inverted", {
            "assumptions": [{"key": "dscr", "minimum": 20, "maximum": 0}]})
        assert "admits nothing" in detail

    def test_a_clause_with_no_key_is_a_refusal_not_a_keyerror(self, registry):
        """It used to be a raw `KeyError` out of `bounds_of` — a 500, and a
        stack trace where a message naming the clause belongs."""
        detail = self._create(registry, "c.nokey", {
            "guarantees": [{"minimum": 0.42}]})
        assert "guarantees[0]" in detail and "no 'key'" in detail

    def test_an_unknown_boundary_policy_is_refused(self, registry):
        detail = self._create(registry, "c.policy", {
            "assumptions": [{"key": "dscr", "minimum": 0}],
            "on_boundary_violation": "ignore"})
        assert "ignore" in detail and "reject" in detail

    def test_a_well_formed_contract_is_still_accepted(self, registry):
        """The refusals must be about malformation, not about contracts."""
        urn = self._model(registry, "c.good")
        version = registry.create_version(urn, "1.0.0", dict(self.KERNEL), {
            "assumptions": [{"key": "dscr", "minimum": 0, "maximum": 20}],
            "guarantees": [{"key": "gini", "minimum": 0.42}],
            "on_boundary_violation": "reject"})
        assert version["contract"]["assumptions"][0]["maximum"] == 20

    def test_an_absent_contract_is_still_allowed(self, registry):
        """A version may genuinely make no promise; that is different from one
        that appears to make a promise and does not."""
        urn = self._model(registry, "c.none")
        assert registry.create_version(urn, "1.0.0", dict(self.KERNEL))


class TestAnAssumptionMustBeAboutSomethingTheKernelReads:
    """The contract and the schemas were two declarations nobody compared.

    `{"key": "dscr_typo", "minimum": 0}` beside an `input_schema` naming `dscr`
    was stored, digested into the manifest and carried into the warrant. At
    execution the engine finds no value for it, skips the clause and writes an
    INFO line — so the model runs unconstrained on `dscr` while its contract
    appears to bound it, and the only trace is a log nobody reads.

    `ExecutionEngine` already had `unchecked_inputs` for this exact shape, which
    is the tell: the runtime was built to notice a condition that should never
    have been declarable.
    """

    KERNEL = {"parameter_kind": "estimated_coefficients",
              "fit_procedure": "estimate",
              "input_schema": [{"name": "dscr", "dtype": "numeric"},
                               {"name": "ltv", "dtype": "numeric"}],
              "output_schema": [{"name": "pd_12m", "dtype": "numeric"}]}

    @staticmethod
    def _model(registry, name):
        urn = f"maya://model/{name}"
        registry.register(urn, name, "credit", "retail", "person/o",
                          "LE-US-01", "assumption binding")
        return urn

    def test_an_assumption_about_an_undeclared_field_is_refused(self, registry):
        import pytest

        from core.registry.common import RegistryError

        urn = self._model(registry, "bind.typo")
        with pytest.raises(RegistryError) as refusal:
            registry.create_version(urn, "1.0.0", dict(self.KERNEL), {
                "assumptions": [{"key": "dscr_typo", "minimum": 0,
                                 "maximum": 20}]})
        detail = str(refusal.value)
        assert "dscr_typo" in detail
        assert "dscr, ltv" in detail, "say what it could have meant"

    def test_an_assumption_about_a_declared_field_is_accepted(self, registry):
        urn = self._model(registry, "bind.good")
        version = registry.create_version(urn, "1.0.0", dict(self.KERNEL), {
            "assumptions": [{"key": "dscr", "minimum": 0, "maximum": 20},
                            {"key": "ltv", "minimum": 0, "maximum": 2}]})
        assert len(version["contract"]["assumptions"]) == 2

    def test_a_guarantee_may_name_something_that_is_not_an_output(self, registry):
        """`gini` is a property of the model, not a column it returns, and there
        is no closed vocabulary of those — refusing here would mean inventing
        one, so guarantees are deliberately not bound."""
        urn = self._model(registry, "bind.metric")
        version = registry.create_version(urn, "1.0.0", dict(self.KERNEL), {
            "assumptions": [{"key": "dscr", "minimum": 0}],
            "guarantees": [{"key": "gini", "minimum": 0.42}]})
        assert version["contract"]["guarantees"][0]["key"] == "gini"

    def test_a_version_with_no_input_schema_is_left_to_the_other_check(
            self, registry):
        """Two refusals for one silence would name the wrong problem. An absent
        schema is refused where it does damage — at the fit warrant and the
        alias move — not a second time here."""
        urn = self._model(registry, "bind.noschema")
        kernel = {k: v for k, v in self.KERNEL.items() if k != "input_schema"}
        assert registry.create_version(urn, "1.0.0", kernel, {
            "assumptions": [{"key": "anything", "minimum": 0}]})
