# 16 — Five things a feature is not

*What a feature turns out to be once you stop assuming it is a number in a
column somebody owns forever. Each section is one assumption, why it fails, and
what the register does instead.*

---

Everything here follows from a single observation: the ordinary picture of a
feature — *a scalar, defined in one place, mutable, permanent, and belonging to
whoever created it* — is wrong in five separate ways, and each one causes a
distinct failure in a governed estate.

| Assumption | Fails because | §|
|---|---|---|
| a feature is a number | a yield curve is a vector and a correlation is a matrix | 1 |
| a feature is defined in one place | inheriting from one parent and combining several are the same operation | 2 |
| a feature is mutable | a parent that can move is a parent nobody can build on | 3 |
| a feature is permanent | a set pulled for one experiment should not outlive it | 3 |
| a feature belongs to its author | authorship is history; ownership is a responsibility | 4 |

A sixth section covers what happens between the store and the model — gap
filling, normalisation, alignment — which is where the most damaging errors in
this whole area actually live, because they are invisible afterwards.

---

## 1. Not always a number

A feature carries a **shape**, and along its first axis optional **component
names**.

| Shape | Kind | Example |
|---|---|---|
| `()` | scalar | `dscr` |
| `(10,)` | vector | a yield curve at ten tenors |
| `(10, 10)` | matrix | the correlation between them |
| `(5, 10, 10)` | tensor | that matrix under five scenarios |

Rank is capped at 4 and any axis at 100,000. Beyond that a "feature" is a dataset
with a name, and a feature view of its own is the honest home for it.

**Component order is the axis order.** A curve whose tenors came back
alphabetically would be a different curve — and one nobody would notice was
wrong — so resolution preserves insertion order and never sorts. That is the
single most consequential line in this section.

Three refusals, each preventing an ambiguity rather than a crash:

- naming *some* components and not others: the rest would be identified only by
  position, which is exactly what the names exist to avoid;
- naming any on a scalar;
- duplicate names, because an operation on a duplicated name has two meanings.

`check_rows` samples values against the declared shape, because **a declared
shape nobody verifies is a comment** — and a model given ten tenors where it
expected eleven produces an answer rather than an error.

---

## 2. Not always defined in one place

Inheriting from one parent and combining several are the same operation at
different arities. So there is one mechanism, and inheritance is the one-parent
case.

> **A left-to-right fold in which the rightmost wins. An object's own operations
> are applied last, and are therefore the most prominent of all.**

```
compose([a, b, c])  =  merge(merge(a, b), c)     then the object's own operations
```

### It is a monoid, and that is not decoration

Associative, with the empty composition as identity — both asserted in
`tests/test_composition.py` (`L-19`). Three things follow that would otherwise be
conventions somebody half-remembers:

1. **Order of grouping does not matter.** `(A ∘ B) ∘ C` and `A ∘ (B ∘ C)` are the
   same object, so *which order did we build this in* stops being a question with
   a consequence.
2. **Precedence is a property, not a preference.** Leftmost is least prominent. A
   child inheriting from three parents has one answer rather than three.
3. **"A combination of features is a feature"** is a statement rather than an
   aspiration — it is the closure property of the fold, and it is why the same
   mechanism serves features and featuresets without a second implementation.

### Independent edits commute

`add`, `drop` and `override` generate a monoid **acting** on the definition. The
law worth having is that two edits naming **different** members produce the same
result in either order (`L-20`, `tests/test_laws.py`).

That is what lets two people edit a shared featureset and have the order of their
edits carry no meaning — the difference between a merge and a conflict whose
resolution is itself a decision. It was never tested until recently, and a
failure could not have been found by testing one edit at a time.

Dependent edits are deliberately **not** claimed to commute: `override` then
`drop` of the same slot is not `drop` then `override`, and the second order is
refused.

### Every operation is total

| Operation | Refused when | Because |
|---|---|---|
| `add` | the member already exists | say `override` if replacing is what is meant; the two read differently to a reviewer and should |
| `drop` | no parent has it | a drop that quietly does nothing leaves a child differing from what its author wrote |
| `override` | no parent has it | say `add` if introducing it is what is meant |

