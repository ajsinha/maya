# Feature set reference

A model does not read features one at a time; it reads a panel. A **feature
set** maps attributes of member features onto the names a model expects,
assembles them on a declared index by a declared alignment, fills the gaps under
a recorded policy precedence, and filters the result. Like a feature, it is
versioned, reviewed, approved and pinned. This page documents every key of a
feature set definition, the resolution order, cascade pins, shapes and
downloads.

## The whole definition at a glance

```json
# A complete feature set definition
{
  "index": ["date", "symbol"],
  "grid": {"calendar": "NYSE"},
  "alignment": {"mode": "asof", "member": "maya://feature/eq/px@v2",
                "tolerance_days": 3, "direction": "backward"},
  "members": [
    {"attr": "close",  "ref": "maya://feature/eq/px@v2",  "source_attr": "close"},
    {"attr": "volume", "ref": "maya://feature/eq/vol@v1", "source_attr": "vol",
     "cast": "float64", "rule": "forward_fill(limit=2)"},
    {"attr": "vix",    "ref": "maya://feature/mkt/vix@v1", "source_attr": "level"}
  ],
  "global_policy": {"rules": {"close": "forward_fill(limit=3)"}, "default": "none"},
  "group_policies": [{"name": "flows", "attrs": ["volume"], "rule": "zero"}],
  "filters": {"start": "2025-01-01", "end": "2025-12-31",
              "universe": {"attr": "symbol", "values": ["AAA", "BBB"]},
              "expr": "close > 0"}
}
```

| Key | Required | Default | Purpose |
|---|---|---|---|
| `index` | yes | — | the set's index; the first column is event time |
| `members` | yes | — | one entry per output attribute |
| `alignment` | no | `{"mode": "inner"}` | how member keys combine into rows |
| `grid` | no | `"as_is"` | a calendar to lay the rows on |
| `global_policy` | no | `{}` | set-wide fill rules |
| `group_policies` | no | `[]` | fill rules for named groups of attributes |
| `filters` | no | `{}` | date range, universe and a row expression |
| `extends` | no | none | inherit a parent set and store only the difference |

Validation at submit refuses, all at once:

| Problem | Message |
|---|---|
| no index | `a feature set declares its index, e.g. [date, symbol]` |
| no members | `a feature set maps at least one attribute` |
| duplicate `attr` | `attribute names must be unique` |
| a member without `attr`, `ref` or `source_attr` | `member mapping {...} is missing 'ref'` |
| an unknown alignment | `alignment.mode must be inner, outer, left or asof` |

## Members

Each entry maps one output attribute to one attribute of one member feature.

| Key | Required | Meaning |
|---|---|---|
| `attr` | yes | the output name, unique in the set |
| `ref` | yes | the member feature: a version (`@v2`) or a pin (`#eom/2026-01-31`) |
| `source_attr` | yes | the attribute of the member to read |
| `cast` | no | a logical type to cast the column to |
| `rule` | no | an attribute-level fill rule: the strongest layer of the precedence |
| `aggregate` | when the member has extra index columns | how to collapse them, for example `last`, `mean`, `sum` |
| `filter` | no | an expression over the member's columns; values where it is false become null |

Several entries may name the same member; it is resolved once. The output type
of an attribute is its `cast` when given, else the member attribute's type.

### Members with a different index

A member may carry **fewer** index columns than the set (a market-wide series
on `[date]` in a `[date, symbol]` set): it is broadcast, joined on the columns
it has. A member with **more** columns than the set (a `[date, symbol, venue]`
series in a `[date, symbol]` set) must declare `aggregate` on every attribute
taken from it, or the definition is refused:
`member '…' has index column(s) ['venue'] the set does not; attribute 'volume' must declare an aggregation`.
At least one member must carry the full set index.

```json
# Collapse venues, broadcast a market series
[
  {"attr": "volume", "ref": "maya://feature/eq/venue_vol@v1", "source_attr": "vol",
   "aggregate": "sum"},
  {"attr": "vix", "ref": "maya://feature/mkt/vix@v1", "source_attr": "level"}
]
```

## Alignment

Alignment decides which index keys become rows, before the grid and the fill.

| Mode | Rows | Extra keys |
|---|---|---|
| `inner` (default) | keys present in every full-index member | — |
| `outer` | keys present in any full-index member | — |
| `left` | the keys of one driving member | `member` (default: the first full-index member) |
| `asof` | the keys of the driving member; others are joined as of the nearest earlier (or later) date | `member`, `tolerance_days` (default 0), `direction` (`backward` default, or `forward`) |

```json
# Drive rows from prices; take each fundamentals value known within 5 days before
{"mode": "asof", "member": "maya://feature/eq/px@v2", "tolerance_days": 5,
 "direction": "backward"}
```

