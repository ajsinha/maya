# 15 — Featuresets and the Parameter Object

*The specification for a named presentation of X and a stored inhabitant of P.
The narrative account, with a worked New Jersey home-price regression, is the
in-app help topic **Featuresets and fitted parameters**; this document is the
part a reviewer needs: the schema, the laws, the interfaces and the refusals.*

---

## 1. What was missing

A model in MAYA is a parametric kernel, `f : P × X → D(Y)` ([00
§2](00-mathematical-foundations.md)). Fitting does not change `f`. It *inhabits*
`P`.

Two of those three letters were not objects in the register.

**`X`** existed only as an item list inside one model version's
`feature_contract` — anonymous (identified by a digest), unnameable, unshareable,
and impossible to compare across models. "These two models read the same data"
was not expressible.

**`P`** was not stored at all. A version carried `artifact_digest` and
`artifact_uri`; there was no row anywhere holding the coefficients an estimation
produced. Law **L-W4** already required a `fit` warrant to declare
`sink: parameter_object`, so the grammar demanded the parameters go somewhere and
the register had nowhere to put them. The warrant plane was ahead of the register.

---

## 2. The separation of schema from constituents

A **featureset** declares a schema: named slots, each with a dtype and a
nullability. A **featureset version** binds each slot to a feature *and* to the
feature view version supplying its values.

That separation is load-bearing. It is what makes the following two statements
simultaneously true, which is what the design has to deliver:

- different versions of a featureset may draw on **entirely different features**;
- a kernel defined over the featureset is **unchanged** by that.

```
inflation            slots: {gb_index: numeric, us_index: numeric, daily_index: numeric}
inflation@v1         gb_index→UKRPI  us_index→USCPI  daily_index→DAILY_INFLATION
inflation@v2         gb_index→UKRPI  us_index→USCPI  daily_index→EUHICP
```

A model reads `daily_index` and always did. A version that **cannot fill the
schema** — a missing slot, or a slot filled with an incompatible dtype — is
refused: it is not a version of this featureset. It is a different featureset, or
it is a model change, and the register decides which rather than the developer
remembering.

Where the slot name equals the feature name (the common case) nobody has to think
about slots at all.

### 2.1 Every binding pins the view version

`_resolve` records `{feature, view, view_version, feature_view_id, namespace,
dtype, derived, definition_version, certification}` per slot.

A featureset that named views without pinning versions would resolve to different
bytes after the next materialisation with its digest unchanged. That is
adversarial finding **C-2** ([11](11-adversarial-review.md)) exactly, one level
out from the feature view — invisible to every design-time check, and green on
every monitor.

Ambiguity is refused rather than guessed: a feature supplied by more than one
view must name the view and version explicitly.

### 2.2 What the set owns, and what the warrant owns

| | Owner | Why |
|---|---|---|
| Slots, dtypes | Featureset | It is the schema `X` |
| Feature → view version | Featureset version | Reproducibility: *same version → same bytes* |
| Entity, grain | Featureset | What one row is |
| Column roles, label slot | Featureset | Leakage detection needs declared roles, not inference |
| Outcome window | Featureset | Whether a cohort is mature enough to train on |
| Point-in-time rule | Featureset | Platform discipline, stated once |
| **`as_of`, date window** | **Warrant** | The set is reusable across periods; the period is what varies per run |

Putting the window in the set would make "same features, 2019–2023 versus
2020–2024" two featuresets. It is one featureset and two warrants.

---

## 3. Derived features

`core/features/derived.py`, `core/features/expressions.py`.

A derived feature computes its values from other features: `Z = f(X, Y)`.

### 3.1 The expression language

Parsed with Python's own parser, then walked against a whitelist of AST node
types. Admitted: arithmetic, comparison, boolean and conditional operators, and
`log · exp · sqrt · abs · min · max · round · floor · ceil`. Names beginning with
a double underscore are refused. Attribute access, subscripting, comprehensions,
lambdas, imports and unlisted calls are structurally unreachable — the refusal is
"that node type is not part of the language", not a blocklist.

The row's own event clock is readable as `event_year` (spelled `year(event_ts)`
where it reads better), so an age is correct for the row rather than for the
moment the expression ran.

**The line this draws.** MAYA transforms features it already holds; it does not
run models. Computing `x / y` over a stored column is the same class of act as
computing the null rate MAYA already reports for every materialisation. Running a
kernel is not. An expression needing a library, external data or a model is
declared `evaluator: external` — the definition is still stored, so lineage, the
leakage check and the retirement guard all apply, but the values arrive by
materialisation and the register says the platform did not compute them.

### 3.2 The four rules

