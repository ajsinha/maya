# 17 — The algebra: features, featuresets, models, and the documentation graph

*What is built. Every claim below is checked by a named test; where something is not
built, the section says so and says why.*

---

## 1. The problem this solves

Four places in MAYA asked one question — **does this thing fit where that thing
was?** — and each answered it its own way.

| Where | What it asked | How it answered |
|---|---|---|
| An alias move | is the replacement version substitutable? | `substitutable()` in `core/domain/schemas.py` |
| A fit warrant | does the featureset provide what the kernel reads? | a hand-written slot loop |
| A contract | does the new contract refine the old one? | `refines()` in `core/domain/contracts.py` |
| A dependency edge | does the source's output arrive where the target reads? | **it did not ask** |

Four implementations of one relation. They disagree eventually, and the direction
is predictable: toward permitting more, because that is the direction in which
nobody files a bug. The fourth row is the worst — a dependency graph whose edges
were never checked, followed by a blast radius that trusted them.

So the relation is written once, and everything that used to ask its own version
of the question now asks it.

---

## 2. The order

`core/domain/lattice.py`. One partial order on schemas:

> **`A ⊑ B`** iff `A` has every field `B` has, each accepting **at least** what
> `B`'s accepted.

Read it as *A can stand in for B*. `A` may have extra fields — they are simply
not read — and each shared field must accept at least the values `B`'s did,
because a replacement that rejects an input its predecessor took is a
replacement that breaks a caller.

> **A correction worth recording.** The first draft of this document said a
> refinement is "at a type no wider". That is backwards. Standing in for
> something requires accepting **at least** what it accepted, so a *wider*
> acceptance is fine and a *narrower* one regresses. The prose came from the
> intuition that a subtype is narrower; the `accepts` relation in the code had it
> right all along. Writing the implementation found the error in the design note,
> which is the ordinary direction of that traffic and worth admitting.

### It is a lattice

| | | |
|---|---|---|
| **meet** `A ⊓ B` | the **union** of the fields, each widened to accept both | the schema that can stand in for either — what a featureset must provide to serve two models at once |
| **join** `A ⊔ B` | the **intersection** of the fields, narrowed to what both accepted | what two schemas *agree* on — what a consumer of either may rely on |
| **top** | the empty schema | it demands nothing, so everything can stand in for it |

There is no bottom, and saying so matters: a least element would have to carry
every field name that could ever exist. The structure is a lattice on each finite
fragment, which is the only fragment anything here inhabits.

**Meet is partial, and its failure is informative.** Two schemas whose shared
field carries two different dtypes have no meet — no schema accepts both a number
and a string in one slot — and the honest answer to *can one featureset serve both
these models* is then **no**, with the slot named. It raises `NoMeet` rather than
returning `None`, because the caller who asked has a decision to make, and a
`None` threaded through three layers becomes a silent empty schema somewhere.

### What it unified

| Question | Before | Now |
|---|---|---|
| Featureset satisfies the kernel (`L-W10`) | a bespoke loop | `refines(resolved, kernel_inputs)` |
| Replacement is substitutable (`L-12`) | `accepts_superset_of` | the same `refines` |
| Is this child a refinement of its parent? | **not askable** | `A ⊑ B` |
| What must a featureset provide to serve both? | **not askable** | their meet |
| What do two versions agree on? | **not askable** | their join |

`L-20` in [00 §12](00-mathematical-foundations.md), asserted over generated
schemas in `tests/test_laws.py::TestL20SchemasFormALattice`: partial order, meet
below both, join above both, idempotence, commutativity, associativity,
absorption, and the link `A ⊑ B ⟺ A ⊓ B = A` that makes it a lattice *order*
rather than an order and two unrelated operations.

---

## 3. The edit algebra

`add`, `drop` and `override` generate a monoid acting on featureset schemas. Each
is **total**: an `add` of something present, a `drop` of something absent and an
`override` that changes nothing are each refused, because an operation that
silently did nothing is one somebody believes happened.

Three laws hold, and the third is the one that matters:

```
drop(x) · add(x, τ)               =  id                (where x is absent)
override(x, σ) · override(x, τ)   =  override(x, σ)    (the later wins outright)
op₁ · op₂                         =  op₂ · op₁         (naming different slots)
```

