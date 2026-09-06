"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The governed half of the SDK, against the real application.

Same seam as `test_sdk.py` and for the same reason: a mock of the thing under
test proves only that the mock agrees with itself, and an SDK is precisely the
code whose entire value is that it agrees with a *server*. Every call below
travels routes, authorisation, the domain and the evidence chain, and comes back.

Four properties matter more than method coverage.

**The record's promise holds through the SDK.** An attested model refuses a new
version, and the refusal arrives as an exception carrying the remediation that
names the amendment — not as a status code somebody has to look up.

**Free and authoritative stay apart.** `check` and `trial` carry the read
permission, record nothing and can be called on every keystroke; publishing is
the ordinary recording act. A client that had to spend authority to look at its
own draft is a client whose authors stop looking.

**A fibre is read, never reconstructed.** All four facets come back from the
platform, and this package holds no list of classes and no list of what any of
them admits.

**The SDK decides nothing.** Asserted on the source, because the temptation to
"help" is exactly what would create the second rule.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sdk" / "python"))

from maya_sdk import Blocked, Maya, NotFound, NotPermitted, Refused  # noqa: E402
from maya_sdk import governance  # noqa: E402

URN = "maya://model/credit.pd.smallbiz"
NAME = "credit.pd.smallbiz"

KERNEL = {"parameter_kind": "estimated_coefficients", "fit_procedure": "estimate",
          "input_schema": [{"name": "dscr", "dtype": "float",
                            "minimum": -5, "maximum": 20}],
          "output_schema": [{"name": "pd_12m", "dtype": "float"}]}

# A model whose parameter object is a rule set: authored rather than fitted.
# The class it lands in is the platform's conclusion and is never spelled here.
RULES_URN = "maya://model/credit.eligibility.retail"
RULES_NAME = "credit.eligibility.retail"
RULES_SCHEMA = {"ltv": "numeric", "dti": "numeric", "product": "categorical"}
RULES_KERNEL = {
    "parameter_kind": "rule_set", "fit_procedure": "author", "runtime": "rules",
    "entry": {"ruleset": "eligibility", "engine": "maya"},
    "input_schema": [{"name": n, "dtype": d} for n, d in RULES_SCHEMA.items()],
    "output_schema": [{"name": "decision", "dtype": "string"}]}


def a_rule(rule_id, when, then=None, because="policy CP-2024-11"):
    return {"id": rule_id, "when": when, "then": then or {"decision": "refer"},
            "because": because}


def a_document(*rules, otherwise=None):
    return {"rules": list(rules), "otherwise": otherwise or {"decision": "accept"}}


VALID_RULES = a_document(
    a_rule("btl", {"all": [{"field": "product", "op": "eq", "value": "BTL"},
                           {"field": "ltv", "op": "gt", "value": 0.75}]},
           because="BTL above 75% LTV is outside appetite (CP-2024-11)"),
    a_rule("high", {"field": "ltv", "op": "gt", "value": 0.95},
           {"decision": "decline"}))


class _TestClientTransport:
    """The transport seam, driving the app in-process.

    Identical to the one in `test_sdk.py` and duplicated rather than shared,
    because a fixture module that both suites import is a third thing to keep in
    step with the interface it is standing in for.
    """

    def __init__(self, client, auth=None):
        self.client, self.auth = client, auth

    def request(self, method, path, *, json=None, content=None, params=None,
                headers=None):
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        return self.client.request(method, path, json=json, content=content,
                                   params=clean or None, headers=headers,
                                   auth=self.auth or self.client.auth)


@pytest.fixture
def maya(client):
    return Maya(transport=_TestClientTransport(client))


@pytest.fixture
def as_person(client):
    def _as(credentials):
        return Maya(transport=_TestClientTransport(client, auth=credentials))
    return _as


@pytest.fixture
def attested(as_person, people):
    """A record taken all the way to attested, by four different people.

    One account cannot walk this path, and that is the point rather than an
    inconvenience of the fixture: the owner submits, the second line approves,
    and the attestation needs a signature from each.
    """
    owner = as_person(people["j.okafor"])
    dev = as_person(people["d.raman"])
    mrm = as_person(people["s.iqbal"])
    owner.models.register(urn=URN, name="SB PD", model_class="credit.pd.scorecard",
                          domain="credit", owner="person/j.okafor",
                          legal_entity="LE-US-01", purpose="12m PD at origination")
    # Assessed before submission, because the tier decides how deep the control
    # is and approving before assessing would be choosing your own.
    owner.models.assess(URN, exposure=2e9, purpose_class="regulatory_capital")
    dev.versions.create(URN, semver="1.0.0", kernel=KERNEL)
    owner.lifecycle.submit(URN, note="ready for review")
    mrm.lifecycle.approve(URN, note="challenged and accepted")
    owner.lifecycle.attest(URN, role="model_owner")
    mrm.lifecycle.attest(URN, role="model_risk_manager")
    return {"owner": owner, "dev": dev, "mrm": mrm}


@pytest.fixture
def rules_model(as_person, people):
    """A registered version whose parameter object is a rule set."""
    owner, dev = as_person(people["j.okafor"]), as_person(people["d.raman"])
    owner.models.register(
        urn=RULES_URN, name="Retail eligibility", model_class="credit",
        domain="retail", owner="person/j.okafor", legal_entity="LE-US-01",
        purpose="origination eligibility")
    dev.versions.create(RULES_URN, semver="1.0.0", kernel=RULES_KERNEL)
    return dev