| Rule | Refusal / behaviour | Failure it prevents |
|---|---|---|
| **Lineage is the transitive closure** | `dependants_of()` blocks retirement | A primitive retired under something deriving from it |
| **`ingest_ts(Z) = max(ingest_ts(X), ingest_ts(Y))`** | Computed in `knowable_at()` | The single easiest way to leak the future: a derived value appearing knowable before its inputs were |
| **No slot may derive from the label** | `FeatureError` at publish, surfacing as `feature_refused` / 409 | Leakage with a division sign in front of it |
| **Certification is the meet of its inputs** | `certification_of()` | Deriving from an uncertified feature to launder it |

Two further refusals: a feature defined in terms of itself, directly or through
any number of hops; and inputs spanning more than one entity, because a ratio of
a per-customer to a per-account number is not one number and stored as one it
would be silently wrong.

**Definitions are versioned, never edited.** A correction is
`definition_version + 1`, because somebody may already have trained against the
previous one.

**Undefined arithmetic is a null, not a failure.** `log` of a non-positive
number, division by zero: the definition is sound and this row has no answer. One
bad row must not fail a materialisation of a million. `on_error: refuse` is
available where a null would be wrong.

### 3.3 Leakage is checked before resolution

`publish()` checks leakage on the bindings **as requested**, before any view
lookup. *"You cannot train on the answer"* is a better message than *"no view
supplies that"*, and the leaky binding must be refused whether or not its view
happens to be materialised.

---

## 4. The parameter object

`core/parameters/`.

**A fit produces a parameter set, not a model version.** The kernel did not
change; only `P` was re-inhabited. Minting a model version per retrain would make
"the model changed" mean two different things.

But a parameter set changes behaviour, so it is immutable, versioned, and cannot
be run on until approved by somebody other than whoever recorded it — the same
gate that governs model versions, applied to the other half of the pair.

### 4.1 Three routes, three depths of governance

| Provenance | Classes | Evidence | Governance |
|---|---|---|---|
| `fitted` | T2 · T3 · T4 · T5 | A fit warrant MAYA issued, and the featureset version | Approve each parameter set |
| `calibrated` | T1 | Market data, often daily | Approve the *procedure*; record each run against it |
| `declared` | T0 · T7 · T8 | A person's assertion | Attestation |

The middle row is why provenance is not cosmetic: a Hull–White model recalibrated
every morning would drown the register if each day needed a committee.

The bottom row is the model that never trains. **L-W1** already refuses a `fit`
for T0 and T6 as a type error, so no separate rule is needed; the register adds
the complementary refusals `nothing_to_fit` and `parameters_not_reachable` when
somebody tries to *record* a fitted set against a terminal or opaque parameter
object.

### 4.2 Accepted only against a warrant MAYA issued

`_check_warrant` refuses `warrant_required` (no id), `unknown_warrant` (not
ours), `warrant_revoked`, `warrant_names_another_model` and
`warrant_names_another_version`.

There is no back door. Without it, *"which data produced these numbers"* has no
answer, and the lineage that pinned view versions and bitemporal clocks exist to
establish stops one step short of the thing it was for.

The grant is what is checked, not the resolved descriptor: a descriptor is minted
per request and not persisted, so the grant is what MAYA can vouch for.

### 4.3 Storage

Values up to `MAX_INLINE_VALUES` (4,096) live in the register, because a
coefficient vector is a record a reviewer should be able to read. Beyond that a
`values_uri` is required and the register holds the digest and cardinality — a
hundred million weights are an artifact, and inlining them would make every read
of the register carry them.

### 4.4 Resolution refuses to guess

`resolve(urn, semver, name=None)` returns the newest **approved** set.
`no_approved_parameters` when there is none; `ambiguous_parameters` when there is
more than one name and the caller supplied none. Choosing for the caller is how a
model quietly runs on last quarter's coefficients.

---

## 5. Laws added

| Law | Statement | Where |
|---|---|---|
| **L-W8** | Every run names the point in `P` it runs at. `parameters.source.binding` is drawn from a closed vocabulary; a `fit` binds `to_be_fitted` and nothing else; every other verb binds something that is not `to_be_fitted`. | `rules.check_parameter_source` |
| **L-W9** | A featureset read for fitting is bounded in both clocks — an `as_of` and a `from`/`to` window. The set fixes the columns; the warrant fixes the period. | `rules.check_featureset_bounds` |
| **L-W10** | A featureset a warrant names must provide what the kernel declares it reads. Contravariance in inputs — the variance rule (**L-12**) that gates alias promotion, applied one level out. Refused as `schema_not_satisfied` / 409, naming the missing slots. | `WarrantService._check_schema` |

L-W10 is checked at warrant time and not at publish, because a featureset does
not belong to a model: whether it provides what a particular kernel reads is only
answerable once both are named. `POST /api/v1/fit-warrants` is where that
happens, and where *adding a regressor is a model change, not a data change* is
enforced rather than remembered.

`featureset` joins `feature_namespace` and `dataset_snapshot` in
`BITEMPORAL_BINDINGS`, so **L-W3** admits training from it.

`parameters.source.binding` vocabulary: `artifact` · `parameter_set` ·
`declared` · `to_be_fitted` · `vendor_internal`. The `artifact` binding requires
no `uri`: where the artifact lives is `realisation`'s job, and saying it twice
would let the two disagree.

