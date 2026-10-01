# Restated data under a live model

For the model owner, a model manager, or the administrator standing in for them, when MAYA
reports that data under a live model's training pin was corrected. A restatement never touches
a pin: that is what two clocks are for, and it is why a model fitted on the pin goes on running
on values the source has since said were wrong. MAYA measures what the correction would have
changed and asks a person to decide. This runbook is how to decide.

## Symptoms

- Alert `MayaRestatementUnderLiveModel` (an open impact) or `MayaRestatementUnacknowledged`
  (one has been open for a week).
- An inbox notification of kind `restatement`: *"<warrant uri>: data under its training pin
  (<pin> as of <date>) was restated — N row(s) changed, … predictions moved by … (largest …);
  holdout RMSE a → b"*.
- The warrant's page, `/warrants/execution/<id>`, shows *"N restatement(s) to acknowledge"*
  under **Restated data**. The audit log has a `restatement.impact` entry.

## Diagnosis

```bash
curl -s "$MAYA_URL/api/v1/warrants/execution/<id>/restatements" -H "Authorization: Bearer $MAYA_API_KEY"
```

or `my.execution.restatements("<id>")`. For each impact read:

- `trigger` — the feature whose ingest restated rows, and `knowledge_time`;
- `rows` — `changed`, `changed_in_holdout`, `added`, `dropped`, out of `compared`;
- `metrics_sealed` against `metrics_corrected` — the approved parameters on the holdout as
  sealed and as corrected (a formula from its IR, a black box in the sandbox);
- `shift` — `mean_abs`, `max_abs` and `share_moved` of the predictions over every row.

Then find what the source said and why: the feature's page lists its ingests, and a
restatement is flagged there with its note.

## Remedy

Decide which of two things is true, then record it.

1. **Immaterial.** The shift is small against the model's tolerance, the holdout metric barely
   moved, and the corrected rows are few or old. Acknowledge with the reason:

   ```bash
   curl -s -X POST "$MAYA_URL/api/v1/restatements/<impact-id>/acknowledge" \
     -H "Authorization: Bearer $MAYA_API_KEY" -H "Content-Type: application/json" \
     -d '{"reason": "Immaterial: 3 days in January, holdout RMSE 0.0101 -> 0.0103"}'
   ```

2. **Material.** Refit. Pin the feature set again (a new pin sees the corrected values), draw a
   new training warrant on it, fit and approve parameters, score them blind, seal, and move
   production to a new execution warrant. `POST /warrants/training/<id>/refit` gives MAYA's own
   least-squares fit on the old warrant as a quick check of how far the parameters would move.
   Acknowledge the impact naming the new warrant.

Only the warrant's owner, a model manager or an administrator may acknowledge. The note is
audited (`restatement.acknowledged`) and shown on the warrant.

## Verification

- The warrant page no longer shows *"to acknowledge"*; the impact shows who acknowledged it
  and the note.
- `maya_restatement_impacts{state="open"}` returns to 0 within one metrics cache period
  (`observability.metrics.cache_seconds`), and the alert clears.

## What this does not reach

- A feature set member that is itself a feature set is resolved as its definition names it,
  not at the version its pin held.
- Nothing is suspended automatically: a correction that invalidates a model is a judgement,
  and so is its urgency. If the model must stop now, revoke the warrant (see
  [A suspended execution warrant](suspended-execution-warrant.md) for the difference).
- The check runs on restatements MAYA ingests. A correction made only upstream, never
  ingested, is invisible to it.
- `restatements.alerts: false` turns the automatic check off; **Check now** on the warrant
  page still works.
