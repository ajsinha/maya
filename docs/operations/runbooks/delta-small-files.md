# Delta small-file explosion

For the administrator or `techops` engineer whose reads have got slow without anything in the
catalog changing. A Delta table made of thousands of tiny Parquet files spends its time opening
files instead of reading rows, and the `_delta_log` that lists them all gets expensive to
replay. Specification §20 asks for a runbook; this is it.

The important thing to know before starting: MAYA has **two kinds of lake table, and only one
of them can be compacted.**

| Table | Path | Shape | Compaction |
|---|---|---|---|
| Ingest log | `lake/raw/<ns>/<name>/<hash>/` | Unpartitioned, one file appended per ingest | Works: consecutive small files are merged |
| Pin store | `lake/pins/<ns>/<name>/`, `lake/fspins/<ns>/<name>/` | Partitioned by `_fragment=<content hash>`, **one file per fragment** | Does nothing: there is never more than one file in a partition to merge |

So a pin table with a hundred thousand files has a hundred thousand fragments, and the lever is
the fragment size (`lake.fragment.target_rows`), not the compactor. Reaching for maintenance
there wastes a maintenance window.

## Symptoms

- Reads of a pin or a feature's history slow down while row counts stay the same.
- `/metrics` shows the file count and the ratio below the compaction target:

  ```text
  maya_delta_files{table="raw/eq/volumes/308e5cb1b5ef"} 9
  maya_delta_small_file_ratio{table="raw/eq/volumes/308e5cb1b5ef"} 1
  ```

  A ratio of 1 means every file is under the compaction target, which on a pin table is
  true of a healthy one too — every fragment is far below 128 MB. Read the ratio together
  with the count, which is what the shipped alert does.

- The `MayaDeltaSmallFileExplosion` alert fires
  ([the rules file](../../../config/prometheus/maya-slo.rules.yml)): ratio above 0.9 with more than
  200 files, for two hours.
- `ls` on a table directory shows page after page of `part-00000-*.snappy.parquet`.

## Diagnosis

**Which tables, and how bad.** Sort the gauges by file count:

```bash
curl -s "$MAYA_URL/metrics" -H "Authorization: Bearer $MAYA_METRICS_TOKEN" \
  | grep "^maya_delta_files" | sort -t' ' -k2 -gr | head -20
```

Those gauges are held for `observability.metrics.cache_seconds` (60 by default), so a figure up
to a minute old is normal.

**Average file size is the number that matters**, not the count: ten thousand 100 MB files is a
2 TB table behaving correctly, and ten thousand 4 KB files is the problem.

```bash
curl -s "$MAYA_URL/metrics" | python - <<'PY'
import re, sys
files, nbytes = {}, {}
for line in sys.stdin:
    m = re.match(r'maya_delta_(files|bytes)\{table="([^"]+)"\} ([0-9.e+]+)', line)
    if m:
        (files if m[1] == "files" else nbytes)[m[2]] = float(m[3])
rows = [(t, files[t], nbytes.get(t, 0) / max(files[t], 1)) for t in files]
for t, n, avg in sorted(rows, key=lambda r: r[2])[:20]:
    print(f"{avg/1024:10.1f} KiB average  {n:8.0f} files  {t}")
PY
```

**Then decide which kind of table it is.** `raw/…` is an ingest log and compaction is the
answer. `pins/…` or `fspins/…` is a fragment store and it is not; go to step 3.

On disk, directly:

```bash
find "$MAYA_HOME/lake/raw" -name '*.parquet' | wc -l
du -sh "$MAYA_HOME/lake/raw" "$MAYA_HOME/lake/pins"
```

## Steps

