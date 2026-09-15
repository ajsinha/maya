"""
MAYA — baseline import and compliance debt.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.

Adversarial review judged this the single most likely cause of total failure: on
import day 1,200 models arrive with no evidence, every gate fails, every
dashboard is red, and the programme dies in month seven.

TestGapsAreComputed and TestDebtIsNotBreach carry the design. The first because
declared gaps would produce a register in which every model has exactly two. The
second because a platform that renders baseline debt and a missed validation the
same colour is one nobody believes.
"""
import time

import pytest

from core.baseline import BASELINED, BaselineError, gaps
from core.registry import RegistryError

DAY = 86400.0

BATCH = [
    {"urn": "maya://model/legacy.pd.corporate", "name": "Corporate PD",
     "owner": "person/j.okafor", "legal_entity": "LE-US-01",
     "purpose": "PD for corporate lending", "domain": "credit", "tier": 1},
    {"urn": "maya://model/legacy.var.rates", "name": "Rates VaR",
     "owner": "", "legal_entity": "LE-UK-02", "purpose": "",
     "domain": "market", "tier": 2},
]


# =========================================================== gaps are computed
class TestGapsAreComputed:
    """Declared gaps produce a register where every model has exactly two."""

    def test_the_full_gap_list_is_published(self):
        described = gaps.describe()
        assert len(described) >= 10
        assert all(g["materiality"] for g in described)

    def test_a_bare_model_is_missing_almost_everything(self):
        found = gaps.find({"model": {"owner": "o", "purpose": "p", "tier": 1},
                           "versions": []})
        keys = {g.key for g in found}
        assert {"version", "tier"} & keys == {"version"}, "tier was present"
        assert {"validation", "monitoring", "documentation", "attestation"} <= keys

    def test_a_fully_governed_model_has_no_gaps(self):
        state = {
            "model": {"owner": "o", "purpose": "p", "tier": 1,
                      "legal_entity": "LE-US-01"},
            "versions": [{"artifact_digest": "sha256:" + "8" * 64, "contract": {"assumptions": []}}],
            "feature_contract": {"items": []}, "validations": [{"id": "v"}],
            "monitoring": {"monitors": 1}, "documents": [{"id": "d"}],
            "lifecycle": {"attested_at": 1.0},
            "attachments": [{"kind": "model_development_document",
                             "state": "accepted"}],
        }
        assert gaps.find(state) == []

    def test_an_importer_cannot_under_declare(self, baseline, registry):
        """The gaps come from the register, not from the import file."""
        result = baseline.import_models("legacy-inventory.csv", BATCH[:1])
        recorded = result["imported"][0]["debt"]
        assert "validation" in recorded and "monitoring" in recorded
        assert "version" in recorded


# ================================================================== importing
class TestImporting:
    def test_a_batch_is_imported_and_baselined(self, baseline, registry):
        result = baseline.import_models("legacy-inventory.csv", BATCH,
                                        actor="s.iqbal")
        assert result["models"] == 2 and result["debt_items"] > 0
        assert registry.get(BATCH[0]["urn"])["status"] == BASELINED

    def test_baselined_is_not_draft(self, baseline, registry):
        """The register must never imply that historical evidence was asserted."""
        baseline.import_models("csv", BATCH[:1])
        assert registry.get(BATCH[0]["urn"])["status"] == "baselined"

    def test_a_model_with_no_owner_carries_a_critical_gap(self, baseline, debts,
                                                          registry):
        baseline.import_models("csv", BATCH)
        model = registry.get(BATCH[1]["urn"])
        owner_debt = [d for d in debts.open_for(model["id"]) if d["gap_key"] == "owner"]
        assert owner_debt and owner_debt[0]["materiality"] == "Critical"

    def test_one_bad_row_does_not_stop_the_batch(self, baseline, registry):
        """1,199 models must not fail because of one."""
        batch = BATCH + [{"urn": BATCH[0]["urn"], "name": "duplicate"}]
        result = baseline.import_models("csv", batch)
        assert result["models"] == 2 and len(result["skipped"]) == 1
        assert "already in the register" in result["skipped"][0]["reason"]

    def test_an_empty_batch_is_refused(self, baseline):
        with pytest.raises(BaselineError, match="no models"):
            baseline.import_models("csv", [])

    def test_the_result_states_the_governance_position(self, baseline):
        result = baseline.import_models("csv", BATCH)
        assert "existing use is not blocked" in result["detail"]

    def test_expiry_is_longer_for_lower_tiers(self, baseline, debts, registry):
        baseline.import_models("csv", BATCH)
        tier1 = debts.open_for(registry.get(BATCH[0]["urn"])["id"])[0]
        tier2 = debts.open_for(registry.get(BATCH[1]["urn"])["id"])[0]
        assert tier2["expires_at"] > tier1["expires_at"], \
            "a Tier 1 model must close its gaps sooner"


