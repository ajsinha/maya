# Orphaned pin partitions

For the administrator or `techops` engineer who has been told the lake is bigger than the
pins in it. A pin is a saga (§15.3): write the Delta partition, verify the hash, commit the
metadata. If the last step never happens, or the pin is later failed or cancelled, the
partition it wrote stays on disk with nothing referencing it. MAYA reports those fragments and
**never deletes them**, because a garbage collector that is wrong once destroys a sealed
pin — so reclaiming the space is a deliberate, stop-the-world procedure, described here in
full and marked plainly as unsupported.

The related runbook is [stuck or failed jobs and pins](stuck-or-failed-jobs-and-pins.md),
which is about the job that left the mess. This one is about the bytes it left behind.

## Symptoms

- `/admin/storage` (or `GET /api/v1/system/storage`) reports orphans:

  ```json
  {
    "pins": 2,
    "fragments": 6,
    "logical_bytes": 1357,
    "stored_bytes": 3258,
    "referenced_bytes": 1357,
    "saved_ratio": 0.0,
    "orphan_fragments": 4,
    "orphan_bytes": 1901,
    "gc_note": "Orphans are fragments no sealed pin references (left by failed pins). They are reported, never deleted automatically."
  }
  ```

- `storage.root` grows while the pin count does not.
- `maya_pins{state="failed"}` or `maya_pins{state="materializing"}` is above zero in `/metrics`;
  the `MayaPinStuckMaterializing` alert fires after an hour
  ([the rules file](../../config/prometheus/maya-slo.rules.yml)).
- `python -m maya.cli admin verify-integrity` is still clean: orphans are not drift. Nothing
  is broken — there is simply rubbish.

## Diagnosis

Orphan bytes on their own do not tell you whether to act. Three questions do.

**1. How much, and in which table.**

```bash
curl -s "$MAYA_URL/api/v1/system/storage" -H "Authorization: Bearer $MAYA_API_KEY" \
  | python -c "import json,sys; r=json.load(sys.stdin)['data']; print(r['orphan_fragments'], 'fragment(s),', r['orphan_bytes'], 'bytes')"
```

Per table, from `/metrics` (`maya_delta_files` and `maya_delta_bytes` are the current
snapshot, so they include orphans; `maya_namespace_pin_bytes` counts only sealed pins — the
difference is the waste):

```bash
curl -s "$MAYA_URL/metrics" | grep -E "^maya_delta_(files|bytes)|^maya_namespace_pin_bytes"
```

**2. Which pins left them.** Every orphan comes from a pin that is not `sealed`:

Save this as `unsealed.py` and run it with MAYA stopped, or against a copy:

```python
import os, sqlite3
c = sqlite3.connect(os.environ["MAYA_HOME"] + "/maya.db")
for row in c.execute(
    "SELECT p.state, n.name||'/'||f.name||'#'||p.pin_name||'/'||p.as_of_date,"
    " json_array_length(p.fragments), p.failure"
    " FROM feature_pins p JOIN features f ON f.id=p.feature_id"
    " JOIN namespaces n ON n.id=f.namespace_id"
    " WHERE p.state <> 'sealed' ORDER BY p.state"):
    print(*row, sep="  ")
```

On a throwaway estate with two failed and two stalled pins it prints:

```text
failed  eq/prices#20260105/2026-01-05  1  simulated for the runbook
failed  eq/prices#20260115/2026-01-15  1  simulated for the runbook
materializing  eq/prices#20260110/2026-01-10  1  None
materializing  eq/volumes#20260105/2026-01-05  1  None
```

On PostgreSQL the same query through `psql -d maya -c`, with `jsonb_array_length`.

**3. Whether anything is still in flight.** A pin that is `materializing` may simply be
*running*. Close those out first — [stuck jobs and pins](stuck-or-failed-jobs-and-pins.md) —
because a partition belonging to a live pin is not an orphan, and deleting it would break the
pin that is about to seal.

On disk, each fragment is its own partition directory:

```bash
ls "$MAYA_HOME/lake/pins/<namespace>/<name>/"
# _delta_log  _fragment=707d32c2…  _fragment=9156b446…  _fragment=25c41be5…
```

## Steps

1. **Decide whether to act at all.** Orphans are harmless: nothing reads them, they never
   affect a hash, and `verify-integrity` ignores them. On any estate where the waste is a few
   percent, record the number and move on. The cost of the procedure below — downtime and a
   rewrite of a Delta table — is real, and the benefit is only disk.
2. **Close the pins out first.** Fail every stalled pin properly, so the fragment list you are
   about to trust is not about to change:

   ```bash
   curl -s -X POST "$MAYA_URL/api/v1/jobs/<job-id>/cancel" -H "Authorization: Bearer $MAYA_API_KEY"
   ```

   Cancelling a queued pin job fails its pin (MAYA does that on purpose, so the name and date
   are not blocked for good).