**Independent edits commute.** That is what lets two people edit a shared
featureset and have the order of their edits carry no meaning — the difference
between a merge and a conflict whose resolution is a decision. It was never
tested, and a failure could not have been found by testing one edit at a time.
`core/features/composition.py::independent` names the condition;
`tests/test_laws.py::TestTheEditOperationsCommuteWhenIndependent` asserts it.

Dependent edits are deliberately **not** claimed to commute. `override` then
`drop` of the same slot is not `drop` then `override` — the second order is
refused — and stating the law only for independent edits is the honest form of it.

---

## 4. The point-in-time read, as an operator

The condition was always checked. The *read* was never characterised, and the read
is where reproducibility actually lives.

```
AsOf(R, ℓ, a) = argmax over (event_ts, ingest_ts) of
                { r ∈ R : r.event ≤ ℓ  ∧  r.ingest ≤ min(ℓ, a) }
```

Four properties, all asserted in `tests/test_laws.py::TestL10TheAsOfOperator`:

| | |
|---|---|
| **Idempotent** | reading the result again returns it |
| **Commutes with projection** | which row is admissible is decided on the clocks alone, so reading fewer columns cannot change the choice |
| **Monotone in `a`** | a later `as_of` can only *widen* what is admissible; nothing knowable stops being knowable |
| **Saturating at `ℓ`** | **the reproducibility guarantee** |

The fourth is the one to understand. Because the ingest bound is `min(ℓ, a)`,
**every `a ≥ ℓ` gives the same answer**. A training row assembled the day its
label matured and the same row re-assembled a year later are identical, however
many restatements arrived in between.

Without the `min`, a re-run would quietly *improve* on the original — the least
useful kind of reproducibility, because the numbers then agree with nothing,
including themselves. That is the concrete case the two clocks exist for: a Q1
figure revised in August must not reach a row labelled in May, and must reach a
row labelled in September.

---

## 5. Derived features on the provenance polynomial

A derived feature is a **term**. Annotate each base feature with its own variable
and evaluate the term in `ℕ[X]` — the free commutative semiring, implemented in
`core/evidence/semirings.py` for the evidence chain and now used one layer across.

Every other question about the feature is a **homomorphism out of it**:

| Question | The homomorphism |
|---|---|
| what does this rest on? | the free variables of the polynomial |
| when did it become knowable? | pushforward into the max-semiring |
| does it touch the label? | membership of the label's variable |
| how much do we trust it? | pushforward into the trust semiring |

The ingest clock is the interesting one. `ingest(Z) = max` over the inputs was
described as *arithmetic, so it cannot be forgotten*. It is stronger than that:
it is a homomorphism, and **a homomorphism has no exceptions to forget**.

**Two lineages, answering different questions.** Writing this made a distinction
precise that had been implicit:

- `lineage()` is every ancestor, derived ones included — the right answer to *what
  would break if this changed*.
- `rests_on()` is the free variables of the polynomial: the base features and
  nothing else — the right answer to *what data does this ultimately read*.

The second is the first minus its derived members, and that is asserted rather
than assumed.

---

## 6. Composition, typed

An `input_to` edge asserts that what one model produces arrives where another
reads it. Recorded and never checked, it was a **drawing**: the blast radius
followed edges nobody had validated, a composite had no derived schema, and
`L-14` — the interaction premium — had nothing to quantify over.

It is now refused unless the ends compose, through the order of §2:

```
refines( output_schema(source), input_schema(target) )
```

| | |
|---|---|
| extra outputs | fine — simply unread |
| a missing output | refused: a wire to nowhere |
| a narrowed output | refused, the same regression `L-12` names at an alias move, one level out |
| either end has no version yet | recorded **without** a type check, and the log says so — refusing an edge for a schema nobody has decided would make the register harder to build than the estate is to describe |
| `challenger_of`, `benchmark_for` | not type-checked: they record how somebody *thinks* about a model, and there is no wire |
| `calibrated_by` | propagates but does not compose — a calibration solves parameters rather than handing an output to an input |

`composite_schema(A, B)` derives the type of `B ∘ A`: the source's inputs, the
target's outputs. **Derived, not declared** — a composite whose schema somebody
wrote down is a composite that can disagree with its parts.

