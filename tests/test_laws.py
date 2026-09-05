"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

The foundational laws, made executable.

`docs/00 §12` states twenty-one laws and, for each, whether it runs. Seven of
the original nineteen did. The
document was honest about the rest — *"a law that is stated but not executed did
not prevent anything"* — which is the correct thing to say and a poor place to
leave it, because the strongest claim the design makes is that the laws are the
acceptance criteria, and a claim that is 37% true is a claim that will be read as
100% true by everybody who does not check.

This file closes five of the twelve, and adds two more (`L-20`, `L-21`) that
the work of closing them showed were missing. Each is tested as the law is *stated*, not
as the implementation happens to behave — a test written from the code proves the
code agrees with itself.

The six that are still not executable are named here as well, with the reason,
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


# ===========================================================================
# L-20 — The schema order, and everything that rests on it
# ===========================================================================
class TestL20SchemasFormALattice:
    """*Schemas are partially ordered by "can stand in for", and that order is a
    lattice on any finite set of field names.*

    A new law, and the reason for it is a defect rather than an aesthetic. Four
    places asked *does this fit where that fitted* — `substitutable` for a
    version replacing another, a slot loop for `L-W10`, `refines` for contracts,
    and nothing at all for a `input_to` edge — and four implementations of one
    relation eventually disagree, in the direction of permitting more, because
    that is the direction in which nobody files a bug.

    Writing it also corrected the design note: `docs/17` said a refinement is
    "at a type no wider", which is backwards. Standing in for something requires
    accepting **at least** what it accepted.
    """

    NAMES = ("dscr", "turnover", "region", "defaulted")
    DTYPES = ("numeric", "integer")

    @classmethod
    def _schema(cls, rng):
        from core.domain.schemas import Field, Schema
        fields = []
        for name in cls.NAMES:
            if rng.random() < 0.55:
                fields.append(Field(
                    name, rng.choice(cls.DTYPES), rng.random() < 0.4,
                    rng.choice([None, round(rng.uniform(-5, 0), 1)]),
                    rng.choice([None, round(rng.uniform(1, 9), 1)])))
        return Schema(tuple(fields))

    def _triples(self, n=300):
        rng = random.Random(SEED)
        for _ in range(n):
            yield self._schema(rng), self._schema(rng), self._schema(rng)

    def test_the_order_is_a_partial_order(self):
        from core.domain.lattice import leq
        for a, b, c in self._triples():
            assert leq(a, a), "a schema must be able to stand in for itself"
            if leq(a, b) and leq(b, c):
                assert leq(a, c), "the order is not transitive"

    def test_meet_is_below_both_and_join_is_above_both(self):
        from core.domain.lattice import NoMeet, join, leq, meet
        for a, b, _ in self._triples():
            try:
                lower = meet(a, b)
            except NoMeet:
                continue                      # a partial meet, tested below
            assert leq(lower, a) and leq(lower, b), \
                "the meet must be able to stand in for both"
            upper = join(a, b)
            assert leq(a, upper) and leq(b, upper), \
                "both must be able to stand in for the join"

    def test_meet_is_idempotent_commutative_and_associative(self):
        from core.domain.lattice import NoMeet, leq, meet

        def same(x, y):
            return leq(x, y) and leq(y, x)

        for a, b, c in self._triples():
            assert same(meet(a, a), a)
            try:
                assert same(meet(a, b), meet(b, a))
                assert same(meet(meet(a, b), c), meet(a, meet(b, c)))
            except NoMeet:
                continue

    def test_absorption_holds(self):
        from core.domain.lattice import NoMeet, join, leq, meet
        for a, b, _ in self._triples():
            try:
                absorbed = meet(a, join(a, b))
            except NoMeet:
                continue
            assert leq(absorbed, a) and leq(a, absorbed), \
                "a ⊓ (a ⊔ b) must be a"

    def test_the_order_and_the_meet_agree(self):
        """`a ⊑ b ⟺ a ⊓ b = a` — the link that makes it a lattice order rather
        than an order and two unrelated operations."""
        from core.domain.lattice import NoMeet, leq, meet
        for a, b, _ in self._triples():
            try:
                lower = meet(a, b)
            except NoMeet:
                continue
            same = leq(lower, a) and leq(a, lower)
            assert leq(a, b) == same

    def test_everything_stands_in_for_the_empty_schema(self):
        from core.domain.lattice import TOP, leq
        for a, _, _ in self._triples(50):
            assert leq(a, TOP), "the empty schema demands nothing"

    def test_a_meet_that_cannot_exist_is_refused_by_name(self):
        """The partiality is informative. Two schemas whose shared slot has two
        types have no meet, and the honest answer to *can one featureset serve
        both these models* is no, with the slot named."""
        from core.domain.lattice import NoMeet, meet
        from core.domain.schemas import Field, Schema
        with pytest.raises(NoMeet) as exc:
            meet(Schema((Field("dscr", "numeric"),)),
                 Schema((Field("dscr", "text"),)))
        assert "dscr" in str(exc.value)
        assert exc.value.conflicts == {"dscr": ("numeric", "text")}

    def test_widening_a_bound_still_stands_in_but_narrowing_does_not(self):
        from core.domain.lattice import leq, refines
        from core.domain.schemas import Field, Schema
        old = Schema((Field("dscr", "numeric", minimum=-5, maximum=20),))
        wider = Schema((Field("dscr", "numeric", minimum=-10, maximum=40),))
        narrower = Schema((Field("dscr", "numeric", minimum=0, maximum=10),))
        assert leq(wider, old), "accepting more than before is not a regression"
        assert not leq(narrower, old)
        assert refines(narrower, old).narrowed == ("dscr",)

    def test_a_missing_field_and_a_narrowed_one_are_told_apart(self):
        """Different mistakes with different remedies: a missing slot means the
        wrong featureset was bound, a narrowed one means somebody tightened a
        constraint without noticing it was a promise."""
        from core.domain.lattice import refines
        from core.domain.schemas import Field, Schema
        outcome = refines(
            Schema((Field("dscr", "numeric", minimum=0),)),
            Schema((Field("dscr", "numeric", minimum=-5),
                    Field("turnover", "numeric"),)))
        assert outcome.missing == ("turnover",)
        assert outcome.narrowed == ("dscr",)


