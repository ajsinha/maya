# 15 — X and P: featuresets, derived features, and the parameter object

*The two letters of `f : P ⊗ X → D(Y)` that are not the kernel. What each is in
the register, what each refuses, and which law holds it. The narrative version
with a worked regression is the in-app tutorial
[**one model, end to end**](../content/tutorials/06-end-to-end.md);
this is the part a reviewer needs.*

---

## 1. Two of the three letters were not objects

A model is a parametric kernel. Fitting does not change `f` — it **inhabits `P`**.
That sentence is the whole design, and for a long time the register could not
express two thirds of it.

**`X` had no name.** It existed as an item list inside one model version's feature
contract: anonymous, identified by a digest, unshareable, and impossible to
compare across models. *"These two models read the same data"* was not a statement
the register could hold, so neither was *"a change here reaches both"*.

**`P` had nowhere to live.** A version carried an artifact digest and a URI. There
was no row anywhere holding the coefficients an estimation produced — while law
`L-W4` already required a `fit` warrant to declare `sink: parameter_object`. The
warrant plane demanded the parameters go somewhere and the register had nowhere to
put them.

Both are objects now, and the rest of this document is what follows from making
them so.

---

## 2. A featureset is a schema; a version fills it

A **featureset** declares named slots, each with a dtype and a nullability. A
**featureset version** binds every slot to a feature *and* to the exact feature
view version supplying its values.

That separation carries the design, because it is what makes two things true at
once:

- different versions of a featureset may draw on **entirely different features**;
- a kernel defined over the featureset is **unchanged** by that.

```
inflation          slots: {gb_index: numeric, us_index: numeric, daily_index: numeric}
inflation @ v1     gb_index→UKRPI   us_index→USCPI   daily_index→DAILY_INFLATION
inflation @ v2     gb_index→UKRPI   us_index→USCPI   daily_index→EUHICP
```

A model reads `daily_index`, and always did. Swapping what fills the slot did not
change the model's input space — it changed what the model was **fitted on**,
which is a different event with a different control.

A version that cannot fill the schema is refused. It is not a version of this
featureset; it is a different featureset, or it is a model change, and the
register decides which rather than the developer remembering. Where the slot name
equals the feature name — the common case — nobody has to think about slots at
all.

### 2.1 Every binding pins the view version

A binding records `{feature, view, view_version, feature_view_id, namespace}`.
The namespace is version-scoped, so a featureset version always resolves to the
same bytes.

This is finding **C-2** — *a stable identifier over moving contents* — closed one
level up from where it was first found. The featureset is the stable identifier;
without the pin, its contents move underneath every model fitted from it, and
every such model's training set silently becomes something else.

### 2.2 The schema is a point in a lattice

A featureset's resolved slots are a `Schema`, and schemas carry an order
([17 §2](17-feature-and-model-algebra.md)):

> `A ⊑ B` iff `A` has every field `B` has, each accepting **at least** what `B`'s
> accepted.

That single relation answers what used to be four separate checks. In particular
`L-W10` — *does this featureset provide what the kernel reads* — is now
`refines(resolved, kernel_inputs)`, literally the same comparison `L-12` makes
when one version replaces another. They were one relation implemented twice.

Two questions become askable that were not:

| | |
|---|---|
| what must a featureset provide to serve **both** these models? | their **meet** |
| what may a consumer of **either** rely on? | their **join** |

And the meet is **partial**: two models whose shared slot has two different dtypes
have no common featureset, and the refusal names the slot rather than returning an
empty schema nobody notices.

### 2.3 What the set owns, and what the warrant owns

| The featureset owns | The warrant owns |
|---|---|
| the slots and their types | the **window** the fit reads |
| which feature and view version fills each | the **`as_of`** |
| the label slot and the outcome window | which model, which version, which principal |

The set is meant to be reusable across periods, so it fixes the columns and
deliberately not the period. `L-W9` requires the warrant to bound both clocks,
because a read with neither is *"everything we know now"*, which cannot be shown
point-in-time correct however carefully the set was pinned.

---

## 3. Derived features

`Z = f(X, Y)`, computed rather than supplied.

### 3.1 The expression language

