# Data, pins and the lake

This guide follows a row from the moment it reaches MAYA to the moment it is
sealed in a pin and read back years later. It covers the bitemporal ingest log,
the resolution order, pins and their saga, content-addressed fragments, the two
Delta backends in `maya_delta`, compaction and vacuum, integrity verification
and downloads.

## Where data lives

| Store | Path under `storage.root` (`MAYA_HOME`) | Holds |
|---|---|---|
| Blob store | `blobs/` | every uploaded file, workbook and exported bundle, by SHA-256 |
| Ingest logs | `lake/raw/<namespace>/<feature>/<schema generation>` | one Delta table per feature and schema: every batch ever ingested |
| Feature fragments | `lake/pins/<namespace>/<feature>` | one Delta table per feature: the fragments of its pins |
| Feature-set fragments | `lake/fspins/<namespace>/<set>` | the same for feature-set pins |
| Database | SQLite file, or PostgreSQL | the catalog: definitions, versions, pin manifests, fragment index, audit |

The database never holds data rows, and the lake never holds governance
records. `LakeStore` (in `maya/storage/lake.py`) is the only module that talks
to `maya_delta`.

## The bitemporal ingest log

Every row carries two times.

| Time | Column | Meaning |
|---|---|---|
| Event time | the first index column | what the value is about, such as the trading day |
| Knowledge time | `_knowledge_time` | when MAYA could first have known it |

An ingest **appends** a batch to the feature's log with its knowledge time. A
correction is a new batch with a later knowledge time; nothing is overwritten.
So MAYA can answer both "what is the value?" and "what did we believe on 31
March?".

| How rows arrive | Knowledge time |
|---|---|
| Upload (`csv`, `parquet`, `json`) | `knowledge_time` on the call, else `source.knowledge_time_column` per row, else the moment of ingest |
| Pull (`sql`, `python`) | the source's publication column when the definition names one, else the moment of the pull |
| `delta` source | read at resolution and stamped with the current time; there is no log |

```python
# Ingest a batch, then a correction three days later
import maya.sdk as maya
my = maya.connect(base_url="http://127.0.0.1:8600", api_key="maya_…")
my.features.ingest("eq/prices", open("prices.csv", "rb").read(), fmt="csv",
                   knowledge_time="2026-01-09T18:00:00Z")
out = my.features.ingest("eq/prices", b"date,symbol,close\n2026-01-06,AAA,101.7\n",
                         fmt="csv", knowledge_time="2026-01-12T09:00:00Z")
print(out["rows"], out["restatement"], out["lake_version"])
```

```text
# Expected output
1 True 1
```

Each ingest response carries the stored blob's hash, the row count, the
knowledge time, the Delta table version it produced, `restatement` (the batch
overlaps index keys already in the log) and `duplicate_upload_of` (the same bytes
were uploaded before).

!!! note "The log is keyed by schema"
    The ingest table name includes a digest of the feature's columns and types.
    A version that adds or retypes an attribute therefore starts a fresh log,
    and uploads go to the log of the latest version's schema.

## Resolution, step by step

Every read — a preview, a download, a derivation, a pin — resolves in the same
order, so the answer is reproducible.