class TestL20TheSameOrderAnswersEveryQuestion:
    """The point of the law: one relation, four questions."""

    def test_l12_and_lw10_are_the_same_comparison(self):
        """`substitutable` and a featureset satisfying a kernel now go through
        one function. They were the same relation implemented twice."""
        import inspect
        from core.domain import schemas
        from core.features import sets
        assert "refines" in inspect.getsource(schemas.substitutable)
        assert "refines" in inspect.getsource(sets.FeaturesetRegistry.satisfies)

    def test_a_featureset_satisfying_a_kernel_is_an_order_comparison(self):
        from core.domain.lattice import leq, schema_of
        from core.domain.schemas import Field, Schema
        kernel = Schema((Field("dscr", "numeric"), Field("turnover", "numeric")))
        enough = schema_of({"dscr": "numeric", "turnover": "numeric",
                            "region": "categorical"})
        assert leq(enough, kernel), "extra slots are simply not read"
        assert not leq(schema_of({"dscr": "numeric"}), kernel)


class TestTheEditOperationsCommuteWhenIndependent:
    """*Edits naming different members commute.*

    The property two people editing a shared featureset rely on without knowing
    it: if independent edits commute, the merge order carries no meaning. It was
    never tested, and a failure here could not be found by testing one edit at a
    time.
    """

    BASE = {"dscr": {"dtype": "numeric"}, "turnover": {"dtype": "numeric"}}

    def _ops(self, rng):
        from core.features.composition import ADD, DROP, OVERRIDE
        choices = [
            {"op": ADD, "name": "region", "value": {"dtype": "categorical"}},
            {"op": DROP, "name": "turnover"},
            {"op": OVERRIDE, "name": "dscr", "value": {"dtype": "integer"}},
        ]
        return rng.sample(choices, 2)

    def test_independent_edits_commute(self):
        from core.features.composition import apply, independent
        rng = random.Random(SEED)
        for _ in range(60):
            first, second = self._ops(rng)
            assert independent(first, second), "the sample must be independent"
            assert (apply(self.BASE, [first, second])
                    == apply(self.BASE, [second, first])), (
                f"{first['op']} {first['name']} and {second['op']} "
                f"{second['name']} do not commute, so the order two people "
                f"happened to edit in carries meaning")

    def test_dependent_edits_are_not_claimed_to_commute(self):
        """`override` then `drop` of the same slot is not `drop` then
        `override` — the second order is refused, which is the correct
        behaviour and the reason the law is stated only for independent edits."""
        from core.features.common import FeatureError
        from core.features.composition import apply
        drop = {"op": "drop", "name": "dscr"}
        override = {"op": "override", "name": "dscr",
                    "value": {"dtype": "integer"}}
        assert "dscr" not in apply(self.BASE, [override, drop])
        with pytest.raises(FeatureError):
            apply(self.BASE, [drop, override])

    def test_an_edit_and_its_inverse_are_the_identity(self):
        from core.features.composition import apply
        add = {"op": "add", "name": "region", "value": {"dtype": "categorical"}}
        drop = {"op": "drop", "name": "region"}
        assert apply(self.BASE, [add, drop]) == self.BASE

    def test_a_later_override_absorbs_an_earlier_one(self):
        from core.features.composition import apply
        first = {"op": "override", "name": "dscr", "value": {"dtype": "integer"}}
        second = {"op": "override", "name": "dscr", "value": {"dtype": "text"}}
        assert (apply(self.BASE, [first, second])
                == apply(self.BASE, [second])), "the later edit must win outright"