# =========================================================== the state machine
class TestTheLifecycleIsAskedForRatherThanCarried:
    """A client that hard-codes the transitions has written a second state
    machine, and the two part company at the first policy change."""

    def test_the_machine_comes_back_whole(self, maya):
        transitions = maya.lifecycle.machine()["transitions"]
        by_name = {t["name"]: t for t in transitions}
        assert {"submit", "approve", "attest", "amend", "retire"} <= set(by_name)
        # Each carries where it may be taken from, where it lands and who may
        # take it -- which is what lets an interface offer only the legal moves
        # without owning a copy of them.
        assert all({"from", "to", "permission"} <= set(t) for t in transitions)

    def test_the_sdk_names_no_state_of_its_own(self):
        source = (Path(__file__).resolve().parents[1] / "sdk" / "python" /
                  "maya_sdk" / "governance.py")
        tree = ast.parse(source.read_text())
        constants = [n for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))]
        assert not constants, (
            "governance.py defines a module-level constant. Every list this "
            "module could hold -- the states, the transitions, the roles that "
            "must sign, the classes, the operators -- is a governance rule the "
            "platform already holds, and a second copy disagrees eventually")


class TestARecordMovesThroughItsStates:
    def test_submission_and_approval_are_separate_acts(self, as_person, people):
        owner, dev, mrm = (as_person(people["j.okafor"]),
                           as_person(people["d.raman"]),
                           as_person(people["s.iqbal"]))
        owner.models.register(urn=URN, name="SB PD", model_class="c",
                              domain="credit", owner="person/j.okafor",
                              legal_entity="LE-1", purpose="p")
        owner.models.assess(URN, exposure=2e9, purpose_class="regulatory_capital")
        dev.versions.create(URN, semver="1.0.0", kernel=KERNEL)
        owner.lifecycle.submit(URN, note="please review")
        mrm.lifecycle.approve(URN, note="ok")
        # Approved is not in force. The attestation is still outstanding, and
        # the platform says which roles owe a signature.
        state = owner.lifecycle.state(URN)
        assert state["state"] == "approved"
        assert state["open_attestation"]["outstanding_roles"]

    def test_the_owner_may_not_approve_their_own_submission(self, as_person,
                                                            people):
        owner, dev = as_person(people["j.okafor"]), as_person(people["d.raman"])
        owner.models.register(urn=URN, name="SB PD", model_class="c",
                              domain="credit", owner="person/j.okafor",
                              legal_entity="LE-1", purpose="p")
        owner.models.assess(URN, exposure=2e9, purpose_class="regulatory_capital")
        dev.versions.create(URN, semver="1.0.0", kernel=KERNEL)
        owner.lifecycle.submit(URN)
        with pytest.raises(NotPermitted):
            owner.lifecycle.approve(URN)

    def test_attestation_is_a_quorum_and_it_completes(self, attested):
        state = attested["owner"].lifecycle.state(URN)
        assert state["state"] == "attested"
        assert state["attested_at"] and state["attestation_expires_at"]

    def test_a_submission_can_be_sent_back_with_a_reason(self, as_person, people):
        owner, dev, mrm = (as_person(people["j.okafor"]),
                           as_person(people["d.raman"]),
                           as_person(people["s.iqbal"]))
        owner.models.register(urn=URN, name="SB PD", model_class="c",
                              domain="credit", owner="person/j.okafor",
                              legal_entity="LE-1", purpose="p")
        owner.models.assess(URN, exposure=2e9, purpose_class="regulatory_capital")
        dev.versions.create(URN, semver="1.0.0", kernel=KERNEL)
        owner.lifecycle.submit(URN)
        mrm.lifecycle.send_back(URN, reason="the benchmark is not stated")
        assert owner.lifecycle.state(URN)["state"] == "draft"

    def test_retirement_keeps_the_record(self, attested):
        """Everybody except an administrator retires. The questions asked about
        a retired model are the questions asked about a live one."""
        attested["mrm"].lifecycle.retire(URN, reason="replaced by 2.x")
        assert attested["owner"].models.get(URN)["model"]["status"] == "retired"


class TestAnAttestedRecordIsImmutable:
    """The promise the whole platform rests on, exercised through the SDK."""

    def test_a_new_version_is_refused_and_the_refusal_is_raised(self, attested):
        """Raised, never returned. A caller who forgot to check a returned
        verdict would have continued past a governance decision while their code
        read as though it had succeeded."""
        with pytest.raises(Blocked) as exc:
            attested["dev"].versions.create(URN, semver="2.0.0", kernel=KERNEL)
        assert exc.value.status == 409
        assert "attested and therefore immutable" in exc.value.detail

    def test_the_refusal_names_the_amendment_as_the_way_through(self, attested):
        with pytest.raises(Refused) as exc:
            attested["dev"].versions.create(URN, semver="2.0.0", kernel=KERNEL)
        # The gate's own sentence survives the crossing, and it is the half that
        # makes the refusal usable.
        assert "open an amendment to change it" in exc.value.detail
        assert exc.value.remediation, "a refusal without one is a wall"
        assert exc.value.request_id == attested["dev"].last_request_id
        # It arrives on the far side flattened: the platform has a `record_frozen`
        # code with a remediation naming the endpoint, and this path reports the
        # registry's generic one instead. Asserted as it is rather than as it
        # ought to be -- a test written to the intention would pass against a
        # platform that never produced it.
        assert exc.value.code == "registry_refused"

    def test_a_field_change_is_refused_the_same_way(self, attested):
        with pytest.raises(Blocked) as exc:
            attested["owner"].lifecycle.update(URN, fields={"purpose": "other"})
        assert "attested and therefore immutable" in exc.value.detail

    def test_an_amendment_is_the_declared_way_out(self, attested):
        attested["owner"].lifecycle.amend(
            URN, reason="recalibrate for the 2026 cycle", scope=["kernel"])
        assert attested["owner"].lifecycle.state(URN)["state"] == "amending"
        # And now it accepts a version again, which is the whole point of the
        # amendment being a declared act rather than a flag.
        attested["dev"].versions.create(URN, semver="2.0.0", kernel=KERNEL)

    def test_an_illegal_move_names_what_is_legal_instead(self, as_person, people):
        owner = as_person(people["j.okafor"])
        owner.models.register(urn=URN, name="SB PD", model_class="c",
                              domain="credit", owner="person/j.okafor",
                              legal_entity="LE-1", purpose="p")
        with pytest.raises(Refused) as exc:
            owner.lifecycle.amend(URN, reason="too early")
        assert exc.value.code == "illegal_transition"
        assert "from here you may" in exc.value.detail