3. **If you must reclaim the space — stop MAYA and back up first.** This is not a supported
   operation. There is no `maya admin gc`, and `maya_delta` has no delete: the only way to
   remove a partition is to rewrite the table without it.

   ```bash
   # 1. stop every MAYA process (web, workers, the CLI's --local mode)
   # 2. take the backup of the restore drill, both halves, database first
   #    (docs/runbooks/restore-drill.md §1)
   # 3. rewrite one table, keeping only what sealed pins reference
   ```

   The rewrite, saved as `reclaim.py` and run once per table:

   ```python
   """MAYA_HOME=... python reclaim.py pins/<namespace>/<name>

   Rewrites one pin table keeping only the fragments sealed pins still reference.
   Stop MAYA and back up storage.root first."""
   import sys
   sys.argv = ["reclaim"] + sys.argv[1:]
   from maya.config import load_settings
   from maya.services.platform import Platform

   kind, namespace, name = sys.argv[1].split("/")
   p = Platform.build(load_settings("config/application.yaml", fresh=True), start_workers=False)
   pin_table, fk, owner_table = {
       "pins": ("feature_pins", "feature_id", "features"),
       "fspins": ("feature_set_pins", "feature_set_id", "feature_sets"),
   }[kind]
   with p.uow() as uow:
       ns = uow.repo("namespaces").find_one(name=namespace)
       obj = uow.repo(owner_table).find_one(namespace_id=ns["id"], name=name)
       keep = {h for pin in uow.repo(pin_table).list(state="sealed")
               if pin[fk] == obj["id"] for h in pin["fragments"]}
   path = p.lake.table_path(kind, namespace, name)
   present = {f["partitionValues"]["_fragment"] for f in p.lake.delta.files(path)}
   print(f"{len(present)} present, {len(keep)} referenced, {len(present - keep)} to drop")
   if present - keep and keep:
       data = p.lake.delta.read(path, partitions={"_fragment": sorted(keep)})
       version = p.lake.delta.write(path, data, mode="overwrite", partition_by=["_fragment"])
       removed = p.lake.delta.vacuum(path, retention_hours=0, enforce_retention=False)
       print(f"rewrote at version {version}; vacuumed {len(removed)} file(s)")
   p.shutdown()
   ```

   Run against a throwaway `MAYA_HOME` it prints, for a table with one orphan of three:

   ```text
   3 fragment(s) present, 2 referenced, 1 to drop
   rewrote pins/eq/volumes at version 3; vacuumed 3 file(s)
   files: 3 -> 2
   ```

   Two things about it are deliberate. `retention_hours=0` with `enforce_retention=False`
   destroys time travel for that table — that is the point, and it is why the backup is not
   optional. And a table where **no** fragment is referenced is not rewritten: if every pin
   that used it failed, delete the whole directory instead, which the script says rather than
   doing.
4. **Verify before letting anyone back in** (next section). Only then restart MAYA.
5. **Fix the cause.** Repeated orphans mean repeated failed pins. The pin's `failure` column
   and the job's `error` say why; a quality contract that blocks every pin is a definition
   problem, not a storage problem.

## Verification

```bash
python -m maya.cli --local admin verify-integrity
# <n> pin(s) checked; drift: 0; audit chain ok: True        (exit 0)
```

That is the check that matters: the rewrite moved sealed data, so if it went wrong, it went
wrong here. Then:

```bash
curl -s "$MAYA_URL/api/v1/system/storage" -H "Authorization: Bearer $MAYA_API_KEY"
# orphan_fragments is lower; stored_bytes and referenced_bytes now agree
```

Read one affected pin end to end — a download, not just a hash — and check the row count
against its manifest.

**Commands run while this runbook was written.** All of the above, against a throwaway
`MAYA_HOME` on SQLite: the storage report, the pin query, the `reclaim.py` rewrite (on a table
with one orphan of three, and on a table with no referenced fragment at all), and
`verify-integrity` afterwards, which stayed clean. The PostgreSQL variants of the SQL are
**not exercised**.

## What this does not reach

- **There is no supported garbage collection.** §29.3 asks for "a garbage collector that is
  provably safe against sealed pins". MAYA reports orphans and stops there. The procedure
  above is a documented manual rewrite, not that collector, and it is unsupported: nothing in
  the test suite covers it.
- **It does not shrink the ingest log.** `lake/raw/<ns>/<name>/` keeps every ingested batch
  bitemporally on purpose. It is not orphaned; it is history. See
  [Delta small files](delta-small-files.md) for making it fewer, larger files.
- **Blobs are not covered.** Uploaded artifacts, PDFs, bundles and estate dumps under
  `blobs/` are content-addressed and never collected either. Nothing reports unreferenced
  blobs at all.
- **It cannot tell a slow pin from a dead one.** A `materializing` pin with no live job is
  orphaned work; a `materializing` pin whose job is running is not. Only the jobs table
  distinguishes them, and only while the job row is still there.
