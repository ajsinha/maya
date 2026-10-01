# Stuck or failed jobs and pins

For `techops` and administrators when slow work does not finish: a job that sits `queued` or
`running`, a job that failed or dead-lettered, or a pin stuck `materializing` or `failed`.
Slow work — pinning, validating a model artifact, shadow replay, the recorded challenger —
runs as jobs in a queue held in the database, claimed by worker threads in the MAYA process
that launched the server. A pin is sealed by its job; if the job does not finish, neither
does the pin, and a pin left `materializing` blocks its name and date.

## Symptoms

- A job's state in `/admin/jobs`, `GET /api/v1/jobs?all=true` or
  `python -m maya.cli job watch <id>` does not move.
- The health page's `jobs` shows a growing `queued` count, a `running` count that never
  drops, or a non-zero `dead_letter`; the Prometheus gauge `maya_jobs{state=…}` says the same,
  and each dead letter emits a `job.dead_letter` event.
- A pin request fails because its name and date are taken:

  ```text
  ConflictError: Pin <name>/<date> already exists (materializing)
  ```

- A retry is refused: *"Only failed or dead-lettered jobs are retried"*, or, for anyone but an
  administrator or `techops`, *"Retrying a dead-lettered job is a techops action"*.

## Diagnosis

```bash
python -m maya.cli --json job watch <job-id>          # streams progress; returns at a terminal state
curl -s "$MAYA_URL/api/v1/jobs/<job-id>" -H "Authorization: Bearer $MAYA_API_KEY"
# state, attempts / max_attempts, run_after, worker, progress, message, error,
# result.problem (a refusal) or result.traceback (a dead letter), params.pin_id
python -m maya.cli --json feature show <namespace>/<name>   # its pins: id, pin_name, as_of_date, state, failure
curl -s "$MAYA_URL/api/v1/system/health" -H "Authorization: Bearer $MAYA_API_KEY" \
  | python -c "import json,sys; h=json.load(sys.stdin); print(h['jobs'], h['process'])"
```

| What you see | What it means |
|---|---|
| `queued`, `run_after` in the future, `error` set | An unexpected error, retrying with exponential backoff until `jobs.max_attempts` (3) is spent |
| `queued`, nothing claims it, `jobs.workers` is 0 | No worker is running. Workers run only in the launching process; `health.process.role` is `web` in the other web processes and they report 0 |
| `running` for far longer than the work should take, the process that claimed it (`worker` is `<pid>-w<n>`) gone | The process died mid-job. The job stays `running` until the next start of MAYA, which requeues it with the note *"requeued by the reaper"* |
| `running`, the process alive | The handler is still working, or hung. There is no job timeout |
| `failed`, `result.problem` set | A deliberate refusal — a quality check, a contract mismatch, nothing to pin. It is not retried, because it would refuse again |
| `dead_letter`, `result.traceback` set | An unexpected error on every attempt |
| Pin `requested` | Not stuck: it awaits a pin authorizer (someone else — separation of duties) |
| Pin `failed`, `failure` set | The pin saga recorded why. The name and date are free for a new request |

## Steps

**A failed job or pin.** Read `result.problem` or the pin's `failure`, fix the cause — usually
the data (a quality contract) or the definition — and request the pin again under the same
name and date; a `failed` pin is replaced by the new request. Retrying the job
(`POST /api/v1/jobs/<id>/retry`, `my.jobs.retry(id)`, or *Retry* on `/admin/jobs`) reruns it
unchanged, which only helps if what it depended on has changed since.

**A dead-lettered job.** Read `result.traceback` — it is an unexpected error, so it is a
defect or an environmental fault (disk full, a lake table another tool touched, the database
gone away). Fix the cause, then retry it; retrying resets its attempts.

**A job `running` in a dead process.** Restart MAYA (`SIGTERM` drains the workers). The
launcher requeues every job left `running` at startup, and the pin saga resumes: pin writes
are content-addressed, so a rerun writes nothing twice.

**A job `running` and hung.** Request cancellation (`POST /api/v1/jobs/<id>/cancel`,
`python -m maya.cli job cancel <id>`, or *Cancel* on `/admin/jobs`). Cancellation is
cooperative: a handler honours it at its next progress report, and **a feature pin job reports
progress only once, at its start** — after that it runs to the end whatever you ask. If the
handler really is hung, restart MAYA; the job is requeued and runs again, or — if you had
requested cancellation — stops at its first progress report, and its pin is marked `failed`.

**Cancelling a pin job.** Cancelling a pin job that has not started marks the job `cancelled`
and its pin `failed`, so the name and date are free for a new request; a feature-set cascade
cancelled mid-job rolls its member pins back. The *Cancel* button on `/admin/jobs` does this.

**On the 0.3.0 release commit this is a trap.** The fix above came after that commit
(`92ade9b`) without a change of version number, so check the build, not the version: on
`92ade9b`, cancelling a queued pin job leaves its pin `materializing`, and every way out is
refused — the job cannot be retried (*"Only failed or dead-lettered jobs are retried"*), the
name and date cannot be pinned again (*"Pin <name>/<date> already exists (materializing)"*),
and the pin cannot be retired (*"Only a sealed pin can be retired"*). Reproduced against that
commit. There, do not cancel queued pin jobs. If it has already happened, the pin can be freed
only by changing its row directly — with MAYA stopped, `UPDATE feature_pins SET state =
'failed', failure = '<why>' WHERE id = '<pin-id>'` — a change to the record made outside
MAYA's audit trail. Write down who did it and why before you do it, or pin under another name
and leave the stranded row where it is.

## Verification

- The job reaches `succeeded`, and `job watch` returns its result.
- The pin is `sealed`, with a content hash, in `feature show`.
- The health page's `jobs.dead_letter` count is back to what it was, and nothing is `running`
  without a live worker.

## What this does not reach

- **There is no job timeout** and no stuck-job alert. A hung handler holds a worker until MAYA
  restarts; with the default two workers, two hung jobs stop the queue.
- **Requeueing happens only at startup.** Jobs a crash left `running` wait, visibly `running`,
  until MAYA is started again.
- **Orphan fragments** — fragments a failed pin wrote before it failed — are reported by
  `GET /api/v1/system/storage` (`orphan_fragments`, `orphan_bytes`) and never deleted. There is
  no supported command to collect them.
- Cancellation is proven for a pin cancelled while queued and a cascade cancelled mid-job
  (`tests/test_concurrency.py`); not for every stage of every job type.