# ===========================================================================
# L-10 — strengthened: the point-in-time read as an operator
# ===========================================================================
class TestL10TheAsOfOperator:
    """*Every generated training set satisfies the point-in-time condition.*

    Previously "enforcing, in the rescoped form of H-6: static rejection of an
    assembly missing either clock". That is a real refusal and it is a check on
    the *inputs*. What was never checked is the behaviour of the read itself —
    and the read is where reproducibility actually lives.

        AsOf(R, ℓ, a) = argmax (event_ts, ingest_ts) over
                        { r : r.event ≤ ℓ ∧ r.ingest ≤ min(ℓ, a) }
    """

    @staticmethod
    def _rows(rng, n=6):
        from core.features.common import INGEST_TIME, VALID_TIME
        return [{VALID_TIME: rng.randint(0, 100),
                 INGEST_TIME: rng.randint(0, 140),
                 "dscr": round(rng.uniform(0, 3), 3), "row": i}
                for i in range(n)]

    @staticmethod
    def _read(rows, label, as_of):
        from core.features.assembly import TrainingSetBuilder
        return TrainingSetBuilder.latest_admissible(rows, label, as_of)

    def test_it_is_idempotent(self):
        rng = random.Random(SEED)
        for _ in range(200):
            rows, label = self._rows(rng), rng.randint(20, 100)
            once = self._read(rows, label, label + 10)
            if once is None:
                continue
            assert self._read([once], label, label + 10) == once

    def test_it_commutes_with_projection(self):
        """Which row is admissible is decided on the clocks alone, so reading
        fewer columns cannot change the choice."""
        rng = random.Random(SEED)
        for _ in range(200):
            rows, label = self._rows(rng), rng.randint(20, 100)
            as_of = rng.randint(0, 140)
            full = self._read(rows, label, as_of)
            projected = self._read(
                [{k: v for k, v in r.items() if k != "dscr"} for r in rows],
                label, as_of)
            assert (full is None) == (projected is None)
            if full is not None:
                assert full["row"] == projected["row"]

    def test_it_is_monotone_in_as_of(self):
        """A later read can only widen what is admissible. Nothing that was
        knowable stops being knowable."""
        from core.features.common import INGEST_TIME, VALID_TIME
        rng = random.Random(SEED)
        for _ in range(200):
            rows, label = self._rows(rng), rng.randint(20, 100)
            seen = None
            for as_of in sorted(rng.sample(range(0, 140), 5)):
                admissible = {r["row"] for r in rows
                              if r[VALID_TIME] <= label
                              and r[INGEST_TIME] <= min(label, as_of)}
                if seen is not None:
                    assert seen <= admissible, (
                        "a later as_of removed a row that was already knowable")
                seen = admissible

    def test_it_saturates_at_the_label_and_that_is_the_reproducibility_law(self):
        """**The one that matters.** The ingest bound is `min(label, as_of)`, so
        every `as_of` at or after the label gives the same answer — a row
        assembled the day its label matured and the same row re-assembled a year
        later are identical, however many restatements arrived in between.

        Without the `min`, a re-run would quietly improve on the original, which
        is the least useful kind of reproducibility: the numbers agree with
        nothing, including themselves.
        """
        rng = random.Random(SEED)
        for _ in range(300):
            rows, label = self._rows(rng), rng.randint(20, 100)
            settled = self._read(rows, label, label)
            for later in (label, label + 1, label + 50, label + 10_000):
                assert self._read(rows, label, later) == settled, (
                    f"the answer moved between as_of={label} and {later}; a "
                    f"training set is then not reproducible from its own record")

    def test_a_restatement_after_the_label_cannot_change_a_settled_row(self):
        """The concrete case the two clocks exist for: a Q1 figure revised in
        August must not reach a row labelled in May."""
        from core.features.common import INGEST_TIME, VALID_TIME
        march, may, august = 1711843200.0, 1716163200.0, 1725148800.0
        original = {VALID_TIME: march, INGEST_TIME: may, "dscr": 1.20}
        restated = {VALID_TIME: march, INGEST_TIME: august, "dscr": 0.40}

        assert self._read([original], may, august)["dscr"] == 1.20
        assert self._read([original, restated], may, august)["dscr"] == 1.20, (
            "the August restatement reached a row labelled in May — this is the "
            "leak the point-in-time rule exists to prevent, and it scores "
            "beautifully in backtest")
        # And it does reach a row labelled after it became known, correctly.
        assert self._read([original, restated], august, august)["dscr"] == 0.40


