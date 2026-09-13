# 00 — Mathematical Foundations

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

---

## 0. What this document is for, and the rule it obeys

A model estate throws up the same few questions thousands of times a year. *Is this a model at all?
May this version replace that one? Does this featureset provide what that kernel reads? What
supports this claim? Was this training set honest? Is this obligation set coherent?* Each of them
can be answered by opinion, and each of them is answered by opinion in most of the tooling that
exists. An opinion cannot be tested, cannot be reproduced, and cannot be defended to somebody who
disagrees.

So each question here is given a **structure** that decides it, and the structure earns its place
only by paying rent:

> An abstraction is admitted only if it delivers a property we would otherwise have to hand-build,
> hand-check or hand-migrate — and only if that property can be stated as a law a machine can find
> false.

Mathematics that is merely elegant is recorded in §13 and not implemented. The rent an abstraction
pays is a **law**, and §12 states every law with whether it runs. Where a law runs, a failure fails
the build. Where it does not, §12 says so by name, because an unexecuted law is a claim about a
design, and a document that lets the two look alike has stopped being a foundation and become a
brochure.

**Eighteen of the twenty-one foundational laws are executable** today. The four that are not are
`L-6`, `L-11` and `L-13`, each named in §12 with the reason. That list is
itself asserted in `tests/test_laws.py`, which reads this document's table and fails if the two
disagree — so the count above cannot quietly drift from the code.

### Category theory, or a representation theorem?

Both, at different scales, and it is worth being exact about which does what.

**Category theory is the spine**, because the questions that dominate model management are
compositional and structural: how does a model built from other models inherit their properties?
When may B replace A? How do we add a kind of thing without disturbing the kinds already there?
Those are the questions category theory was built for, and it answers them with laws —
functoriality, naturality, universal properties — that turn into tests.

**Representation theorems are local tools.** Three earn their place. The **Yoneda lemma** licenses
identity-by-behaviour, and with it the honest caveat that such a claim is only as strong as the
probe set (§4.3). **De Finetti's theorem** is why a fitted "population parameter" is a meaningful
object at all, and says precisely when the exchangeability behind a training set fails — a
validation test rather than a formality. **Representable Markov categories** are the bridge that
lets a model returning a point estimate and one returning a predictive distribution be the same kind
of thing (§2.4).

---

## 1. The four failures that made this necessary

Not abstraction for its own sake. Each structure below closes a failure that had already been paid
for — three of them in the industry, and the fourth in this codebase.

| Failure without formalisation | Root cause | What answers it |
|---|---|---|
| adding a model class — a quantum-annealing optimiser, a differential-privacy mechanism — needs a schema migration and touches every module | the class was baked into the schema instead of being a **fibre** over it | fibrations, §8 |
| adding a regulator needs "scope" to be re-modelled, because scope was a boolean | regimes were treated as attributes of one logic rather than as **distinct logics with translations** | institutions, §9 |
| lineage, trust scoring, cost attribution and classification propagation are four engines that disagree | they are one computation over different **semirings** | §6 |
| four places asked *does this thing fit where that thing was?* and each answered it its own way | one relation, four implementations | the schema lattice, §3 |

The fourth is worth stating in full because it is the one found here rather than read about.
`substitutable` decided it for an alias move, a hand-written slot loop decided it for a fit warrant,
a contract check decided it for a contract — and **nothing at all** decided it for a dependency
edge, which meant a blast radius that followed edges nobody had validated. Four implementations of
one relation disagree eventually, and the direction is predictable: toward permitting more, because
that is the direction in which nobody files a bug.

### The answer in one page

| Question the platform must answer | Structure | The refusal it makes possible | Law |
|---|---|---|---|
| what *is* a model? | `Para(Stoch)` — parametrised maps into distributions | asking a closed-form pricer for its training set is a type error, not an empty field | `L-3` |
| may this stand in for that? | a **lattice** on schemas; assume–guarantee contracts | an alias move that narrows an input, a featureset that misses a slot, a dependency edge whose ends do not compose | `L-7`, `L-12`, `L-20`, `L-21` |
| what can we say about a box we cannot open? | contracts + Galois connections + probe-relative Yoneda | a summary that understates risk; an equivalence claim resting on three probes | `L-6` |
| how do things compose? | symmetric monoidal structure; a merge monoid on definitions | a composite risk figure presented as the sum of its parts | `L-14`, `L-19` |
| what supports this claim? | provenance semirings, including the universal `ℕ[X]` | a citation that does not in fact support what it is cited for | `L-9`, `L-18` |
| when did we know it? | bitemporal algebra with a named `AsOf` operator | a re-run that quietly improves on the original | `L-10` |
| how is everything indexed? | fibrations | a model class with no evidence schema | `L-15` |
| how do regulators coexist? | institutions and comorphisms | a regime whose encoding changes the truth, or contradicts itself | `L-8`, `L-16` |
| how is risk ordered? | monotone maps and a Galois connection between lattices | a tier that falls when exposure rises | `L-4`, `L-5` |

One of those refusals is **not made today**: `L-6` is stated and does not run, so a
generated summary that understates risk passes unremarked. `L-14` used to sit beside it —
a composite risk figure that nothing computed — and now runs: `core/risk/aggregate.py`
orders the tier lattice and names the obstructions, which is the interaction term
expressed as *what is unassessed* rather than as a magnitude nobody could defend. The row
says what the structure licenses; §12 says what is checked, and the two are deliberately
not the same column.

---

## 2. What a model is

### 2.1 The definition

A **Markov category** is a symmetric monoidal category in which the unit is terminal and every
object carries a commutative comonoid structure — a *copy* and a *discard* — compatible with the
tensor. Morphisms behave like Markov kernels: stochastic maps that compose, run in parallel, copy
and discard. The canonical example is `Stoch`, the Kleisli category of the Giry monad. *Deterministic*
morphisms are exactly those that commute with copying.

That gives stochastic behaviour and not parameters. For parameters, the **Para construction**: a
morphism `X → Y` in `Para(C)` is a pair `(P, f : P ⊗ X → Y)` — a parameter object together with a
map that consumes parameters and input. Composition tensors the parameter objects.

> **A model is a morphism in `Para(Stoch)`:** a triple `(P, X, Y)` with a kernel `f : P ⊗ X → D(Y)`,
> where `P` is the parameter object, `X` the input object and `Y` the output object.

### 2.2 Why that covers the whole estate

The nine trainability classes of [02](02-model-taxonomy.md) are not nine kinds of object. They are
nine answers to one question — **how is `P` inhabited?** — each characterised by a fitting morphism
`φ : D → P` from some evidence object.

| Class | Parameter object `P` | Fitting morphism `φ` |
|---|---|---|
| **T0** analytical | `1`, the terminal object — no parameters | none; there is nothing to fit |
| **T1** market-calibrated | calibration parameters | a solver over the calibration instruments, re-run daily |
| **T2** statistically estimated | coefficients | an estimator over a dataset snapshot |
| **T3** machine-learned | weights and hyperparameters | a training run |
| **T4** adaptive / online | time-indexed parameters | `φ` is itself a process, run continuously |
| **T5** foundation / pretrained | base weights, prompt, corpus, tools, guardrails | configuration, retrieval, an optional adapter fit |
| **T6** vendor black box | `P` exists and is **not accessible**; only `f(P, −)` is observable | external and opaque |
| **T7** expert judgment | weights and thresholds | an elicitation protocol over a panel |
| **T8** deterministic rule / EUC | a rule set: ordered rules, first match wins, a stated `otherwise` | policy authoring — `φ` is a person, and that is what `declared` provenance means |

`ParametricKernel.trainability_class` computes this and stores nothing: T6 if `P` is inaccessible,
T0 if `P` is terminal, T4 if the procedure is training and the model is adaptive, otherwise the
class the fit procedure implies. There is no `trainability.py`, because there is nothing to keep.

Three consequences that are immediately operational.

**One interface.** The register needs `parameter_object`, `input_object`, `output_object` and a
`fitting_procedure` that may be null. It does not need a `TrainedModel` table beside a
`PricingModel` table. This is the formal answer to *some models are never trained*: training is not
part of the definition of a model, it is one way of inhabiting `P`.

**T0 is not a degenerate machine-learning model; it is the case `P = 1`.** Asking a Black–Scholes
implementation for its training set is a type error, and the platform says so precisely rather than
by convention. `requires_fitting_evidence` is exactly `class ∉ {T0, T6}`, and it is the predicate
the warrant grammar refuses on.

**T6 is characterised by inaccessibility of `P`, not by its absence.** That is why the evidence
schema for a vendor model demands *behavioural* evidence — own-outcomes analysis, benchmarking —
rather than developmental evidence. The mathematics says the only thing observable is the composite.

### 2.3 Two of the three letters became objects

`f : P ⊗ X → D(Y)` names three things, and for a long time only the morphism had a home: a model
version was the record, and `P` and `X` were fields on it. Both are registrable objects now, and
each closes a question the other shape could not answer.

**`X` is a featureset.** It declares a schema of named slots; a *version* of it binds every slot to
a feature and to the exact feature view version supplying the values. The kernel reads the **slot**,
so swapping a constituent does not change `X` — it changes what the model was *fitted on*, which is
a different event with a different control. A version that cannot fill the schema is refused: it is
a different featureset, or it is a model change, and the register decides which.

