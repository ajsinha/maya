# 16 — Features Composed, Shaped and Prepared

*MAYA — Model & AI Lifecycle Assurance.*  **Evidence, not assertion.**

**Annex to** [07 — The Feature Platform](07-feature-platform.md), alongside
[15 — Featuresets and the Parameter Object](15-featuresets-and-parameters.md).
The composition monoid is [00 §5.4](00-mathematical-foundations.md#54-composition-of-definitions-is-a-monoid).

*A feature is not always a number, is not always defined in one place, and does
not always outlive the request that made it. This is the specification for the
five things that follow from that.*

---

## 1. Dimensionality

`core/features/shapes.py`

A feature carries a **shape** and, along its first axis, optional **component
names**.

| Shape | Kind | Example |
|---|---|---|
| `()` | scalar | `dscr` |
| `(10,)` | vector | a yield curve at ten tenors |
| `(10, 10)` | matrix | the correlation between them |
| `(5, 10, 10)` | tensor | that matrix under five scenarios |

Rank is capped at 4 and any axis at 100,000: beyond that a "feature" is a
dataset with a name, and a feature view of its own is the honest home.

**Component order is the axis order.** A curve whose tenors came back
alphabetically would be a different curve, and one nobody would notice was wrong,
so resolution preserves insertion order and never sorts.

Naming *some* entries and not others is refused — the rest would be identified
only by position, which is what the names exist to avoid. So is naming any on a
scalar, and so are duplicates, because an operation on a duplicated name would be
ambiguous.

`check_rows` samples the values against the declared shape. A declared shape
nobody verifies is a comment, and a model given ten tenors where it expected
eleven produces an answer rather than an error.

---

## 2. Composition

`core/features/composition.py`

Inheriting from one parent and combining several are the same operation with a
different arity, so there is one mechanism and inheritance is the one-parent case.

> **A left-to-right fold in which the rightmost wins. An object's own operations
> are applied last, and are therefore the most prominent of all.**

```
compose([a, b, c]) = merge(merge(a, b), c)     then the object's own operations
```

Nothing else would be defensible: if a parent could override a child, naming a
parent would be an act of surrender.

### Why the closure property holds

Merge-with-rightmost-wins over a keyed map is **associative**, and the empty map
is its **identity**. Composition is therefore a **monoid**, which is precisely
what makes *a combination of features is a feature* and *a combination of
featuresets is a featureset* true statements rather than aspirations: grouping
does not matter, and the empty composition is the thing itself.

Both properties are asserted in `tests/test_composition.py`.

### Operations, and their totality

| Operation | Refused when |
|---|---|
| `add` | a parent already has it — say `override`; the two read differently to a reviewer and should |
| `drop` | no parent has it |
| `override` | no parent has it — say `add` |

Each refusal exists because the no-op alternative is worse: a child that quietly
differs from what its author believed they had written.

Also refused: a cycle (no fixed point to resolve to), a chain deeper than 12 (a
modelling problem rather than a depth problem), and composing anything ephemeral.

### Parents are stamped, and drift is reported

A composition records the parent's **`definition_version`** — which definition of
it the child was written against. A parent that could move underneath its
children unremarked is adversarial finding **C-2** wearing a third hat: the
child's digest stable while its contents were not.

Be exact about what the stamp does, because the obvious reading is wrong and this
is the third place in the platform where the wrong reading has cost something.
**Resolution reads the parent as it currently stands.** The stamp is compared
against the parent's live `definition_version`, and any difference surfaces as
`drift` on the resolved view — naming the parent, the version composed against,
the version it is at now, and whether it has since been sealed. It does not
freeze the parent and it does not refuse the read: a child whose parent has moved
is a thing to be *told about*, not a read that should fail, because the parent
usually moved for a good reason and failing closed would make the platform
unusable at exactly the moment somebody improved a definition.

So this is a **detector, not a pin**, and the word matters. Calling it a pin
would repeat C-2's original error one abstraction higher — a name that sounds
like a guarantee over something that can still move.

> **A gap, stated rather than left to be found.** Featuresets compose by the same
> fold and **carry no stamp**: `composes` records the parent's name and nothing
> about which definition of it. A composed featureset therefore has no drift to
> report, which is the same finding a third time, still open. It is recorded in
> [11 · C-2](11-adversarial-review.md) rather than only here.

### Resolution is a read-time act

The row holds what the object *declares*; resolution happens on read. Storing the
resolved set would apply the operations a second time on the next read — which is
a bug the tests caught, and the reason `resolve` is idempotent by construction
rather than by care.

`explain()` answers the question a reviewer actually asks about an inherited
thing, which is never *what does it have* but *which of these did somebody here
decide*.

---

## 3. Sealing and ephemerality

`core/features/lifecycle.py`

**Sealed.** Final: no amendment, no further versions, no change of owner — and
still composable. That combination is the point. Sealing is what makes a parent
safe to build on, because a sealed parent is one that cannot move; evolution does
not stop, it moves to a child where it is visible.

Breaking a seal is administrators-only and requires a reason. A seal anybody
could lift would not be a seal; one nobody could lift makes a typo permanent, and
the platform already accepts an administrator escape for deleting a model. Both
acts stay in the chain.

**Ephemeral.** Created for one purpose, read, destroyed — by TTL (default 1 day,
maximum 30) or on request. Two consequences, both refusals:

- **Nothing may depend on one.** A composition pinning an ephemeral parent would
  resolve today and dangle tomorrow, and a dangling pin is worse than no pin
  because it looks like one.
- **It cannot be sealed.** Permanent and temporary are not two flags that happen
  to be set; one of them is wrong.

Longer than 30 days is refused with the reason stated: something needed for
longer is not ephemeral, and declaring it so is a way of avoiding the governance a
durable object owes.

**Destruction is recorded.** The rows go and the evidence stays, with the version
digests. A throwaway featureset somebody pulled a million rows through is exactly
what an examiner asks about, and *"it was ephemeral"* is not an answer.

---

## 4. Ownership

Two facts, kept apart:

- **`created_by`** is history and never changes.
- **`owner`** is a responsibility and can be transferred — to somebody named, by
  somebody entitled, with the handover in the chain.

An owner field that quietly becomes a leaver's username is how a model ends up
accountable to nobody. `provenance()` reports both and says whether they differ.

Transfer is refused on a sealed object, to nobody, and to the current owner.

---

## 5. Retrieval: policy, preparation, normalisation, alignment

`core/features/policy.py`, `preparation.py`, `normalisation.py`, `alignment.py`

### The policy, and where it comes from

Filling gaps, normalising and aligning are decisions somebody must make. Leaving
them to each caller has two failure modes: the same feature means different
things in two models, or the awkward columns are skipped and somebody downstream
turns the nulls into zeros without saying so.

So the decision attaches to the feature or featureset as its **default
behaviour**, and a request may override it. The precedence is **the composition
rule again**, deliberately:

```
parents (left to right)  →  the object's own defaults  →  the request
```

Merging is **section by section and column by column**. A parent that fills three
columns and a child that normalises one end up doing both; replacing the section
wholesale would silently drop the parent's decision, and the child's author would
never see it go. `explain()` reports which layer decided each column.

### Point-in-time normalisation

Statistics are fitted from rows where `event_ts <= as_of AND ingest_ts <= as_of`,
and from nothing else.

A z-score fitted over the whole column encodes what the mean *turned out* to be,
including the part of the history that had not happened when the row was scored.
That is leakage, and it is invisible afterwards because the column looks
unremarkable. **A request with no `as_of` is refused** rather than served from the
full column: the leaky answer is the one somebody would get by accident, so it is
the one that must not be the default.

Methods: `zscore` · `minmax` · `robust` (median/IQR) · `rank` · `none`. Fewer than
30 observations is refused — a statistic on fewer is a guess with a decimal point.
Vectors and tensors normalise elementwise. A constant column returns zeros and
*says so* rather than dividing by zero silently.

**The fitted statistics come back with the data.** Whoever scores one row
tomorrow must apply the same transform, and a reviewer asking what was done to a
column deserves a number rather than a method name.

### Missing values

Null, NaN and infinity arrive by different routes — no observation, a division
with no answer, an overflow — and are equally unusable, so all three count as
missing. A NaN is never folded into a statistic; doing so makes the statistic a
NaN, which then propagates through every value it touches.

Strategies: `keep` · `constant` · `zero` · `mean` · `median` · `most_frequent`.
The last three fit a statistic and therefore need an `as_of`, for the same reason.

**The fill rate is part of the answer**, and loud past 20%: filling forty per cent
of a column with zeros produces a model that trains without complaint and means
nothing.

### The order, and why it is the order

> **Fit on observed → fill → normalise.**

Fitting the normalisation on imputed values would shrink the spread by exactly the
amount that was invented, because every filled cell sits at the centre and pulls
the variance down. So the statistics are fitted on what was observed and then
applied to everything, including what was filled.

### Alignment

Features arrive on their own clocks — a balance monthly, a rating annually, a
price daily and not at weekends. Aligning them onto one axis and filling the gaps
gives an execution engine a rectangle instead of a ragged frame.

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

**They are not refused. They are stamped honestly**, and the machinery already
here does the rest: a value derived from a later observation inherits that
observation's `ingest_ts`, because that is genuinely when it became knowable. An
ordinary point-in-time read at the grid point then excludes it, with nobody
having to remember a flag.

That is the whole design. The leakage is not caught by a check; it is made
arithmetically impossible to hide.

A **carry limit** bounds how far an observation may travel: a balance from
eighteen months ago is not this month's balance, and carrying it forever turns a
stale observation into a fabricated one. Interpolation will not **extrapolate**
from one side under the name of interpolating — that is a different act with a
different error, and doing it silently would hide which was done.

---

## 6. Schema

Added to `feature`: `shape`, `components`, `composes`, `operations`, `defaults`,
`definition_version`, `sealed_at`, `sealed_by`, `seal_note`, `ephemeral`,
`expires_at`, `created_by`.

Added to `featureset`: `composes`, `operations`, `defaults`, `sealed_at`,
`sealed_by`, `seal_note`, `ephemeral`, `expires_at`.

Identical in both dialects, as everything here is.

---

## 7. Interfaces

```
GET    /api/v1/retrieval                     the rules, published
GET    /api/v1/features/{name}/resolved      composition, shape, policy, lifetime
POST   /api/v1/features/{name}/amend         feature:define — refused when sealed
POST   /api/v1/features/{name}/seal          feature:seal
POST   /api/v1/features/{name}/break-seal    principal:manage, with a reason
POST   /api/v1/features/{name}/transfer      hand on the responsibility
DELETE /api/v1/features/{name}               ephemeral only

GET    /api/v1/featuresets/{name}/resolved   slots, lineage, policy, who decided
POST   /api/v1/featuresets/{name}/seal       featureset:seal
PUT    /api/v1/featuresets/{name}/policy     default retrieval behaviour
POST   /api/v1/featuresets/{n}/versions/{v}/prepared    aligned, filled, normalised
```

`feature:seal` and `featureset:seal` are their own permissions: sealing makes
something final, and whoever may define a thing is not automatically who may end
it. Both sit with the second line.

---

## 8. What this deliberately does not do

- **No transformation language in a policy.** A policy says `fill`, `normalise`
  and `align` and nothing else; one that could say anything would be a scripting
  language wearing a dictionary's clothes.
- **No refusal of the unsafe rules.** Back-fill and interpolation are offered,
  labelled, and stamped so a point-in-time read excludes them. Forbidding a
  legitimate analytical tool would only move it somewhere MAYA cannot see.
- **No automatic sealing, no automatic transfer.** Both are decisions with a name
  attached, and inferring them would remove the name.

---

## 9. Traceability

| Section | Satisfies |
|---|---|
| §1 Dimensionality | `FR-FEA-021`; a shape checked rather than declared |
| §2 Composition | `FR-FEA-022..024`; **C-2** at the composition level |
| §3 Sealing, ephemerality | `FR-FEA-025..027` |
| §4 Ownership | `FR-FEA-028`; accountability that survives a leaver |
| §5 Retrieval | `FR-FEA-029..032`; `L-10` extended to normalisation and alignment |

---

Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).
*Not legal, regulatory or financial advice — see NOTICE §4.*