| Step | What happens |
|---|---|
| 1. Knowledge-time cut | drop rows known after `as_of_known` (none dropped when it is not given) |
| 2. Latest per key | for each full index key, keep the row with the greatest remaining knowledge time |
| 3. Grid | `as_is`, or every calendar day crossed with every non-date key |
| 4. Date range | the requested `start` and `end` (a pin's `as_of` is its `end`) |
| 5. Rules | each attribute's fill rule, per group, in event-time order |
| 6. Transform | the feature's pipeline |

The plan returned with every preview states what was done, for example:

```json
# A resolution plan
["maya://feature/eq/prices (draft): read ingest log (8 source rows)",
 "knowledge-time cut at now; grid ISO_business_days; rules per attribute"]
```

Continuing the example above, the correction shows up only for readers whose
cut is after it was known:

| Call | `close` for AAA on 2026-01-06 |
|---|---|
| `my.features.preview(ref)` | 101.7 (known 2026-01-12) |
| `my.features.preview(ref, as_of_known="2026-01-10T00:00:00Z")` | 101.5 (known 2026-01-09) |
| `as_of_known` before 2026-01-09T18:00Z | no row: nothing was known yet |

Rows created by the grid have no knowledge time of their own (`NaT`): they are
fills, and the fill report counts them.

## Pins

A pin freezes one resolution as sealed, content-addressed data. It lives in a
named **series** at an **as-of date**: `maya://feature/eq/prices#eom/2026-01-31`.

| Input | Default | Meaning |
|---|---|---|
| `version_no` | — | the version to resolve; it must be approved or published |
| `pin_name` | — | the series; letters, digits, `_` and `-` |
| `as_of` | — | the event-time end date |
| `as_of_known` | the moment of pinning | the knowledge-time cut; the provenance records when it was defaulted |
| `idempotency_key` | none | a retry with the same key returns the same job |

```bash
# Pin from the CLI
python -m maya.cli feature pin eq/prices --version 1 --name eom --as-of 2026-01-09
```

```text
# Expected output (after the job's progress lines)
sealed 5d6539b3ad9d9a96585cadd95e9c0228a78528968c3a731e2626f471cac16bb2 (10 rows, 272 new bytes)
```

### Who pins, and the request path

Someone holding the pin capability starts the pin job at once (state
`materializing`). Anyone else with the request right creates a pin in state
`requested`; a pin authorizer approves it with `my.features.approve_pin(pin_id)`
(**Catalog → Features → Pins**), and the requester can never approve their own
request. In your `scratch.<you>` namespace you always pin directly. Feature-set
pins have no request path: they need the pin permission.

### The pin saga

| Step | On failure |
|---|---|
| Resolve the version at `as_of` and `as_of_known`, recording the fill report and plan | the job fails with the error |
| Run the quality contract | the pin is `failed`, with every check's result stored on it (audit `pin.failed`) |
| Refuse an empty result | `failed`: `Nothing to pin: resolution produced no rows` |
| Cut the rows into fragments and write only the new ones | the job fails; fragments already written become orphans |
| Re-read the fragments and recompute the content hash | `failed`: `Pin hash verification failed after write` |
| Seal: store the manifest and provenance, link lineage, audit `pin.sealed` | — |

A pin is never half-sealed: the manifest and hash are written only in the last
step. A `failed` series and date may be pinned again; a sealed, requested or
materializing one is a conflict: `Pin eom/2026-01-31 already exists (sealed)`.

!!! warning "A job error leaves the pin materializing"
    Only the quality, empty-result and verification failures mark the pin
    `failed`. An unexpected error while resolving or writing fails the job
    (`my.jobs.get(job_id)` shows the error) and leaves the pin row in
    `materializing`, which blocks the same series and date. Pin under another
    date or series.

| State | Meaning |
|---|---|
| `requested` | awaiting a pin authorizer (feature pins only) |
| `materializing` | the job is running |
| `sealed` | hashed, verified, immutable |
| `failed` | the quality contract, an empty result or hash verification failed |
| `retired` | withdrawn by an administrator with a reason (`my.features.retire_pin(pin_id, reason)`) |

### What a sealed pin records

| Field | Content |
|---|---|
| `content_hash` | the hash of the whole pin, over values |
| `schema_digest` | the hash of its column names and types |
| `fragments` | the ordered list of fragment hashes |
| `row_count`, `bytes_total`, `bytes_new` | size, and what this pin added to storage |
| `fill_report` | what every rule filled |
| `quality` | every check's result |
| `provenance` | definition hash, engine version, Python, pyarrow and pandas versions, lake backend, fragment parameters, actor, wall clock, plan, inputs |

Reading a pin (`#series/date`, or `#series` for the latest sealed one) never
resolves anything: it reassembles the stored fragments.

## Content addressing and fragments

Consecutive month-end pins of a long history share almost all their rows. MAYA
therefore stores pins as fragments named by their content.

1. The resolved table is sorted by its index.
2. Every row gets a digest computed over its **values** (canonical encoding),
   never over file bytes.
3. Content-defined chunking cuts the rows into fragments at points chosen by
   those digests, within the configured bounds.
4. Each fragment's hash is taken over its row digests; the pin's content hash
   over the schema digest and the fragment hashes in order.
5. Only fragments the table has never stored are written, one Delta partition
   each (`_fragment`), with a row number (`_row`) to restore order.

Because cut points follow content, an appended month changes only the
fragments at the end; the rest are shared and cost nothing.

| Setting | Default | Meaning |
|---|---|---|
| `lake.fragment.target_rows` | 512 | the typical fragment size |
| `lake.fragment.min_rows` | 32 | no cut before this many rows |
| `lake.fragment.max_rows` | 8192 | a forced cut at this many rows |

The fragment parameters are part of the hash contract and are recorded in every
pin's provenance. Hashes do not depend on which Delta backend wrote the files.

**Admin → Storage** (`/admin/storage`) reports what content addressing saved:

| Field | Meaning |
|---|---|
| `pins`, `fragments` | sealed pins and stored fragments |
| `logical_bytes`, `stored_bytes`, `saved_ratio` | what the pins add up to, what is stored, and the saving |
| `orphan_fragments`, `orphan_bytes` | fragments no sealed pin references (left by failed pins); reported, never deleted automatically |

## The lake: maya_delta and its two backends

`maya_delta` is one API over two interchangeable implementations of Delta Lake.

| Backend | What it is | Chosen when |
|---|---|---|
| `native` | delta-rs through the `deltalake` wheel | it imports and passes a self-check (write and read a tiny table) |
| `pure` | MAYA's own implementation of a declared subset of the Delta transaction-log protocol over pyarrow | `deltalake` is unavailable or fails the self-check, or it is pinned |

```yaml
# config/application.yaml
lake:
  backend: auto        # auto | native | pure
```

Selection is never silent: the chosen backend, its version and the reason are
reported (`LakeBackendInfo`) and recorded in every pin's provenance. Pinning
`native` where it is unusable is an error, not a fallback. The pure backend
refuses, by name, a table that uses a protocol feature it does not implement,
such as deletion vectors or v2 checkpoints, rather than misreading it.

Both backends return the same result contract: the schema in log order, with
normalised types (lists named `element`, timestamps in microseconds, UTC when
zoned).

## Compaction and vacuum

Every ingest and every pin appends files, so tables collect many small files.
MAYA maintains every table under the lake root, on either backend:

1. **Compact** (`optimize`): rewrite small files into larger ones, up to the
   target size, in one commit that changes the layout and not the content.
2. **Vacuum**: delete files no table version needs once they are older than the
   retention window.

| Setting | Default | Meaning |
|---|---|---|
| `lake.maintenance.interval_seconds` | 86400 | how often the scheduler runs it (daily) |
| `lake.maintenance.target_size_mb` | 128 | the compaction target |
| `lake.maintenance.vacuum_retention_hours` | 168 | how long unreferenced files are kept for time travel; below 168 is allowed but is passed through explicitly |

Run it on demand from **Admin → Storage** or the SDK (administrators and
techops):

```python
# Compact and vacuum every lake table now
out = my.admin.lake_maintain()
print(len(out["tables"]), "tables;", out["filesRemoved"], "small files compacted into",
      out["filesAdded"], "-", out["vacuumed"], "unreferenced files vacuumed")
```

Each entry of `tables` gives `table`, `filesRemoved`, `filesAdded`, `vacuumed`
and the resulting `version`. The run is audited as `lake.maintained`.

!!! tip "Why maintenance cannot change a pin"
    A pin is read by fragment value and row number, never by file name, and an
    ingest log is read at its latest version. Compaction moves rows between
    files and vacuum removes files no version needs, so neither can change what
    a pin or an as-of query returns. Integrity verification proves it.

## Integrity verification

Integrity verification re-reads every sealed feature and feature-set pin,
recomputes its content hash and compares it with the sealed one, and verifies
the audit hash chain.

```bash
# Verify every pin and the audit chain
python -m maya.cli admin verify-integrity
```

```text
# Expected output, with two sealed pins in the estate
2 pin(s) checked; drift: 0; audit chain ok: True
```

The command exits 0 when there is no drift and the chain verifies, and 1
otherwise. Any drift notifies every administrator. The SDK call is
`my.admin.verify_integrity()`, returning `checked`, `drift`, per-pin `results`
and `audit_chain`; in the UI it is the **Verify integrity now** button on
**Admin → Storage**.

## Downloads

| Format | Manifest carried as |
|---|---|
| `parquet` (default) | schema metadata |
| `arrow` (IPC file) | schema metadata |
| `json` | `{"manifest": …, "rows": […]}` |
| `ndjson` | the first line |
| `csv` | a first line `# maya-manifest: {…}` |

```bash
# Download a pin as CSV
python -m maya.cli feature download "maya://feature/eq/prices#eom/2026-01-09" \
    --out prices.csv --format csv
```

```text
# The first lines of prices.csv
# maya-manifest: {"axes": {}, "columns": {"_knowledge_time": "timestamp", "close": "float64", "date": "date", "symbol": "string"}, "encoding": null}
date,symbol,close,_knowledge_time
2026-01-05,AAA,100.0,2026-01-09 18:00:00+00:00
```

Nested attributes in CSV need `--csv-encoding` `wide`, `packed` or `json`; CSV
never gets an undeclared array. The download manifest (returned with the bytes)
names the reference, the content hash, the row count, the format, the time and
the reader, the `as_of_known`, any access condition and the combined licence.
Every download is audited, and a licence that forbids the redistribution level
refuses it.

## Scratch data

`python -m maya.cli feature quick prices.csv --name prices` infers a definition
from the file, creates it in your private `scratch.<you>` namespace, ingests
the rows and approves version 1 in one step, marked **ungoverned**. The same
lake, logs and pins apply; only the review is skipped. To govern it, create the
feature in a real namespace.

Related: [Feature definition reference](/help/guides/features-reference) for
sources and rules, and [Tutorial 1](/help/guides/tutorial-01-first-feature) for
a pin and a restatement end to end.