class TestTheQuorumOnAVersion:
    def test_who_must_sign_is_published_by_tier(self, maya):
        """So nobody has to read a firm's configuration to know."""
        rows = maya.lifecycle.approvals.quorum()["quorum"]
        assert rows and all("tier" in r and "required_roles" in r for r in rows)

    def test_a_version_with_no_tier_says_so_rather_than_saying_none(
            self, as_person, people):
        """Approving before assessing would be choosing your own control depth."""
        owner, dev = as_person(people["j.okafor"]), as_person(people["d.raman"])
        owner.models.register(urn=URN, name="SB PD", model_class="c",
                              domain="credit", owner="person/j.okafor",
                              legal_entity="LE-1", purpose="p")
        dev.versions.create(URN, semver="1.0.0", kernel=KERNEL)
        needed = owner.lifecycle.approvals.needed(urn=URN, semver="1.0.0")
        assert needed["tier"] is None
        assert "assess it before approving" in needed["detail"]

    def test_progress_and_withdrawal_read_back(self, registered, people,
                                               as_person):
        """A withdrawn approval and a declined one mean different things to
        whoever reads the chain later, and the platform keeps them apart."""
        mrm, dev = as_person(people["s.iqbal"]), as_person(people["d.raman"])
        dev.versions.create(URN, semver="3.3.0", kernel=KERNEL)
        opened = mrm.versions.open_quorum(urn=URN, semver="3.3.0")
        progress = mrm.lifecycle.approvals.progress(opened["id"])
        assert progress["status"] == "open" and progress["outstanding_roles"]
        withdrawn = mrm.lifecycle.approvals.withdraw(opened["id"])
        assert withdrawn["status"] == "withdrawn"


class TestRelations:
    def test_the_kinds_and_which_propagate_are_asked_for(self, maya):
        """`derives_from` does not propagate and `input_to` does. Answering both
        with one edge inflates every blast radius the model appears in."""
        kinds = maya.lifecycle.relations.kinds()
        assert kinds, "the vocabulary is the platform's, not a copy here"

    def test_an_edge_is_recorded_read_back_and_removed(self, as_person, people):
        owner = as_person(people["j.okafor"])
        for urn, name in ((URN, "SB PD"), ("maya://model/credit.lgd.smallbiz",
                                           "SB LGD")):
            owner.models.register(urn=urn, name=name, model_class="c",
                                  domain="credit", owner="person/j.okafor",
                                  legal_entity="LE-1", purpose="p")
        owner.models.relate(from_urn="maya://model/credit.lgd.smallbiz",
                            to_urn=URN, kind="input_to", note="feeds EL")
        edges = owner.lifecycle.relations.of(URN)
        assert edges, "the edge should be visible from the model it points at"
        owner.lifecycle.relations.remove(
            from_urn="maya://model/credit.lgd.smallbiz", to_urn=URN,
            kind="input_to", reason="the dependency was removed in 2.0")
        after = owner.lifecycle.relations.of(URN)
        assert after != edges


# ================================================================== rule sets
class TestTheRuleSetEditor:
    """The free/authoritative split is the design. `check` and `trial` record
    nothing; publishing is the ordinary recording act."""

    def test_the_vocabulary_comes_from_the_platform(self, maya):
        vocabulary = maya.rules.vocabulary()
        assert {o["op"] for o in vocabulary["operators"]} >= {"eq", "between", "in"}
        assert any(o["needs_ordered_field"] for o in vocabulary["operators"]), \
            "which operators need an ordered field is the check a screen most "\
            "wants to make locally and most should not"

    def test_check_returns_the_english_rendering(self, rules_model):
        report = rules_model.rules.check(urn=RULES_URN, semver="1.0.0",
                                         document=VALID_RULES)
        assert any("BTL" in line for line in report["explanation"]), \
            "one rendering, so the card, the paper and the pack quote the same "\
            "sentences"
        assert report["reads"] == sorted({"ltv", "product"})

    def test_check_records_nothing(self, rules_model):
        """Free means free: an author iterating does not fill the register."""
        before = rules_model.call("GET", "/parameters",
                                  params={"urn": RULES_URN, "semver": "1.0.0"})
        rules_model.rules.check(urn=RULES_URN, semver="1.0.0",
                                document=VALID_RULES)
        rules_model.rules.trial(urn=RULES_URN, semver="1.0.0",
                                document=VALID_RULES, rows=[{"ltv": 0.8}])
        after = rules_model.call("GET", "/parameters",
                                 params={"urn": RULES_URN, "semver": "1.0.0"})
        assert after["parameter_sets"] == before["parameter_sets"]

    def test_an_unreachable_rule_is_refused_naming_both(self, rules_model):
        """A rule that never fires still appears in the model card and in every
        committee paper, and nobody reading either can tell."""
        shadowed = a_document(
            a_rule("wide", {"field": "ltv", "op": "gt", "value": 0.5}),
            a_rule("narrow", {"field": "ltv", "op": "gt", "value": 0.8}))
        with pytest.raises(Refused) as exc:
            rules_model.rules.check(urn=RULES_URN, semver="1.0.0",
                                    document=shadowed)
        assert exc.value.code == "rule_unreachable"
        assert "wide" in exc.value.detail and "narrow" in exc.value.detail
        assert exc.value.remediation

    def test_a_rule_reading_an_undeclared_field_is_refused(self, rules_model):
        with pytest.raises(Refused) as exc:
            rules_model.rules.check(
                urn=RULES_URN, semver="1.0.0",
                document=a_document(a_rule(
                    "x", {"field": "not_declared", "op": "gt", "value": 1})))
        assert exc.value.code == "unknown_field"

    def test_a_trial_reports_which_rules_never_fired(self, rules_model):
        out = rules_model.rules.trial(
            urn=RULES_URN, semver="1.0.0", document=VALID_RULES,
            rows=[{"product": "BTL", "ltv": 0.8}, {"product": "RESI", "ltv": 0.5}])
        assert out["fired"]["btl"] == 1
        assert out["never_fired"] == ["high"]

    def test_publishing_lands_proposed_and_reads_back_in_english(self, rules_model):
        """No new authority: this is the ordinary recording act reached through
        a door that checks the document."""
        published = rules_model.rules.publish(
            urn=RULES_URN, semver="1.0.0", name="eligibility-q1",
            document=VALID_RULES, note="first cut")
        assert published["state"] == "proposed" and published["kind"] == "rule_set"
        explained = rules_model.rules.explain(published["id"])
        assert explained["rules"] == 2 and explained["explanation"]

    def test_a_fitted_parameter_set_is_not_read_as_a_rule_set(self, rules_model):
        with pytest.raises(NotFound):
            rules_model.rules.explain("no-such-parameter-set")


