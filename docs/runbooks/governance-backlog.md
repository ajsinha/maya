# A governance backlog: critical findings, or a review queue that does not drain

For the head of model risk, a model manager, or whoever runs the review rota. Neither alert
here means something broke. Each means work that should have been done is piling up, and
the inventory is quietly carrying more risk than its records say.

## Symptoms

- `MayaCriticalFindingOpen`: a validation finding of severity `critical` has been `open`,
  `remediating` or `remediated` (awaiting verification) for over a day.
- `MayaReviewQueueBacklog`: more than the threshold of feature, feature set and model
  versions have sat `in_review` for two days.

## Diagnosis

- Findings: the **Governance** page, or `GET /governance/findings?state=active` (read each
  row's `severity`). Each names its model, its owner and its state.
- The queue: **Workflow → Review queue**, or `GET /workflow/queue`. Look at who each item is
  waiting on. A queue usually jams on one approver, one namespace or one kind of object.

## Remedy

- **A critical finding** needs an owner, a remediation plan and a date. Move it through its
  states with evidence (`POST /governance/findings/<id>/move`). If the model should not run
  while it is open, revoke or suspend its execution warrant. A finding does not do that by
  itself.
- **A jammed queue.** Add approvers for the namespace (a model manager can review), or
  delegate. If one reviewer holds everything, reassign. Where the policy asks for more
  sign-off than the risk justifies, change the workflow policy for that namespace rather
  than approving by break-glass.

## Verification

`maya_findings_open{severity="critical"}` and `sum(maya_versions{state="in_review"})` fall
within one metrics cache period, and the alerts clear.

## What this does not reach

The threshold of 25 versions is a placeholder. A large team clears 25 in an afternoon; a
small one may never have 25 open. Set it in `config/prometheus/maya-governance.rules.yml`
from your own throughput.