**`P` has its inhabitants.** A fit produces a **parameter set** and not a new model version, because
the kernel did not change. Minting a version per retrain would make *"the model changed"* mean two
different things, and the more common meaning would win. A parameter set nonetheless changes
behaviour, so it is immutable, versioned, accepted only against a warrant MAYA issued, named by the
featureset version that produced it, and approved by somebody other than whoever recorded it.

**One inhabitant of `P` has a structure the platform can read.** For every other class the values
are numbers, and MAYA holds them, digests them and refuses a run at an unapproved point without ever
knowing what they mean. For **T8** the point of `P` is a rule set somebody wrote, and `core/rules/`
gives it a shape — a tree of `field op value` with `all`/`any`/`not`, no arithmetic — over which four
questions are decidable that are undecidable over a free expression: does every input reach an
outcome, can this rule ever fire, do two rules disagree, and does every field a rule reads exist in
the version's `input_schema`. That last one is the `refines` question again, asked of a read-set
instead of a schema — the same order, asked directly rather than routed through
`core/domain/lattice.py`. The gain is not convenience; it is that a governed object stopped being opaque to the thing
governing it. [02](02-model-taxonomy.md#t8-the-fibre-that-was-least-served) states the boundary that
keeps this from being a training tool, and states precisely how incomplete the reachability analysis
is.

Specification: [15 — X and P](15-featuresets-and-parameters.md).

### 2.4 Determinism is a property, and the output type is an object

In a Markov category, `f` is deterministic iff `copy ∘ f = (f ⊗ f) ∘ copy`. MAYA stores this as a
first-class flag because it has a governance consequence: a non-deterministic model cannot be
reproduced by re-execution alone, so its reproducibility evidence must pin the random source. That
is `L-3`, and it is checked both ways — the estimator runtime is run twice on identical input and
compared bit for bit, and a determinism claim with no seed is **refused** wherever the runtime
executes code MAYA cannot read (`L-W5`). A flag that is only ever asserted is a flag that will
eventually be wrong.

A model returning a point estimate and one returning a full predictive distribution differ in `Y`,
not in kind. In a **representable** Markov category, kernels `X → Y` correspond to deterministic
maps `X → P(Y)`; MAYA exploits this to hold predictive distributions as a first-class output type
and treat point predictions as the deterministic section. That is what lets calibration tests —
reliability diagrams, PIT histograms — and interval-based monitoring be defined once rather than per
family.

---

## 3. When may one thing stand in for another?

This is the question the platform asks most often, and until recently it had four answers.

`core/domain/lattice.py` holds one order on schemas:

> **`A ⊑ B`** iff `A` has every field `B` has, each accepting **at least** what `B`'s accepted.

Read it as *A can stand in for B*. `A` may carry extra fields — they are simply not read — and each
shared field must accept at least what `B`'s did, because a replacement that rejects an input its
predecessor took is a replacement that breaks a caller.

> **A correction worth recording.** An earlier design note said a refinement is "at a type no
> wider". That is backwards, and the code had it right while the prose did not. Standing in for
> something requires accepting **at least** what it accepted, so a wider acceptance is fine and a
> narrower one regresses. The intuition that misled was *a subtype is narrower*, which is true of
> the values and false of the acceptance.

`refines` returns two failure modes rather than a boolean, because they have different remedies:
**`missing`** (fields `B` has that `A` does not — the wrong thing was bound) and **`narrowed`**
(fields `A` has that accept less — somebody tightened a constraint without noticing it was a
promise).

### 3.1 It is a lattice, and the partiality is the useful part

| | | |
|---|---|---|
| **meet** `A ⊓ B` | the **union** of the fields, each widened to accept both | what a featureset must provide to serve two models at once |
| **join** `A ⊔ B` | the **intersection** of the fields, narrowed to what both accepted | what a consumer of either may rely on |
| **top** | the empty schema | it demands nothing, so everything can stand in for it |

There is no bottom, and saying so matters: a least element would have to carry every field name that
could ever exist. The structure is a lattice on each finite fragment, which is the only fragment
anything here inhabits.

**Meet is partial.** Two schemas whose shared slot carries two different dtypes have no meet — no
schema accepts both a number and a string in one slot — and the honest answer to *can one featureset
serve both these models* is then **no**, with the slot named. It raises `NoMeet` rather than
returning `None`, because the caller has a decision to make, and a `None` threaded through three
layers becomes a silent empty schema somewhere.

`L-20` asserts, over three hundred generated triples: reflexivity, transitivity, meet below both,
join above both, idempotence, commutativity, associativity, absorption, and the link
`A ⊑ B ⟺ A ⊓ B = A` that makes it a lattice *order* rather than an order beside two unrelated
operations.

### 3.2 What now goes through it

| Question | Before | Now |
|---|---|---|
| is a replacement version substitutable? (`L-12`) | `accepts_superset_of` | `refines`, with `provides` for the covariant half |
| does this featureset provide what the kernel reads? (`L-W10`) | a bespoke slot loop | `refines(resolved, kernel_inputs)` |
| does a dependency edge type-check? (`L-21`) | **it did not ask** | `refines(output(source), input(target))` |
| what must a featureset provide to serve both? | not askable | their meet |
| what do two versions agree on? | not askable | their join |

The variance rule is the familiar one and now has one implementation: a replacement is
**contravariant in inputs** and **covariant in outputs**. The covariant half is judged only on name
and dtype, deliberately more coarsely than the inputs, because narrowing the range of something you
*produce* is a promise kept more tightly rather than one broken.

**One thing is not unified, and the document should not pretend otherwise.** Contract refinement
(`L-7`) is a different relation, over the *bounds* of an assume–guarantee pair rather than over
schema fields, and it is not routed through the lattice. Three of the four callers are one relation;
the fourth is a cousin.

### 3.3 Composition is typed, and a composite's schema is derived

An `input_to` edge asserts that what one model produces arrives where another reads it. Recorded and
never checked, it was a **drawing**: a blast radius followed edges nobody had validated, and `L-14`
had nothing to quantify over.

It is now refused unless the ends compose. Extra outputs are fine — simply unread. A missing output
is a wire to nowhere. A narrowed output is the same regression `L-12` names at an alias move, one
level out. Where either end has no version yet the edge is recorded **without** a type check and the
log says so, because refusing an edge for a schema nobody has decided would make the register harder
to build than the estate is to describe. `challenger_of` and `benchmark_for` are not type-checked at
all: they record how somebody thinks about a model, and there is no wire.

`composite_schema(A, B)` then derives the type of `B ∘ A` — the source's inputs, the target's
outputs, with the wire elided precisely because it has been proved to compose. **Derived, never
declared**: a composite whose schema somebody wrote down is a composite that can disagree with its
parts.

> **On the name.** The relation was called `feeds`, and that was a bad name in a bank, where a
> *feed* means market data or a nightly file — so `A feeds B` read as though MAYA consumed or
> produced one. It does neither: MAYA moves no data and runs no model. `feeds` is still accepted on
> the way in and stored as `input_to`, and is deliberately not published in the vocabulary, because
> offering two words for one relation invites somebody to believe they differ.

---

## 4. What can we say about a model we cannot open?

Three tools, all needed, because they answer different questions.

### 4.1 Assume–guarantee contracts

A **contract** is a pair `C = (A, G)`: an assumption about the environment and a guarantee about
behaviour when the assumption holds. Contract theory supplies an algebra.

| Operation | Meaning | Where it is used |
|---|---|---|
| **refinement** `C' ⪯ C` | weaker assumption, stronger guarantee | *may B replace A?* — decided, not discussed |
| **composition** `C₁ ⊗ C₂` | the contract of the composed system | what a model chain promises end to end |
| **conjunction** `C₁ ∧ C₂` | satisfy both viewpoints | merging a performance, a fairness and a latency contract on one model |
| **quotient** `C / C₁` | what the missing component must guarantee | *given the target and what we have, what must the challenger deliver?* — a validation gap turned into a specification |

The mapping is exact, and it is the formal content of the operating-boundaries requirement:
**assumption `A`** is the input domain, valid ranges, population definition, market regime, data
freshness and upstream contracts; **guarantee `G`** is the performance envelope — accuracy,
discrimination, calibration, latency, fairness bounds, output range, explainability.

Two consequences no surveyed product provides. Off-boundary use is a contract violation detected
mechanically: when `input ⊨ A` fails, the guarantee is formally **void**, which is a much stronger
and more defensible statement than *the input looked unusual*. And refinement gives version
compatibility for free: promoting a challenger is permitted iff its contract refines the champion's,
which is a proof obligation MAYA discharges rather than a judgement in a meeting.

Two details of `refines` are decisions rather than accidents. **An absent assumption is the weakest
possible**, so only keys present in both are compared — a replacement that declines to constrain
something its predecessor constrained is accepting more, which is exactly what refinement permits.
**An absent guarantee is a promise withdrawn**, and fails. The asymmetry is the whole content of the
relation.

The same asymmetry decides the three operations, and it is what keeps them from collapsing into one
another. Both are written over two partial operations on a single `Bound`: **meet**, the strongest
band admitting what both admit, and **join**, the weakest band admitting what either does.

- **Composition `⊗`** wires two components together, so its guarantees **meet** — both promises are
  made — and its assumptions are what the *caller* must still supply. A downstream assumption that
  the upstream's guarantee **implies** is discharged inside the pair and asked of nobody outside. An
  upstream that speaks to the key without implying it discharges nothing, and MAYA reports that key
  separately: it is the case where somebody wired two models together believing the boundary was
  covered.
- **Conjunction `∧`** puts two viewpoints on *one* component. Its guarantees also meet, but its
  assumptions **join**, which reads backwards until it is said out loud: a contract promises nothing
  outside its assumptions, so a model holding both is entitled to the union of the regions they
  cover, and an assumption only one viewpoint makes constrains nothing — the other promised its
  guarantee without it. Intersecting here would narrow where a model may be used every time somebody
  added a viewpoint, which is the opposite of what adding one means.
- **Quotient `/`** discharges a target guarantee only where what we already have **implies** it.
  A partner that speaks to the key without meeting it discharges nothing and the residual carries
  the requirement in full — a challenger promising `gini ≥ 0.2` does not satisfy a target of
  `gini ≥ 0.4`, and an empty residual reads as *nothing more is needed*. The residual may **rely**
  on what the partner guarantees, so those become its assumptions alongside the target's own.

Both operations are **partial**, and where they do not exist MAYA refuses rather than approximating.
Two bands with a gap between them have no join: `[0,1] ∪ [5,6]` is not a band, and `[0,6]` is not it
— widening to span the gap would claim a contract holds at 3, where neither of the contracts it came
from says anything at all. Two guarantees that exclude each other have no meet, and a combination
that quietly kept one of them would promise less than one side committed to. This is the same
decision, for the same reason, as `NoMeet` in the schema lattice of `L-20`.

### 4.2 Galois connections and sound summaries

A **model card is an abstraction of a model**, and abstract interpretation says exactly what makes
an abstraction trustworthy. With `Concrete` the lattice of behaviours and `Abstract` the lattice of
summaries, a Galois connection `α ⊣ γ` satisfies `α(c) ⊑ a ⟺ c ⊑ γ(a)`, and **soundness** is
`c ⊑ γ(α(c))`: the summary never *excludes* real behaviour.

> **The soundness law.** Every generated artifact that stands in for a model — model card,
> documentation section, risk summary, tier — must be a **sound over-approximation**. It may
> overstate risk; it must never understate it.

It also settles the perennial question of how much detail belongs in a model card: as much as keeps
the abstraction sound at the required precision, and no more.

**This is `L-6`, and it does not run.** The check would replay a document's quantitative claims
against the register; the replay exists for validation episodes and not for documents. The law is
stated because knowing which direction an artifact is allowed to be wrong in is worth having even
unenforced — but stating it is not enforcing it, and §12 records that.

### 4.3 Identity by behaviour, relative to a probe set

Yoneda says an object is determined by the totality of maps into it — an object *is* what it does.
Applied here: a model is determined by its responses to all probes. We cannot enumerate all probes,
so identity is defined **relative to a declared set**:

> Let `Π` be a finite set of probes with their expected-property assertions. Two versions are
> **Π-equivalent**, `v₁ ≡_Π v₂`, iff they agree on every probe in `Π` within declared tolerance.

That makes version semantics precise. A **PATCH** is `v_new ≡_Π v_old` on the regression probe set —
an implementation change with *proven* behavioural equivalence. A **MINOR** is the same `(P, X, Y)`
and the same `φ`, with a new inhabitant of `P`. A **MAJOR** changes `φ`, `P`, `X` or `Y`: a
different morphism.

And it forces the caveat no product states: **equivalence is only as strong as `Π`.** So `Π` is
stored with every equivalence claim and its coverage is measured.

> **State, stated.** `pi_equivalent` and its coverage measure are implemented in
> `core/domain/identity.py` and exercised by the domain tests. They are **not wired into version
> promotion**: nothing today refuses a PATCH bump for a thin probe set. The definition had to be
> right first; the gate is not built, and calling it built would be exactly the failure this section
> exists to make checkable.

---

## 5. How things compose

### 5.1 The dependency graph is a string diagram

`Para(Stoch)` is symmetric monoidal, so model networks are string diagrams: boxes wired together,
with sequential composition, parallel composition, copying (one model's output read by two
consumers) and discarding. The yield-curve → pricer → XVA → RWA chain of
[02 §12](02-model-taxonomy.md#12-cross-cutting-the-feederconsumer-graph) is a morphism in this
category, built from generators.

This is not analogy. It gives typed composition (§3.3); a **blast radius that is the downstream
closure** of a node, so the graph structure is the computation rather than a report generated beside
it; **parameter accumulation**, since composing `(P, f)` and `(Q, g)` yields parameter object
`Q ⊗ P`, which is precisely why a curve recalibration is a change event for everything downstream;
and the observation that Petri nets generate free symmetric monoidal categories, so concurrent
approval workflows — parallel approvers, joins, quorum — live in the same formal world as model
composition. That last one is an observation and not a shared implementation: quorum approval is its
own code, and saying otherwise would be claiming a reuse that does not exist.

### 5.2 Aggregate risk is *lax* monoidal — and that is the regulator's point

SR 26-2 says aggregate model risk "reflects interactions and dependencies among models; reliance on
common assumptions, data, or methodologies". Let `ρ` assign each model a risk value in a lattice.
If `ρ` were a **strict** monoidal functor, `ρ(g ∘ f) = ρ(g) ⊔ ρ(f)`: aggregate risk would be the
join of component risks, and could be computed by a spreadsheet.

It is not. `ρ` is **lax**:

```
ρ(g ∘ f)  ⊒  ρ(g) ⊔ ρ(f)
```

The gap is the interaction term — shared dependencies, common assumptions, error amplification —
which is exactly what the guidance is asking about. Making laxity explicit turns a vague sentence
into a computable quantity, and it is also the reason the board pack **refuses to produce a single
model-risk score**: an aggregate that composed strictly would be a number that is wrong in a known
direction.

**`L-14` is built**, and the shape of it is the argument. `core/risk/aggregate.py` computes `ρ` as
the risk **tier** and the interaction term as a set of **named obstructions** — never a magnitude.
That is not a limitation working around a missing model; it is the honest form of the answer. A
premium with a coefficient in it is a number somebody has to defend, and no coefficient here could
be. What can be defended is that a particular interaction is *present*, and that the composite is at
least as risky as its parts.

Six obstructions, each read from something the register already holds: a shared upstream
(`shared_dependencies`, which was always the computable part of this), an `input_to` edge admitted
without a type check, a boundary the source speaks to and does not settle (§4.1's composite
contract), two contracts that cannot both hold, a tier inversion, and an untiered component. The
composite escalates one step per *kind* of interaction rather than per instance: three shared
dependencies are more interaction than one, but a four-point scale cannot honestly express "three
times", and what it can express is *this pair interacts in two distinct ways*.

One choice in the lattice is load-bearing and reads backwards until it is said out loud. **An
unassessed component is the top, not the bottom.** The join of *tier 4* and *not assessed* is *not
assessed*, because a pair is only as well understood as its least understood half — and treating
`None` as least risky would make the aggregate of an untiered estate look excellent, which is the
failure this whole platform is written against.

### 5.3 Composing *definitions* is a monoid

Underneath the composition of models runs a humbler one that carries more weight day to day:
composing the definitions of features and featuresets, where one object inherits from a parent or
combines several.

Inheriting from one parent and combining several are the same operation at different arities, so
there is one mechanism. Members resolve by a **left-to-right fold in which the rightmost wins**, and
an object's own operations are applied last:

```
resolve(x) = apply( merge( fold(parents), members(x) ), operations(x) )
merge(a, b) = b overrides a, key by key
```

Merge-with-rightmost-wins over a keyed map is **associative** with the empty map as **identity**, so
composition is a monoid. That is `L-19`, and it is not decoration: it is what makes *"a combination
of features is a feature"* a statement rather than an aspiration. Grouping does not matter, so
`(a·b)·c` and `a·(b·c)` cannot disagree. Without associativity, the order in which a reviewer *read*
a composition could differ from the order the platform *resolved* it, and neither would be wrong.

Two things follow from the algebra rather than from taste.

**Every operation is total.** An `add` of something a parent already has, a `drop` of something no
parent has, and an `override` of something no parent has are each refused. The no-op alternative
leaves a child quietly differing from what its author wrote, which is a divergence nobody is looking
for.

**Independent edits commute.** Two edits naming *different* members produce the same result in
either order — asserted over sixty generated pairs. That is what lets two people edit a shared
featureset and have the order of their edits carry no meaning: the difference between a merge and a
conflict whose resolution is itself a decision. Dependent edits are deliberately **not** claimed to
commute, and `override` then `drop` of the same slot is not `drop` then `override` — the second
order is refused.

The same fold is reused for retrieval policy and for warrant profiles, so a reader who has learnt
the precedence rule once has learnt it everywhere. Specification:
[16 — Five things a feature is not](16-features-composed-and-shaped.md).

---

<a id="92-one-engine-many-analyses"></a>

## 6. What supports a claim?

### 6.1 Evidence is an annotated derivation

Green, Karvounarakis and Tannen showed that provenance, bag semantics, probabilistic databases,
access control and incomplete information are **the same computation over different commutative
semirings**. Annotate each base fact with an element of `K = (K, ⊕, ⊗, 0, 1)`; relational algebra
then propagates annotations using `⊗` for joint dependence (a join: *this AND that*) and `⊕` for
alternative derivations (a union: *this OR that*).

MAYA's evidence graph is exactly that. Every derived governance claim — *model M is validated*,
*version v is reproducible*, *this figure in the document is current* — is computed from base
evidence nodes by `⊕` and `⊗`.

### 6.2 One traversal, six questions

**The same evidence computation, evaluated in different semirings, answers different questions.**

| Annotation | `⊕`, `⊗` | The question it answers |
|---|---|---|
| `boolean` — `({⊥,⊤}, ∨, ∧)` | or, and | *is there sufficient evidence at all?* — gate evaluation |
| `counting` — `ℕ` under `+`, `×` | plus, times | *how many independent derivations support this?* — corroboration depth |
| `why` — sets of sets of evidence ids | union with absorption, pairwise union | *which minimal sets suffice?* — what an examiner must be shown |
| `trust` — `([0,1], max, ×)` | max, product | *how much confidence does this claim carry?* |
| `cost` — tropical `(ℝ⁺∪{∞}, min, +)` | min, plus | *what is the cheapest path to closing this gap?* — remediation planning |
| `freshness` — `(Time, max, max)` | latest, latest | *as of when is this claim current?* — staleness |

A seventh annotation, `polynomial` — `ℕ[X]` — is not a further question but the object the other six
are homomorphic images of, which is §6.3.

The engine is implemented **once**, generically over `K`. Adding an analysis means defining an
annotation, and it is automatically consistent with the others because they share the derivation
structure. The last row is the one that does not quite belong, and §6.3 says why.

### 6.3 `ℕ[X]` is universal, and that is now a theorem the suite checks

`ℕ[X]` is the *free* commutative semiring: compute once in it, apply a homomorphism `h : ℕ[X] → K`,
and recover the answer in any other `K`. That is `L-9`, and it stopped being an aspiration when the
polynomial was implemented. `pushforward` applies the induced homomorphism — a monomial's exponents
become repeated `⊗`, a coefficient becomes repeated `⊕` — and the law is asserted over **200 random
derivation DAGs against five semirings**: Boolean, counting, trust, cost and why. A thousand checks
that the platform's own claim — *the same traversal answers a different question for each semiring*
— is true.

It also earns its keep one layer across. A **derived feature is a term**: annotate each base feature
with its own variable, evaluate in `ℕ[X]`, and every other question about it becomes a homomorphism
out of one object — what it rests on (the free variables), when it became knowable (pushforward into
the max monoid), whether it touches the label (membership of the label's variable), how far it is
trusted (pushforward into trust). *`ingest(Z) = max` over the inputs* used to be described as
arithmetic, so it cannot be forgotten. It is stronger: it is a homomorphism, **and a homomorphism
has no exceptions to forget.**

> **Writing the law found that `FRESHNESS` is not a semiring.** It is `(max, max)` with
> `zero = one = 0.0`, and `max(0, 5) ≠ 0`, so its zero does not annihilate. It is a commutative
> idempotent monoid used twice, and the universal property does not reach it. The practical
> consequence is precise and worth knowing: **a claim resting on a missing fact reports the
> freshness of the facts that are present**, rather than reporting that it has none. It stays in the
> code, does useful work, and is excluded from `L-9` by a test that says why, so it is not quietly
> re-included.

> **Complexity, stated honestly (finding M-2).** `Why(X)` is worst-case *exponential* in the number
> of alternative derivations, and governance DAGs are not always shallow. The mitigations are
> concrete: canonical form with absorption (`a ⊕ ab = a`), memoisation over subgraphs, and a hard
> term cap of **4,096** that stops accumulating and returns `truncated = true` alongside the partial
> value. Note exactly what that does: it **marks** the answer as partial. It does not fall back to a
> cheaper semiring, and a caller ignoring the marker gets a `Why` set that is a subset of the true
> one. The marker is the control; the partial answer is not silently correct.

### 6.4 What the chain refuses to hold

`L-18`: a node flagged `contains_personal_data` carries **no payload at all** — not an erasable
pointer. It is enforced in the append path rather than in DDL, and the detail that makes it work is
that the node **hashes what it stored**, not what it was given — so an erased node still verifies
against itself and the chain does not break when the right to erasure is exercised.

### 6.5 Gluing: evidence as a sheaf

Provenance says how a claim was derived; it does not say whether independently-produced pieces of
evidence are mutually *consistent*. For that, evidence is a **presheaf** over the structure of a
model — its components, slices, time windows — and *do local validations assemble into a global
claim?* is the **gluing condition** of a sheaf.

Concretely: one validator tests slice A, another tests slice B, both report acceptable performance
on the overlap, and their numbers differ. Sheaf-theoretic data fusion gives a **consistency radius**
measuring how far the local sections are from gluing, and a non-zero radius is a contradiction no
per-section check can see. This is what "effective challenge" as a *global* property would mean.

**`L-13` is not built. No consistency radius is computed anywhere.** The construction is recorded
because it names a real class of defect that nothing currently detects, not because it is close to
shipping.

---

<a id="111-bitemporality-and-the-point-in-time-correctness-theorem"></a>

## 7. When did we know it?

### 7.1 Two clocks

Feature data is **bitemporal**: every fact has a *valid time* (when it was true in the world) and a
*transaction time* (when the system learned it). Training-serving skew and look-ahead leakage are
failures to respect the distinction, and they are the dominant silent failure mode in
[01 §5.2](01-industry-research.md) — silent because a leaked model backtests beautifully.

> **The point-in-time condition.** A training row for entity `e` with label time `ℓ`, assembled as of
> system time `a`, is point-in-time correct iff for every feature the value used is the one with
> `max{ valid_time ≤ ℓ ∧ transaction_time ≤ a }`. A training set is correct iff every row is.

Stated that way it is mechanically verifiable, and MAYA verifies it in three layers rather than
trusting the query author: an assembly missing either clock is **statically refused**; a stratified
sample is independently recomputed; and two leakage screens run over the result. Sampling gives
detection, never absence — the refusal is the part that is a guarantee.

That is the textbook condition, and the read MAYA performs is **stricter than it**. §7.2 is the
reason, and the difference is where reproducibility actually lives.

### 7.2 The read is an operator, and its fourth property is the guarantee

The condition was always checked. The *read* was never characterised, and the read is where
reproducibility actually lives.

```
AsOf(R, ℓ, a) = argmax over (event_ts, ingest_ts) of
                { r ∈ R : r.event ≤ ℓ  ∧  r.ingest ≤ min(ℓ, a) }
```

| Property | |
|---|---|
| **idempotent** | reading the result again returns it |
| **commutes with projection** | admissibility is decided on the clocks alone, so reading fewer columns cannot change which row is chosen |
| **monotone in `a`** | a later `as_of` can only widen what is admissible; nothing knowable stops being knowable |
| **saturating at `ℓ`** | **the reproducibility guarantee** |

The fourth is the one to understand. Because the ingest bound is `min(ℓ, a)`, **every `a ≥ ℓ` gives
the same answer**. A training row assembled the day its label matured and the same row re-assembled
a year later are identical, however many restatements arrived between. Without the `min`, a re-run
would quietly *improve* on the original — the least useful kind of reproducibility, because the
numbers then agree with nothing, including themselves.

That `min` is a repair, not a decoration. The ingest bound used to be `a` alone, and `a` is a single
scalar for the whole assembly, so a fact true before the label and *learned afterwards* was
admitted: knowable at assembly time, not at decision time. Back-filled alignment makes it concrete —
a value first observed in April, carried back onto a March grid point, arrives carrying April's
ingest stamp. Both bounds are kept because they refuse different things: `ℓ` is what the model could
have known when the decision was made, `a` is what the platform could have known when the set was
built.

The worked case, asserted as a test: a March figure ingested in May reads as 1.20; the same March
figure restated in August reads as 0.40. A row labelled in May gets **1.20** whenever it is
assembled. A row labelled in August gets 0.40. That is the leak the two clocks exist to prevent, and
it is the one that scores beautifully in backtest.

Because `a` is explicit, MAYA can also distinguish *the world changed* from *we found out we were
wrong*, and identify exactly which historical training sets, versions and decisions a source
restatement touches.

### 7.3 Documentation as a lens

The relationship between the evidence graph and a document is bidirectional in principle: documents
are generated from evidence, but humans edit narrative sections, and those edits must survive
regeneration. That is an **asymmetric lens**, `get : Evidence → Doc` and `put : Evidence × Doc →
Evidence`, subject to GetPut (regenerating an unedited document changes nothing), PutGet (a human
edit is not silently discarded) and PutPut (edit history composes).

And it would give the definition one actually wants: a document is **stale** with respect to current
evidence exactly when `get(e') ≠ d` on the generated sections, with the diff being precisely *what
changed*.

**`L-11` is not executable, and the reason is that the design went the other way.** There are
fifteen lenses and all of them are `get`. The compiler regenerates whole documents, so there is no
`put` and no round trip to test. The honest reading is that the featureset is where a lens actually
exists — `resolved ← (parents, operations)` is a `get` — and that building a `put` to satisfy a law
would be building the wrong thing.

---

<a id="7-pillar-4--indexing-fibrations-and-the-grothendieck-construction"></a>

## 8. How is everything indexed?

Almost everything here is *a family of things indexed by something else*: versions by model,
parameter sets by version, deployments by environment, inventories by legal entity, evidence schemas
by model class.

The mathematics of indexed families is the **fibration**. A functor `p : E → B` is a fibration when
every morphism in the base lifts cartesianly; equivalently (Grothendieck), a fibration over `B` is
an indexed family `B^op → Cat`.

| Total category | Base | Fibre over `b` | What the lifting means |
|---|---|---|---|
| versions | models | that model's versions | re-owning a model carries its versions canonically |
| parameter sets | versions | that version's inhabitants of `P` | a T1 model recalibrates daily without version churn |
| evidence schemas | model classes | the evidence that class requires | **adding a class adds a fibre — no migration** |
| deployments | environments | what runs in dev, uat, prod | promotion is a cartesian lift |
| inventory views | legal entities | that entity's models | consolidation is a limit over the entity diagram |
| policy sets | jurisdictions | the rules in force there | §9 |

> **Extension property (informal).** Because model classes are the base of a fibration rather than a
> column in a table, introducing a new class — a quantum optimiser, a differential-privacy
> mechanism, a technique nobody has invented — requires supplying a fibre (its evidence schema,
> lifecycle, metric set, templates) and *nothing else*. No existing fibre, table, API or screen
> changes.

That is what makes "every kind of model is fair game" architectural rather than aspirational.

**`L-15` is built, and closing it moved the base.** The law says the base is the *model class*, and
that is wrong — `model_class` is a free-text column, and totality over free text has two resolutions,
both bad. Close the vocabulary, and *"adding a class adds a fibre — no migration"* becomes false.
Leave it open, and the gate is defeated by typing a word nobody registered, which is a gate that
reports success.

The base is the **trainability class**, `T0`…`T8`. It is derived from how `P` is inhabited and never
declared, so the index cannot be typed wrong, extended by accident, or disagree with the model it
indexes. `core/fibres/` holds the nine fibres, `FibreRegistry.verify()` runs at start-up and refuses
to serve on a partial one, and `register()` refuses a partial fibre so the registry cannot hold one
between restarts.

The fibre content was not invented for this. It was already written out class by class in
[02 §5](02-model-taxonomy.md) — what conceptual soundness rests on, what outcomes analysis is, what
monitoring can answer — which is a good sign that this was the real base all along; that document
even calls the T-classes "typical fibre" in its bindings table. It was a fibration written in a table
nothing could read.

`model_class` keeps its job: an organisational label for grouping and reporting. It indexes nothing.

---

## 9. How do many regulators coexist?

### 9.1 The problem

The same model is simultaneously out of scope for SR 26-2, in scope for SS1/23 (whose definition
reaches expert-judgment inputs and qualitative outputs), high-risk under the EU AI Act if it scores
consumer creditworthiness, and a key control under SOX. These are not four values of one attribute.
They are four **different logical systems**, each with its own vocabulary, its own sentences, and
its own notion of what makes a sentence true of an inventory.

Modelling that as a boolean, an enum or a set of tags is the mistake that forces a re-architecture
every time a regulator publishes.

### 9.2 Institutions

An **institution** (Goguen and Burstall's abstract model theory) is a category `Sign` of signatures,
a functor `Sen : Sign → Set` giving the sentences over each signature, a functor
`Mod : Sign^op → Cat` giving the models — here, inventory states — and a satisfaction relation
`⊨_Σ`, subject to the **satisfaction condition**: for any signature morphism `σ : Σ → Σ'`,

```
M' ⊨_Σ'  σ(φ)    ⟺    Mod(σ)(M') ⊨_Σ  φ
```

— *truth is invariant under change of notation.*

| Institution component | Here |
|---|---|
| signature `Σ` | the vocabulary a regime reasons in — SR 26-2 speaks of complexity, exposure, purpose and quantitative theory; the AI Act of intended purpose, deployer, natural persons and Annex III |
| sentence `φ` | one regulatory obligation, expressed in that vocabulary |
| model `M` | the state of the inventory as seen through that vocabulary |
| satisfaction `M ⊨ φ` | **compliance.** A scope determination is `M ⊨ in_scope` |
| comorphism | the translation from a regime's vocabulary into the core signature |

Three regimes are encoded — SR 26-2, SS1/23 and the EU AI Act — over a core vocabulary of
thirty-two terms.

### 9.3 What that buys, and what is checked

**Adding a regulator is adding an institution and a comorphism.** MAS, APRA, OSFI E-23 — each is a
signature, its sentences, a translation, and no change to the core schema, the API or the interface.

**The satisfaction condition is a testable consistency guarantee, and it gates activation.**
Translating an inventory state into a regime's vocabulary and then evaluating an obligation must
give the same answer as evaluating the translated obligation directly. If they disagree, the
translation is wrong — and that is exactly the class of bug that produces a scope determination
nobody can defend to an examiner. `L-8` checks it **over probe states spanning the corners rather
than over generated ones**, which is a weaker claim than a property test and is stated as such; a
regime whose encoding fails it **cannot be activated**. The check also distinguishes two failures
that need different fixes: a sentence reading a term it never declared, and truth genuinely changing
under translation.

**Scope determinations become derivations, not opinions.** *Why is this out of SR 26-2 scope?* is
answered by the derivation of `M ⊭ is_model`, citing the clause and the inventory facts.

### 9.4 An obligation set that contradicts itself cannot be turned on

`L-16` used to be a placeholder waiting for a deontic logic. It no longer is, and the reason it can
run is that the ambition was cut to the decidable part.

A full deontic logic is not what this needs: `holds` is an opaque predicate and consistency over
arbitrary predicates is undecidable. What *is* decidable is the case that actually occurs — **two
sentences in one vocabulary pulling a term in opposite directions**, which is what happens when a
regime is encoded by two people. `deontic_conflicts` finds every term that is both obliged and
forbidden, names both sentences, and activation refuses with `obligation_contradiction`. It is
checked *before* the satisfaction condition, because a regime that contradicts itself makes every
determination unsatisfiable, and the satisfaction condition would report that as something subtler
than it is.

Two exclusions carry the design.

**A conditional obligation is not counted against an unconditional prohibition.** *If it is high-risk
then it must have human oversight* and *it must not run unattended* may simply never both apply, and
reporting that as a contradiction would train somebody to ignore the check.

**What the check cannot read is named rather than assumed clean.** A sentence whose predicate is
opaque contributes nothing to the conflict search, so `undecidable()` returns those sentences by
name and they are recorded on the activation evidence node. A check that quietly ignores what it
cannot judge reports success for exactly the cases it was least able to judge.

### 9.5 Obligations in time

Governance obligations are temporal statements with deadlines, so they are naturally metric temporal
logic:

```
G( tier = 1  →  F[0, 365d] validation_completed )
G( finding.severity = Critical  →  F[0, 30d] (remediated ∨ formally_accepted) )
G( overlay_active  →  F[0, 90d] (reviewed ∨ expired) )
```

Monitors for MTL formulae can be synthesised automatically by standard runtime-verification
constructions, so an obligation engine could in principle be a compiler from declarative
specifications rather than a hand-written scheduler with cases.

> **State, stated.** That compiler is **not built**. What ships is the thing it would have
> generated: **27 idempotent jobs**, each doing one obligation's work — the evidence chain is
> walked and checkpointed only when it verifies; worklists are delivered and unchanged ones
> suppressed; a lapsed attestation and a stalled monitor each raise a finding; overlays past their
> window close; baseline debt reconciles or expires into a breach; a missed remediation window is
> recorded as **its own** finding rather than by rewriting the original's severity; and an
> unacknowledged finding raises a third. Eight hand-written monitors are not an argument against the
> construction; they are what the construction is worth deferring until there are fifty. The
> formulae above are a specification of those jobs, not a description of a compiler.

---

## 10. How is risk ordered?

### 10.1 Tiering is a monotone map

Materiality and complexity are **not** numbers to be added. Following SS1/23 1.3 they are separate
orders: materiality is generated by quantitative exposure joined with qualitative purpose
(*regulatory capital* ⊐ *financial reporting* ⊐ *risk management* ⊐ *commercial*), and complexity is
built from its declared components — data quality, methodology, implementation integrity, use
intensity, interpretability, opacity of the model family.

Tier is a **monotone map** `τ : M × C → Tier` into a finite chain `Tier₄ ⊏ Tier₃ ⊏ Tier₂ ⊏ Tier₁`.

> **Monotonicity.** If exposure increases, or purpose becomes more critical, or complexity
> increases, the tier can only rise or stay the same. Never fall.

That is `L-4`, tested as a property over generated lattice pairs. It is exactly the assurance an
examiner asks for and which no rules-engine-with-a-spreadsheet can give — and it is the reason the
tier can be *derived* rather than assigned, because a derived tier that could fall when exposure
rose would be worse than an assigned one.

> **One word this document used to overclaim.** Materiality is genuinely a **join** of two orders.
> Complexity is a score over declared components, clamped into a chain — arithmetic, not a lattice
> meet. Both are monotone, which is what `L-4` needs; only one of them is a lattice operation, and
> the code comment that calls the second a meet is wrong.

### 10.2 Control intensity is a Galois connection with tier

Let `Ctrl` be the lattice of control sets ordered by strictness. The map from tier to required
controls, `req : Tier → Ctrl`, and from an applied control set to the highest tier it can support,
`sup : Ctrl → Tier`, form a **Galois connection**:

```
req(t) ⊑ c   ⟺   t ⊑ sup(c)
```

Left to right: *the applied controls satisfy the tier's requirements*. Right to left: *the tier is
within what those controls can defend*. They are the same statement. That is why one definition
answers both *what must I do for this Tier 1 model?* and *given what we actually did, what tier can
this model legitimately be?* — and why a control gap and a tier inflation are one defect seen from
two sides. `L-5`, exhaustive over the finite chain, and it also decides the version-approval quorum.

### 10.3 Classification propagates by join

A model trained on `Confidential ⊔ PII` inherits `Confidential ⊔ PII`, and so do its artifacts,
documents and monitoring extracts. Policy sets compose by **meet** — all applicable policies must
hold. Both are the same order-theoretic machinery.

Recorded honestly: sensitivity today is a **column on the feature**, not an annotation propagated
through the evidence semiring. The security lattice is one of the semirings the construction
*implies* and that is not built, along with an admissibility semiring over regimes. The engine would
support them; nothing has been written.

---

## 11. Where may a machine do the work?

The structures above were justified by governance properties. They have a second use that was not
the design intent and is arguably the most consequential result here: several of them are **decision
procedures**, and a decision procedure is exactly what makes machine-generated output safe to
accept.

> **Oracle.** For a task `T` with outputs in `O`, an *oracle* is a decidable predicate
> `ok_T : O → 𝔹`, computable from the formal structure and from data independent of the output, such
> that `ok_T(o)` holds only if `o` is correct.

> **Automation admissibility.** If `T` is oracle-backed, the soundness of *verified automation* —
> compute `g(x)`, accept iff `ok_T(g(x))` — is **independent of the generator `g`**. No incorrect
> output is accepted, whatever produced it; the generator's error rate determines *throughput*, not
> correctness. If `T` is not oracle-backed, the correctness of the output is exactly the correctness
> of `g`.

Which yields a criterion that is a property of the *domain* rather than of any model:

> **Deploy machine generation where the formalism supplies a mechanical check. Use people where it does not.**

This is built, not merely argued. A capability claiming its output is checked must **name a
registered oracle** or it is refused at registration as `oracle_required`, and naming one that does
not exist is refused as `unknown_oracle`. Five are registered: cited evidence nodes resolve; a
proposed contract refines the incumbent (`L-7`); proposed schemas satisfy variance (`L-12`); a
proposed validation test exists in the catalogue; a generated warrant validates against the grammar.

**Citation soundness** is a corollary of §6.2. Let claim `c` have derivation `d_c` over evidence
identifiers `X`, and let `S ⊆ X` be a cited set. Then `S` supports `c` **iff** `d_c` evaluates to
`⊤` in the Boolean semiring under the valuation switching on exactly `S` — equivalently, iff `S`
contains a minimal support. Verifying a machine-generated citation is a Boolean evaluation over a
structure that already exists, not a further model call.

**What admits no oracle, and why.** For a derived quantity `q = f(Φ)` defined by a versioned rule
`f` — a tier, a control requirement, a scope determination — there is no automation question about
computing `q`: evaluating `f` is deterministic. The question arises only for supplying `Φ`, which is
oracle-backed when facts come from systems of record, and for *proposing `f`*, which is a normative
choice. Since `f` **constitutes** the standard, no independent specification exists against which a
proposed `f` could be checked. Concluding a validation, granting an approval and accepting residual
risk are in the same class. These are not weakly-checkable tasks withheld out of caution; they have
no notion of correctness independent of the authority exercising them.

**Well-foundedness.** Admitting machine assistance into a system that governs machines is not
circular. The governing machinery — `τ`, the evidence structure, the institutions, the lifecycle
category — is not an element of the governed population; every assistant is. Where the strata touch
(an assistant drafting a regime encoding), the dependency is mediated by an oracle that is not
itself machine-produced. **Generation may cross the strata; acceptance may not.**

Operational consequences: [13 — AI, LLMs and agents inside the platform](13-ai-in-the-platform.md).

---

## 12. The laws MAYA enforces

A law is what separates a foundation from an ornament: a statement precise enough that a machine can
tell you it has stopped being true.

The law tests live **beside the code they constrain** — there is no `tests/laws/` package — and the
column below says where each one runs. Where a law does not run, the row says so, because the
opposite habit (a document implying every law is checked while six are not) is the exact failure
this section exists to prevent.

| # | Law | From | State, and where it runs |
|---|---|---|---|
| **L-1** | *Functoriality of lifecycle.* A model's history is a path in the free category on its lifecycle graph, whose objects include **two initial** states; no state is reachable except along declared transitions or by creation in an initial state. | §2 | **Executable.** `tests/test_laws.py::TestL1LifecycleIsAFreeCategory` computes the reachable closure of the initial set and asserts it equals the declared state set. Writing it found that `baselined` was reachable by no edge — not a violation but a second initial object, since an imported record must not enter through `draft` or the register would imply historical evidence was asserted when it was not. `core/lifecycle/states.py::INITIAL` now says so |
| **L-2** | *Immutability.* For any version `v`, `hash(manifest(v))` is constant over its lifetime. | §2 | **Executable.** `tests/test_laws.py::TestL2AVersionDigestNeverMoves` carries a version through assessment, approval and an alias move and asserts the digest at each step, and checks it is over the *manifest* rather than the row — a digest over the row would move whenever a status column did. There is still no `CHECK` and no trigger: this is application-enforced, and finding C-3's trigger remains a Postgres design rather than shipped DDL |
| **L-3** | *Determinism claims are checked.* `deterministic(f)` ⟹ repeated execution on identical input is bit-identical — and a claim nothing can back is refused. | §2.4 | **Executable.** `tests/test_laws.py::TestL3ADeterminismClaimIsChecked` runs the same call through the estimator runtime twice and compares bit for bit. The other half is `L-W5`, which refuses a determinism claim a stochastic runtime cannot back, so the flag is *checked* where it can be and *refused* where it cannot |
| **L-4** | *Tiering monotonicity.* `(m,c) ⊑ (m',c') ⟹ τ(m,c) ⊑ τ(m',c')`. | §10.1 | **Executable.** Property test over generated lattice pairs — `tests/test_risk.py::TestTauMonotonicity` |
| **L-5** | *Control adequacy is a Galois adjunction.* `req(t) ⊑ c ⟺ t ⊑ sup(c)`. | §10.2 | **Executable.** Exhaustive over the finite tier chain — `tests/test_risk.py::TestControlAdjunction`. Also decides the version-approval quorum |
| **L-6** | *Abstraction soundness.* For every generated summary `a` of behaviour `c`: `c ⊑ γ(a)`. | §4.2 | **Not built.** Rescoped by M-5 to quantitative claims in structured sections. The replay that would check them exists for validation episodes and not for documents, so there is no `γ` and nothing compares a summary to what it summarises |
| **L-7** | *Contract refinement on substitution.* An alias move to `v'` requires `contract(v') ⪯ contract(v)`. | §4.1 | **Executable and enforcing.** `core/domain/contracts.py::refines`, discharged in `core/registry/aliases.py::obligations` at alias-move time and **written into the alias history**, so the proof survives the move; `tests/test_domain.py` |
| **L-8** | *Satisfaction condition.* For every regime comorphism `σ`: `M' ⊨ σ(φ) ⟺ Mod(σ)(M') ⊨ φ`. | §9.2 | **Enforcing, over probe states rather than generated ones.** `core/regimes/translation.py::satisfaction_condition` runs over six states spanning the corners, and a regime whose encoding fails it cannot be activated. The weaker quantifier is stated rather than hidden |
| **L-9** | *Provenance homomorphism.* For any semiring homomorphism `h : ℕ[X] → K`, evaluating in `K` equals `h` applied to the `ℕ[X]` result. | §6.3 | **Executable.** `core/evidence/semirings.py::POLYNOMIAL` and `pushforward`; `tests/test_laws.py::TestL9TheProvenancePolynomialIsUniversal` checks it over 200 random derivation DAGs against Boolean, counting, trust, cost and why, and `TestL9ReachesDerivedFeatures` extends it to derived features. It also surfaced that `FRESHNESS` is not a semiring — its zero does not annihilate — with the consequence recorded in §6.3 |
| **L-10** | *Point-in-time correctness.* Every generated training set satisfies §7.1, and the read `AsOf(R, ℓ, a)` is idempotent, commutes with projection, is monotone in `a`, and **saturates at `ℓ`**. | §7 | **Enforcing and executable.** Static rejection of an assembly missing either clock is a genuine refusal (`core/features/pit.py::static_check`) and sampling gives detection, never absence. The operator's four properties are asserted in `tests/test_laws.py::TestL10TheAsOfOperator`, and the fourth is the reproducibility guarantee: because the ingest bound is `min(ℓ, a)`, every `a ≥ ℓ` gives the same answer |
| **L-11** | *Lens laws.* GetPut, PutGet and PutPut hold for every document template. | §7.3 | **Not built.** Fifteen lenses, all `get`. The compiler regenerates whole documents, so there is no `put` and no round trip to test |
| **L-12** | *Schema variance.* A replacement version is contravariant in inputs and covariant in outputs. | §3.2 | **Executable and enforcing.** `core/domain/schemas.py::substitutable`, now routed through `core/domain/lattice.py::refines`, at alias moves and — as `L-W10` — at warrant issuance; `tests/test_domain.py` |
| **L-13** | *Evidence gluing.* Overlapping evidence sections have consistency radius ≤ declared tolerance. | §6.5 | **Not built.** No gluing computation exists anywhere; no consistency radius is computed |
| **L-14** | *Lax monoidality of risk.* `ρ(g∘f) ⊒ ρ(g) ⊔ ρ(f)` for all composable pairs. | §5.2 | **Executable and enforcing.** `core/risk/aggregate.py`; `tests/test_laws.py::TestL14AggregateRiskIsLaxMonoidal`. `ρ` is the **risk tier** and deliberately not a score — the board pack refuses to produce a single number and this is not the side door it comes in through. The interaction term is a set of **named obstructions** rather than a magnitude, each read from something the register holds: a shared upstream, an edge admitted without a type check, a boundary the wire does not settle, contracts that cannot both hold, a tier inversion, an untiered component. The composite escalates one step per *kind* of interaction, floored at tier 1. An unassessed component is the **top** of the lattice, not the bottom: a model nobody has tiered is not a safe model |
| **L-15** | *Fibration completeness.* Every class has a total evidence schema, lifecycle, metric set and template set; no fibre is empty. | §8 | **Executable and enforcing.** `core/fibres/registry.py::verify` runs at start-up and refuses to serve on a partial fibration; `register` refuses a partial fibre, so the registry cannot hold one between restarts; `tests/test_laws.py::TestL15NoFibreIsEmpty`. The base is the **trainability class**, not the free-text `model_class` — see §8 for why that distinction is the whole of the closure. The fibre is not inert: a `performance` monitor on a T0 pricer and a `calibration` monitor on a T5 assembly are now refused `kind_not_answerable` |
| **L-16** | *No obligation contradiction.* The obligation set is deontically consistent: no `O φ ∧ F φ`. | §9.4 | **Executable and enforcing**, over the sentences whose shape is declared. `core/regimes/sentences.py::deontic_conflicts` finds every term both obliged and forbidden, activation refuses it as `obligation_contradiction`, and `undecidable()` **names** the sentences the check cannot read rather than assuming them consistent. A conditional obligation is not counted against an unconditional prohibition: they may never both apply |
| **L-17** | *Contract–serving agreement.* For every active warrant, the feature namespace served equals the namespace pinned by its contract. | [11 · C-2](11-adversarial-review.md) | **Executable and enforcing.** It was recorded as blocked on an online store, and it was blocked on the wrong thing: a store sits on the serving path at request latency, and [10 §7](10-roadmap.md) says MAYA will not own that. The engine already knows what it read, so it **declares** it — `core/features/serving.py::ServingRegister` compares against `serving_namespaces`, names the three ways they can disagree, and records the answer whether or not it agrees. `tests/test_laws.py::TestL17ContractServingAgreement`. An attestation proves *disagreement* rather than agreement, and disagreement is what is worth catching: it is training–serving skew. **Never attested** is reported as its own state — silence is not agreement |
| **L-18** | *No personal data in evidence nodes.* A node flagged `contains_personal_data` carries no payload. | §6.4 | **Executable and enforcing**, in the append path rather than in DDL: `core/evidence/engine.py` stores an empty payload for such a node *and hashes what it stored*, so the node verifies against itself; `tests/test_evidence.py`. This row said "only an erasable pointer", and there is no pointer — no `payload_uri`, no per-subject key, no shred path. The payload is **discarded**, which is stronger than the law requires and weaker than the sentence implied |
| **L-19** | *Composition is a monoid.* Merge-with-rightmost-wins over definitions is associative, with the empty composition as identity. | §5.3 | **Executable.** Both properties asserted in `tests/test_composition.py`; strengthened by `tests/test_laws.py::TestTheEditOperationsCommuteWhenIndependent`, so the order two people happened to edit in carries no meaning |
| **L-20** | *Schemas are a lattice.* `A ⊑ B` ("A can stand in for B") is a partial order; meet and join exist on every finite fragment; the empty schema is top. | §3 | **Executable and enforcing.** `core/domain/lattice.py`; `tests/test_laws.py::TestL20SchemasFormALattice`. Written because **four** places asked one question and four implementations of one order disagree eventually, in the direction of permitting more. `L-12`, `L-W10` and `L-21` now go through it. Meet is **partial**, informatively so: two schemas whose shared slot has two types have no meet, which is the honest answer to *can one featureset serve both models* |
| **L-21** | *Composition type-checks.* An `input_to` edge holds only if what the source produces can stand in for what the target reads. | §3.3 | **Executable and enforcing.** `core/registry/composition.py`; `tests/test_laws.py::TestL21FeedsIsCompositionRatherThanADrawing`. Until this, an edge was recorded and never checked — a blast radius over edges nobody had validated. With it, a composite has a **derived** schema, which is what `L-14` would need |

### 12b. The fourteen warrant admissibility laws

A second family governs what a warrant may *ask for*. `L-W0` through `L-W13` are not invented for
the grammar: the trainability class is derived from how `P` is inhabited, so what a class admits is
what the class **means**, and `requires_fitting_evidence` is exactly the predicate that decides
whether `fit` is coherent for a given kernel.

They quantify over facts the platform derives — the parameter kind, the source binding, the runtime,
the trainability class — and never over a category anybody attached to a model. That is what lets
warrants **differ by kind of model as refusals over one document rather than as different
documents**: were the document to fork by type, every engine, replay path and audit query would
branch on model type before it could read anything, and the branch would grow a case per family
without bound.

All fourteen are checked **before** the signature. Thirteen are decided by the grammar over the
document alone; `L-W10` is decided at issuance, because it compares a featureset version's resolved
slots against a model version's input schema and neither is in the document being validated.

They are stated once, with what each refuses and why, in
[06 §5 — Warrants and the execution contract](06-warrants-and-execution.md). Stating them twice
would create two accounts able to disagree, which is the failure `L-2` exists to prevent one level
along.

---

## 13. What was considered and not adopted

Honesty about what is *not* being done is part of the design. Each was weighed against §0's rule.

| Not adopted | Why not |
|---|---|
| **Representation theory of groups and algebras** | it is about representing algebraic structures as linear operators, and is genuinely useful *inside* particular models — symmetry in PDE solvers, equivariant networks. It says nothing about managing a heterogeneous estate. Wrong scale |
| **Homotopy type theory / univalent foundations** | the equality-as-path machinery buys nothing at this scale; ordinary typed schemas plus the probe-relative equivalence of §4.3 give what is needed at a fraction of the comprehension cost |
| **Topos-theoretic internal logic** | an elegant unification of §6 and §9, at a large comprehension cost for no operational capability that institutions plus semirings do not already give. Revisit only if regime interactions become genuinely non-classical |
| **Full mechanised proof (Coq, Lean)** | disproportionate. The middle path is taken instead: laws stated formally in §12 and enforced by property-based testing. If a regulator later requires machine-checked evidence for one component — the tiering monotonicity proof, say — §10.1 is small enough to formalise in isolation |
| **Categorical database schemas (functorial data migration, CQL)** | attractive and closely related to §8, but the ecosystem, tooling and hiring pool do not support it for a production banking system. The *idea* is taken — schemas as categories, migrations as functors — and implemented with conventional SQL and disciplined fibre boundaries |
| **Measure-theoretic probability as the primary formalism** | used where it belongs, inside `Stoch` and in validation tests. Kolmogorov-style measure theory does not compose, and composition is the whole problem. Markov categories exist to fix exactly that |
| **Ontologies and description logics as the core model** | good for the *glossary*, and RDF is worth emitting for interoperability. But description logics are weak on the parametric, temporal and compositional structure that dominates here |

---

## 14. From theory to code

The package is `core/`. Where a concept has no row it has no code, and the row says so — an index
that quietly omits the unbuilt entries is how a reader concludes the whole table is built.

| Concept | Where it lives |
|---|---|
| `Para(Stoch)` model definition | `core/domain/algebra.py` — `ParametricKernel`, `ParameterObject`, `FitProcedure` |
| Trainability class as a derived property | `core/domain/algebra.py` — `trainability_class`; there is no `trainability.py`, because there is nothing to store |
| The order on schemas, and the lattice | `core/domain/lattice.py` — `refines`, `leq`, `meet`, `join`, `provides`, `NoMeet`, `TOP` |
| Schema variance (`L-12`) | `core/domain/schemas.py` — `substitutable`, routed through `lattice.refines` |
| Contract algebra (⪯, ⊗, ∧, /) | `core/domain/contracts.py` — `refines`, `compose`, `conjoin`, `quotient` |
| Probe-relative equivalence | `core/domain/identity.py` — `pi_equivalent`; defined and tested, **not** wired into promotion (§4.3) |
| Typed composition (`L-21`) | `core/registry/composition.py` — `relate`, `composite_schema`, `blast_radius`, `shared_dependencies` |
| Definition composition as a monoid | `core/features/composition.py` — `merge`, `fold`, `apply`, `independent`, `Resolver` |
| Provenance semirings | `core/evidence/semirings.py` — `Semiring` and **seven** instances, one of which is `ℕ[X]` and one of which (§6.3) is not a semiring |
| Evidence chain and evaluation | `core/evidence/engine.py` — `append`, `verify_chain`, `evaluate` |
| The `AsOf` operator | `core/features/assembly.py::latest_admissible`; the three-layer verifier in `core/features/pit.py` |
| Derived features on the polynomial | `core/features/derived.py` — `provenance`, `rests_on`, `lineage`, `knowable_at` |
| Risk lattices and the Galois connection | `core/risk/lattices.py`, `core/risk/tiering.py` — `tau`, `required_controls`, `supports_tier` |
| Institutions and comorphisms | `core/regimes/` — `signature.py`, `sentences.py` (incl. `deontic_conflicts`, `undecidable`), `translation.py`, `library.py` |
| Warrant grammar and its laws | `core/execution/grammar/` — `vocabulary.py`, `rules.py`, `validator.py`, `schema.py`; `L-W10` in `core/execution/warrants.py` |
| Featuresets and parameter sets | `core/features/sets.py`, `core/parameters/register.py` |
| Rule sets: the T8 parameter object, given a shape | `core/rules/` — `conditions.py` (the tree, `describe`, `conforms`), `domains.py` (reachability, **sound and incomplete**), `ruleset.py` (`Rule`, `RuleSet`, canonical form, `decide`), `editor.py` (`check`, `trial`, `publish`, `explain` — no authority the parameter register did not already hold), and the `rules` runtime in `core/execution/runtimes/rules.py` |
| The content-addressed artifact store | `core/artifacts/store.py` — the digest is the address, so *the bytes match the warrant* is true by construction rather than by a check somebody remembered to write |
| Document lenses | `core/docs/lenses.py` — fifteen lenses, `get` only (see `L-11`) |
| Oracles for machine assistance | `core/assist/oracles.py` — five registered; `core/assist/capabilities.py` refuses a Tier A capability that names none |
| The obligation jobs | `core/scheduler/jobs.py` — ten, doing the work an MTL compiler would have generated (§9.5) |
| The executable laws | Beside the code they constrain: `tests/test_laws.py` (L-1, L-2, L-3, L-9, L-10, L-14, L-15, L-16, L-17, L-20, L-21), `tests/test_risk.py` (L-4, L-5), `tests/test_domain.py` (L-7, L-12), `tests/test_regimes.py` (L-8), `tests/test_evidence.py` (L-18), `tests/test_composition.py` (L-19), `tests/test_grammar.py` (L-W0…L-W9), `tests/test_warrant_profiles.py` (L-W11…L-W13), `tests/test_api.py` (L-W10) |
| Sheaf consistency radius (`L-13`) | **Not built** |
| The aggregate `ρ` as a magnitude | **Not built, and deliberately.** `L-14` itself runs — `core/risk/aggregate.py` joins the tier lattice and carries named **obstructions** — but the interaction term is a list of what has not been assessed, never a number. A composite risk figure that looks like a measurement and is not one is worse than the absence of one |
| The fibration | `core/fibres/` — nine fibres over the trainability classes, a totality gate at start-up (`L-15`), and the per-class metric set that makes an unanswerable monitor a refusal |
| An MTL obligation compiler (`L-16`'s *original* ambition) | **Not built**, and `L-16` is not waiting on it. The law says the obligation set is deontically consistent, and that is checked and enforced at activation (§12). What was never built is the temporal-logic compiler that would have *generated* the monitoring from the obligations; the 27 scheduler jobs do that work by hand. The rows above that say a law does not run are `L-11` and `L-13`; the other two are components that do not exist beneath laws that do |
| An online feature store | **Not built, and `L-17` no longer waits on it.** The law was blocked on the wrong thing: §7 says MAYA will not sit on the serving path, so the engine **attests** which namespaces it read and MAYA compares against what the contract pins (`core/features/serving.py`). What a store would buy is *observation* rather than attestation — MAYA seeing for itself rather than being told — which is a smaller claim than this row used to make |

The architecture in [04](04-architecture.md) is organised around these boundaries, which is why its
module structure looks the way it does. The data model is [05](05-data-model.md).

---

## 15. Sources

**Categorical probability and parametric models**
- [Markov category (nLab)](https://ncatlab.org/nlab/show/Markov+category)
- T. Fritz, *A synthetic approach to Markov kernels, conditional independence and theorems on sufficient statistics* — [ResearchGate](https://www.researchgate.net/publication/341724752_A_synthetic_approach_to_Markov_kernels_conditional_independence_and_theorems_on_sufficient_statistics)
- Fritz, Gonda, Perrone, et al., *Representable Markov categories and comparison of statistical experiments in categorical probability* — [arXiv:2010.07416](https://arxiv.org/pdf/2010.07416) · [TCS](https://www.sciencedirect.com/science/article/abs/pii/S0304397523002098)
- Fritz & Rischel, *Infinite products and zero-one laws in categorical probability* — [arXiv:1912.02769](https://arxiv.org/pdf/1912.02769)
- *A category-theoretic proof of the ergodic decomposition theorem* — [arXiv:2207.07353](https://arxiv.org/pdf/2207.07353)
- *Compositional imprecise probability* — [arXiv:2405.09391](https://arxiv.org/pdf/2405.09391)

**Contracts and compositional system design**
- Benveniste, Caillaud, Nickovic, et al., *Contracts for System Design*, Foundations and Trends in EDA — [review](https://www.fmeurope.org/2020/10/30/book-review-contracts-for-system-design/) · [ResearchGate](https://www.researchgate.net/publication/339504304_Contracts_for_System_Design)
- *Synchronous interfaces and assume/guarantee contracts* — [INRIA](https://people.rennes.inria.fr/Albert.Benveniste/pub/MooreInterfacesAGContracts2017.pdf)
- *Some algebraic aspects of assume-guarantee reasoning* — [arXiv:2309.08875](https://arxiv.org/pdf/2309.08875)
- *A mechanically verified theory of contracts* — [arXiv:2108.13647](https://arxiv.org/pdf/2108.13647)
- *Modular assurance of complex systems using contract-based design principles* — [arXiv:2402.12804](https://arxiv.org/pdf/2402.12804)
- *Compositional cyber-physical systems theory* — [arXiv:2109.04858](https://arxiv.org/pdf/2109.04858)

**Provenance semirings**
- Green, Karvounarakis & Tannen, *Provenance Semirings*, PODS 2007 — [paper](https://web.cs.ucdavis.edu/~green/papers/pods07.pdf) · [ACM](https://dl.acm.org/doi/10.1145/1265530.1265535)
- [Provenance semirings — slides](https://www.cis.upenn.edu/~plclub/propr/greg-slides.pdf)
- *Revisiting semiring provenance for Datalog* — [KR 2022](https://proceedings.kr.org/2022/10/kr2022-0010-bourgaux-et-al.pdf)
- *Semiring provenance for lightweight description logics* — [arXiv:2310.16472](https://arxiv.org/pdf/2310.16472)
- *Provenance for regular path queries* — [arXiv:2001.09864](https://arxiv.org/pdf/2001.09864)

**Institutions and heterogeneous specification**
- Goguen & Burstall, *Institutions: abstract model theory for specification and programming*, JACM — [ACM](https://dl.acm.org/doi/10.1145/147508.147524) · [PDF](https://courses.grainger.illinois.edu/cs522/sp2016/InstitutionsAbstractModelTheory.pdf)
- [Institution Theory — Internet Encyclopedia of Philosophy](https://iep.utm.edu/insti-th/)
- *Introducing H, an institution-based formal specification and verification language* — [arXiv:1908.09868](https://arxiv.org/pdf/1908.09868)
- *Truth invariant under change of notation: a certified category of logics* — [ResearchGate](https://www.researchgate.net/publication/405835750_Truth_Invariant_Under_Change_of_Notation_A_Certified_Category_of_Logics)

**Referenced in passing**
- Cousot & Cousot, abstract interpretation — Galois connections and sound over-approximation (§4.2)
- Foster et al., lenses and bidirectional transformations (§7.3)
- Baez & Master, Petri nets as free symmetric monoidal categories (§5.1)
- Robinson, sheaf-theoretic data fusion and the consistency radius (§6.5)
- Allen's interval algebra; Snodgrass, bitemporal data management; SQL:2011 system-versioned and application-time tables (§7)
- Rondon et al., *Liquid Types* — refinement types, the same idea as the bounds carried by a `Field` (§3)
- Koymans, metric temporal logic; Bauer, Leucker & Schallhart, runtime verification (§9.5)

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