`L-21`, asserted in `tests/test_laws.py::TestL21FeedsIsCompositionRatherThanADrawing`.

### On the name

The relation was called `feeds`. That was a bad name in a bank, where a *feed*
means market data or a nightly file — so `A feeds B` read as though MAYA consumed
or produced one.

**It does neither.** MAYA moves no data and runs no model. The edge is a statement
about two entries in the register, and the wire it describes is carried by
whatever engine runs the two ends. `input_to` says what the relation is; `feeds`
is still accepted on the way in and stored under the new name, and is deliberately
**not** published in `KINDS` — a vocabulary offering two words for one relation
invites somebody to think they mean different things.

---

## 7. How a model is shown

The definition the platform is organised around is `f : P ⊗ X → D(Y)`, and until
recently a reader had to assemble it from four cards on the model page. It is now
the first thing on the page:

```
            P              ⊗              X                →        D(Y)
   ──────────────────         ─────────────────────            ─────────────
   coefficients               dscr     : ℝ[-5, 20]             Bernoulli
   estimated_coefficients     turnover : ℝ⁺                    over pd_12m

   T3  ·  estimated_coefficients  ·  estimate  ·  runtime estimator
```

Every part is derived from the version. The trainability class is shown **beside
the two facts it falls out of**, which is the difference between a label and an
explanation.

### Not built

Two diagrams the register has the data for and does not draw:

- **the featureset fold** — parents → operations → resolved, so a reader can see
  where each slot came from and which parent lost;
- **a string diagram** of composition — boxes for models, wires for schemas,
  `input_to` as composition and shared inputs as tensor. Now that the wires
  type-check, a broken one would be visibly broken rather than silently recorded.

---

## 8. Documentation as a graph

Documentation does not arrive all at once about one thing. It arrives at **five
moments about five objects**:

| When | About | Example |
|---|---|---|
| before anything runs | the **model** | the methodology paper, the literature the approach comes from |
| a version is created | the **version** | the specification of that kernel |
| a fit warrant executes | the **parameter set** | the convergence study, the note explaining one morning |
| a featureset is filled | the **featureset version** | the data dictionary, the source-system agreement |
| validation concludes | the **validation** | the independent recode, the reviewer's working |

Everything used to be filed against a model or a version, so the third and fourth
were **unfilable** — and they are the two that matter most in practice. A
calibrated model produces a parameter set every morning; a featureset's
documentation is read by every model fitted from it, so filing it against one of
them makes it invisible to the rest.

**A subject is always pinned.** `featureset_version`, never `featureset`. A
document filed against the *set* would describe something that has since moved —
finding C-2 in documentation's clothing — so `featureset` is deliberately absent
from the vocabulary rather than discouraged in a comment.

### The training record

Compiled per parameter set from what the register already holds: the warrant that
authorised the fit, the featureset version it read, the window, the `as_of`, the
diagnostics the estimator returned, who recorded it and who accepted it.

Compiled rather than written, and that is the point. A model recalibrated every
morning produces **two hundred and fifty governed acts a year**, each with a
warrant behind it and a signature on it, and none of them had a record anybody
could read. Compiling means all of them exist whether or not somebody had time to
write one, and the one that needs a human note has a place to put it — an
attachment against the same subject.

A fit with **no warrant** is a named gap rather than a blank section: a fitted set
with no warrant has no answer to *which data produced these numbers*, and that is
worth saying out loud.

### The dossier

The graph, walked from a model:

```
model
 ├── attached: methodology paper, literature, vendor note
 ├── compiled: model development document, model card, Annex IV
 └── version 1.0.0
      ├── attached: kernel specification
      ├── compiled: validation report
      ├── parameter set ps-8817        (fitted 2026-03-31)
      │    ├── compiled: training record
      │    └── attached: convergence study
      └── fitted from  featureset sb_core @ v1
           ├── attached: data dictionary, source agreement
           └── feature dscr
                └── attached: business definition
```

**Computed, never stored.** Its inputs are all versioned or immutable, so there is
nothing to keep in step — and a stored dossier would be a second account of the
model's documentation, able to disagree with the first.

