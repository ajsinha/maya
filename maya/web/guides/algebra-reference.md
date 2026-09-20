# Feature algebra reference

A derived feature is not a copy of data and not a script. Its source is a
**derivation**: an operator applied to other features. Every operator takes
features and yields a feature definition, so results compose. This page lists
every operator, its arity, its options with their defaults, its typing rule, how
it executes, and what it does to causality.

## How a derivation works

Each operator has two halves.

| Half | When it runs | What it does |
|---|---|---|
| **typecheck** | at submit, with no data | checks arity, index compatibility, attribute names and types; computes the output index and schema |
| **execute** | whenever the feature is read or pinned | resolves each operand, then replays the operator over the resolved frames |

So a mistake surfaces when the version is submitted, with the operator's own
message, and never in a nightly job. The typecheck also runs again before every
execute.

A derivation lives in `source`:

```json
# A derived feature: the union of two vendors
{
  "schema": [{"name": "close", "type": "float64"}],
  "source": {
    "type": "derived",
    "derivation": {
      "operator": "union",
      "operands": ["maya://feature/eq/px_vendor_a@v2",
                   "maya://feature/eq/px_vendor_b@v1"],
      "options": {"collision": "prefer_left"}
    }
  },
  "resolution": {"grid": "as_is", "rules": {}},
  "transform": [], "quality": []
}
```

| Key | Meaning |
|---|---|
| `operator` | one of the twelve operators below |
| `operands` | feature references, in order; a version (`@v2`) or a pin (`#eom/2026-01-31`) |
| `options` | the operator's options; omitted means every default |

A derived feature declares no `index` of its own: the typecheck supplies it.
It still declares a `schema`, naming the attributes the operator produces (it
is validated like any other schema), and it may carry its own `resolution`,
`transform` and `quality`, which run on the operator's output. Derivations nest
up to a depth of 16.

The change class of a new version of a derived feature is computed like any
other feature's, by comparing its index and schema with the previous version
(see the [Feature definition reference](/help/guides/features-reference)).

!!! tip "Reference versions, not the moving head"
    An operand written without `@v` or `#` means the latest approved version at
    the moment of resolution. Name a version or a pin so the derived feature
    cannot move when someone approves an operand's next version.

## The operators at a glance

| Operator | Notation | Operands | Options | Output index |
|---|---|---|---|---|
| `project` | π[attrs](F) | 1 | `attrs` | F's |
| `rename` | ρ[a→b](F) | 1 | `mapping` | F's |
| `transform` | τ[pipeline](F) | 1 | `pipeline` | F's |
| `union` | F₁ ∪ F₂ ∪ … | 2 or more | `collision` | shared |
| `intersect` | F₁ ∩ F₂ | 2 | `priority` | shared |
| `difference` | F₁ ∖ F₂ | 2 | — | shared |
| `compose` | F₁ ⋈ F₂ | 2 | `prefixes`, `broadcast` | shared, or the wider |
| `coalesce` | ⊕(F₁, F₂, …) | 2 or more | — | shared |
| `aggregate` | γ[by, agg](F) | 1 | `by`, `agg` | `by` |
| `lag` | lag[n](F) | 1 | `n`, `attrs` | F's |
| `resample` | resample[freq](F) | 1 | `freq`, `agg` | F's |
| `case` | σ[cond](F₁, F₂) | 2 | `cond` | shared |

"Shared" means every operand must have **identical** index columns in the same
order; otherwise the typecheck refuses with
`operator 'union' needs identical indexes; got ['date', 'symbol'] and ['date']`.

An unknown operator is refused with the list of allowed ones. The wrong number
of operands is refused as `operator 'intersect' takes 2 operand(s), got 3`.

## Single-operand operators

### project

Keeps only the named attributes. The index is always kept.

| Option | Required | Rule |
|---|---|---|
| `attrs` | yes | a non-empty list of existing attributes |

```json
# Keep only the close
{"operator": "project", "operands": ["maya://feature/eq/ohlc@v1"],
 "options": {"attrs": ["close"]}}
```

Error: `project names unknown or no attribute(s) ['clsoe']`.

### rename

Renames attributes. Index columns cannot be renamed.

| Option | Required | Rule |
|---|---|---|
| `mapping` | yes | old name → new name; every old name must exist; no duplicates may result |

```json
# Rename a vendor's column to the house name
{"operator": "rename", "operands": ["maya://feature/eq/px_vendor_b@v1"],
 "options": {"mapping": {"px_last": "close"}}}
```

Errors: `rename cannot rename index columns`, `rename names unknown attribute(s) [...]`,
`rename produces duplicate attribute names`.

### transform

Runs a transformation pipeline over one feature. The steps are exactly those of
a feature's `transform` list (`rename`, `cast`, `filter`, `derive`, `aggregate`,
`pivot`, `unpivot`, `window`, `lag`, `resample`, `dedupe`, `clip`,
`winsorize`); see the [Feature definition reference](/help/guides/features-reference).
The output schema is computed from the steps without running them.

| Option | Required | Rule |
|---|---|---|
| `pipeline` | yes | a list of steps |

