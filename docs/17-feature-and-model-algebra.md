# 17 — Strengthening the algebra: features, featuresets, models, and the documentation graph

*A design proposal. Nothing here is built yet; §7 says what I would build first and in
what order, and every part names the law that would make it testable rather than
asserted.*

---

## 0. Why this document exists

Three things in MAYA are called algebraic and only one of them fully is.

**Composition of featuresets is a monoid** and that is asserted, tested (`L-19`) and
load-bearing. Good.

**Everything else around features is a set of operations with rules attached.** `add`,
`drop`, `override` are total and refuse their no-ops; shapes are checked; derived
features have lineage; the point-in-time read has a correctness condition. Each is
right. None of them composes with the others, and none of them has an order — so
questions that ought to be one comparison are bespoke checks written twice.

**Models have a formalism in the paper and a data structure in the code.**
`f : P ⊗ X → D(Y)` is the definition; what the register holds is a URN, a kernel spec
and a DAG of typed edges. `input_to` is drawn as composition and is not checked as
composition.

The cost is not elegance. It is that the same question — *does this thing fit where
that thing was* — is answered by `substitutable()` for schemas, by a hand-written
slot check for `L-W10`, by `refines()` for contracts, and not at all for `input_to`.
Four implementations of one order relation will eventually disagree, and they will
disagree in the direction of permitting more.

---

## 1. What is here now, stated precisely

| Object | Carrier | Operations | Laws that run |
|---|---|---|---|
| Feature | name, entity, dtype, shape, components, owner, lineage | define, derive, seal, transfer | shape conformance; lineage is a DAG; ingest clock = `max` over inputs |
| Derived feature | a term over a whitelisted expression language | — | no path to the label (leakage) |
| Featureset | finite map `slot ↦ type` | `compose` (fold) + `add`/`drop`/`override` | **L-19** monoid: associative, `{}` identity |
| Featureset version | `slot ↦ (feature, view version)` | fill, seal, roll forward | binding pins a Delta version |
| Model kernel | `parameter_kind`, `fit_procedure`, input/output `Schema` | create version | **L-12** variance at alias moves and `L-W10` at warrant issuance |
| Model relation | typed edge in a DAG | relate, unrelate | acyclicity; `input_to` propagates, `derives_from` does not |

Two things to notice. The featureset carrier is a **dict with no order on it**, so
"is A a refinement of B" cannot be asked. And the model relation carries **no type
obligation at all** — `input_to` is recorded, never checked.

---

## 2. Five gaps, named