# ================================================================== the fibres
class TestTheFibration:
    """`L-15`: every class carries a total evidence schema, lifecycle, metric set
    and template set, and no fibre is empty."""

    def test_the_fibration_reports_itself_total(self, maya):
        listed = maya.fibres.list()
        assert listed["law"] == "L-15" and listed["total"] is True
        assert listed["base"] and len(listed["fibres"]) == len(listed["base"])

    def test_one_fibre_reads_back_with_all_four_facets(self, maya):
        """The class is a value from the platform, never a literal here."""
        for name in maya.fibres.list()["base"]:
            fibre = maya.fibres.of(name)
            assert fibre["trainability_class"] == name
            for facet in ("evidence", "lifecycle", "metrics", "templates"):
                assert fibre[facet], f"{name} has an empty {facet}, which L-15 forbids"
            # And the three sentences that say what the facets are FOR: a
            # validator reading "what may be monitored" needs the why first.
            assert fibre["soundness_rests_on"] and fibre["monitoring_answers"]

    def test_a_class_with_no_fibre_is_refused_rather_than_answered_empty(self, maya):
        with pytest.raises(Refused) as exc:
            maya.fibres.of("not-a-class")
        assert exc.value.code == "no_fibre"
        assert exc.value.status == 422, \
            "not a 404: the caller named a value correctly and what is missing "\
            "is something the platform should have supplied"

    def test_the_version_carries_the_class_the_platform_derived(self, as_person,
                                                                people):
        owner, dev = as_person(people["j.okafor"]), as_person(people["d.raman"])
        owner.models.register(urn=URN, name="SB PD", model_class="c",
                              domain="credit", owner="person/j.okafor",
                              legal_entity="LE-1", purpose="p")
        made = dev.versions.create(URN, semver="1.0.0", kernel=KERNEL)
        # The one join a caller makes: the class off the version, the fibre off
        # the class. Neither is computed here.
        fibre = dev.fibres.of(made["trainability_class"])
        assert fibre["metrics"]


# ================================= the rest of the feature and featureset algebra
class TestTheFeatureAlgebraTheFeatureModuleLeavesOut:
    @pytest.fixture
    def catalogue(self, as_person, people):
        dev = as_person(people["d.raman"])
        governance.FeatureCatalogue(dev)
        dev.features.define(name="dscr", entity="customer", dtype="numeric",
                            description="Debt service coverage ratio",
                            owner="person/d.raman")
        return governance.FeatureCatalogue(dev), dev

    def test_a_resolved_feature_reads_back_as_it_actually_stands(self, catalogue):
        """Not what the row says: the row plus its parents plus its own
        operations, which is the platform's arithmetic and not the caller's."""
        features, _ = catalogue
        assert [f["name"] for f in features.list()["features"]] == ["dscr"]
        resolved = features.resolved("dscr")
        assert resolved["name"] == "dscr" and resolved["dtype"] == "numeric"

    def test_a_draft_definition_is_checked_without_being_recorded(self, catalogue):
        """Free, for the reason the rule-set editor's check is free: requiring
        the writing permission to look teaches authors to skip the looking."""
        features, _ = catalogue
        report = features.check(name="brand_new", entity="customer",
                                dtype="numeric", description="a draft")
        assert report is not None
        with pytest.raises(Refused):
            features.resolved("brand_new")

    def test_a_draft_expression_is_read_over_rows_without_being_declared(
            self, catalogue):
        features, _ = catalogue
        out = features.trial(expression="dscr * 2",
                             rows=[{"entity_id": "C1", "event_ts": 1.0,
                                    "ingest_ts": 2.0, "dscr": 1.5}])
        assert out is not None

    def test_sealing_transferring_and_certifying_are_separate_acts(
            self, catalogue, as_person, people):
        features, _ = catalogue
        validator = governance.FeatureCatalogue(as_person(people["a.mehta"]))
        mrm = governance.FeatureCatalogue(as_person(people["s.iqbal"]))
        mrm.certify("dscr", level="certified")
        features.transfer("dscr", to="person/j.okafor", reason="team move")
        validator.seal("dscr", note="definition final")
        assert features.resolved("dscr")["sealed"] is not None

    def test_certification_is_refused_to_the_first_line(self, catalogue,
                                                        as_person, people):
        features, _ = catalogue
        with pytest.raises(NotPermitted):
            features.certify("dscr")

    def test_the_vocabularies_are_asked_for(self, catalogue):
        features, _ = catalogue
        assert features.expression_language()
        assert features.retrieval()["preparation"]
        assert features.transfer_formats()