Parsed with Python's own parser, then walked against a whitelist of AST node
types. Admitted: arithmetic, comparison, boolean and conditional operators, and
`log · exp · sqrt · abs · min · max · round · floor · ceil`. Names beginning with
a double underscore are refused. Attribute access, subscripting, comprehensions,
lambdas, imports and unlisted calls are **structurally unreachable** — the refusal
is *"that node type is not part of the language"*, not a blocklist somebody has to
keep current.

The row's own event clock is readable as `event_year`, so an age is correct for
the row rather than for the moment the expression ran.

**The line this draws.** MAYA transforms features it already holds; it does not
run models. Computing `x / y` over a stored column is the same class of act as
computing the null rate MAYA already reports for every materialisation. Running a
kernel is not. An expression needing a library, external data or a model is
declared `evaluator: external` — the definition is still stored, so lineage, the
leakage check and the retirement guard all apply, and the register says plainly
that the platform did not compute the values.

### 3.2 The polynomial underneath

A derivation is a **term**. Annotating each base feature with its own variable and
evaluating in `ℕ[X]` — the same free commutative semiring the evidence chain uses
— makes every question about a derived feature a homomorphism out of one object:

| Question | The homomorphism |
|---|---|
| what does this rest on? | the free variables |
| when did it become knowable? | pushforward into the max-semiring |
| does it touch the label? | membership of the label's variable |
| how far do we trust it? | pushforward into the trust semiring |

The ingest clock is the case that matters. `ingest(Z) = max` over the inputs used
to be described as *arithmetic, so it cannot be forgotten*. It is stronger:
**it is a homomorphism, and a homomorphism has no exceptions to forget.**

Two lineages fall out, and they answer different questions:

- **`lineage()`** — every ancestor, derived ones included. *What breaks if this
  changes.*
- **`rests_on()`** — the free variables: base features only. *What data this
  ultimately reads.*

The second is the first minus its derived members, which is asserted rather than
assumed.

### 3.3 The four rules

| Rule | Refusal | The failure it prevents |
|---|---|---|
| Lineage is the transitive closure | retirement blocked by `dependants_of()` | a primitive retired under something deriving from it |
| `ingest_ts(Z) = max` over inputs | computed, never entered | the easiest way to leak the future: a value appearing knowable before its inputs were |
| No slot may derive from the label | `feature_refused` at publish | leakage with a division sign in front of it |
| Certification is the **meet** of its inputs | `certification_of()` | deriving from an uncertified feature to launder it |

Two further refusals: a feature defined in terms of itself, at any depth; and
inputs spanning more than one entity, because a ratio of a per-customer number to
a per-account number is not one number and storing it as one would be silently
wrong.

**Definitions are versioned, never edited.** A correction is
`definition_version + 1`, because somebody may already have trained against the
previous one.

**Undefined arithmetic is a null, not a failure.** `log` of a non-positive number,
a division by zero: the definition is sound and this row has no answer. One bad
row must not fail a materialisation of a million. `on_error: refuse` exists where
a null would itself be wrong.

### 3.4 Leakage is checked before resolution

`publish()` checks leakage on the bindings **as requested**, before any view
lookup. *"You cannot train on the answer"* is a better message than *"no view
supplies that"* — and the leaky binding must be refused whether or not its view
happens to be materialised, or the refusal depends on an accident.

---

## 4. The parameter object

**A fit produces a parameter set, not a model version.** The kernel did not
change; only `P` was re-inhabited. Minting a version per retrain would make *"the
model changed"* mean two different things, and the more common one would win.

But a parameter set changes behaviour, so it is immutable, versioned, and cannot
be run on until approved by somebody other than whoever recorded it — the same
gate that governs versions, applied to the other half of the pair.

### 4.1 Three routes, three depths of governance

| Provenance | Classes | Evidence | Governance |
|---|---|---|---|
| `fitted` | T2 · T3 · T4 · T5 | a fit warrant MAYA issued, and the featureset version | approve each parameter set |
| `calibrated` | T1 | market instruments, often daily | approve the **procedure**; record each run against it |
| `declared` | T0 · T7 · T8 | a person's assertion | attestation |

The middle row is why provenance is not cosmetic. A Hull–White model recalibrated
every morning produces two hundred and fifty sets a year; requiring a committee
for each is a control nobody performs, and pretending otherwise is worse than
having none.