**Every node with nothing filed is a named gap**, with what was expected. A page
that silently omits what it could not find reads as complete, and a reader cannot
tell a thin model from a thin page unless the page says which it is.

It travels whole into the **export pack**: the pack already held each document,
but not how they relate, and a reader outside the platform cannot walk the
register.

---

## 9. What the literature and the products offer

### Borrowed

**Provenance semirings** — Green, Karvounarakis & Tannen (PODS 2007). `ℕ[X]` is
implemented and its universal property is `L-9`, checked over 200 random
derivation DAGs against five semirings. Used for evidence, and now for derived
features.

**Bitemporality** — Snodgrass; SQL:2011 system-versioned and application-time
tables. MAYA's two clocks are exactly those, and SQL:2011's `AS OF` is the
standard §4 names.

**Refinement types** — Rondon et al., *Liquid Types*. The operating contract
already carries `dscr ∈ [-5, 20]` as an *assumption*; the lattice's `Field`
carries the same bounds, so the two are now one idea in two places rather than
two ideas.

### Studied, not adopted

**Functorial data migration** — Spivak; Wisnesky's CQL. A schema morphism induces
`Δ ⊣ Σ` and `Δ ⊢ Π`, the principled form of "map one featureset onto another's
shape". The *vocabulary* is worth having; the machinery is not built, and
pretending otherwise would be the kind of claim this document exists to avoid.

**Semantic layers** — dbt MetricFlow, Cube, Malloy, LookML. These have real
composition semantics and are ahead of every feature store on it. MetricFlow's
measure / dimension / entity split is the right decomposition. **None of them is
bitemporal**, so none can answer *as we knew it*.

**Lenses** — Foster et al. Named because `L-11` is stated over document templates
and is not executable: the compiler regenerates whole documents, so there is no
`put`. The honest reading is that the featureset is where a lens actually exists —
`resolved ← (parents, operations)` is a `get` — and building one to satisfy a law
would be building the wrong thing.

### The competitive position, stated honestly

**No feature store has an algebra.** Feast is deliberately un-opinionated;
Tecton's composition is Python function composition, so it is untyped and
un-analysable; Databricks leans on Delta time travel at table granularity;
Hopsworks is genuine prior art for featureset versions and worth citing as such.

**The semantic layers have an algebra and no time.**

MAYA has both, and that is a position rather than a slogan: the lattice is tested,
the `AsOf` law is tested, and composition type-checks.

---

## 10. What is not built

Stated here as well as in [00 §12](00-mathematical-foundations.md), because a gap
recorded in one place is a gap somebody has to go looking for.

| | |
|---|---|
| **`L-6`** abstraction soundness | needs a replay that checks a document's quantitative claims against the register; the replay exists for validation episodes, not for documents |
| **`L-11`** lens laws | needs a `put`; the compiler regenerates whole documents |
| **`L-13`** evidence gluing | no consistency radius is computed anywhere |
| **`L-14`** interaction premium | §6 gives it something to quantify over; the aggregate `ρ` and composite warrants are not built |
| **`L-15`** fibration completeness | needs a plugin loader that refuses to boot on a partial fibre; model classes are strings |
| **`L-17`** contract–serving agreement | needs an online store. Half exists: `serving_namespaces` computes what serving *must* read |
| Featureset morphisms (`Δ/Σ/Π`) | §9; vocabulary borrowed, machinery not built |
| The two diagrams | §7 |

---

## 11. What this lets MAYA say

Each of these is a sentence an examiner can be shown, and each is checked by a
test rather than asserted by a document:

- *A featureset is a point in a lattice, and every substitutability question in
  the platform — schema variance, warrant admissibility, parent refinement — is
  the same comparison in it.* (`L-20`)
- *Reading a featureset at a later moment can only add what became knowable, and a
  read at or after the label always gives the same answer.* (`L-10`)
- *A derived feature's lineage, its ingest clock, its trust and its leakage check
  are four homomorphisms out of one polynomial.* (`L-9`)
- *Two models compose only if their schemas do, so the dependency graph is typed
  and a composite's schema is derived rather than declared.* (`L-21`)
- *Every document about this model, every fit that produced its parameters, and
  every note about the featureset versions it was fitted from: one page, following
  the pins, with the gaps named.*