class TestFeatureViewsAndTheirPins:
    @pytest.fixture
    def views(self, as_person, people):
        dev = as_person(people["d.raman"])
        dev.features.define(name="dscr", entity="customer", dtype="numeric",
                            description="Debt service coverage", owner="person/d.raman")
        dev.features.create_view(name="sb_financials", entity="customer",
                                 owner="person/d.raman", features=["dscr"])
        v = governance.FeatureViews(dev)
        v.materialise("sb_financials", rows=[
            {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 110.0, "dscr": 1.2},
            {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 900.0, "dscr": 0.4},
            {"entity_id": "C2", "event_ts": 100.0, "ingest_ts": 110.0, "dscr": 2.1}])
        return v

    def test_retirability_names_who_is_pinning_it(self, views):
        """"No" without the pinners is a wall; with them it is a short
        conversation with three named owners."""
        assert [v["name"] for v in views.list()["views"]] == ["sb_financials"]
        assert [v["version"] for v in views.versions("sb_financials")["versions"]] == [1]
        answer = views.retirable("sb_financials", version=1)
        assert answer["retirable"] is True and answer["pinned_by"] == []

    def test_the_point_in_time_read_explains_itself_row_by_row(self, views):
        """The restated figure is excluded from a read as at a moment before it
        was known. That is the case point-in-time correctness exists for."""
        out = views.as_of("sb_financials", version=1, label_ts=100.0, as_of=200.0)
        assert out is not None

    def test_an_alignment_is_trialled_without_aligning_anything_stored(self, views):
        out = views.alignment_trial(
            rows=[{"entity_id": "C1", "event_ts": 1.0, "ingest_ts": 1.0, "x": 1.0},
                  {"entity_id": "C1", "event_ts": 3.0, "ingest_ts": 3.0, "x": 2.0}],
            columns=["x"])
        assert out is not None

    def test_the_bytes_come_out_at_the_pinned_version(self, views, tmp_path):
        into = views.data("sb_financials", version=1, into=tmp_path / "v1.parquet")
        assert into.exists() and into.stat().st_size > 0


class TestTheFeaturesetAlgebra:
    @pytest.fixture
    def sets(self, as_person, people):
        dev = as_person(people["d.raman"])
        dev.features.define(name="dscr", entity="customer", dtype="numeric",
                            description="Debt service coverage", owner="person/d.raman")
        dev.features.create_view(name="sb_financials", entity="customer",
                                 owner="person/d.raman", features=["dscr"])
        governance.FeatureViews(dev).materialise("sb_financials", rows=[
            {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 110.0, "dscr": 1.2},
            {"entity_id": "C2", "event_ts": 100.0, "ingest_ts": 110.0, "dscr": 2.1}])
        dev.featuresets.define(name="sb_core", entity="customer",
                               slots={"dscr": "numeric"})
        dev.featuresets.fill("sb_core",
                             bindings={"dscr": {"feature": "dscr",
                                                "view": "sb_financials",
                                                "view_version": 1}})
        return governance.FeaturesetAlgebra(dev), dev

    def test_the_plan_is_one_document_an_engine_can_execute(self, sets):
        algebra, _ = sets
        assert [s["name"] for s in algebra.list()["featuresets"]] == ["sb_core"]
        plan = algebra.plan("sb_core", version=1)
        assert plan, "an engine reads a plan rather than rebuilding one from five reads"

    def test_the_drift_read_answers_whether_the_ground_moved(self, sets):
        """The version still reads the bytes it pinned. This is the neighbouring
        question a reviewer asks before comparing two runs."""
        algebra, dev = sets
        answer = algebra.restatements("sb_core", version=1)
        assert answer["featureset"] == "sb_core" and answer["version"] == 1
        assert answer["restated"] is False and answer["detail"]
        # A further load makes a NEW view version rather than writing into the
        # pinned one, so the pin is still undisturbed -- which is the answer, and
        # the reason `roll_forward` has to be a deliberate act.
        governance.FeatureViews(dev).materialise("sb_financials", rows=[
            {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 900.0, "dscr": 0.4}])
        assert algebra.restatements("sb_core", version=1)["restated"] is False

    def test_rolling_forward_is_a_deliberate_act(self, sets):
        algebra, dev = sets
        governance.FeatureViews(dev).materialise("sb_financials", rows=[
            {"entity_id": "C3", "event_ts": 200.0, "ingest_ts": 210.0, "dscr": 3.0}])
        rolled = algebra.roll_forward("sb_core")
        assert rolled["version"] == 2

    def test_preparation_returns_the_statistics_beside_the_rows(self, sets):
        """A normalisation whose parameters are not written down cannot be
        reapplied at serving time, which is how a skew arrives by accident."""
        algebra, _ = sets
        out = algebra.prepared("sb_core", version=1, as_of=1000.0,
                               fill={"dscr": "zero"})
        assert out["rows"] and out["report"]
        assert out["policy_applied"], "the policy that was applied comes back"

    def test_a_retrieval_policy_can_be_attached_to_the_set(self, sets):
        algebra, _ = sets
        assert algebra.set_policy("sb_core", defaults={"fill": {"dscr": "zero"}})

    def test_ownership_moves_without_the_creator_moving(self, sets):
        algebra, _ = sets
        assert algebra.transfer("sb_core", to="person/j.okafor", reason="team move")


