# Periodic review overdue, or an execution warrant expiring

For the model owner, a model manager, and the validator who does periodic reviews. Two dates
end a model's time in production without anyone deciding anything: its periodic review
falling due, and its execution warrant's validity running out. Both are known in advance,
which is what the alerts are for.

## Symptoms

- `MayaPeriodicReviewOverdue` or `MayaTierOneReviewOverdue`: a model's `next_review_due` has
  passed. The governance sweep suspends every live execution warrant of that model with the
  reason *"Periodic review overdue since <date>"*, and its consumers are refused (HTTP 423).
- `MayaExecutionWarrantExpiring`: a live warrant's `valid_to` is within seven days. The owner
  also has an `expiry` notification thirty days out. After `valid_to`, every consumer is
  refused with *"Warrant expired on <date>"*.

## Diagnosis

The **Governance** page lists every model with its tier, `next_review_due` and whether it is
overdue; `GET /governance` returns the same, with `overdue_reviews` counted. The
**Warrants** page and `GET /warrants/execution` show each execution warrant's `valid_to`.

The review interval follows the tier: 365 days for tier 1, 730 for tier 2, 1,095 for tier 3,
unless the model's governance profile sets its own.

## Remedy

**A review is due.** Someone other than the model's owner looks at it and records the
outcome — `satisfactory`, `needs_improvement` or `unsatisfactory` — with what was looked at:

```bash
curl -s -X POST "$MAYA_URL/api/v1/governance/models/<namespace>/<name>/reviews" \
  -H "Authorization: Bearer $MAYA_API_KEY" -H "Content-Type: application/json" \
  -d '{"outcome": "satisfactory", "note": "Back-test Q3, covenants clean, no open findings"}'
```

A recorded review moves `next_review_due` on and reinstates the warrants the sweep suspended
for this reason (and only those).

**A warrant is expiring.** Draw the next version of the execution warrant (same namespace and
name), take it through approval, and seal it before the current one lapses. Consumers fetch
the new bundle; the old version expires on its date and remains in the record.

## Verification

- The model leaves the overdue list, and `maya_models_review_overdue` falls within one metrics
  cache period.
- The new warrant version shows `live`; `maya_execution_warrants_expiring{within_days="7"}`
  falls once the old one is superseded or lapses.

## What this does not reach

- Recording a review does not make the model better. An `unsatisfactory` review is recorded
  like any other; findings are how the problems it found are tracked.
- A warrant suspended for a covenant breach is not reinstated by a review. See
  [A suspended execution warrant](suspended-execution-warrant.md).