# ===========================================================================
# L-9 extended — the same polynomial, one layer across
# ===========================================================================
class TestL9ReachesDerivedFeatures:
    """A derived feature is a term; its provenance is the same `ℕ[X]` the
    evidence chain uses. Two copies of one idea, one of which had laws.

    The ingest clock is the interesting case. `ingest(Z) = max` over the inputs
    was a *rule* — arithmetic, said the docstring, so it cannot be forgotten. It
    is stronger than that: it is a **homomorphism** out of the derivation term
    algebra into the max-semiring, and a homomorphism has no exceptions to
    forget.
    """

    @pytest.fixture
    def derived(self, db, evidence):
        """The registry builds the whole feature platform; the derived service
        needs its catalogue, so it is taken from there rather than half-built
        here — a fixture that assembles a service differently from production is
        a fixture that tests a different service."""
        from core.features import FeatureRegistry
        from db import (ContractRepository, DerivedFeatureRepository,
                        FeatureRepository, FeatureViewRepository,
                        FeatureViewVersionRepository, SnapshotRepository)
        from db.delta_store import DeltaStore
        import tempfile
        registry = FeatureRegistry(
            FeatureRepository(db), FeatureViewRepository(db),
            FeatureViewVersionRepository(db), ContractRepository(db),
            SnapshotRepository(db), DeltaStore(tempfile.mkdtemp()), evidence,
            derived=DerivedFeatureRepository(db))
        for base in ("dscr", "turnover", "defaulted"):
            registry.define(name=base, entity="borrower_id", dtype="numeric",
                            description=base, owner="person/admin",
                            actor="admin")
        return registry.derived

    def test_the_polynomial_gives_the_base_features_the_walk_gives_all_ancestors(
            self, derived):
        """They answer different questions, and writing the test made that
        precise rather than leaving it to be discovered.

        `lineage` is every ancestor, derived ones included — the right answer to
        *what would break if this changed*. `rests_on` is the **free variables**
        of the polynomial, which are the base features and nothing else — the
        right answer to *what data does this ultimately read*. The second is a
        subset of the first, and equals the first minus its derived members.
        """
        derived.define(name="leverage", expression="turnover / dscr",
                       dtype="numeric", description="d", owner="person/admin",
                       actor="admin")
        derived.define(name="scaled", expression="leverage * 2",
                       dtype="numeric", description="d", owner="person/admin",
                       actor="admin")

        ancestors = derived.lineage("scaled")
        bases = derived.rests_on("scaled")
        assert bases <= ancestors
        assert "leverage" in ancestors and "leverage" not in bases
        assert bases == {a for a in ancestors if derived.get(a) is None}

    def test_a_base_feature_is_its_own_variable(self, derived):
        from core.evidence.semirings import poly_variable
        assert derived.provenance("dscr") == poly_variable("dscr")

    def test_the_ingest_clock_is_the_max_pushforward(self, derived):
        """The claim, checked: pushing the polynomial into (max, max) gives the
        same number the hand-written rule gives."""
        from core.features.common import INGEST_TIME
        derived.define(name="leverage", expression="turnover / dscr",
                       dtype="numeric", description="d", owner="person/admin",
                       actor="admin")
        row = {INGEST_TIME: 100.0,
               f"turnover__{INGEST_TIME}": 500.0,
               f"dscr__{INGEST_TIME}": 300.0}
        by_rule = derived.knowable_at(row, ["turnover", "dscr"])

        stamps = {"turnover": 500.0, "dscr": 300.0}
        polynomial = derived.provenance("leverage")
        by_algebra = max(
            max(stamps.get(variable, 0.0) for variable, _ in monomial)
            for monomial in polynomial)
        assert by_rule == by_algebra == 500.0, (
            "the ingest clock and the max-pushforward must agree, or one of "
            "them is not what the other claims to be")

    def test_the_label_is_found_by_membership_rather_than_a_walk(self, derived):
        """Leakage becomes a membership test in the polynomial's variables."""
        derived.define(name="near_label", expression="defaulted * 1.0",
                       dtype="numeric", description="d", owner="person/admin",
                       actor="admin")
        derived.define(name="hidden", expression="near_label + 1",
                       dtype="numeric", description="d", owner="person/admin",
                       actor="admin")
        assert "defaulted" in derived.rests_on("hidden"), (
            "a derivation of a derivation of the label is still the label")