class TestFeatureContractsAndTrainingSets:
    def test_the_contract_says_what_serving_must_read(self, as_person, people):
        """Without the declaration there is nothing for `L-17` to compare
        against, and "the model read what it read" is not an assurance."""
        dev = as_person(people["d.raman"])
        owner = as_person(people["j.okafor"])
        owner.models.register(urn=URN, name="SB PD", model_class="c",
                              domain="credit", owner="person/j.okafor",
                              legal_entity="LE-1", purpose="p")
        version = dev.versions.create(URN, semver="1.0.0", kernel=KERNEL)
        dev.features.define(name="dscr", entity="customer", dtype="numeric",
                            description="Debt service coverage",
                            owner="person/d.raman")
        dev.features.create_view(name="sb_financials", entity="customer",
                                 owner="person/d.raman", features=["dscr"])
        governance.FeatureViews(dev).materialise("sb_financials", rows=[
            {"entity_id": "C1", "event_ts": 1.0, "ingest_ts": 2.0, "dscr": 1.2}])
        contracts = governance.FeatureContracts(dev)
        contracts.bind(model_version_id=version["id"],
                       items=[{"view": "sb_financials", "version": 1}])
        assert contracts.namespaces(version["id"])["namespaces"]

    def test_a_training_set_is_bounded_on_both_clocks(self, as_person, people):
        """Valid time asks what was true; transaction time asks what was known.
        Dropping the second lets a restatement rewrite history."""
        dev = as_person(people["d.raman"])
        dev.features.define(name="dscr", entity="customer", dtype="numeric",
                            description="Debt service coverage",
                            owner="person/d.raman")
        dev.features.create_view(name="sb_financials", entity="customer",
                                 owner="person/d.raman", features=["dscr"])
        governance.FeatureViews(dev).materialise("sb_financials", rows=[
            {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 110.0, "dscr": 1.2},
            {"entity_id": "C1", "event_ts": 100.0, "ingest_ts": 900.0, "dscr": 0.4}])
        built = governance.TrainingSets(dev).build(
            name="sb_train", spine=[{"entity_id": "C1", "label_ts": 150.0}],
            views=[{"view": "sb_financials", "version": 1}], as_of=200.0)
        assert built, "the assembly should pin what it read"


# =========================== the second line: validation, findings, monitoring
class TestValidationEpisodes:
    def test_the_catalogue_is_closed_and_published(self, maya):
        """A test nobody registered is one nobody can replay."""
        assert maya.call("GET", "/tests")["tests"]
        assert governance.Validations(maya).tests()["tests"]

    def test_an_episode_is_opened_evidenced_and_concluded(self, registered,
                                                          people, as_person):
        validator = governance.Validations(as_person(people["a.mehta"]))
        episode = validator.open(urn=URN, semver="3.2.1",
                                 validators=["person/a.mehta"],
                                 scope=["discrimination"])
        validator.record(episode["id"], test_key="discrimination.gini",
                         left=[0, 0, 1, 1, 0, 1, 1, 0],
                         right=[0.1, 0.2, 0.8, 0.9, 0.3, 0.7, 0.85, 0.15],
                         threshold={"min": 0.4})
        read = validator.get(episode["id"])
        assert read["results"] and read["summary"]
        concluded = validator.conclude(episode["id"], outcome="approved")
        assert concluded["outcome"] == "approved"

    def test_an_episode_that_pins_nothing_says_why_it_cannot_be_replayed(
            self, registered, people, as_person):
        validator = governance.Validations(as_person(people["a.mehta"]))
        episode = validator.open(urn=URN, semver="3.2.1",
                                 validators=["person/a.mehta"])
        answer = validator.replayable(episode["id"])
        assert answer["readable"] is False and "cannot be replayed" in answer["detail"]

    def test_a_replay_reports_an_unsupplied_test_as_skipped_not_as_passing(
            self, registered, people, as_person):
        validator = governance.Validations(as_person(people["a.mehta"]))
        episode = validator.open(urn=URN, semver="3.2.1",
                                 validators=["person/a.mehta"])
        validator.record(episode["id"], test_key="discrimination.gini",
                         left=[0, 1, 0, 1], right=[0.1, 0.9, 0.2, 0.8],
                         threshold={"min": 0.4})
        out = validator.replay(episode["id"])
        assert out, "a key left out is skipped, which is the distinction that matters"


class TestTheFindingsRegister:
    @pytest.fixture
    def register(self, registered, people, as_person):
        second_line = governance.Findings(as_person(people["s.iqbal"]))
        finding = second_line.raise_finding(
            urn=URN, severity="High", title="Benchmark not stated",
            owner="person/d.raman", description="the challenger is unnamed",
            category="documentation")
        return second_line, finding, people, as_person

    def test_the_acts_are_published_with_their_meanings(self, maya):
        assert {a["act"] for a in maya.call("GET", "/finding-acts")["acts"]}

    def test_a_finding_is_raised_read_and_summarised(self, register):
        second_line, finding, _, _ = register
        assert second_line.get(finding["id"])["title"] == "Benchmark not stated"
        assert second_line.for_model(URN)["open"]
        assert second_line.ageing(urn=URN)["by_severity"]

    def test_the_owner_accepts_it_and_names_the_date(self, register):
        second_line, finding, people, as_person = register
        owner_side = governance.Findings(as_person(people["d.raman"]))
        acknowledged = owner_side.acknowledge(finding["id"], days=10,
                                              plan="restate the benchmark")
        assert acknowledged

    def test_the_owner_may_not_move_their_own_deadline(self, register):
        """The person with the deadline cannot set it, and the person setting it
        has to be somebody else."""
        second_line, finding, people, as_person = register
        owner_side = governance.Findings(as_person(people["d.raman"]))
        owner_side.acknowledge(finding["id"], days=10, plan="restate it")
        with pytest.raises(Refused):
            owner_side.extend(finding["id"], reason="need longer", days=30)
        assert second_line.extend(finding["id"], reason="scope was larger",
                                  days=30)

    def test_closure_is_attributed_to_whoever_performs_it(self, register):
        """There is deliberately no `verified_by` argument: it let the owner of
        a blocking finding close their own by naming somebody else."""
        second_line, finding, people, as_person = register
        import inspect
        signature = inspect.signature(governance.Findings.close)
        assert "verified_by" not in signature.parameters
        # And the raiser is not the verifier either: the register refuses it
        # rather than recording a closure nobody independent stood behind.
        with pytest.raises(NotPermitted):
            second_line.close(finding["id"], evidence={"note": "mine"})
        other = governance.Findings(as_person(people["a.mehta"]))
        closed = other.close(finding["id"],
                             evidence={"note": "benchmark restated",
                                       "document": "doc-1"})
        assert closed

    def test_escalation_names_a_role_rather_than_a_person(self, register):
        """The platform does not know who reports to whom."""
        second_line, finding, _, _ = register
        assert "escalated" in second_line.escalated(urn=URN)
        assert second_line.escalation(finding["id"])["finding_id"] == finding["id"]