1. **Compact and vacuum now, if the table is an ingest log.** This is safe while MAYA is
   running: a pin is read by fragment value and row number, never by file, and the ingest log is
   read at its latest version.

   ```bash
   curl -s -X POST "$MAYA_URL/api/v1/system/lake/maintain" -H "Authorization: Bearer $MAYA_API_KEY"
   ```

   Against a throwaway estate whose ingest log had been appended to nine times, with
   `--lake.maintenance.target_size_mb=1`:

   ```json
   {"filesRemoved": 9, "filesAdded": 1, "vacuumed": 0}
   ```

   per table:

   ```text
   {'table': 'raw/eq/volumes/308e5cb1b5ef', 'filesRemoved': 9, 'filesAdded': 1, 'vacuumed': 0, 'version': 9}
   {'table': 'pins/eq/volumes',             'filesRemoved': 0, 'filesAdded': 0, 'vacuumed': 0, 'version': 5}
   ```

   Note the second line. The pin table was *not* compacted, and that is not a failure: its
   three files are in three different `_fragment=` partitions.

2. **`vacuumed: 0` is usually correct.** Compaction leaves the old files in place for time
   travel until `lake.maintenance.vacuum_retention_hours` (168 by default) has passed, so the
   first maintenance run after a compaction frees no space at all. The space comes back a week
   later, or sooner if you shorten retention deliberately:

   ```bash
   # Keeps one day of time travel. Under 168 is allowed, but say why in your change record.
   python run_maya_web.py --lake.maintenance.vacuum_retention_hours=24
   ```

3. **For a pin table, change the fragment size — for new pins.** Fragments are content
   addressed and immutable: nothing re-fragments a sealed pin, so this only affects pins made
   from now on.

   ```yaml
   lake:
     fragment:
       target_rows: 4096      # was 512
       min_rows: 256
       max_rows: 65536
   ```

   Bigger fragments mean fewer, larger files and a cheaper read; they also mean **less sharing**
   between pins, because a fragment is only reused when its whole content repeats. Watch
   `saved_ratio` in `/admin/storage` after the change: if it collapses, the estate was relying
   on fine-grained sharing and you have traded disk for file count. `min_rows` above 1 also
   stops a one-row daily pin becoming a one-row file.

4. **Raise the compaction target if the files are merged but still small.**

   ```yaml
   lake:
     maintenance:
       target_size_mb: 512    # was 128
       interval_seconds: 21600
   ```

5. **If reads are still slow after the file count is sane, it is not this problem.** Check the
   backend (`/admin/health`: `maya_delta pure` reads Parquet in Python — see
   [the backend runbook](maya-delta-backend-fallback.md)), then the database
   (`maya_db_slow_queries_total`).

## Verification

```bash
curl -s "$MAYA_URL/metrics" | grep -E "^maya_delta_(files|small_file_ratio)"
```

- The affected table's `maya_delta_files` has dropped, and its average file size has risen.
- `python -m maya.cli admin verify-integrity` exits 0 with `drift: 0`. Compaction rewrites
  files; this proves it rewrote them faithfully. **Run it after every compaction of a table that
  holds pins.**
- A read of a pin in the affected table returns the same row count as its manifest.

**Commands run while this runbook was written.** The `/metrics` greps, the average-size script,
`find`/`du`, and lake maintenance on a throwaway `MAYA_HOME` on SQLite — including the nine
ingest files merged into one, and the pin table left untouched — plus `verify-integrity`
afterwards, which stayed clean. The `vacuum_retention_hours=24` variant is **not exercised**:
the throwaway estate had no files older than the retention window, so nothing was vacuumed.

## What this does not reach

- **Pin tables cannot be compacted at all**, for the reason in the table above. §7.1's "compacts
  on a schedule and after every pin" describes a layout MAYA does not use (see the audit's §3);
  the fragment store's file count is decided when the pin is written.
- **Z-ordering and space-filling-curve sort are not built** (§7.4). Compaction merges
  consecutive small files; it does not reorder rows for locality.
- **Per-file min/max statistics are written but only partition pruning is used on read**
  (`maya_delta/files.py`), so file skipping does not reduce the cost of many files the way it
  would elsewhere.
- **Nothing bounds a table's file count.** There is no refusal, no warning at pin time, and no
  automatic re-fragmentation. The alert above is the only thing that will tell you.
- **No measurement of the read cost at scale.** How much a small-file table actually slows down
  has not been benchmarked; `docs/quality/BENCHMARKS.md` does not cover it.