# ============================================================ debt != breach
class TestTheCarveOutIsNarrowAndDeliberate:
    """`admitting_gaps` exists for this importer and nowhere else.

    An ordinary registration refuses a model with no owner, no purpose, no
    name or no legal entity — a blank `"   "` satisfies the route's own
    validation, so the check is at the service. The baseline register is the
    opposite case: a model that arrived from a spreadsheet without its
    evidence, whose missing owner is a **tracked gap** carrying a Critical
    debt item with an expiry date.

    Refusing those rows would leave the models off the register entirely,
    which is strictly worse — an ungoverned model that is recorded can be
    found and fixed; one that was never admitted cannot. So the flag moves
    where the absence is recorded, from a refusal to a dated obligation, and
    it does not skip a control.
    """

    def test_an_ordinary_registration_refuses_a_blank_stated_ground(
            self, registry):
        for field in ("owner", "legal_entity", "purpose", "name"):
            body = {"urn": f"maya://model/plain.{field}", "name": "N",
                    "model_class": "c", "domain": "credit", "owner": "person/x",
                    "legal_entity": "LE-1", "purpose": "p", "actor": "admin"}
            body[field] = "   "
            with pytest.raises(RegistryError, match=f"needs a {field}"):
                registry.register(**body)

    def test_the_importer_admits_them_and_records_the_debt(self, baseline,
                                                            debts, registry):
        out = baseline.import_models("csv", [{"urn": "maya://model/bare.one",
                                              "tier": 1}])
        assert out["models"] == 1, out.get("skipped")
        model = registry.get("maya://model/bare.one")
        assert model is not None, "the row was refused rather than admitted"
        keys = {d["gap_key"] for d in debts.open_for(model["id"])}
        assert {"owner", "purpose", "legal_entity"} <= keys, (
            f"admitted without recording the absence as debt: {sorted(keys)}")

    def test_a_missing_legal_entity_is_critical(self):
        """Not paperwork. Scope is applied by entity, so a model belonging to
        none is absent from every entity-scoped reader's estate, worklist and
        board pack — visible only to the unscoped."""
        found = gaps.find({"model": {"owner": "o", "purpose": "p", "tier": 1}})
        entity = [g for g in found if g.key == "legal_entity"]
        assert entity and entity[0].materiality == "Critical"


class TestDebtIsNotBreach:
    @pytest.fixture
    def imported(self, baseline, registry):
        baseline.import_models("csv", BATCH[:1])
        return registry.get(BATCH[0]["urn"])

    def test_debt_is_reported_separately_from_breach(self, debts, imported):
        status = debts.status(imported["id"])
        assert status["baselined"] is True
        assert status["debt_open"] > 0 and status["breached"] == 0

    def test_open_debt_raises_no_finding(self, debts, findings, imported):
        assert findings.open_for(imported["id"]) == []

    def test_debt_past_its_expiry_becomes_a_breach(self, debts, findings, imported):
        for item in debts.open_for(imported["id"]):
            debts.debts.set({"expires_at": time.time() - DAY}, id=item["id"])
        report = debts.reconcile(imported["id"], {"model": imported, "versions": []})
        assert report["breached"]
        raised = findings.open_for(imported["id"])
        assert raised and "Baseline debt expired" in raised[0]["title"]
        assert "now a breach rather than debt" in raised[0]["description"]

    def test_the_status_counts_overdue_before_it_is_reconciled(self, debts, imported):
        later = time.time() + 3000 * DAY
        assert debts.status(imported["id"], now=later)["overdue"] > 0


# ============================================================== burning down
class TestBurnDown:
    @pytest.fixture
    def imported(self, baseline, registry):
        baseline.import_models("csv", BATCH[:1])
        return registry.get(BATCH[0]["urn"])

    def test_debt_closes_when_the_evidence_arrives(self, debts, imported):
        """A measurement, not a self-report."""
        before = debts.status(imported["id"])["debt_open"]
        filled = {
            "model": {**imported, "owner": "o", "purpose": "p", "tier": 1},
            "versions": [{"artifact_digest": "sha256:" + "8" * 64,
                          "contract": {"assumptions": []}}],
            "validations": [{"id": "v"}], "monitoring": {"monitors": 1},
            "documents": [{"id": "d"}], "feature_contract": {"items": []},
            "lifecycle": {"attested_at": 1.0},
            "attachments": [{"kind": "model_development_document",
                             "state": "accepted"}],
        }
        report = debts.reconcile(imported["id"], filled)
        assert len(report["closed"]) == before and report["remaining"] == 0
        assert "the evidence arrived" in report["detail"]

    def test_nothing_closes_while_the_gap_remains(self, debts, imported):
        report = debts.reconcile(imported["id"],
                                 {"model": imported, "versions": []})
        assert report["closed"] == []

    def test_the_portfolio_reports_the_burn_down(self, baseline, debts, registry):
        baseline.import_models("csv", BATCH)
        before = baseline.portfolio()
        assert before["models_baselined"] == 2 and before["burn_down"] == 0.0

        model = registry.get(BATCH[0]["urn"])
        debts.reconcile(model["id"], {
            "model": {**model, "owner": "o", "purpose": "p", "tier": 1},
            "versions": [{"artifact_digest": "x", "contract": {"a": 1}}],
            "validations": [1], "monitoring": {"monitors": 1}, "documents": [1],
            "feature_contract": {"items": []}, "lifecycle": {"attested_at": 1.0}})
        after = baseline.portfolio()
        assert after["burn_down"] > 0.0
        assert "closed" in after["detail"]

    def test_a_debt_item_can_carry_a_dated_plan(self, debts, imported):
        item = debts.open_for(imported["id"])[0]
        planned = debts.plan_for(item["id"], "Validation scheduled 2026-Q3")
        assert planned["plan"] == "Validation scheduled 2026-Q3"

    def test_an_empty_plan_is_refused(self, debts, imported):
        item = debts.open_for(imported["id"])[0]
        with pytest.raises(BaselineError, match="dated plan"):
            debts.plan_for(item["id"], "   ")

    def test_unplanned_debt_is_counted(self, debts, imported):
        assert debts.status(imported["id"])["unplanned"] > 0

    def test_the_same_gap_is_not_recorded_twice(self, debts, imported):
        with pytest.raises(BaselineError, match="already open"):
            debts.raise_debt(imported["id"], "validation", "person/o", tier=1)

    def test_an_unknown_gap_is_refused(self, debts, imported):
        with pytest.raises(BaselineError, match="unknown gap"):
            debts.raise_debt(imported["id"], "vibes", "person/o")
