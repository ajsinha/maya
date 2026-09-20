# Storage quota exhaustion

For the administrator or `techops` engineer dealing with a lake that is filling up, or one team
consuming the space everybody else needs.

**Read this first, because it decides which half of the runbook you need.** §7.3's
per-namespace storage quota is built: a namespace's `quota_bytes` is checked **twice** on the
way to a pin — against an estimate when the pin is asked for, so an impossible pin is refused
before a worker spends minutes on it, and again against the writer's real figure before any
byte is stored, so a queue of pins cannot slip past a quota while none of them is written
yet. What is charged is **stored** bytes, counted once per content-addressed fragment, so a
re-pin of unchanged data adds nothing. A namespace with no `quota_bytes` is unlimited, which
is the shipped default, and on such an estate the failure mode you meet is not a quota at all
but the filesystem filling up — which MAYA still handles as an ordinary write error, badly.

So this runbook has three parts: a namespace that has hit its quota, a filesystem that is
full, and the job queue shedding, which is backpressure rather than storage.

## Symptoms

Three different situations arrive looking similar.

**A namespace is at its quota.** The pin is refused, by name and with the arithmetic:

```text
maya.core.errors.QuotaExceeded: Namespace 'eq' holds 940 MB of a 1000 MB quota; this pin
needs about 120 MB more. Retire pins you no longer need, or ask an administrator to raise
the quota.
```

HTTP 429, carrying `namespace`, `quota_bytes`, `stored_bytes` and `needs_bytes` in the error
detail. A pin refused at the *second* check — the writer's real figure, after the estimate
let it through — is left `failed` with the quota named, and its partition behind it.

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
  "gc_note": "Orphans are fragments no pin references at all (left by failed pins). Nothing collects them on a schedule; an administrator can, from the Retention page or `maya admin collect-fragments`, and the collection is a Delta remove — a vacuum past the retention window is what frees the disk."
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

**4. What each namespace's quota is, and what it holds against it:**

```bash
curl -s "$MAYA_URL/api/v1/namespaces" -H "Authorization: Bearer $MAYA_API_KEY" \
  | python -c "import json,sys; [print(n['name'], n.get('quota_bytes')) for n in json.load(sys.stdin)['data']]"
```

`None` means unlimited. For the other side of the sum — what the namespace holds and what
one more pin would add — ask for a pin preview, which is where a user meets the same numbers
before pinning rather than after, and which names the quota among its blockers:

```bash
curl -s -X POST "$MAYA_URL/api/v1/features/eq/prices/pin-preview" \
  -H "Authorization: Bearer $MAYA_API_KEY" -H 'Content-Type: application/json' \
  -d '{"version_no": 3, "as_of": "2026-01-31"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['data']['storage'])"
# {"estimated_bytes": …, "held_bytes": …, "quota_bytes": …, …}
```

A preview that would exceed the quota comes back with the blocker spelled out —
*"the namespace holds &lt;n&gt; of &lt;q&gt; bytes and this pin is estimated at &lt;e&gt;: it
would exceed the quota"* — and the pin control stays disarmed.

**5. If the queue is shedding, look at the queue, not the disk:**

```bash
curl -s "$MAYA_URL/metrics" | grep -E "^maya_job_(queue_depth|queue_owners|oldest_queued_seconds)|^maya_job_shed_total"
```

`maya_job_queue_owners` at 1 with a deep queue is one person's campaign; the fair-queueing
claim order (§15.2) already interleaves it with everybody else, so the answer is workers, not
priority.

## Steps

### A namespace is at its quota

The refusal is the control working, so the first question is whether the quota is right, not
how to get round it.

