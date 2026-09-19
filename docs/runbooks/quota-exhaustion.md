# Storage quota exhaustion

For the administrator or `techops` engineer dealing with a lake that is filling up, or one team
consuming the space everybody else needs.

**Read this first, because it changes what you can do.** §7.3 and §21.2 ask for per-namespace
storage quotas: a footprint estimated before a pin is created, charged against the namespace's
allowance, and refused when it is exceeded. **That is not built.** `quota_bytes` exists as a
column on every namespace and can be set through the API, and nothing in MAYA ever reads it. No
pin is refused for space, no warning is issued, and no estimate is shown. So there is no quota to
"exhaust" in the sense the specification means, and the failure mode a deployment actually meets
is the filesystem filling up — which MAYA handles as an ordinary write error, badly.

What this runbook gives you is: how to see the consumption MAYA does not enforce, how to get out
of a full filesystem without losing a sealed pin, and the two backpressure limits that *do* work.

## Symptoms

Three different situations arrive looking similar.

**The filesystem under `storage.root` is full.** Pins fail rather than queue:

```text
OSError: [Errno 28] No space left on device
```

in the job's `error`, the pin left `failed` or `materializing`, and orphaned fragments behind it.
The database may fail too — on SQLite it is the same filesystem.

**One namespace is consuming everything.** Nothing fails; the numbers just move:

```text
maya_namespace_pin_bytes{kind="feature",namespace="eq"} 2443
maya_namespace_pins{kind="feature",namespace="eq"} 4
```

**The job queue is shedding.** This *is* enforced, and it is not a storage limit — it is
§15.4 backpressure:

```text
maya.core.errors.QuotaExceeded: MAYA's job queue is full (2000 queued, the limit is 2000).
Nothing was queued. The queue should clear in about 10000 second(s); submit again then, or
cancel jobs you no longer need.
```

or, for one person:

```text
QuotaExceeded: You already have too many jobs waiting (200 queued, the limit is 200). …
```

Both are HTTP 429, both are counted as `maya_job_shed_total{reason="queue_depth"}` or
`{reason="per_user_queued"}`, and the `MayaQueueShedding` alert fires on either.

## Diagnosis

**1. How much space is there, and where is it going.**

```bash
df -h "$MAYA_HOME"
du -sh "$MAYA_HOME"/*
# lake/  blobs/  keys/  logs/  maya.db (on SQLite)
du -sh "$MAYA_HOME"/lake/pins/* | sort -h | tail -20
```

**2. What MAYA thinks it is storing**, which is not the same number:

```bash
curl -s "$MAYA_URL/api/v1/system/storage" -H "Authorization: Bearer $MAYA_API_KEY"
```

```json
{
  "pins": 2, "fragments": 6,
  "logical_bytes": 1357, "stored_bytes": 3258, "referenced_bytes": 1357,
  "saved_ratio": 0.0, "orphan_fragments": 4, "orphan_bytes": 1901,
  "gc_note": "Orphans are fragments no sealed pin references (left by failed pins). They are reported, never deleted automatically."
}
```

Read it in this order: `referenced_bytes` is what sealed pins actually need, `orphan_bytes` is
rubbish, and `stored_bytes - referenced_bytes - orphan_bytes` is Delta files kept for time travel
until `lake.maintenance.vacuum_retention_hours` passes. `du` will exceed `stored_bytes` by the
ingest log under `lake/raw/`, which is bitemporal history and not a pin.

**3. Which namespace**, from the scrape-time gauges:

```bash
curl -s "$MAYA_URL/metrics" | grep -E "^maya_namespace_(pins|pin_bytes)" | sort -t' ' -k2 -gr
```

Those are held for `observability.metrics.cache_seconds` (60) and can be turned off entirely with
`observability.metrics.namespace_gauges: false` on an estate where counting pin rows every minute
is itself too expensive.

**4. What the quota says, so you know it is being ignored:**

```bash
curl -s "$MAYA_URL/api/v1/namespaces" -H "Authorization: Bearer $MAYA_API_KEY" \
  | python -c "import json,sys; [print(n['name'], n.get('quota_bytes')) for n in json.load(sys.stdin)['data']]"
```

A number here means somebody recorded an intent. It has no effect.

**5. If the queue is shedding, look at the queue, not the disk:**

```bash
curl -s "$MAYA_URL/metrics" | grep -E "^maya_job_(queue_depth|queue_owners|oldest_queued_seconds)|^maya_job_shed_total"
```

`maya_job_queue_owners` at 1 with a deep queue is one person's campaign; the fair-queueing
claim order (§15.2) already interleaves it with everybody else, so the answer is workers, not
priority.

## Steps

### The filesystem is full

1. **Stop new work before freeing anything**, or you will race the thing filling the disk:

   ```bash
   # Refuse new submissions at once (the message tells callers to come back)
   python run_maya_web.py --jobs.queue.max_depth=1
   # or stop the worker processes and set the primary's workers to zero
   python run_maya_web.py --jobs.workers=0
   ```

2. **Free space in this order — safest first.**

   | Order | What | How | Cost |
   |---|---|---|---|
   | 1 | Logs | rotate or truncate `$MAYA_HOME/logs/` | none |
   | 2 | Delta files past retention | lake maintenance (below) | time travel beyond the window |
   | 3 | Orphaned fragments | [orphaned pin partitions](orphaned-pin-partitions.md) | downtime; unsupported procedure |
   | 4 | Retired pins | nothing does this — see *what this does not reach* | — |

   ```bash
   curl -s -X POST "$MAYA_URL/api/v1/system/lake/maintain" -H "Authorization: Bearer $MAYA_API_KEY"
   # {"filesRemoved": 9, "filesAdded": 1, "vacuumed": 0}
   ```

   `vacuumed: 0` on the first run is normal: nothing is deleted until it is older than
   `lake.maintenance.vacuum_retention_hours` (168). To free space now, shorten it deliberately and
   record why:

   ```bash
   python run_maya_web.py --lake.maintenance.vacuum_retention_hours=24
   ```