An operation that silently did nothing is one somebody believes happened. That is
the whole argument, and it is why none of the three is idempotent.

### Parents are stamped, and drift is reported

A composition records the **version** of each parent it resolved against. When a
parent moves, the child does not silently change — `drift()` reports which parents
have advanced and by how much, and re-resolution is a deliberate act with a diff.

### Resolution is a read-time act

The fold runs when somebody asks. Storing the resolved result would create a
second copy that can disagree with the parents, which is the failure the pin
exists to prevent, one level along.

`preview` runs the same fold **without declaring anything**, and refuses exactly
what declaring would — so an author can find out what a composition resolves to
without filling the register with attempts.

---

## 3. Not always mutable, and not always permanent

**Sealed.** Final: no amendment, no further versions, no change of owner — and
**still composable**. That combination is the point. Sealing is what makes a
parent safe to build on, because a sealed parent is one that cannot move;
evolution does not stop, it moves to a child where it is visible.

Breaking a seal is administrators-only and requires a reason. A seal anybody could
lift is not a seal; one nobody can lift makes a typo permanent, and the platform
already accepts an administrator escape for deleting a model. Both acts stay in
the chain.

**Ephemeral.** Created for one purpose, read, destroyed — by TTL (default 1 day,
maximum 30) or on request. Two consequences, both refusals:

- **Nothing may depend on one.** A composition pinning an ephemeral parent would
  resolve today and dangle tomorrow, and a dangling pin is worse than no pin
  because it looks like one.
- **It cannot be sealed.** Permanent and temporary are not two flags that happen
  to be set together; one of them is wrong.

Longer than 30 days is refused, with the reason stated: something needed for
longer is not ephemeral, and declaring it so is a way of avoiding the governance a
durable object owes.

**Destruction is recorded.** The rows go and the evidence stays, with the version
digests. A throwaway featureset somebody pulled a million rows through is exactly
what an examiner asks about, and *"it was ephemeral"* is not an answer.

---

## 4. Not always accountable to its author

Two facts, deliberately kept apart:

- **`created_by`** is history, and never changes.
- **`owner`** is a responsibility, and can be transferred — to somebody named, by
  somebody entitled, with the handover in the chain.

An owner field that quietly becomes a leaver's username is how a model ends up
accountable to nobody. `provenance()` reports both and says whether they differ.

Transfer is refused on a sealed object, to nobody, and to the current owner.

---

## 5. What happens between the store and the model

Filling gaps, normalising and aligning are **decisions somebody must make**.
Leaving them to each caller has two failure modes, and both are quiet: the same
feature comes to mean different things in two models, or the awkward columns get
skipped and somebody downstream turns the nulls into zeros without saying so.

So the decision attaches to the feature or featureset as its **default
behaviour**, and a request may override it. The precedence is the composition rule
again, deliberately rather than coincidentally:

```
parents (left to right)  →  the object's own defaults  →  the request
```

Merging is **section by section and column by column**. A parent that fills three
columns and a child that normalises one end up doing both; replacing the section
wholesale would silently drop the parent's decision and its author would never see
it go. `explain()` reports which layer decided each column.

### Normalisation is point-in-time or it is leakage

Statistics are fitted from rows where `event_ts ≤ as_of AND ingest_ts ≤ as_of`,
and from nothing else.

A z-score fitted over the whole column encodes what the mean *turned out* to be,
including the part of the history that had not happened when the row was scored.
That is leakage, and it is invisible afterwards because the column looks
unremarkable.

**A request with no `as_of` is refused** rather than served from the full column.
The leaky answer is the one somebody would get by accident, so it must not be the
default — that is the whole principle, applied here.

Methods: `zscore` · `minmax` · `robust` (median/IQR) · `rank` · `none`. Fewer than
30 observations is refused: a statistic on fewer is a guess with a decimal point.
Vectors and tensors normalise elementwise. A constant column returns zeros and
**says so** rather than dividing by zero silently.

**The fitted statistics come back with the data.** Whoever scores one row tomorrow
must apply the same transform, and a reviewer asking what was done to a column
deserves a number rather than a method name.

### Missing values