```json
# A 20-day rolling mean over another feature
{"operator": "transform", "operands": ["maya://feature/eq/px@v2"],
 "options": {"pipeline": [
   {"op": "window", "attr": "close", "fn": "mean", "size": 20, "name": "close_ma20"}]}}
```

### aggregate

Groups by part of the index and aggregates each attribute.

| Option | Required | Rule |
|---|---|---|
| `by` | yes | a non-empty subset of the operand's index; becomes the output index |
| `agg` | yes | attribute → function; only the attributes named survive |

Output types: `count` gives `int64`; `mean` and `std` give `float64`; any other
function keeps the attribute's type.

```json
# Average close per day across symbols
{"operator": "aggregate", "operands": ["maya://feature/eq/px@v2"],
 "options": {"by": ["date"], "agg": {"close": "mean"}}}
```

Errors: `aggregate 'by' must be a non-empty subset of the index`,
`aggregate needs an aggregation per attribute; unknown [...]`.

### lag

Shifts values `n` rows back, within each group (every index column after the
first), in index order.

| Option | Default | Rule |
|---|---|---|
| `n` | `1` | a whole number ≥ 0 |
| `attrs` | every attribute | the attributes to shift; the rest are left as they are |

```json
# Yesterday's close
{"operator": "lag", "operands": ["maya://feature/eq/px@v2"], "options": {"n": 1}}
```

!!! warning "A negative lag is refused"
    `n = -1` would put tomorrow's value on today's row. It is refused at submit:
    `lag n must be non-negative; a negative lag is look-ahead`. The `lag`
    transform step has the same guard, so the pipeline is not a back door.

### resample

Moves to a lower frequency, per group.

| Option | Default | Rule |
|---|---|---|
| `freq` | — (required) | `W` (weeks ending Friday), `M` (month end) or `Q` (quarter end) |
| `agg` | `last` for every attribute | attribute → aggregation |

```json
# Month-end close from a daily feature
{"operator": "resample", "operands": ["maya://feature/eq/px@v2"],
 "options": {"freq": "M", "agg": {"close": "last"}}}
```

Error: `resample freq must be W, M or Q`.

## Set operators

### union

Stacks the rows of two or more features with identical indexes and identical
attribute names. Types are unified attribute by attribute.

| Option | Default | Values |
|---|---|---|
| `collision` | `error` | `error`: any index key present in more than one operand fails the read; `prefer_left`: keep the earliest operand's row; `prefer_right`: keep the latest's |

```json
# Two vendors, the first wins where both have a row
{"operator": "union",
 "operands": ["maya://feature/eq/px_vendor_a@v2", "maya://feature/eq/px_vendor_b@v1"],
 "options": {"collision": "prefer_left"}}
```

With `collision: error`, operand order cannot matter, so the operands are
sorted before hashing: `A ∪ B` and `B ∪ A` hash the same and a duplicate
definition is caught at submit. With a preference, order is meaningful and is
kept. At read time an `error` collision fails with
`union has 4 colliding index row(s) and collision policy 'error'`.

### intersect

Rows whose index key is present in both operands.

| Option | Default | Values |
|---|---|---|
| `priority` | `left` | `left` keeps the first operand's values; `right` the second's |

### difference

Rows of the first operand whose index key is absent from the second. The output
schema is the first operand's.

```json
# Prices for symbols not on the restricted list
{"operator": "difference",
 "operands": ["maya://feature/eq/px@v2", "maya://feature/eq/restricted@v1"]}
```

`difference` requires identical indexes but not identical attributes.

## Combining operators

### compose

Joins two features side by side on the index (an outer join).

| Option | Default | Rule |
|---|---|---|
| `prefixes` | `["", ""]` | a prefix for each operand's attribute names |
| `broadcast` | `false` | allow one index to be a subset of the other |

Attribute names must not clash after prefixing:
`compose attribute name clash ['close']; declare prefixes`.

With `broadcast: true` and one index a subset of the other (for example
`[date, symbol]` and `[date]`), the wider index drives the rows and the
narrower operand is left-joined onto them: a market-wide series broadcast to
every symbol. Without it, differing indexes are refused.

```json
# Prices beside volumes
{"operator": "compose",
 "operands": ["maya://feature/eq/px@v2", "maya://feature/eq/vol@v1"],
 "options": {"prefixes": ["px_", "vol_"]}}
```

```json
# A market factor broadcast onto every symbol
{"operator": "compose",
 "operands": ["maya://feature/eq/px@v2", "maya://feature/mkt/vix@v1"],
 "options": {"broadcast": true}}
```

### coalesce

For every index key present in any operand, each attribute takes the first
non-null value, operand by operand, in order. Indexes and attribute names must
match; types are unified.

```json
# The primary vendor, falling back to the secondary
{"operator": "coalesce",
 "operands": ["maya://feature/eq/px_primary@v3", "maya://feature/eq/px_backup@v1"]}
```

### case

Takes the first operand's values where a condition holds, and the second's
elsewhere, row by row over the union of their keys.

| Option | Required | Rule |
|---|---|---|
| `cond` | yes | an expression over the first operand's attributes and index columns |

