---
title: Validation and findings
slug: validation
section: Assurance
order: 90
icon: clipboard-check
summary: An episode of challenge is worth having only if it can refuse something, and a finding is worth having only if somebody is accountable for closing it. The independence rule, the test catalogue, replay against the pinned snapshot — and the four acts from which a finding's ageing, acceptance and escalation are all derived.
audience: Model validation, Model risk, Model owners
---

# Validation and findings

Challenge produces two objects, and MAYA keeps them apart because they have
different lifecycles. An **episode** concludes. A **finding** stays open until
somebody fixes it.

They exist for different reasons, too, and each design follows from its reason:

- An episode is worth having only if it can **refuse** something. So it is
  independent, its results are immutable, and it cannot conclude `approved` over
  a failure.
- A finding is worth having only if somebody is **accountable** for closing it.
  So the register records acts rather than statuses, and derives ageing,
  acceptance and escalation from them.

One column joins the two: **`blocking`**. An open blocking finding stops the
model being served at all.

---

# Part one — the episode

A validation is an **episode of independent challenge** against one model
version, recorded as an object with a lifecycle rather than as a document
attached to a model, because three things about it need to be enforceable.

## Rule 1 — independence

A validator may not be the person who built the version.

```bash
POST /api/v1/validations                      # needs validation:open
{
  "urn": "maya://model/credit.pd.smallbiz",
  "semver": "3.2.1",
  "validators": ["person/a.mehta"],
  "kind": "initial",
  "scope": ["discrimination", "calibration"],
  "snapshot_id": "snap-2026-03-31"
}
```

If any named validator is the version's `created_by`, the episode is refused:

```
independence failed: person/d.raman built this version; effective challenge
requires a validator who did not build the version
```

This is SS1/23 Principle 4 and SR 26-2's *effective challenge*, in the only form
a system can actually check. The attestation is stored on the episode either
way, so the record shows who validated and what the independence position was.
An episode with no named validator at all is refused too.