!!! warning "A forward as-of join reads the future"
    `direction: forward` attaches a later observation to an earlier row. Use it
    only for data that is genuinely known at the row's date, and expect
    reviewers to ask why.

## Grid

`"as_is"` keeps the rows alignment produced. `{"calendar": NAME}` lays the rows
on a calendar (`natural_days`, `ISO_business_days`, `NYSE`, `LSE`, `TARGET`)
from `filters.start` (or the first key) to `filters.end` (or the last), crossed
with every non-date key; days with no member value become gaps for the fill.

## Fill policy and its precedence

Members arrive already resolved under their own policies. The set then chooses
one rule per attribute from the first layer that sets one, and re-applies it on
the set's rows, so it fills only the gaps that alignment and the grid created.

| Layer | Set by | `layer` in the manifest |
|---|---|---|
| 1 | the member entry's own `rule` | `attribute` |
| 2 | a `group_policies` entry listing the attribute | `group` |
| 3 | the set's `global_policy` (`rules` for the attribute, else `default`) | `global` |
| 4 | a parent set's `global_policy`, nearest ancestor first | `inherited` |
| 5 | the member feature's own resolution rule for `source_attr` | `member` |
| 6 | nothing: leave it null | `default` |

The rules are those of a feature (see the
[Feature definition reference](/help/guides/features-reference)). A
`group_policies` entry is `{"name", "attrs", "rule"}`; the first entry listing
an attribute wins.

Every preview and pin records the choice per attribute:

```json
# The manifest of a two-attribute set
{"attributes": {
   "x": {"member": "maya://feature/eq/signals@v1", "source_attr": "x",
         "rule": "none", "layer": "default", "source": "system"},
   "y": {"member": "maya://feature/eq/signals@v1", "source_attr": "y",
         "rule": "none", "layer": "default", "source": "system"}},
 "plan": ["maya://feature/eq/signals@v1: read ingest log (180 source rows)",
          "knowledge-time cut at now; grid as_is; rules per attribute",
          "alignment: inner",
          "join member 'maya://feature/eq/signals@v1' on ['date', 'symbol']"],
 "rows": 180, "non_causal": [], "withheld": []}
```

An attribute is listed under `non_causal` when its chosen rule is non-causal or
its member feature is. That list is what a training warrant's leakage
certificate reads.

## Filters

| Key | Meaning |
|---|---|
| `start`, `end` | inclusive bounds on the event-time column; they also bound a calendar grid |
| `universe` | `{"attr": column, "values": [...]}`, or a plain list applied to the second index column |
| `expr` | a row filter in the expression language, applied after the fill |

The resolution order is: resolve members; alignment; grid; joins; `start`,
`end` and `universe`; the fill; then `expr`. Each row's `_knowledge_time` is the
latest knowledge time among the member values it combines.

## Inheritance: extends

A child set names a parent version and stores only overrides.

```json
# A US-only child with a stricter fill on close
{"extends": {"parent": "maya://featureset/eq/panel@v1",
             "override": {"filters": {"universe": {"attr": "symbol", "values": ["AAA"]}},
                          "attribute_rules": {"close": "forward_fill(limit=1)"},
                          "drop_attributes": ["vix"]}}}
```

| Override key | Effect |
|---|---|
| `drop_attributes` | removes members by `attr` |
| `add_members` | appends member entries |
| `attribute_rules` | sets `rule` on named members (layer `attribute`) |
| `filters`, `grid`, `alignment` | replace the parent's |
| `global_policy` | the child's own global policy; the parent's becomes the `inherited` layer |

Inheritance is capped at eight levels:
`Feature set inheritance exceeds the depth cap (8)`.

## Versions, approval and duplicates

Submitting a draft validates the definition and its effective (inherited)
form, then hashes the index, grid, alignment, filters, policies, members
(sorted by `attr`) and the inherited chain. A different set with the same hash
is refused outright, so near-copies are reused rather than multiplied:
`An equivalent feature set already exists: 'panel' v1. Reuse it rather than adding a near-copy`.

The default policy approves a feature set with one `feature_manager` approval
and these checks:

| Check | Passes when |
|---|---|
| `definition_valid` | the definition validates |
| `members_approved` | every member referenced by version is approved or published (pins pass) |
| `no_open_blocking_comments` | no blocking review comment is open |

## Pins and the cascade

Only an approved version can be pinned. A set refuses to pin while any member is
referenced by version rather than by pin, because the data under it could still
move:

```text
# Refused without the cascade
NotApproved: A feature set refuses to pin unless every member is pinned.
Unpinned: maya://feature/eq/signals@v1. Use cascade pin to pin them together.
```