The expression language is the one used by `filter` and `derive` steps. It is
canonicalized before hashing. A null condition counts as false.

```json
# Live price where it is positive, end-of-day otherwise
{"operator": "case",
 "operands": ["maya://feature/eq/px_live@v1", "maya://feature/eq/px_eod@v1"],
 "options": {"cond": "close > 0"}}
```

Error: `case condition refers to unknown name(s) ['clsoe']`.

## Typing rules

| Rule | Operators | Error |
|---|---|---|
| Identical indexes | `union`, `intersect`, `difference`, `coalesce`, `case`; `compose` without `broadcast` | `needs identical indexes` |
| Identical attribute names | `union`, `intersect`, `coalesce`, `case` | `needs identical attributes` |
| Type unification | same as above | the pair of types that cannot be unified |
| Known attributes | `project`, `rename`, `aggregate`, `lag`, `case` | names the unknown attribute |
| No name clash | `compose`, `rename` | names the clash |

## Causality

The output of an operator is **non-causal** if any operand is. An operand is
non-causal when its own resolution uses a rule that reads the future
(`backward_fill`, `linear_interp`, `spline_interp`) or when it is itself built on
one. The flag is set at submit, stored on the version, reported in the fill
report and carried into every feature set and training warrant downstream,
where the leakage certificate refuses it unless justified.

No operator can introduce look-ahead of its own: the only one that shifts in
time, `lag`, refuses a negative `n`.

## Hashing and duplicates

The definition hash of a derived feature covers the operator, its canonical
options (pipelines and conditions canonicalized) and the operand references.
Consequences:

* a different operand version is a different definition;
* reformatting a condition or reordering a step's keys is not a change;
* for `union` with `collision: error`, operand order is not a change;
* a second feature with an identical derivation is flagged for the reviewer.

## Lineage and licences

Submitting a derived feature records its structure. Approving it writes
lineage: each operand is linked to an operator node with an `operand_of` edge
(labelled with its position), and the operator node to the feature with a
`derived_from` edge. The lineage graph therefore shows exactly what a derived
feature is built from.

Before the typecheck, the licences of every operand are combined; a vendor
whose terms say `derived_works: forbidden` stops the submit, naming the vendor
and the clause.

## The canvas

`/lineage?root=maya://feature/ns/name@v1` draws that graph. Object versions and
pins are nodes, operators are diamonds, and edges are styled by type. It is also
on the Lineage tab of every object page.

| Control | What it does |
|---|---|
| Direction | upstream (what built this), downstream (what breaks if I change this), or both — re-fetched in place |
| Depth | how far to walk |
| Overlay | recolours by **freshness**, **approval status**, **access** or **cost**, and writes the value into the label as well |
| Type, Namespace, Status | narrows what is drawn, stating how many nodes the filter removed |
| Pinned only | keeps the pins |
| Collapse inheritance chains | folds a chain of `extends` into one node with the count folded into it; click it to expand |
| Cluster the far graph | beyond ~300 nodes MAYA does this itself: the root's neighbourhood is drawn in full and the rest counted per namespace |

Click a node for its detail — owner, state, when it last changed, and for an
operator its notation, typing rule and collision policy. Double-click to re-root.
Select two or more features (shift-click, or the list under *The same graph in
words*, which is keyboard-reachable) and the canvas offers an operator: it opens
the feature designer prefilled with that algebra. One feature set selected offers
its cascade pin.

**What the canvas will not do is draw a smaller graph quietly.** `GET /lineage`
leaves out every object you may not read and counts them; the canvas draws that
count as a node of its own and says it in words under the graph. On a review
screen the canvas carries the change as an overlay: added nodes green, changed
amber, removed struck through, taken from the same semantic diff as the table.

## Worked example: SDK

```python
# Create, submit and preview a derived feature
import maya.sdk as maya

my = maya.connect(base_url="http://127.0.0.1:8600", api_key="maya_…")

definition = {
    "schema": [{"name": "px_close", "type": "float64"}, {"name": "vol_volume", "type": "int64"}],
    "source": {
        "type": "derived",
        "derivation": {
            "operator": "compose",
            "operands": ["maya://feature/eq/px@v2", "maya://feature/eq/vol@v1"],
            "options": {"prefixes": ["px_", "vol_"]},
        },
    },
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [],
}
my.features.create("eq", "px_vol", definition)
my.features.transition("eq/px_vol", 1, "submit")  # the typecheck runs here
print(my.features.draft_preview("eq/px_vol")["plan"])
```

The plan names the operator and its operands, for example
`maya://feature/eq/px_vol (draft): algebra 'compose' over 2 operand(s)`.

In the UI, choose **Derived** as the kind of definition in
**Workbench → Feature designer** (`/workbench/features/new`), pick the operator,
list the operands one per line, and give the options as JSON.

## Operators or transform steps?

Row-level work within one feature (windows, casts, filters, computed columns)
belongs in a transform pipeline: in the feature's own `transform` list, or via
the `transform` operator over another feature. Operators are for combining,
reshaping or re-indexing features. `lag`, `aggregate` and `resample` exist in
both places; the operator form makes the result a separately governed feature
with its own version, lineage and pins.