3. **Never delete anything under `lake/` by hand.** Fragments are content-addressed and read by
   fragment value; removing a file behind the Delta log turns a sealed pin into drift, which is an
   incident ([integrity drift](integrity-drift.md)) and is not recoverable except from backup.
   Blobs under `blobs/` are equally load-bearing: they hold model artifacts, specification PDFs and
   estate exports.

4. **Grow the filesystem, or move `storage.root`.** Moving it is a stop, copy, repoint:

   ```bash
   # MAYA stopped
   rsync -a "$MAYA_HOME"/ /new/place/
   python run_maya_web.py --storage.root=/new/place
   python -m maya.cli --local admin verify-integrity     # prove the copy is faithful
   ```

   On SQLite the database file moves with it (`db.sqlite.path` is `${storage.root}/maya.db`), so
   this is a database move as well: stop MAYA first, always.

5. **Clean up what the full disk broke**: pins left `failed` or `materializing`, and the orphans
   they left — [stuck jobs and pins](stuck-or-failed-jobs-and-pins.md), then
   [orphaned pin partitions](orphaned-pin-partitions.md).

### One namespace is consuming everything

There is no enforcement to turn on, so the levers are social and structural:

1. **Record the intent anyway.** `quota_bytes` is the field the enforcement will read when it is
   built, and setting it now means the day it lands nothing has to be reconstructed:

   ```bash
   curl -s -X PATCH "$MAYA_URL/api/v1/namespaces/<name>" -H "Authorization: Bearer $MAYA_API_KEY" \
     -H 'Content-Type: application/json' -d '{"quota_bytes": 1099511627776}'
   ```

2. **Alert on the gauge instead.** Add a rule beside the shipped ones
   ([the rules file](../../config/prometheus/maya-slo.rules.yml)) — a threshold per namespace is a
   one-line `maya_namespace_pin_bytes{namespace="eq"} > 1.1e12`. That is the only enforcement
   available today, and it is after the fact.
3. **Reduce what a pin costs.** Bigger fragments make fewer files but share less;
   `materialize_policy: on_demand` or `never` on a feature-set pin (ADR-025) seals by hash and
   stores nothing at all, replaying from members on read. That is the largest single saving
   available, and it is per pin.
4. **Split the lake.** §24.3's last scaling lever is partitioning namespaces across Delta roots.
   MAYA has one `storage.root`, so this means a second instance, which means a second estate.

### The queue is shedding

1. **Add workers** — that is what the refusal is asking for:

   ```bash
   python run_maya_web.py --worker            # one job worker process, no port bound
   ```

2. **Raise the limits only if you mean it.** `jobs.queue.max_depth` and
   `jobs.per_user.max_queued` are refusals on purpose: accepting work MAYA cannot start is a
   promise it cannot keep, and the estimate in the message is honest about the wait.
3. **Cancel what nobody needs.** A double-click never duplicates a job (the idempotency key
   dedupes), but an abandoned campaign still holds the queue:

   ```bash
   curl -s -X POST "$MAYA_URL/api/v1/jobs/<job-id>/cancel" -H "Authorization: Bearer $MAYA_API_KEY"
   ```

## Verification

- `df -h "$MAYA_HOME"` has headroom, and `du` agrees with `stored_bytes` plus the ingest log.
- `python -m maya.cli admin verify-integrity` exits 0 with `drift: 0`. Run it after **every** step
  that removed a file, including lake maintenance and a move of `storage.root`.
- `maya_pins{state="materializing"}` is 0 and no job is stuck `running`.
- A pin of a small feature succeeds end to end.
- `maya_job_shed_total` stops increasing, and `maya_job_oldest_queued_seconds` falls.

**Commands run while this runbook was written.** Against a throwaway `MAYA_HOME` on SQLite: the
storage report (the JSON above is its actual output, on an estate with four orphans), the
`maya_namespace_pin_bytes` and `maya_job_queue_*` gauges, `df`/`du`, lake maintenance (nine ingest
files merged into one, nothing vacuumed inside retention), and `verify-integrity` afterwards. The
two backpressure refusals are quoted from `maya/jobs/queue.py` and are covered by
`tests/test_job_fairness.py`. **Not exercised:** an actually full filesystem, the `rsync` move of
`storage.root`, and the `PATCH /namespaces` quota write.

## What this does not reach

- **Quotas are not enforced.** `quota_bytes` is stored and never read. §7.3's footprint estimate
  before a pin, the charge against the namespace, and the refusal are all unbuilt — as are §21.2's
  per-namespace export quotas and manifest watermarking.
- **There is no cost estimate anywhere.** §7.3 and §6.7 ask for one on a pin and on a feature set;
  nothing computes one, so nobody is warned before the expensive thing happens.
- **No cold tier and no archive.** §7.3's infrequent-access tier for cold pins and compressed
  bundle for retired pins do not exist. A retired pin still occupies its full space forever.
- **No garbage collection.** Orphans are reported, never collected
  ([orphaned pin partitions](orphaned-pin-partitions.md) has the manual, unsupported procedure).
- **MAYA does not watch the disk.** There is no free-space check, no threshold, no refusal before
  the filesystem fills, and no metric for it: `/readyz` only checks that the lake root *exists*.
  Monitor the filesystem with the same tools you use for everything else.
- **A full disk is not handled gracefully.** The write fails, the job records the error, and the
  pin is left behind with its partition. Nothing retries it when space returns.