**L-W8 found a real error in the shipped examples.** `02-quantlib-hullwhite-calibrate`
declared its parameters came from an artifact while its verb was `fit` — a
calibration *produces* the calibration set, so the warrant described the wrong
direction. Corrected, along with `04` and `08`.

---

## 6. Schema

Three tables, identical in both dialects. See `db/schema/sqlite.sql` and
`db/schema/postgres.sql`.

- **`derived_feature`** — `(name, definition_version)` unique; `expression`,
  `inputs`, `evaluator`, `on_error`, `digest`. The feature itself is an ordinary
  `feature` row; this table is its *definition*.
- **`featureset`** — `name` unique; `slots` (slot → `{dtype, nullable}`),
  `label_slot`, `outcome_window_days`, `entity`, `grain`.
- **`featureset_version`** — `(featureset_id, version)` unique; `bindings`
  (slot → resolved binding), `label_binding`, `digest`.
- **`parameter_set`** — `(model_version_id, name, version)` unique; `kind`,
  `provenance`, `values_inline` / `values_uri`, `cardinality`, `diagnostics`,
  `featureset_version_id`, `window_from`/`window_to`, `as_of`, `snapshot_id`,
  `warrant_id`, `digest`, `state`, `superseded_by`.

---

## 7. Interfaces

```
GET  /api/v1/expression-language              what a derived feature may be written in
GET  /api/v1/derived-features
POST /api/v1/derived-features                 feature:define
GET  /api/v1/derived-features/{name}/lineage  rests_on and depended_on_by

GET  /api/v1/featuresets
POST /api/v1/featuresets                      featureset:define
GET  /api/v1/featuresets/{name}
POST /api/v1/featuresets/{name}/versions      featureset:publish
GET  /api/v1/featuresets/{name}/versions/{n}  the assembly plan
POST /api/v1/featuresets/{name}/roll-forward  featureset:publish
POST /api/v1/featuresets/{name}/training-sets featureset assembly -> snapshot

GET  /api/v1/parameter-provenance
GET  /api/v1/parameters?urn=&semver=          status + the sets
POST /api/v1/parameters                       parameter:record
GET  /api/v1/parameter-sets/{id}
POST /api/v1/parameter-sets/{id}/review       parameter:approve

POST /api/v1/fit-warrants                     warrant:issue — L-W10 checked here
GET  /api/v1/engine                           the captive engine's isolation boundary
```

The parameter routes are deliberately **not** nested under
`/models/{name:path}`: that converter is greedy and swallows a trailing segment.
It has caused this class of bug four times in this codebase.

**Permissions.** `featureset:define`, `featureset:publish` and
`parameter:record` sit with the first line (model developer, model owner);
`parameter:approve` sits with the second (validator, model risk manager). The
register checks identity again on top of the role grant, because a role grant is
a policy that can change and segregation of duty is not.

---

## 8. Roll-forward

Publishing a new feature view version deliberately changes nothing about an
existing featureset version. `roll_forward(name)` mints a new version
re-resolved to the newest view version of every binding, and returns a **diff**
naming each slot that moved and the namespaces it moved between.

The cost of full resolution is version churn. Making the correct thing convenient
is how you stop people routing around it.

**Assembly.** `build_from_featureset(name, version, spine, as_of)` resolves the
pinned namespaces and runs the existing three-layer PIT verification over them.
The resulting `dataset_snapshot` records the featureset version and its digest,
so a fit warrant may pin the snapshot instead of the set and recompute nothing —
which is what an audit replay wants, where the set is what a recurring retrain
wants.

**Retirement** now walks contracts → featuresets → views:
`FeaturesetRegistry.can_retire(view, version)` returns the featureset versions
still pinning it. A query, where it used to be a scan.

---

## 9. What this deliberately does not do

- **No feature engineering.** The expression language is small on purpose;
  anything richer is `external`.
- **No fitting.** MAYA issues the warrant and takes delivery of the result. The
  estimation happens in an execution engine — the boundary drawn everywhere else.
- **No feature selection.** No automatic selection, no importance ranking, no
  suggestion engine. The register records what you chose, pins it so it cannot
  move underneath you, and refuses the combinations that are type errors.
- **No online serving tier.** The Delta namespace *is* the serving contract;
  reading it at request latency is the execution engine's problem.

---

## 10. Traceability

| Section | Satisfies |
|---|---|
| §2 Featuresets | `FR-FEA-001..017`; finding **C-2** at the featureset level |
| §3 Derived features | `FR-FEA-006`; `L-10` point-in-time correctness |
| §4 Parameter object | `L-W4` completed on the register side |
| §5 Laws | `L-W8`, `L-W9`; `L-W1`, `L-W3` extended to the new binding |
| §7 Interfaces | Segregation per [09 §4](09-security-compliance.md) |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
