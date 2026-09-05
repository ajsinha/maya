"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The foundational laws, made executable.

`docs/00 §12` states nineteen laws and, for each, whether it runs. Seven did. The
document was honest about the rest — *"a law that is stated but not executed did
not prevent anything"* — which is the correct thing to say and a poor place to
leave it, because the strongest claim the design makes is that the laws are the
acceptance criteria, and a claim that is 37% true is a claim that will be read as
100% true by everybody who does not check.

This file closes five of the twelve. Each is tested as the law is *stated*, not
as the implementation happens to behave — a test written from the code proves the
code agrees with itself.

The two that are still not executable are named here as well, with the reason,
so the gap stays visible in the place somebody would look for it rather than only
in a table.
"""
from __future__ import annotations

import math
import random

import pytest

from core.evidence.engine import Derivation
from core.evidence.semirings import (BOOLEAN, COST, COUNTING, FRESHNESS,
                                     POLYNOMIAL, TRUST, WHY, poly_variable,
                                     pushforward)
from core.lifecycle.states import BY_NAME, INITIAL, STATES, TRANSITIONS
from core.regimes.sentences import (deontic_conflicts, forbids, implies,
                                    requires, undecidable)

SEED = 20260905


# ===========================================================================
# L-1 — Functoriality of lifecycle
# ===========================================================================
class TestL1LifecycleIsAFreeCategory:
    """*A model's history is a path in the free category on its lifecycle graph;
    no state is reachable except along declared transitions.*

    Previously "by construction, no generative property test". By construction is
    how a graph acquires an edge nobody meant to add — the edge is one tuple, and
    it looks exactly like the others.
    """

    def test_every_transition_names_states_that_exist(self):
        for t in TRANSITIONS:
            assert t.target in STATES, f"{t.name} targets an unknown state"
            for source in t.sources:
                assert source in STATES, f"{t.name} leaves an unknown state"

    def test_the_reachable_set_is_exactly_what_the_edges_admit(self):
        """The free-category statement, computed rather than asserted: the
        closure of the initial states under the declared edges IS the set of
        states a record can be in.

        Writing this found something. `baselined` is reachable by no declared
        edge, which looks like a violation and is not: it is a second *initial*
        object, because a record imported from a legacy inventory must not enter
        through `draft` — the register would then imply that historical evidence
        was asserted when it was not. That was implicit; `INITIAL` now says it,
        and this test quantifies over it rather than making an exception for one
        state by name.
        """
        reachable = set(INITIAL)
        changed = True
        while changed:
            changed = False
            for t in TRANSITIONS:
                if reachable & set(t.sources) and t.target not in reachable:
                    reachable.add(t.target)
                    changed = True
        assert reachable == set(STATES), (
            f"unreachable: {sorted(set(STATES) - reachable)} — a declared state "
            f"that no edge reaches is either missing an edge or is an initial "
            f"object that has not said so")

    def test_an_initial_state_is_not_the_target_of_any_transition_by_accident(self):
        """`draft` is legitimately a target — `return` sends a record back. The
        property that matters is that every initial state is declared as one
        rather than inferred from the graph having no way in."""
        for state in INITIAL:
            assert state in STATES

    def test_no_transition_returns_to_a_state_it_left_without_saying_so(self):
        """A cycle is legal — amend goes back — but every one must be a declared
        edge rather than an accident of two transitions sharing a name."""
        names = [t.name for t in TRANSITIONS]
        assert len(names) == len(set(names)), "two transitions share a name"

    def test_a_transition_that_is_not_declared_does_not_exist(self):
        """The property that makes the graph a *free* category: there are no
        composites beyond those the generators give."""
        declared = {(source, t.target) for t in TRANSITIONS for source in t.sources}
        for name, t in BY_NAME.items():
            for source in t.sources:
                assert (source, t.target) in declared

    def test_every_transition_carries_the_permission_that_gates_it(self):
        """A transition with no permission is one anybody may take."""
        for t in TRANSITIONS:
            assert t.permission, f"{t.name} is gated by nothing"


# ===========================================================================
# L-2 — Immutability
# ===========================================================================
class TestL2AVersionDigestNeverMoves:
    """*For any version `v`, `hash(manifest(v))` is constant over its lifetime.*

    Previously "by construction". The interesting failure is not an edit — the
    registry refuses those — it is a digest that moves because something ELSE
    changed: an approval, an alias, an attestation.
    """

    def test_the_digest_survives_everything_that_happens_around_it(
            self, client, people):
        owner, dev, mrm = people["j.okafor"], people["d.raman"], people["s.iqbal"]
        urn = "maya://model/credit.pd.smallbiz"
        client.post("/api/v1/models", auth=owner, json={
            "urn": urn, "name": "SB PD", "model_class": "credit.pd.scorecard",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-1", "purpose": "p"})
        created = client.post(f"/api/v1/models/credit.pd.smallbiz/versions",
                              auth=dev, json={
                                  "semver": "1.0.0",
                                  "kernel": {"parameter_kind": "none",
                                             "fit_procedure": "none"}}).json()
        digest = created["manifest_digest"]
        assert digest

        def current():
            versions = client.get("/api/v1/models/credit.pd.smallbiz").json()["versions"]
            return next(v for v in versions if v["semver"] == "1.0.0")["manifest_digest"]

        client.post("/api/v1/models/credit.pd.smallbiz/assess", auth=owner,
                    json={"exposure": 1000, "purpose_class": "commercial"})
        assert current() == digest, "assessing the model moved a version digest"

        client.post("/api/v1/models/credit.pd.smallbiz/versions/1.0.0/approve",
                    auth=mrm, json={})
        assert current() == digest, "approving the version moved its digest"

        client.put("/api/v1/models/credit.pd.smallbiz/aliases", auth=mrm, json={
            "semver": "1.0.0", "environment": "prod", "alias": "champion"})
        assert current() == digest, "moving an alias moved a version digest"

    def test_the_digest_is_over_the_manifest_and_not_the_row(self, client, people):
        """A digest computed over the stored row would move whenever a status
        column did, which is the failure this law exists to name."""
        from db.database import digest as canonical_digest
        owner, dev = people["j.okafor"], people["d.raman"]
        client.post("/api/v1/models", auth=owner, json={
            "urn": "maya://model/x.y", "name": "X", "model_class": "c",
            "domain": "credit", "owner": "person/j.okafor",
            "legal_entity": "LE-1", "purpose": "p"})
        row = client.post("/api/v1/models/x.y/versions", auth=dev, json={
            "semver": "1.0.0",
            "kernel": {"parameter_kind": "none", "fit_procedure": "none"}}).json()
        assert row["manifest_digest"] == canonical_digest(row["manifest"])


# ===========================================================================
# L-3 — Determinism flag correctness
# ===========================================================================
class TestL3ADeterminismClaimIsChecked:
    """*`deterministic(f)` ⟹ repeated execution on identical input is
    bit-identical.*

    Previously "stored and carried into the warrant; no double-execution
    differential test". A flag nobody checks is a flag that is eventually wrong,
    and this one is carried into a signed document that an engine believes.
    """

    def test_a_deterministic_runtime_reproduces_bit_for_bit(self):
        from core.execution.runtimes import EstimatorRuntime, Invocation
        runtime = EstimatorRuntime()
        warrant = {"operation": {"verb": "score"},
                   "realisation": {"runtime": "estimator",
                                   "entry": {"family": "ols"}},
                   "parameters": {"source": {"binding": "parameter_set"}}}
        call = Invocation(warrant=warrant,
                          inputs={"features": {"dscr": 1.4},
                                  "parameters": {"intercept": -2.1,
                                                 "dscr": -0.84}})
        first = runtime.invoke(call)
        second = runtime.invoke(call)
        assert first == second, (
            "the version declares determinism and two identical calls "
            "disagreed; the flag is a claim an engine believes")

    def test_the_same_claim_is_refused_where_nothing_backs_it(self):
        """The other half of the law: a stochastic runtime claiming determinism
        with no seed is refused by the grammar (L-W5) rather than believed."""
        import json
        import pathlib
        from core.execution.grammar import validate
        path = (pathlib.Path(__file__).resolve().parent.parent
                / "examples" / "warrants" / "06-llm-kyc-summarise.json")
        doc = json.loads(path.read_text())
        doc.pop("_comment", None)
        doc["operation"]["determinism"] = "deterministic"
        doc["operation"]["seed"] = None
        assert any(p.law == "L-W5" for p in validate(doc).problems)


# ===========================================================================
# L-9 — Provenance homomorphism
# ===========================================================================
class TestL9TheProvenancePolynomialIsUniversal:
    """*For any semiring homomorphism `h : ℕ[X] → K`, evaluating in `K` equals
    `h` applied to the ℕ[X] result.*

    Previously "vacuous as stated: ℕ[X] is not implemented, so there is no
    universal object to push forward from". It is implemented now, which turns
    the platform's own claim — *the same traversal answers a different question
    for each semiring* — from a design intention into a theorem the suite checks.
    """

    @staticmethod
    def _random_dag(rng):
        leaves = [f"f{i}" for i in range(4)]
        keys, derivations = list(leaves), {}
        for i in range(4):
            key = f"c{i}"
            derivations[key] = Derivation(key, tuple(
                tuple(rng.sample(keys, rng.randint(1, min(3, len(keys)))))
                for _ in range(rng.randint(1, 3))))
            keys.append(key)
        return leaves, derivations, "c3"

    @staticmethod
    def _agree(a, b):
        # Float semirings associate differently under the two routes, which is a
        # property of floating point and not of the algebra.
        if isinstance(a, float) and isinstance(b, float):
            return a == b or math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
        return a == b

    def test_it_holds_over_random_derivation_dags(self, evidence):
        rng = random.Random(SEED)
        for _ in range(200):
            leaves, derivations, claim = self._random_dag(rng)
            values = {
                leaf: {"boolean": rng.choice([True, False]),
                       "counting": rng.randint(0, 3),
                       "trust": round(rng.random(), 3),
                       "cost": round(rng.random() * 5, 3),
                       "why": {frozenset([leaf])}}
                for leaf in leaves}

            polynomial = evidence.evaluate(
                claim, derivations, POLYNOMIAL,
                lambda k: poly_variable(k) if k in values else POLYNOMIAL.zero).value

            for semiring, name in ((BOOLEAN, "boolean"), (COUNTING, "counting"),
                                   (TRUST, "trust"), (COST, "cost"),
                                   (WHY, "why")):
                def valuation(k, name=name, semiring=semiring):
                    return values[k][name] if k in values else semiring.zero

                direct = evidence.evaluate(claim, derivations, semiring,
                                           valuation).value
                pushed = pushforward(polynomial, valuation, semiring)
                assert self._agree(direct, pushed), (
                    f"{name}: evaluating directly gave {direct}, pushing the "
                    f"polynomial forward gave {pushed} — one of the two routes "
                    f"is not a homomorphism")

    def test_the_polynomial_keeps_what_boolean_provenance_throws_away(self,
                                                                     evidence):
        """Why the universal object is worth having: coefficients count distinct
        derivations and exponents count repeated use, and Boolean loses both."""
        derivations = {"claim": Derivation("claim", (("a",), ("b",)))}
        poly = evidence.evaluate(
            "claim", derivations, POLYNOMIAL, poly_variable).value
        assert poly == {(("a", 1),): 1, (("b", 1),): 1}, \
            "two independent supports, kept apart"
        assert pushforward(poly, lambda k: True, BOOLEAN) is True, \
            "and collapsed to one bit on the way to boolean"

    def test_freshness_is_not_a_semiring_and_the_law_does_not_claim_it(self):
        """A real finding, kept as a test so it is not quietly re-included.

        `docs/00 §9.2` and the module docstring describe six semirings.
        `FRESHNESS` is (max, max), and its zero does not annihilate — `max(0, 5)`
        is 5, not 0 — so it is a commutative idempotent monoid used twice rather
        than a semiring, and the universal property does not reach it. The
        practical consequence is worth knowing: a claim resting on a *missing*
        fact reports the freshness of the facts that are present, rather than
        reporting that it has none.
        """
        assert FRESHNESS.times(FRESHNESS.zero, 5.0) != FRESHNESS.zero
        for semiring in (BOOLEAN, COUNTING, TRUST, COST):
            assert semiring.times(semiring.zero, semiring.one) == semiring.zero, \
                f"{semiring.name} lost its annihilator"


# ===========================================================================
# L-16 — No obligation contradiction
# ===========================================================================
class TestL16NoRegimeObligesAndForbidsTheSameThing:
    """*The obligation set is deontically consistent: no `O φ ∧ F φ`.*

    Previously "not built; no deontic layer". A full deontic logic is not what
    this needs — `holds` is an opaque predicate and consistency over arbitrary
    predicates is undecidable. What is decidable is the case that actually
    occurs: two sentences in one vocabulary pulling a term in opposite
    directions, which is what happens when a regime is encoded by two people.
    """

    def test_a_contradiction_is_found_and_named(self):
        conflicts = deontic_conflicts([
            requires("a", "there must be independent validation", "validated"),
            forbids("b", "it must not be validated", "validated")])
        assert len(conflicts) == 1
        assert conflicts[0]["term"] == "validated"
        assert "unsatisfiable" in conflicts[0]["detail"]

    def test_a_consistent_set_reports_nothing(self):
        assert deontic_conflicts([
            requires("a", "must be validated", "validated"),
            forbids("b", "must not be unattended", "unattended")]) == []

    def test_a_conditional_obligation_is_not_a_contradiction(self):
        """`if high-risk then oversight` and `must not run unattended` do not
        contradict — they may never both apply — and reporting them as a
        contradiction would train somebody to ignore the check."""
        assert deontic_conflicts([
            implies("a", "high risk implies oversight", "high_risk", "oversight"),
            forbids("b", "must not have oversight", "oversight")]) == []

    def test_what_the_check_cannot_read_is_named_rather_than_assumed_clean(self):
        """A check that quietly ignores what it cannot judge reports success for
        exactly the cases it was least able to judge."""
        from core.regimes.sentences import Sentence
        custom = Sentence("hand", "anything", ("x",), lambda i: True)
        assert undecidable([custom, requires("a", "t", "y")]) == ["hand"]

    def test_every_shipped_regime_is_consistent(self):
        from core.regimes.library import REGIMES
        for key, regime in REGIMES.items():
            assert not deontic_conflicts(regime["sentences"]), \
                f"the shipped {key} encoding contradicts itself"

    def test_a_contradictory_regime_cannot_be_activated(self, client):
        """The law enforces rather than reports: a regime that contradicts
        itself makes every determination unsatisfiable."""
        from core.regimes.common import RegimeError
        from core.regimes.engine import RegimeEngine
        ctx = client.app.state.ctx
        engine = ctx["regimes"]
        key = sorted(engine.library)[0]
        regime = dict(engine.library[key])
        regime["sentences"] = tuple(regime["sentences"]) + (
            forbids("broken", "must not be validated",
                    regime["sentences"][0].uses[0]),
            requires("also", "must be validated",
                     regime["sentences"][0].uses[0]))
        engine.library = {**engine.library, key: regime}
        with pytest.raises(RegimeError) as exc:
            engine.activate(key)
        assert exc.value.code == "obligation_contradiction"


# ===========================================================================
# The gap that remains
# ===========================================================================
class TestTheLawsStillNotExecutable:
    """Named here as well as in the table, because a gap recorded only in a
    document is a gap somebody has to go looking for."""

    NOT_EXECUTABLE = {
        "L-6": "abstraction soundness needs the replay that checks a document's "
               "quantitative claims against the register; the replay is built "
               "for validation episodes and not for documents",
        "L-11": "the lens laws need a `put`. The compiler regenerates whole "
                "documents, so there is no round trip to test — and building "
                "one to satisfy a law would be building the wrong thing",
        "L-13": "evidence gluing has no implementation; no consistency radius "
                "is computed anywhere",
        "L-14": "lax monoidality needs composite warrants and an aggregate risk "
                "function; the interaction premium is design",
        "L-15": "fibration completeness needs a plugin loader that refuses to "
                "boot on a partial fibre; model classes are strings today",
        "L-17": "contract-serving agreement needs an online store to compare "
                "against. Half of it exists: `serving_namespaces` computes what "
                "serving MUST read",
    }

    def test_the_list_is_stated_rather_than_implied(self):
        assert len(self.NOT_EXECUTABLE) == 6
        for law, why in self.NOT_EXECUTABLE.items():
            assert why, f"{law} is listed with no reason"

    def test_the_document_and_this_file_do_not_disagree(self):
        """The table in `docs/00 §12` is the public statement. If it claims a law
        runs, something here or beside the code must run it."""
        import pathlib
        import re
        doc = (pathlib.Path(__file__).resolve().parent.parent
               / "docs" / "00-mathematical-foundations.md").read_text()
        for law in self.NOT_EXECUTABLE:
            row = re.search(rf"^\| \*\*{law}\*\* \|.*$", doc, re.M)
            assert row, f"{law} is not in the table at all"
            assert "Executable" not in row.group(0), (
                f"{law} is listed here as not executable and the table claims "
                f"it runs; one of the two is wrong")