**G-1 — The featureset monoid has no order.**
Merge-with-rightmost-wins is a monoid on `slot ↦ type`. It is not a lattice: there is
no `⊑`, no meet, no join. So `L-W10` ("the featureset provides what the kernel reads")
is a bespoke loop, and it is *the same relation* as `L-12` ("the replacement is
contravariant in inputs") applied one level out — which the design document already
says in prose and the code does not share.

**G-2 — The edit operations have no laws.**
`add`, `drop` and `override` are total and refuse no-ops. Nobody has asked whether two
edits to *different* slots commute. They should, and if they do it is the property that
lets two teams edit a shared featureset without the merge order carrying meaning. If
they do not, there is a bug nobody would find by testing one edit at a time — which is
the same shape as the stateful-artefact argument in §11 of the paper.

**G-3 — The point-in-time read is a correctness condition, not an operator.**
`event_ts ≤ label_ts ∧ ingest_ts ≤ min(label_ts, as_of)` is checked. It is never
*named* as a relational operator, so its algebraic properties are unavailable:
idempotence, commutation with projection, and — the one that matters —
**monotonicity in `as_of`**. Reading at a later `as_of` should only ever *add* rows
that became knowable later; it must never change a row that was already knowable.
That is precisely the property reproducibility rests on and it is currently believed
rather than tested.

**G-4 — Derived features and evidence use the same machinery and do not know it.**
A derived feature is a term over a small expression language. Its ingest clock is
`max` over its inputs. That is a **semiring homomorphism** from the term algebra into
the max-semiring — structurally identical to the provenance pushforward implemented
for evidence in `L-9`. Two copies of one idea, one of which has laws.

**G-5 — `input_to` is a drawing, not a composition.**
If B consumes A's output, the register records an edge and checks nothing. It should
be refused unless A's output schema satisfies B's input schema — which is
`substitutable()`, already written. Without that, the blast radius is a reachability
query over edges nobody validated, and `L-14` (the interaction premium) has nothing to
stand on.

---

## 3. What the literature and the products actually offer

### Worth borrowing

**Provenance semirings** — Green, Karvounarakis & Tannen, *Provenance Semirings*
(PODS 2007). Already in MAYA for evidence, and `ℕ[X]` is implemented. The same
construction covers derived features: a feature's value is annotated by the polynomial
of the base features it was computed from, and every downstream question — lineage,
ingest clock, trust, cost — is a homomorphism out of it. **G-4 dissolves.**

**Functorial data migration** — Spivak, *Functorial Data Migration*; Wisnesky's CQL /
Conexus. A schema is a category, a schema morphism `F : S → T` induces three functors
`Δ_F ⊣ Σ_F`, `Δ_F ⊢ Π_F` between instance categories. This is the principled form of
"map one featureset onto another's shape": `Δ` is projection/rename (what an
`override` does), `Σ` is union-like, `Π` is join-like. Adopting the *vocabulary* even
without the full machinery makes featureset morphisms a first-class object rather than
a list of edits, and it gives a correct answer to "what happens to the data when the
schema changes" instead of a migration script.

**Bitemporality** — Snodgrass, *Developing Time-Oriented Database Applications*, and
SQL:2011 system-versioned + application-time tables. MAYA's two clocks are exactly
application time and system time. Borrowing SQL:2011's *vocabulary* would let a
practitioner map what they already know onto what MAYA does, and its `AS OF` semantics
are the standard **G-3** wants to name.

**Semantic layers** — dbt MetricFlow, Cube, Malloy, LookML. These are the products
that actually have composition semantics, and it is worth being honest that they are
ahead of every feature store on this. MetricFlow's split of **measure / dimension /
entity** is the right decomposition, and Malloy's *nesting* gives composition an
associative reading. What they lack is time: none of them is bitemporal, and none can
answer "as we knew it".

**Refinement types** — Rondon et al., *Liquid Types*; F#'s units of measure. MAYA's
operating contract already carries `dscr ∈ [-5, 20]` as an *assumption*. That is a
refinement type written somewhere else. Unifying them means a featureset slot's type
can carry its own constraint, an `override` that widens a constraint is a detectable
weakening, and dimensional errors (a rate as 0.05 vs 5, an amount with no currency)
become type errors instead of incidents.

**Lenses** — Foster et al., *Combinators for Bidirectional Tree Transformations*.
Named because `L-11` is stated over document templates and is not executable — there
is no `put`. The honest reading is that the *featureset* is where a lens actually
exists: `resolved ← (parents, operations)` is a `get`, and "edit the resolved view,
push the change back to the right parent" is a `put` somebody will eventually want.

### Worth studying and *not* copying

**Feast** — entities, feature views, feature services, point-in-time joins. The
closest thing to MAYA's shape, and deliberately un-opinionated: no composition, no
types beyond value types, no governance. Its PIT join is the reference implementation
to compare against.

**Tecton** — transformations as a DAG with materialisation and backfill policy. Strong
on freshness; composition is Python function composition, so it is untyped and
un-analysable.

**Hopsworks** — feature groups + feature views + *training datasets as first-class
objects*. This is the one product that has MAYA's featureset-version idea, and it is
worth citing as prior art rather than pretending otherwise.

**Databricks / Unity Catalog** — tables plus lineage, leaning on Delta time travel.
The lineage is table-level; MAYA's is feature-level, which is the finer grain and the
harder one.

**AWS SageMaker / Vertex Feature Store** — online/offline split done well; no
algebra to speak of.

The honest competitive statement: **no feature store has an algebra.** The semantic
layers have one and no time. MAYA can have both, and that is a defensible position
rather than a marketing one.

---

## 4. The proposal — features and featuresets

### A. Make the featureset carrier a bounded lattice

A featureset schema is a finite map `slot ↦ τ` where `τ` is drawn from the type lattice
that `core/domain/schemas.py` already has. Order it:

> `A ⊑ B` iff every slot of `B` is a slot of `A`, at a type no wider.

Read: *A can be used wherever B was expected.* A has at least B's slots — extra ones
are simply not read — and each is no wider, so nothing that fitted B's slot fails A's.

That single relation then answers, with one implementation:

| Question | Today | Under the order |
|---|---|---|
| Does this featureset satisfy the kernel's inputs? (`L-W10`) | bespoke loop | `resolved(fs) ⊑ inputs(kernel)` |
| Is this replacement version substitutable? (`L-12`) | `substitutable()` | the same `⊑`, contravariant in inputs |
| Is this child a refinement of its parent? | not askable | `child ⊑ parent` |
| What do two featuresets have in common? | not askable | their **join** |
| What does anything reading both need? | not askable | their **meet** |

`⊔` (join) is slot-wise: the slots present in *both*, at the wider type. `⊓` (meet) is
the slots present in *either*, at the narrower — which is exactly what the composition
fold computes when the operations are all `add`. So **composition becomes a special
case of the lattice, not a separate mechanism.**

**Laws to test** — a bounded lattice: idempotence, commutativity, associativity of
both operations, absorption, and the two-way link `A ⊑ B ⟺ A ⊓ B = A`. These are
Hypothesis property tests over generated schemas, and they are cheap.

### B. Make the edit operations a monoid *action*

`add`, `drop`, `override` generate a free monoid acting on schemas. Name the action
and the laws follow:

- `drop(x) · add(x, τ) = id` where `x` is absent (add then drop is a no-op)
- `override(x, σ) · override(x, τ) = override(x, σ)` — the later wins, absorbing
- **`op₁ · op₂ = op₂ · op₁` whenever they name different slots**

The third is the one worth having and the one currently untested. If independent edits
commute, two people can edit a shared featureset and the *order* of their edits carries
no meaning — which is the difference between a merge and a conflict. If they do not
commute, there is a defect that no single-edit test can find.

### C. Name the point-in-time read as an operator, and give it its law

Define `AsOf(R, label_ts, as_of)` on a bitemporal relation:

```
AsOf(R, ℓ, a) = argmax_{(event_ts, ingest_ts)} { r ∈ R : r.event ≤ ℓ ∧ r.ingest ≤ min(ℓ, a) }
                per entity
```

Properties to state and test:

1. **Idempotence** — `AsOf(AsOf(R, ℓ, a), ℓ, a) = AsOf(R, ℓ, a)`.
2. **Commutes with projection** — reading fewer columns cannot change which rows are
   admissible.
3. **Monotone in `a`** — `a ≤ a' ⟹` every row admissible at `a` is admissible at `a'`
   *with the same value*. **This is the reproducibility law.** A backfill that changed
   an answer already given would violate it, and today nothing would catch that.
4. **Anti-monotone in restatement** — a restatement adds a row with a later `ingest`
   and never removes one, so `AsOf` at an earlier `a` is unchanged. That is the
   property the two clocks exist for, and it deserves to be a test rather than an
   argument.

### D. Give derived features the provenance polynomial

A derived feature is a term. Annotate each base feature with its variable and evaluate
the term in `ℕ[X]` — the implementation exists. Then:

- **lineage** = the variables of the polynomial (transitive, free)
- **ingest clock** = pushforward into the max-semiring
- **leakage** = "the label's variable appears in the polynomial" — a membership test
  rather than a graph walk
- **trust / cost / freshness** = pushforwards, for free

One traversal, and the ingest-clock rule stops being a rule anybody could forget: it
is a homomorphism, and homomorphisms do not have exceptions.

---

## 5. The proposal — models

### E. Make `input_to` a checked composition

If `A` is `input_to` `B`, refuse the edge unless `output(A) ⊑ input(B)` under §4A's order. The
implementation is `substitutable()`, already written and already tested.

Consequences:

- **Composite models become expressible.** `B ∘ A` has input `input(A)` and output
  `output(B)`, derived rather than declared.
- **Composite warrants** (FR-WARRANT-017, Phase 5) fall out: a warrant for a composite
  is the composite of warrants for its parts, and the grammar checks the join the same
  way it checks a single one.
- **`L-14` becomes approachable.** With composition typed, `ρ(g ∘ f) ⊒ ρ(g) ⊔ ρ(f)` has
  something to quantify over, and the **interaction premium** — the amount by which a
  composite is riskier than its parts, which is what supervisors ask about and nobody
  computes — becomes a number with a definition.
- **Tensor as well as composition.** Two models run side by side on shared inputs is
  `f ⊗ g`, and that is where shared dependencies live. `shared_dependencies` already
  computes the set; typing it says what the *combination* reads.

### How a model should be represented, and shown

The register holds the right things and shows them as a list of cards. The definition
is `f : P ⊗ X → D(Y)` and a reader cannot see it on the page. I would add, at the top
of the model page, **the model as its type**:

```
credit.pd.smallbiz @ 1.0.0

    P  ⊗  X                    →        D(Y)
    ───────                             ─────
  coefficients   dscr : ℝ[-5,20]     Bernoulli
  (3, approved   turnover : ℝ⁺        over
   ps-8817)      ─ from sb_core@v1 ─  pd_12m : [0,1]

  T3 · estimated_coefficients · estimate · runtime estimator
```

Four things a reader currently assembles from four cards, in the shape the platform
claims to be organised around. Everything in it is derived; nothing is typed by hand.

Beneath it, two diagrams the platform has the data for and does not draw:

- **The featureset fold** — parents → operations → resolved, so a reader can see
  where each slot came from and which parent lost.
- **A string diagram of composition** — boxes for models, wires for schemas, `input_to`
  edges as composition and shared inputs as tensor. The research deck draws these by
  hand; the register could draw them from the edges, and a wire that does not type-check
  would be visibly broken rather than silently recorded.

---

## 6. Documentation as a graph, not a list

This is the part where the current design is furthest from what the work actually
looks like.

### What actually happens

A model accumulates documentation at **different moments, about different objects**:

1. **Before anything runs** — the methodology paper, the literature the approach comes
   from, the design note, the vendor's white paper. About the **model**.
2. **When a version is created** — the specification of that kernel. About the
   **version**.
3. **When a fit warrant executes** — the training record: which featureset version,
   which window, which diagnostics, whose engine, what the estimator reported. About
   the **parameter set**, and there will be one of these per fit, which is one per day
   for a calibrated model.
4. **When a featureset is built** — the definition note, the data dictionary, the
   source-system agreement. About the **featureset version**, and shared by every model
   fitted from it.
5. **When validation concludes** — about the **validation episode**.

Today, attachments bind to a model or a version, and four document kinds compile. A
training run has nowhere to put its record, and a featureset's documentation is
invisible from the model that depends on it.

### The proposal

**One: extend the subject vocabulary.** An attachment's subject becomes any of
`model`, `model_version`, `parameter_set`, `featureset`, `featureset_version`,
`feature`, `validation`. This is a small change to `core/attachments` and it is the
change that makes the rest possible.

**Two: a compiled `training_record`.** When a fit produces a parameter set, MAYA can
compile the record of *that fit* from what it already holds — the warrant, the
featureset version and its bindings, the window, the `as_of`, the diagnostics, the
engine's identity, who reviewed it and what they said. It is a fifth document kind,
compiled by the same lens machinery, which means it **cannot drift from the register**
and it exists whether or not anybody wrote a note. A model with two hundred daily
calibrations then has two hundred training records that nobody had to write, and the
one somebody *does* need to explain has a place for the note.

**Three: the dossier — the holistic view.** Documentation is a *graph* whose edges are
the pins that already exist:

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
           ├── compiled: featureset definition
           └── feature dscr
                └── attached: business definition note
```

A **dossier** is that graph, walked from a model, rendered as one page and carried
whole into the export pack. Three properties make it worth building rather than
listing:

- **It follows the pins, not the names.** The training record links to
  `sb_core@v1`, not to `sb_core`. A document that referenced the *set* would describe
  something that has since moved — finding C-2, in documentation's clothing.
- **Staleness propagates.** A compiled document already computes staleness from the
  evidence chain head. A dossier is stale if *any node beneath it* has moved, and it
  says which — so "is this model's documentation current" is one answer instead of
  eleven.
- **It has gaps, and says so.** The same discipline the export pack uses: a featureset
  with no data dictionary is a gap named in the dossier, not an absence a reader has to
  notice.

**Four: what a dossier must refuse.** It must not resolve personal data (L-18 again),
and it must not present a document attached to `sb_core@v2` as though it described the
`@v1` this model was fitted from. That second one is the whole reason to build this as
a graph rather than a search.

---

## 7. What I would build, in order

Each step is independently useful and each ends with a law that runs.

| # | Work | Law it makes executable | Why this order |
|---|---|---|---|
| 1 | **Featureset lattice** (`⊑`, `⊓`, `⊔`) over the existing type lattice; rewrite `L-W10` to use it | lattice laws; `L-W10` and `L-12` become one relation | Everything else leans on the order. Smallest change, largest unification |
| 2 | **Operation commutation** for independent edits | the monoid action's laws | Cheap, and it either confirms a property people rely on or finds a real defect |
| 3 | **`AsOf` as a named operator** with its four properties | **L-10** strengthened from "static rejection" to a monotonicity law | This is the reproducibility guarantee; today it is believed |
| 4 | **Provenance polynomial for derived features** | **L-9** extended from evidence to features | The machinery exists; this is mostly plumbing and deletion |
| 5 | **Typed `input_to`** + composite schema derivation | a new `L-20`: composition type-checks | Unlocks composite warrants and gives `L-14` something to quantify over |
| 6 | **The model as its type**, on the page | — | The cheapest change here and the one a user notices first |
| 7 | **Attachment subjects** widened | — | Prerequisite for 8 |
| 8 | **`training_record`** compiled per parameter set | — | Fills the gap the daily-calibration case exposes |
| 9 | **The dossier** — graph walk, page, into the export pack | staleness propagation | The holistic view, and it needs 7 and 8 first |
| 10 | **String diagram** of composition on the model page | — | Best done after 5, when the wires type-check |

Steps 1–4 are a fortnight of careful work and they turn four bespoke checks into one
order and two homomorphisms. Steps 7–9 are the documentation ask and are mostly
additive. Step 5 is the one that changes what MAYA can *claim*, because it is what
makes the paper's monoidal structure real in the register rather than in the prose.

---

## 8. What this would let MAYA say that it cannot say today

- *"A featureset is a point in a lattice, and every substitutability question in the
  platform — schema variance, warrant admissibility, parent refinement — is the same
  comparison in it."*
- *"Reading a featureset at a later moment can only add what became knowable; that is a
  law, not a convention."*
- *"A derived feature's lineage, its ingest clock, its trust and its leakage check are
  four homomorphisms out of one polynomial."*
- *"Two models compose only if their schemas do, so the dependency graph is typed and
  the interaction premium has a definition."*
- *"Every document about this model, every training run that produced its parameters,
  and every note about the featureset versions it was fitted from — one page, following
  the pins, with the gaps named."*

Each of those is a sentence an examiner can be shown and a competitor cannot say.