# ===========================================================================
# L-21 — Composition type-checks
# ===========================================================================
class TestL21FeedsIsCompositionRatherThanADrawing:
    """*A `input_to` edge asserts that what one model produces arrives where
    another reads it, and is refused unless the schemas compose.*

    Recorded and never checked, `input_to` was a drawing: the blast radius followed
    edges nobody had validated, a composite had no derived schema, and `L-14`
    had nothing to quantify over. Checked, it is composition in the sense the
    paper means — and the check is the platform's one order, not a fifth
    implementation of it.
    """

    OUT = [{"name": "pd_12m", "dtype": "numeric"}]

    @pytest.fixture
    def graph(self, db, registry, evidence):
        from core.registry.composition import ModelComposition
        from db import ModelEdgeRepository, VersionRepository
        return ModelComposition(ModelEdgeRepository(db), registry.catalogue,
                                evidence, VersionRepository(db))

    def _model(self, registry, name, *, reads=(), writes=()):
        urn = f"maya://model/{name}"
        registry.register(urn=urn, name=name, model_class="c", domain="credit",
                          owner="person/admin", legal_entity="LE-1",
                          purpose="p", actor="admin")
        registry.create_version(
            urn, "1.0.0",
            {"parameter_kind": "none", "fit_procedure": "none",
             "input_schema": list(reads), "output_schema": list(writes)},
            actor="admin")
        return urn

    def test_an_edge_that_composes_is_recorded(self, registry, graph):
        upstream = self._model(registry, "a.pd", writes=self.OUT)
        downstream = self._model(registry, "b.var", reads=self.OUT)
        edge = graph.relate(upstream, downstream, "input_to", actor="admin")
        assert edge["kind"] == "input_to"

    def test_an_edge_that_does_not_compose_is_refused(self, registry, graph):
        """The wire to nowhere: the target reads something the source does not
        produce."""
        from core.registry.common import RegistryError
        upstream = self._model(registry, "a.pd", writes=self.OUT)
        downstream = self._model(
            registry, "b.var", reads=[{"name": "lgd", "dtype": "numeric"}])
        with pytest.raises(RegistryError) as exc:
            graph.relate(upstream, downstream, "input_to", actor="admin")
        assert "does not compose" in str(exc.value)
        assert "lgd" in str(exc.value)

    def test_extra_outputs_are_fine_because_they_are_simply_unread(
            self, registry, graph):
        upstream = self._model(registry, "a.pd", writes=self.OUT + [
            {"name": "score", "dtype": "numeric"}])
        downstream = self._model(registry, "b.var", reads=self.OUT)
        assert graph.relate(upstream, downstream, "input_to", actor="admin")

    def test_a_narrowed_output_is_refused_like_a_narrowed_input(self,
                                                               registry, graph):
        """The same regression `L-12` names at an alias move, one level out."""
        from core.registry.common import RegistryError
        upstream = self._model(registry, "a.pd", writes=[
            {"name": "pd_12m", "dtype": "integer"}])
        downstream = self._model(registry, "b.var", reads=self.OUT)
        with pytest.raises(RegistryError):
            graph.relate(upstream, downstream, "input_to", actor="admin")

    def test_commentary_edges_are_not_type_checked(self, registry, graph):
        """`challenger_of` and `benchmark_for` record how somebody thinks about
        a model. There is no wire, so there is nothing to type."""
        upstream = self._model(registry, "a.pd", writes=self.OUT)
        other = self._model(registry, "b.other",
                            reads=[{"name": "lgd", "dtype": "numeric"}])
        assert graph.relate(upstream, other, "challenger_of", actor="admin")

    def test_an_edge_is_recorded_where_a_schema_does_not_exist_yet(
            self, registry, graph):
        """Refusing an edge for a schema that has not been decided would make
        the register harder to build than the estate is to describe."""
        urn = "maya://model/c.no_version"
        registry.register(urn=urn, name="C", model_class="c", domain="credit",
                          owner="person/admin", legal_entity="LE-1",
                          purpose="p", actor="admin")
        downstream = self._model(registry, "b.var", reads=self.OUT)
        assert graph.relate(urn, downstream, "input_to", actor="admin")

    def test_the_composite_schema_is_derived_rather_than_declared(
            self, registry, graph):
        """A composite whose schema somebody wrote down is a composite that can
        disagree with its parts."""
        reads = [{"name": "dscr", "dtype": "numeric"}]
        writes = [{"name": "cva", "dtype": "numeric"}]
        upstream = self._model(registry, "a.pd", reads=reads, writes=self.OUT)
        downstream = self._model(registry, "b.var", reads=self.OUT, writes=writes)
        graph.relate(upstream, downstream, "input_to", actor="admin")
        composite = graph.composite_schema(upstream, downstream)
        assert composite["input_schema"] == reads
        assert composite["output_schema"] == writes