Concluding is separately gated by
[segregation of duties](/help/approval-and-attestation#segregation-of-duties),
read from the evidence chain against the **version**: whoever recorded
`version_created` may not conclude its validation, whatever roles they hold.
Both checks compare identities the same way, ignoring a `person/` prefix and
case — a comparison that used `==` was a control that worked in tests and was
inert over HTTP.

Seven kinds are recognised: `initial`, `periodic`, `targeted`, `change`,
`vendor`, `annual_review`, `tier_review`.

## The test catalogue

A validation may only run **registered** tests, published at
`GET /api/v1/tests`:

| Key | Measures | Direction |
|---|---|---|
| `discrimination.auc` | Area under the ROC curve | higher is better |
| `discrimination.gini` | 2 × AUC − 1 | higher is better |
| `discrimination.ks` | Kolmogorov–Smirnov separation | higher is better |
| `calibration.brier` | Brier score of the probability forecast | lower is better |
| `calibration.expected_vs_actual` | Predicted rate ÷ observed rate | target 1.0 |
| `stability.psi` | Population Stability Index | lower is better |
| `accuracy.rmse` | Root mean squared error | lower is better |
| `accuracy.mae` | Mean absolute error | lower is better |

Seven of them take labels and scores. `stability.psi` is the exception: it
compares **two samples**, because stability is a question about distributions
rather than about outcomes.

That distinction is enforced rather than documented, and the reason is a bug
worth remembering. The paired-length check that belongs on a labels-and-scores
test was once applied to the two-sample one as well, so a reference window and a
current window of different sizes were silently truncated to the shorter — and a
PSI of 3.54 was recorded as 0.023. The check now runs only where a pair actually
means a pair.

These are computed from their definitions rather than imported from a library. A
result has to be reproducible years after the library that computed it is gone,
and a validator has to be able to show an examiner how the number was arrived
at. Ties take average ranks throughout, and PSI's bin edges come from the
*expected* sample's quantiles with empty bins floored rather than dropped.

Degenerate samples — one class present, a zero base rate, too few points for the
requested bins — return **not computable** rather than a number, and a
not-computable test does **not** pass:

```
not computable on this sample — a class may be absent, or the sample too
small for the requested bins
```

Absent evidence is not evidence of compliance.

## Recording a result

```bash
POST /api/v1/validations/{id}/results         # needs validation:record
{
  "test_key": "discrimination.gini",
  "threshold": {"min": 0.42},
  "left":  [0, 0, 1, 1, ...],
  "right": [0.02, 0.05, 0.61, 0.94, ...],
  "slice": {"region": "EMEA"}
}
```

**The test is a measurement; the threshold is a policy.** Thresholds are
declared per run, because the Gini floor that is right for a Tier 3 marketing
propensity model is not the one that is right for a Tier 1 IRB PD model.

Thresholds take one of three forms — `{"min": x}`, `{"max": x}`, or
`{"target": t, "tolerance": e}` — and one declaring none of the three is
refused. No threshold at all records the measurement and passes: an exploratory
number should not have to invent a limit to be recorded, and it must never look
like a test that met one.

## Rule 2 — no approval over a failure

```bash
POST /api/v1/validations/{id}/conclude        # needs validation:conclude
{"outcome": "approved"}
```

Four outcomes exist: `approved`, `approved_with_conditions`, `rejected`,
`deferred`. If any recorded test failed:

```
cannot approve: 1 test(s) failed (discrimination.gini); conclude
'approved_with_conditions' with the conditions written down, or 'rejected'
```

The legitimate route out is always offered. `approved_with_conditions` is a real
outcome — it just forces the conditions to be written down, which is the whole
point.

## Rule 3 — no approval over a blocking finding

If something blocking is open against the model, approval is refused until it is
closed, naming the findings that stand in the way.

Both rules fire only on `approved`. Rejecting a model over a failed test needs
no permission from the test, and deferring one needs no permission from a
finding.

## Results are immutable once concluded

Recording against a completed episode is refused — *its results are immutable* —
and a concluded episode cannot be concluded again. A validation that can be
edited after the fact is not evidence of anything.

Every refusal in this part comes back as `validation_refused` with HTTP 409 and
a `detail` naming the rule; the finding workflow below carries its own codes.

## Reproducibility replay

```bash
POST /api/v1/validations/{id}/replay
{"data": {"discrimination.gini": [[labels...], [scores...]]}}
```

Each recorded result is recomputed and compared **on its digest**, which covers
the test key, the value, the threshold, the parameters and the slice. So replay
catches more than a changed number — it catches a threshold that moved after the
fact, and a slice definition that drifted, both of which leave the value intact
and the conclusion wrong.

A test whose data cannot be supplied is reported **skipped**, never reproduced:

```json
{"reproducible": false, "reproduced": 1, "skipped": [...],
 "detail": "1 could not be checked"}
```

"We could not check" and "we checked and it matched" are opposite findings. A
replay report that blurs them is worse than no replay at all, so a skip never
counts as a pass.

### Replay without asking you for the data

A replay that takes its numbers from the caller proves the arithmetic. It does
not prove much else, because it can only be run by somebody who already has the
data, and only with their cooperation. That is a control you help perform.

```bash
POST /api/v1/validations/{id}/replay-from-storage
```

This re-reads the dataset snapshot the episode was pinned to and recomputes from
that. Nothing is supplied by the caller, so a mismatch is about the test rather
than about who handed over which file.

**It reads at the pin, not at the path.** The snapshot names a Delta version and
the read uses it. If the table has been written to since, the replay still sees
what the validation saw:

```json
{"pinned_delta_version": 3, "current_delta_version": 5, "restated": true,
 "detail": "the table has been written to since: v3 when the validation ran,
            v5 now. the replay reads v3, so a mismatch is about the test and
            not about the data"}
```

Those are two different findings and the report keeps them apart. A restatement
underneath a validation is worth knowing about; it is not the same as a test
that no longer reproduces.

**What cannot be checked is never reported as checked.** An episode that pins no
snapshot, a snapshot whose table has been removed, or a test whose columns are
not in the frame comes back as *skipped* with the reason. A slice naming a
column the frame does not have yields **nothing** rather than the whole frame,
because a slice silently ignored is a replay of a different population.

```bash
GET /api/v1/validations/{id}/replayable
```

answers the question before you spend anything on it, and across a model's
history gives the number a second line actually wants: not whether replay works,
but what fraction of what was concluded could be checked without asking whoever
concluded it.

---

# Part two — the finding

Every model risk framework requires findings to be tracked. Most systems track
them in a table that nothing reads.

## The one column

**`blocking`.** An open blocking finding refuses three things.

**Alias promotion.**

```
alias move refused: 1 blocking finding(s) open against
maya://model/credit.pd.smallbiz (Label leakage in the training set);
close them or downgrade them before promoting a version
```

**Warrant resolution** — HTTP 423, error code `blocked`:

```json
{
  "error": "blocked",
  "detail": "1 blocking finding(s) open against maya://model/credit.pd.smallbiz (...)",
  "remediation": "close the blocking findings, or withdraw the model from service"
}
```

**Concluding a validation `approved`**, as above.

Resolution is the one point every consumer passes through, so a model that
failed challenge cannot reach production by any route that does not pass through
this register. That is what makes it a control rather than a report.

### Severity and default blocking

| Severity | Remediation window | Blocks by default |
|---|---|---|
| Critical | 30 days | **yes** |
| High | 90 days | no |
| Medium | 180 days | no |
| Low | 365 days | no |
| Observation | 365 days | no |

Blocking can be forced on any finding with `"blocking": true`, and switched off
on a Critical one explicitly. Only Critical blocks without anyone deciding — and
the default is what happens when nobody decides, which is the case worth
designing for.

Due dates are **derived from severity** rather than negotiated per finding, so a
Critical finding is not a diary entry.

```bash
POST /api/v1/findings                          # needs finding:raise
{
  "urn": "maya://model/credit.pd.smallbiz",
  "severity": "Critical",
  "title": "Label leakage in the training set",
  "owner": "person/j.okafor",
  "description": "The 90-day-arrears flag is computed after the label date.",
  "category": "data_quality",
  "source": "validation"
}
```

An owner is required. *A finding with no owner is a finding nobody will fix* —
and that is the refusal message.

## The four acts

A finding used to be raised with an owner and a date, and then nothing happened
to it until somebody closed it. That is the year in which findings actually go
wrong: handed quietly between three people, never accepted by anybody, and given
a later date by the one person with a reason to want one.

Four acts close that, and **none of them is a status**. They are appended to
`finding_action` and everything else — age, overdue-ness, whether the current
owner ever accepted it, how many times the date has moved, whether it should be
escalated — is *computed* from them. There is no status table that can disagree
with the register. The `status` column ends up agreeing with what was done; it
is a summary of the acts, never a substitute, and it moves `open` →
`in_remediation` → `resolved` → `closed`.

```bash
GET /api/v1/finding-acts        # the four acts and what each one means
GET /api/v1/findings/{id}       # the finding and everything derived from its acts
```

### Assignment — the handover is on the record

```bash
POST /api/v1/findings/{id}/assign             # needs finding:assign
{"to": "person/d.raman", "reason": "the re-fit is development work"}
```

Whoever *raised* a finding never changes — that is what the segregation check
reads to decide who may close it. Whoever *owns* it can, and every handover
names who gave it up, who took it on and why. A handover with no reason is
refused: "reassigned" explains nothing to whoever reads it at the next
committee. Handing it to the person who already owns it is refused as
`already_owned`.

**A handover withdraws the previous owner's acceptance.** The new owner has not
agreed to the date the last one named, and treating the old acknowledgement as
current is how a reassignment launders an unaccepted commitment into an accepted
one. Because acknowledgement is derived rather than stored, this needs no code:
an acknowledgement recorded before the last handover simply is not the current
one, and the reading says so.

### Acknowledgement — an owner accepting that it is theirs

```bash
POST /api/v1/findings/{id}/acknowledge        # needs finding:acknowledge
{"plan": "Re-fit on the 2026 sample by 30 June", "days": 60}
```

*A remediation plan nobody agreed to is a date somebody else invented*, and on
every dashboard it looks exactly like a date somebody is working to.

- **Only the owner may acknowledge, and nobody may do it for them**
  (`not_the_owner`). An acknowledgement somebody else recorded for you is the
  paperwork of a commitment without the commitment.
- **A plan is required** (`plan_required`). Acknowledging without saying what
  will be done is a receipt, not a commitment.
- **The committed date may not be later than the due date**
  (`beyond_the_due_date`), nor in the past (`date_in_the_past`). This is the
  hole it closes: an owner who could accept to any date they liked would have an
  extension mechanism that needed nobody's agreement, left no count, and gave no
  reason. The refusal points at the legitimate route.

Acknowledging moves the finding to `in_remediation`.

### The plan — what will be done, by when

```bash
POST /api/v1/findings/{id}/plan               # needs finding:plan
{"plan": "Re-fit on the 2026 sample by 30 June, revalidate in July"}
```

The same act, the same word and the same refusal as the compliance debt
register's `plan_for`: an empty plan is refused, because *"will fix" is not a
plan*. Re-planning does not overwrite — a finding re-planned three times is a
fact about the remediation, and the reading reports how many revisions there
have been.

### Extension — legitimate, never silent, counted

```bash
POST /api/v1/findings/{id}/extend             # needs finding:extend
{"reason": "the 2026 sample does not close until Q3", "days": 30}
```

Dates move for good reasons. What must not happen is a date moving with no
reason, at the discretion of the person it constrains, and uncounted. So:

| Refusal | Why |
|---|---|
| `reason_required` | a date that moves without one is a date nobody is accountable for |
| `self_extension` | the person with the deadline is the last person who should be able to move it |
| `not_acknowledged` | extending a date nobody agreed to moves a number, not a commitment |
| `not_an_extension` | a date brought forward is a plan, not an extension |
| `extension_too_long` | longer than the severity's own window is a new remediation date nobody justified |

Extension is enforced three times over, deliberately: `finding:extend` sits in
the **second line and nowhere else**, so the first line does not hold it at all;
the register refuses the owner however their identity is spelled; and the
evidence chain refuses whoever *acknowledged* the finding, which catches one
person wearing two hats.

**Past the limit, the extension itself becomes a finding.** Two extensions are a
schedule slipping; the third says the date has stopped meaning anything, and
that is a governance failure distinct from whatever the original finding was
about:

```
Remediation date moved repeatedly: Segment drift unexplained
extended 3 time(s) against a limit of 2, adding 30 days; a date moved this
often is not a date
```

It is raised once, not on every extension — the same shape of rule as the
[overlay register's](/help/monitoring) persistence finding.

## Closure needs somebody else

```bash
POST /api/v1/findings/{id}/close              # needs finding:close
{"evidence": {"pr": "1420", "rerun": "val-3391"}}
```

Two rules:

- **The owner may not verify their own closure.** The person who owns the
  remediation is the person with the strongest reason to declare it done, and a
  blocking finding is the only thing standing between a failed model and
  production.
- **Closure evidence is required.** An empty closure is refused.

**A closure is attributed to whoever performs it.** `verified_by` may be sent,
but it is never trusted: naming somebody else is refused with
`verifier_not_self` and the remediation *"omit verified_by, or have that person
close it"*. That field was once believed, which meant a blocking finding's owner
could close their own by naming a colleague — and the forged attribution entered
the permanent evidence chain, which is the part that made it worth fixing
properly rather than patching the message.

There is also no back door: `set_status` will move a finding to
`in_remediation` or `resolved`, but attempting to set it to `closed` is refused
with *use close() — closure needs a verifier and evidence*.

## Escalation — by role, not by hierarchy

```bash
GET /api/v1/findings/{id}/escalation
GET /api/v1/findings/escalated?urn=...     # or estate-wide, within your scope
```

MAYA does not know who reports to whom and does not pretend to. What it knows is
that a finding that is overdue, unaccepted or serially extended has stopped
being only its owner's problem, so the escalation names a **role** — the model
risk manager, the same role and the same reason that the
[notification digest](/help/estate-and-worklist) escalates to.

Escalation is *computed*, never set. An escalation somebody has to remember to
flag is an escalation that happens when somebody remembers. A finding escalates
when it is:

- more than seven days past its remediation date; or
- blocking and past its date at all — it is stopping the model being served; or
- unaccepted more than five days after it was raised or handed over; or
- extended past the limit.

An unaccepted finding also appears on its owner's worklist, so the notification
digest delivers it — derived like everything else there, so it clears itself
when the owner accepts rather than when somebody ticks a task. When the
reminders have been ignored, the `findings.unacknowledged` job records the fact
as a finding of its own, idempotently. Reminders that are ignored have to end
somewhere other than in more reminders.

## The ageing profile

```bash
GET /api/v1/findings/ageing?urn=maya://model/credit.pd.smallbiz
GET /api/v1/findings/ageing                # the estate, within your scope
```

What a risk committee asks for and rarely gets. Not *how many findings* — every
bank has that number — but:

```json
{"open": 12, "blocking": 2, "overdue": 4, "unacknowledged": 3, "unplanned": 3,
 "escalated": 5, "worst_severity": "Critical",
 "by_severity": {"High": {"open": 6, "overdue": 3, "unacknowledged": 1,
                          "extended": 2, "oldest_days": 214.0,
                          "mean_age_days": 88.4}},
 "by_age": {"0-30 days": 4, "91-180 days": 5, "over 180 days": 3},
 "extended": {"findings": 4, "extensions": 9, "over_limit": 1,
              "days_added": 240.0, "most_extended": 3},
 "oldest": {"finding_id": "...", "severity": "High", "age_days": 214.0}}
```

Age is reported as a **distribution rather than a mean**, because one finding
open for four years and nine opened last week average to something reassuring.

The extension counts are the line nobody reports and the one that matters most:
they say whether the remediation dates in the rest of the pack mean anything at
all.

## Sources

`validation`, `monitoring`, `audit`, `regulator`, `self_identified`. The source
matters for reporting: a regulator-raised finding and a self-identified one
carry very different weight in a supervisory conversation, and aggregating them
together loses exactly the distinction that matters.

Two of those five are raised by the platform itself rather than by a person —
monitoring breaches, and the scheduler's sweeps for lapsed attestations, stalled
monitors, missed remediation windows, unaccepted findings, expired baseline debt
and persistent overlays. See [Monitoring](/help/monitoring) and
[The estate and what needs doing](/help/estate-and-worklist).

## Reading the register

```bash
GET /api/v1/findings?urn=maya://model/credit.pd.smallbiz
```

Returns the open list, the blocking subset, and a summary — open count, blocking
count, overdue count, worst severity, and a breakdown by severity. That summary
is what the model page shows, and what an inventory row needs.
