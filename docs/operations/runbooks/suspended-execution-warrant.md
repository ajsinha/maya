# A suspended execution warrant

For the model owner, and the administrator standing in for them, when a consumer of a model
is refused because its execution warrant has been suspended. An execution warrant is a live
instrument: every run under it is reported back, the warrant's covenants are evaluated on each
report, and one breach suspends the warrant at once. From then on every consuming call fails
closed, naming the breach and whom to contact, until a person decides otherwise and says why.
That refusal is the control working — a model running on inputs it was never approved for is
what it exists to stop. The job here is to decide whether it is right, not to make it go away.

## Symptoms

- A consumer — fetching the warrant's bundle, asking for a token, reporting a run — is refused:

  ```json
  {"type": "warrant_suspended", "title": "WarrantSuspended", "status": 423,
   "detail": "Warrant suspended: <breach>. Contact <contact>.",
   "context": {"status": "suspended"}}
  ```

  for example *"Warrant suspended: null rate of 'x' 0.400 > 0.1. Contact risk@example.com."*
  `<contact>` is the warrant's `contact`, or *"the model owner"* when none was set. In the SDK
  this raises `maya.core.errors.WarrantSuspended`.
- The run that caused it was answered `{"accepted": true, "breaches": [...], "status":
  "suspended"}`.
- The model owner has an inbox notification *"<warrant uri> SUSPENDED: <breach>"* (kind
  `covenant_breach`); a `warrant.suspended` event went to webhook subscribers; the warrant's
  custody trail has a `suspended` event by `covenant-monitor`.

The breach texts, one per covenant kind:

| Covenant | Breach |
|---|---|
| `input_null_rate` | `null rate of '<attr>' <observed> > <max>` |
| `input_range`, `output_range` | `'<attr>' min <observed> below <min>` or `'<attr>' max <observed> above <max>` |
| `max_rows_per_day` | `<rows> rows today exceed the limit of <max>` |
| `staleness_days` | `'<attr>' is <days> days stale` |

Several breaches in one report are joined with `; `.

## Diagnosis

```bash
curl -s "$MAYA_URL/api/v1/warrants/execution/<id>" -H "Authorization: Bearer $MAYA_API_KEY"
```

or `my.execution.get("<id>")`, or the warrant's page, `/warrants/execution/<id>`. Read:

- `status` (`suspended`), `suspended_at`, `suspend_reason`;
- `spec.covenants` — what was promised;
- `reports` — newest first; the breaching one carries `breaches` with `observed` values and the
  `input_stats` / `output_stats` the consumer reported, and its `environment`;
- `custody` — the warrant's history, including earlier suspensions and reinstatements.

Then answer one question: **was the breach real?** Ask the consumer what they ran on, and look
at the upstream data for the reported environment and day.

## Steps

**The breach is real** — the inputs really were outside what the warrant allows. Leave the
warrant suspended; consumers failing closed is the correct outcome. Fix the data upstream, then
reinstate as below, citing the fix. If the model must not run again under this warrant at all,
revoke it — permanently, with a reason:
`POST /api/v1/warrants/execution/<id>/revoke {"reason": "…"}` or
`my.execution.revoke(id, reason="…")`.

**The breach was a false positive or a transient** — a vendor file late, a partial load
reported mid-flight. Reinstate with a written reason that a reviewer could check:

```python
import maya.sdk as maya

my = maya.connect()  # MAYA_URL and MAYA_API_KEY of the model owner or an administrator
my.execution.reinstate(
    "<id>", reason="Vendor file landed 06:40, 40 min late; rerun at 07:05 had null rate 0.001"
)
```

The same is `POST /api/v1/warrants/execution/<id>/reinstate` with `{"reason": "…"}`, or the
*Reinstate* form on the warrant's page, shown only while it is suspended. Only the model owner
(holder of `G` on the warrant) or an administrator may reinstate:

```json
{"type": "permission_denied", "title": "PermissionDenied", "status": 403,
 "detail": "Only the model owner or an administrator reinstates", "context": {}}
```

and the reason is required:

```json
{"type": "validation_failed", "title": "ValidationFailed", "status": 422,
 "detail": "Reinstatement requires a written reason", "context": {}}
```

**The covenant itself is wrong** — a threshold set tighter than the model needs. Reinstating
buys time only until the next report breaches again. Covenants are part of the sealed warrant
and cannot be edited: create a new execution warrant with the corrected covenant, take it
through review and seal it, move consumers to it, then revoke the old one.

## Verification

- `GET /api/v1/warrants/execution/<id>` shows `"status": "live"`, `suspended_at` null, and a
  `reinstated` custody event carrying your reason; the audit log has `warrant.reinstated`.
- The consumer's next call succeeds and its bundle is `"attestation": "attested"`.

## What this does not reach

- **Reinstatement does not check that the warrant was suspended.** Reinstating a live warrant —
  or a revoked one, which stays revoked — still writes a `reinstated` custody event and a
  `warrant.reinstated` audit entry. Reproduced against the 0.3.0 code: a second reinstatement
  of a live warrant added a second `reinstated` event. Read the custody trail with that in mind.
- **Covenants are evaluated on what the consumer reports.** The statistics in a report are
  computed and sent by the caller; the SDK sends what it is given. A consumer that reports
  nothing, or reports wrong numbers, is not caught by a covenant.
- **An offline copy is never suspended.** A bundle fetched with `offline=True` runs without
  reporting, so no covenant is evaluated on it; the copy and the warrant are labelled
  `unattested`, which is the whole of the control.
- Rate and volume **limits** are different: going over one throttles the next call (HTTP 429,
  `quota_exceeded`) and records `warrant.limit_exceeded`; it does not suspend.