The bottom row is the model that never trains. `L-W1` already refuses a `fit` for
T0 and T6 as a *type error*, so no separate rule is needed; the register adds the
complementary refusals `nothing_to_fit` and `parameters_not_reachable` for
somebody trying to **record** a fitted set against a terminal or opaque parameter
object.

It is also the row with the platform's one **authoring** surface, and the reason
is stated in the word `declared` itself: for a T8 rule set, authorship *is* the
provenance, so there is no fitting act for an editor to counterfeit. `core/rules/`
therefore edits a parameter object the register already held rather than minting
one — the set still lands `proposed`, the digest is still over the content, and
`self_approval` is still refused. The same argument forbids the obvious next
step: an ONNX or PMML editor would let MAYA mint an artifact that never had a
training run and is indistinguishable in the register from one that did. See
[02](02-model-taxonomy.md#t8-the-fibre-that-was-least-served).

### 4.2 Accepted only against a warrant MAYA issued

`warrant_required` (none given) · `unknown_warrant` (not ours) ·
`warrant_revoked` · `warrant_names_another_model` ·
`warrant_names_another_version`.

There is no back door, and the reason is not procedural. Without the warrant,
*"which data produced these numbers"* has no answer — and the pinned view
versions, the two clocks and the point-in-time rule all stop one step short of the
thing they were for.

The **grant** is checked rather than a resolved descriptor: a descriptor is minted
per request and never persisted, so the grant is what MAYA can vouch for.

### 4.3 Storage

Values up to 4,096 entries live in the register, because a coefficient vector is a
record a reviewer should be able to read. Beyond that a `values_uri` is required
and the register holds the digest and the cardinality: a hundred million weights
are an *artifact*, and inlining them would make every read of the register carry
them. Where the artifact is held by MAYA it goes to the content-addressed store
and the warrant says `held_by_maya`.

One kind of value is read rather than only held. A T8 rule set is checked before
it is stored — every field it reads is declared on the version, no rule is
shadowed by any single earlier one, no two rules with the same condition disagree,
and an `otherwise` exists — and the digest is taken over the **parsed canonical
form**, so two documents differing only in key order are one parameter set while
two differing in rule *order* are two, because with first-match evaluation the
order is the meaning.

### 4.4 Resolution refuses to guess

`resolve(urn, semver, name=None)` returns the newest **approved** set.
`no_approved_parameters` when there is none; `ambiguous_parameters` when there is
more than one name and the caller supplied none.

Choosing for the caller is how a model quietly runs on last quarter's
coefficients.

### 4.5 Every fit now has a document

Compiled per parameter set from what the register already holds — the warrant, the
featureset version, the window, the `as_of`, the diagnostics, who recorded it and
who accepted it. See [17 §8](17-feature-and-model-algebra.md).

Two hundred and fifty governed acts a year had no readable record; now they all
have one whether or not somebody had time to write it, and the one that needs a
human note has a place to put it.

---

## 5. The laws

| Law | Statement | Where |
|---|---|---|
| **L-W8** | Every run names the point in `P` it runs at. A `fit` binds `to_be_fitted` and nothing else; every other verb binds something that is not. | `grammar/rules.py` |
| **L-W9** | A featureset read for fitting is bounded in **both** clocks. The set fixes the columns; the warrant fixes the period. | `grammar/rules.py` |
| **L-W10** | A featureset a warrant names must provide what the kernel reads — now `refines()`, the same order as `L-12`. | `execution/warrants.py` |
| **L-10** | The point-in-time read is idempotent, commutes with projection, is monotone in `as_of`, and **saturates at the label**. | `tests/test_laws.py` |
| **L-9** | The provenance polynomial is universal; every other annotation is a pushforward. Now applied to derived features. | `evidence/semirings.py` |
| **L-20** | Schemas form a lattice; every substitutability question is one comparison in it. | `domain/lattice.py` |

`L-W10` is checked at **warrant time**, not at publish, because a featureset does
not belong to a model: whether it provides what a particular kernel reads is only
answerable once both are named. That is where *adding a regressor is a model
change, not a data change* is enforced rather than remembered.

> **`L-W8` found a real error in a shipped example on the day it was written.**
> `02-quantlib-hullwhite-calibrate` declared its parameters came from an artifact
> while its verb was `fit`. A calibration *produces* the calibration set, so the
> warrant described the wrong direction. Two more examples were wrong the same
> way.

---

## 6. Schema

Four tables, identical in both dialects.

| Table | Key | Carries |
|---|---|---|
| `derived_feature` | `(name, definition_version)` | `expression`, `inputs`, `evaluator`, `on_error`, `digest` |
| `featureset` | `name` | `slots`, `label_slot`, `outcome_window_days`, `entity`, `grain` |
| `featureset_version` | `(featureset_id, version)` | `bindings`, `label_binding`, `digest` |
| `parameter_set` | `(model_version_id, name, version)` | `kind`, `provenance`, `values_inline`/`values_uri`, `cardinality`, `diagnostics`, `featureset_version_id`, window, `as_of`, `snapshot_id`, `warrant_id`, `digest`, `state` |

The feature itself is an ordinary `feature` row; `derived_feature` is its
*definition*.

---

## 7. Interfaces

```
GET  /api/v1/expression-language           what a derived feature may be written in
POST /api/v1/derived-features              feature:define
GET  /api/v1/derived-features/{name}/lineage

POST /api/v1/featuresets                   featureset:define
POST /api/v1/featuresets/preview           the same fold, without declaring it
POST /api/v1/featuresets/{name}/versions   featureset:publish
GET  /api/v1/featuresets/{name}/resolved
POST /api/v1/featuresets/{name}/seal       featureset:seal
POST /api/v1/featuresets/{name}/training-sets   feature:assemble

POST /api/v1/parameters                    parameter:record
POST /api/v1/parameter-sets/{id}/review    parameter:approve  — never the recorder
POST /api/v1/parameter-fits                the captive estimator, under a warrant
GET  /api/v1/training-records/{id}/preview what the record would say
```

Defining a set and publishing a version are separate permissions, and sealing is a
third: whoever may define a thing is not automatically whoever may end it.

---

## 8. Roll-forward and assembly

Publishing a new feature view version deliberately changes **nothing** about an
existing featureset version. `roll_forward(name)` mints a new version re-resolved
to the newest view version of every binding, and returns a **diff** naming each
slot that moved and the namespaces it moved between.

The cost is version churn. Making the correct thing convenient is how you stop
people routing around it.

`build_from_featureset(name, version, spine, as_of)` resolves the pinned
namespaces and runs the three-layer point-in-time verification over them. The
resulting snapshot records the featureset version and its digest, so a fit warrant
may pin the **snapshot** and recompute nothing — which is what an audit replay
wants, where the **set** is what a recurring retrain wants.

**Retirement** walks contracts → featuresets → views: `can_retire(view, version)`
returns the featureset versions still pinning it. A query, where it used to be a
scan.

---

## 9. What this deliberately does not do

| | |
|---|---|
| **No feature engineering** | the expression language is small on purpose; anything richer is `external`, and says so |
| **No fitting** | MAYA issues the warrant and takes delivery. The estimation happens in an execution engine — the boundary drawn everywhere else |
| **No artifact authoring** | a rule set can be written here because authorship is its provenance; a fitted map cannot, because hand-authoring one would put an artifact in the register that is indistinguishable from a trained one and never was |
| **No feature selection** | no automatic selection, no importance ranking, no suggestion engine. The register records what you chose, pins it so it cannot move underneath you, and refuses the combinations that are type errors |
| **No online serving tier** | the Delta namespace *is* the serving contract; reading it at request latency is the engine's problem. `L-17` is not executable until that exists, and the table says so |

---

## 10. Traceability

| Section | Satisfies |
|---|---|
| §2 Featuresets | `FR-FEA-001..017`; finding **C-2** at the featureset level; `L-20` |
| §3 Derived features | `FR-FEA-006`; `L-9` extended; `L-10` |
| §4 Parameter object | `L-W4` completed on the register side |
| §5 Laws | `L-W8`, `L-W9`, `L-W10`, `L-10`, `L-20` |
| §7 Interfaces | segregation per [09 §2](09-security-compliance.md) |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