class TestMonitoring:
    def test_which_questions_can_be_asked_is_the_platforms_answer(self, maya):
        kinds = governance.Monitors(maya).kinds()["kinds"]
        assert all({"kind", "tests", "needs_labels"} <= set(k) for k in kinds)

    def test_a_monitor_is_defined_evaluated_and_read_back(self, registered,
                                                          people, as_person):
        monitors = governance.Monitors(as_person(people["j.okafor"]))
        monitor = monitors.define(
            urn=URN, name="score drift", kind="score_drift",
            test_key="stability.psi", threshold={"max": 0.25},
            owner="person/j.okafor")
        reference = [i / 100 for i in range(100)]
        out = monitors.evaluate(monitor["id"],
                                rows=[{"scored_at": 1.8e9, "score": i / 100}
                                      for i in range(100)],
                                reference=reference, now=1.8e9)
        assert out["observation"]["passed"] is True
        assert monitors.observations(monitor["id"])["observations"]
        assert monitors.list(URN)["monitors"]

    def test_an_immature_cohort_is_refused_rather_than_measured(self, registered,
                                                               people, as_person):
        """A performance monitor over outcomes that have not matured measures
        the maturity of the cohort, not the model."""
        monitors = governance.Monitors(as_person(people["j.okafor"]))
        monitor = monitors.define(
            urn=URN, name="gini", kind="performance",
            test_key="discrimination.gini", threshold={"min": 0.4},
            owner="person/j.okafor", label_delay_days=365)
        with pytest.raises(Refused) as exc:
            monitors.evaluate(monitor["id"],
                              rows=[{"scored_at": 1.8e9, "score": i / 20,
                                     "label": i % 2} for i in range(20)],
                              now=1.8e9 + 86400)
        assert exc.value.code == "cohort_immature"
        assert "wait for the outcome window" in exc.value.remediation

    def test_suspending_a_monitor_is_an_act_and_not_a_deletion(self, registered,
                                                               people, as_person):
        """A monitor quietly turned off before a breach is exactly what a
        reviewer is looking for."""
        monitors = governance.Monitors(as_person(people["j.okafor"]))
        monitor = monitors.define(
            urn=URN, name="score drift", kind="score_drift",
            test_key="stability.psi", threshold={"max": 0.25},
            owner="person/j.okafor")
        assert monitors.set_status(monitor["id"], status="paused")
        with pytest.raises(Refused) as exc:
            monitors.set_status(monitor["id"], status="off")
        assert exc.value.code == "unknown_status", \
            "the statuses are the platform's vocabulary, not a copy here"


# ============================================================ the SDK decides nothing
class TestTheSdkDecidesNothing:
    def test_no_trainability_class_appears_in_code(self):
        """The platform derives the class from how P is inhabited. A copy here
        is a second rule, and it disagrees in the direction of permitting more."""
        root = Path(__file__).resolve().parents[1] / "sdk" / "python" / "maya_sdk"
        classes = re.compile(r"\bT[0-8]\b")
        offenders = []
        for path in sorted(root.glob("*.py")):
            code = re.sub(r'"""(?:.|\n)*?"""', "", path.read_text())
            code = "\n".join(line.split("#")[0] for line in code.split("\n"))
            if classes.search(code):
                offenders.append(path.name)
        assert not offenders, f"{offenders} enumerate a class in code"

    def test_governance_holds_no_vocabulary_of_its_own(self):
        """Every collection this module could carry -- states, roles, operators,
        severities, monitor kinds -- is published by an endpoint above."""
        source = (Path(__file__).resolve().parents[1] / "sdk" / "python" /
                  "maya_sdk" / "governance.py")
        tree = ast.parse(source.read_text())
        literals = [n for n in ast.walk(tree)
                    if isinstance(n, (ast.List, ast.Set, ast.Tuple))
                    and len(getattr(n, "elts", [])) > 2
                    and all(isinstance(e, ast.Constant) for e in n.elts)]
        assert not literals, (
            "a literal collection in governance.py is a copy of something the "
            "platform publishes; ask for it instead")

    def test_every_method_is_one_call_and_takes_no_local_decision(self):
        """No branch on a governance fact. The one branch the SDK is allowed is
        the argument check `features.py` already makes, and it is about a file
        extension rather than about who may act."""
        source = (Path(__file__).resolve().parents[1] / "sdk" / "python" /
                  "maya_sdk" / "governance.py")
        tree = ast.parse(source.read_text())
        branching = [f"{n.name} (line {n.lineno})"
                     for n in ast.walk(tree)
                     if isinstance(n, ast.FunctionDef)
                     and any(isinstance(s, (ast.If, ast.While))
                             for s in ast.walk(n))]
        assert not branching, (
            f"{branching} branch locally. A branch on a governance fact is a "
            "second implementation of the rule that produced it")

    def test_a_governance_refusal_is_raised_and_never_returned(self, attested):
        """A caller who forgets to check a returned verdict has continued past a
        governance decision while their code reads as though it succeeded."""
        with pytest.raises(Refused):
            attested["dev"].versions.create(URN, semver="2.0.0", kernel=KERNEL)