Null, NaN and infinity arrive by different routes — no observation, a division
with no answer, an overflow — and are equally unusable, so all three count as
missing. A NaN is never folded into a statistic: doing so makes the statistic a
NaN, which then propagates through every value it touches.

Strategies: `keep` · `constant` · `zero` · `mean` · `median` · `most_frequent`.
The last three fit a statistic and therefore need an `as_of`, for the reason
above.

**The fill rate is part of the answer**, and loud past 20%. Filling forty per cent
of a column with zeros produces a model that trains without complaint and means
nothing.

### The order, and why it is that order

> **Fit on observed → fill → normalise.**

Fitting the normalisation on imputed values would shrink the spread by exactly the
amount that was invented, because every filled cell sits at the centre and pulls
the variance down. So the statistics are fitted on what was observed, then applied
to everything including what was filled.

### Alignment, and the design that makes leakage impossible to hide

Features arrive on their own clocks — a balance monthly, a rating annually, a
price daily and not at weekends. Aligning them onto one axis gives an execution
engine a rectangle instead of a ragged frame.

| Rule | Fills from | Point-in-time safe |
|---|---|---|
| `none` | nothing | **yes** |
| `flat_forward` | the last observation | **yes** |
| `flat_backward` | the next observation | no |
| `linear` | both neighbours | no |
| `nearest` | whichever is closer | no |

Three of the five reach into the future. They are the right answer for drawing a
curve, for an explicitly retrospective backtest, for showing a history to a
person — and wrong for training.

**They are not refused. They are stamped honestly.** A value derived from a later
observation inherits that observation's `ingest_ts`, because that is genuinely
when it became knowable. An ordinary point-in-time read at the grid point then
excludes it, with nobody having to remember a flag.

That is the whole design, and it is the strongest form the idea takes anywhere in
the platform: **the leakage is not caught by a check; it is made arithmetically
impossible to hide.**

Two bounds complete it. A **carry limit** bounds how far an observation may
travel — a balance from eighteen months ago is not this month's balance, and
carrying it forever turns a stale observation into a fabricated one. And
interpolation will not **extrapolate** from one side under the name of
interpolating: that is a different act with a different error, and doing it
silently would hide which was done.

---

## 6. Schema

`feature` gains `shape`, `components`, `composes`, `operations`, `defaults`,
`ephemeral`, `ttl_days`, `sealed_at`, `sealed_by`; `featureset` gains the same
composition and lifecycle columns. One declaration in `db/schema/tables.py`, rendered
to both dialects: `ephemeral` and the other truth values are `Boolean`, `ttl_days`
is an `Integer` because it is a count, and `sealed_at` is a `Double` epoch second.

---

## 7. Interfaces

```
POST /api/v1/features                       shape, components, composes, operations
GET  /api/v1/features/{name}/resolved       the fold, run at read time
POST /api/v1/features/{name}/seal           feature:seal — a distinct permission
POST /api/v1/features/{name}/break-seal     administrators only, with a reason
POST /api/v1/features/{name}/transfer       ownership, to somebody named
PUT  /api/v1/featuresets/{name}/policy      default retrieval behaviour
GET  /api/v1/featuresets/{name}/versions/{v}/prepared   filled, normalised, aligned
```

Defining, sealing and transferring are three permissions. Whoever may define a
thing is not automatically whoever may end it, or whoever may hand it on.

---

## 8. What this deliberately does not do

| | |
|---|---|
| **No automatic feature engineering** | no generated interactions, no suggested transforms. The register records what you chose |
| **No feature importance** | it is a property of a *model*, not of a feature, and putting it here would attach one model's opinion to a shared object |
| **No cross-feature imputation** | filling `x` from `y` is a model; it belongs in a derived feature where its lineage is visible |
| **No silent extrapolation** | see §5 |

---

## 9. Traceability

| Section | Satisfies |
|---|---|
| §1 Dimensionality | `FR-FEA-011`, `FR-FEA-014` |
| §2 Composition | `L-19` (monoid), `L-20` (independent edits commute) |
| §3 Sealing, ephemerality | `FR-FEA-017` |
| §4 Ownership | `FR-SEC-004` |
| §5 Retrieval | `L-10` point-in-time correctness, extended to normalisation and alignment |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