A **cascade pin** pins every such member under the same series and date (a
member that already has a sealed pin of that series and date reuses it), then
resolves the set over those pins and seals it, in one job. Members are pinned
in a fixed order, and if anything fails — a member's quality contract, a write,
the set's own verification — every member pin the cascade created is removed
and the set pin is marked `failed`. It never leaves half a cascade behind.

```bash
# Pin a set and its members together
python -m maya.cli featureset pin eq/panel --version 1 --name q1 --as-of 2026-02-28 --cascade
```

```python
# The same from the SDK
out = my.featuresets.pin("eq/panel", version_no=1, pin_name="q1", as_of="2026-02-28", cascade=True)
print(my.wait(out["job"])["result"])
```

```json
# The job result
{"pin_id": "68fd4ff9-…", "content_hash": "8d27823e…", "rows": 177,
 "cascaded_member_pins": 1}
```

| Pin state | Meaning |
|---|---|
| `materializing` | the job is resolving, pinning members and writing |
| `sealed` | hashed, verified, immutable |
| `failed` | something failed; the cascade was rolled back; the same series and date can be pinned again |

Pinning needs the pin permission on the set; there is no request-and-approve
step for set pins. The same series and date twice is a conflict unless the first
attempt failed: `Pin q1/2026-02-28 already exists`. The sealed pin records its
member pin ids, its fill manifest and its provenance.

### Where a pin's output is kept

The namespace's `materialize_policy` decides whether the resolved output of a set
pin is written to the lake:

| Policy | At sealing | When read |
|---|---|---|
| `always` (default) | written, re-read and verified against its hash | read from the lake |
| `on_demand` | not written; sealed by the content hash of the output | the first read replays it from the member pins and writes it; later reads come from the lake |
| `never` | not written; sealed by the content hash | every read replays it from the member pins |

The policy changes storage, never content. Every policy seals the same hash for
the same inputs. A replay is served only if it reproduces that hash exactly;
otherwise the read fails with `integrity_error` and nothing is returned.
Integrity verification (`maya admin verify-integrity`) replays unwritten pins the
same way and reports any that no longer reproduce. The first write under
`on_demand` is audited as `pin.materialized`.

```python
# Keep only the recipe for a namespace's feature-set pins
admin.namespaces.update("research", materialize_policy="never")
```

## Reading a feature set

| Call | What it returns |
|---|---|
| `my.featuresets.draft_preview(ref)` | the editable draft, resolved live: up to 200 rows, the columns and the manifest |
| `my.featuresets.preview(ref, as_of_known=None)` | a version or a pin: rows, columns, manifest |
| `my.featuresets.download(ref, format, shape, csv_encoding)` | bytes plus a manifest |

Access control applies member by member. Attributes from a member you may not
read are left out and listed under `withheld`; if you can read none, the read is
refused (`You cannot read any member of this feature set`). Row filters and
column masks granted to you apply too, and are listed under
`access_conditions`.

## Shapes and downloads

| Shape | Form | Download |
|---|---|---|
| `tabular` (default) | one row per key; nested attributes kept as nested columns | yes |
| `wide` | nested values exploded into suffixed columns | yes |
| `tensor` | dense arrays plus an axis manifest, in memory | no: refused, reshape with `maya.resolution.shapes.to_shape` |

Formats are `arrow`, `parquet` (default), `json`, `ndjson` and `csv`. A CSV
starts with a `# maya-manifest:` line naming every column's logical type; a
nested attribute in CSV needs a declared `csv_encoding` of `wide`, `packed`
(base64 of little-endian binary) or `json`.

```bash
# Download a pinned panel
python -m maya.cli featureset download "maya://featureset/eq/panel#q1/2026-02-28" \
    --out panel.parquet --format parquet --shape tabular
```

The manifest names the reference, the row count, the format and shape, the
time and the reader, anything withheld and any access condition applied; every
download is audited.

## References

| Reference | Addresses |
|---|---|
| `maya://featureset/eq/panel@v1` | version 1, resolved live over its members |
| `maya://featureset/eq/panel#q1` | the latest sealed pin in the `q1` series |
| `maya://featureset/eq/panel#q1/2026-02-28` | one sealed pin |

Training warrants accept either a version or a pin. Bind to a pin when the
training data must never move; the warrant records which pin it drew.

## In the UI

* **Workbench → Feature set builder** (`/workbench/featuresets/new`) builds the
  definition and previews it (`/workbench/featuresets/{ns}/{name}/preview`).
* **Catalog → Feature sets** (`/catalog/featuresets`) lists sets; each set's
  page carries its versions, transitions, pins and the pin form (with the
  cascade box).

[Tutorial 2](/help/guides/tutorial-02-featureset-and-model) builds, approves and
cascade-pins a set end to end.