1. **Free stored bytes inside the namespace, in this order.** Each is charged the moment the
   fragments go, because usage is read from the fragment rows its pins reference:

   | Order | What | How | Cost |
   |---|---|---|---|
   | 1 | Orphans left by failed pins | `maya admin collect-fragments --apply` | none; a vacuum frees the disk later |
   | 2 | Retired pins nobody reads | `maya admin cold-pins`, then `maya admin archive-pin <id>` | the pin is read back from a blob, re-hashed on the way |
   | 3 | Unwritten feature-set pins | `materialize_policy: on_demand` or `never` (ADR-025) | the pin is only as readable as its replay |

   `maya admin cold-pins` names what has gone unread past `retention.cold_after_days` and
   what it holds, which is the list to argue from. Archiving does **not** free the pin's
   fragments — they are content-addressed and shared with other pins — so it moves rows out
   of the lake table rather than deleting bytes anything else needs.
2. **Or raise the quota, deliberately.** It is a namespace setting, audited like any other:

   ```bash
   curl -s -X PATCH "$MAYA_URL/api/v1/namespaces/<name>" -H "Authorization: Bearer $MAYA_API_KEY" \
     -H 'Content-Type: application/json' -d '{"quota_bytes": 1099511627776}'
   ```

3. **Clean up a pin refused at the second check.** It is left `failed` with the quota named,
   and its partition is behind it — [orphaned pin partitions](orphaned-pin-partitions.md).

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
   | 2 | Orphaned fragments | `maya admin collect-fragments --apply` | none; the disk frees at the next vacuum |
   | 3 | Delta files past retention | lake maintenance (below) | time travel beyond the window |
   | 4 | Retired pins nobody reads | `maya admin cold-pins`, then `archive-pin` | a read is a restore; shared fragments stay |

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

1. **Give it a quota.** This is the lever, and it now bites — a pin past the allowance is
   refused rather than merely counted:

   ```bash
   curl -s -X PATCH "$MAYA_URL/api/v1/namespaces/<name>" -H "Authorization: Bearer $MAYA_API_KEY" \
     -H 'Content-Type: application/json' -d '{"quota_bytes": 1099511627776}'
   ```

   Set it above what the namespace already holds unless you mean to stop it pinning today:
   the check is `held + this pin <= quota`, so a quota below current usage refuses the next
   pin whatever its size. Read `held` from the pin preview or the
   `maya_namespace_pin_bytes` gauge before you choose the number.
2. **Alert on the gauge as well as capping.** A quota refuses at the boundary; an alert gives
   somebody warning before it. Add a rule beside the shipped ones
   ([the rules file](../../config/prometheus/maya-slo.rules.yml)) — a threshold per namespace is a
   one-line `maya_namespace_pin_bytes{namespace="eq"} > 1.1e12`.
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
`storage.root`, and the `PATCH /namespaces` quota write. The quota half of this runbook was
written after the enforcement landed: its refusal is quoted from `maya/services/quota.py` and
the preview's blocker from `maya/services/catalog.py`, both covered by
`tests/test_quotas.py`, but the commands were not typed against a throwaway estate.

## What this does not reach

- **A storage quota is not an export quota.** §21.2's per-namespace export quotas and
  manifest watermarking are not built, so nothing limits how much a reader may take out.
- **The estimate is an estimate.** The first check measures a compressed sample and scales it,
  or reads the feature's own last sealed pin. A pin whose shape has changed can pass the
  estimate and be refused by the writer's real figure at the end, after the work — safe, but
  the minutes are spent.
- **No cold tier.** `maya admin cold-pins` *names* pins nobody has read past
  `retention.cold_after_days`; moving their bytes to an infrequent-access storage class needs
  the object-store backend of §25, which is not built, and the report says so rather than
  implying a tier exists. Archiving a retired pin (`archive-pin`) packs its rows into a blob
  and does not delete the fragments it shares with other pins.
- **Collecting is not freeing.** `collect-fragments` issues a Delta remove; the disk shrinks
  at the next vacuum past `lake.maintenance.vacuum_retention_hours`
  ([orphaned pin partitions](orphaned-pin-partitions.md)).
- **MAYA does not watch the disk.** There is no free-space check, no threshold, no refusal before
  the filesystem fills, and no metric for it: `/readyz` only checks that the lake root *exists*.
  Monitor the filesystem with the same tools you use for everything else.
- **A full disk is not handled gracefully.** The write fails, the job records the error, and the
  pin is left behind with its partition. Nothing retries it when space returns.