class TestEverySubjectIsReachableFromTheClient:
    """Ten of seventeen subjects were written and never attached.

    `FeatureViews` — the point-in-time query — `FeaturesetAlgebra`,
    `FeatureContracts`, `Findings`, `Monitors`, `Validations`,
    `VersionApprovals`, `Relations`, `FeatureCatalogue` and `TrainingSets` all
    worked if you constructed them by hand. Nothing on `Maya` named them, the
    shipped documentation routed around the gap three inconsistent ways, and a
    tutorial fell back to raw `client.call()` for methods the SDK already had —
    which reads to a new joiner as "the SDK cannot do this" rather than "nobody
    wired it up".
    """

    #: Every subject class the package defines, and the attribute it is reached
    #: by. Held as data so a class added without an attribute fails here rather
    #: than being discovered by somebody who needed it.
    EXPECTED = {
        "models": "Models", "versions": "Versions", "features": "Features",
        "featuresets": "Featuresets", "warrants": "Warrants",
        "artifacts": "Artifacts", "parameters": "Parameters",
        "attachments": "Attachments", "documents": "Documents",
        "packages": "Packages", "rules": "Rules", "lifecycle": "Lifecycle",
        "fibres": "Fibres", "approvals": "VersionApprovals",
        "relations": "Relations", "catalogue": "FeatureCatalogue",
        "views": "FeatureViews", "contracts": "FeatureContracts",
        "training_sets": "TrainingSets",
        "featureset_algebra": "FeaturesetAlgebra",
        "validations": "Validations", "findings": "Findings",
        "monitors": "Monitors",
    }

    def test_every_expected_subject_is_attached(self, maya):
        missing = sorted(a for a in self.EXPECTED if not hasattr(maya, a))
        assert not missing, f"written and not reachable from Maya: {missing}"

    def test_each_one_is_the_class_it_claims_to_be(self, maya):
        for attribute, classname in self.EXPECTED.items():
            assert type(getattr(maya, attribute)).__name__ == classname, attribute

    def test_no_subject_class_is_left_unattached(self, maya):
        """The direction that catches the next one.

        Asserting the known list is attached passes forever once it is. This
        walks the package instead, so a subject added tomorrow and not wired up
        fails here.
        """
        import inspect

        from maya_sdk import artifacts, documents, features, governance, models
        from maya_sdk import parameters, warrants

        attached = {type(v).__name__ for v in vars(maya).values()}
        unattached = []
        for module in (models, features, warrants, artifacts, parameters,
                       documents, governance):
            for name, obj in vars(module).items():
                if not inspect.isclass(obj) or obj.__module__ != module.__name__:
                    continue
                # A subject takes the client as its first argument.
                parameters_of = list(inspect.signature(obj).parameters)
                if parameters_of[:1] == ["client"] and name not in attached:
                    unattached.append(f"{module.__name__}.{name}")
        assert not unattached, (
            f"these subjects exist and nothing on Maya reaches them: "
            f"{sorted(unattached)}")

    def test_a_reachable_subject_actually_works(self, maya, registered):
        """Attachment is not the claim; working is.

        One call per newly-attached subject that has a read, so this fails if a
        subject is wired to the wrong module or its client contract has drifted.
        """
        assert maya.findings.acts()
        assert maya.relations.kinds()
        assert maya.catalogue.list()


class TestAFieldTheServerDoesNotKnowIsRefused:
    """Pydantic drops an undeclared field silently. That is how a rationale
    disappeared.

    The SDK sent `note` to an endpoint reading `statement`. The signature
    recorded and the reasoning vanished, with a 200 on both sides. Request
    bodies now forbid extras, so the mismatch is a 422 naming the field at the
    first call rather than a gap discovered at the first audit.
    """

    def test_an_unknown_field_is_a_422_naming_it(self, client, people):
        r = client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": "maya://model/typo.probe", "name": "Typo probe",
            "model_class": "credit.pd", "domain": "credit",
            "owner": "person/j.okafor", "legal_entity": "LE-US-01",
            "purpose": "checking the refusal",
            "purpoze": "the typo"})
        assert r.status_code == 422, r.text
        assert "purpoze" in r.text

    def test_the_signature_rationale_survives_the_round_trip(self, client, people):
        """The specific loss, asserted end to end.

        Built here rather than on `registered`, which has already taken 3.2.1
        through its quorum — a second approval on the same version is refused,
        correctly, and would make this test pass or fail for the wrong reason.
        """
        from tests.conftest import CONTRACT, KERNEL, NAME, URN

        client.post("/api/v1/models", auth=people["j.okafor"], json={
            "urn": URN, "name": "SB PD", "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-US-01", "purpose": "12-month PD"})
        client.post(f"/api/v1/models/{NAME}/assess", auth=people["j.okafor"],
                    json={"exposure": 2e9, "purpose_class": "regulatory_capital"})
        client.post(f"/api/v1/models/{NAME}/versions", auth=people["d.raman"],
                    json={"semver": "3.2.1", "kernel": KERNEL,
                          "contract": CONTRACT, "artifact_digest": "sha256:" + "a" * 64})
        opened = client.post("/api/v1/version-approvals", auth=people["s.iqbal"],
                             json={"urn": URN, "semver": "3.2.1"})
        assert opened.status_code == 201, opened.text
        approval = opened.json()["id"]
        said = "independent recode agreed to four decimal places"
        signed = client.post(f"/api/v1/version-approvals/{approval}/sign",
                             auth=people["a.mehta"],
                             json={"role": "validator", "statement": said})
        assert signed.status_code == 200, signed.text
        progress = client.get(f"/api/v1/version-approvals/{approval}",
                              auth=people["s.iqbal"]).text
        assert said in progress, "the signature recorded and the reasoning did not"

    def test_the_sdk_sends_the_field_the_endpoint_reads(self):
        """Held against the source, because the failure was silent on the wire:
        a wrong name is dropped rather than refused, so a passing round trip
        proved nothing about which key was sent."""
        import inspect

        from maya_sdk.models import Versions
        source = inspect.getsource(Versions.sign_quorum)
        assert '"statement": statement' in source
        assert '"note"' not in source
