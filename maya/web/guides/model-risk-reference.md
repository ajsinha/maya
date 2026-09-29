# Model risk governance reference

This reference is for model risk managers, validators and model owners: the people who keep the inventory, set how material each model is, raise and close findings, record periodic reviews, watch live models and decide whether a challenger replaces a champion. It covers the inventory and tiering, periodic review and the sweep that enforces it, validation findings, monitoring and covenants, champion/challenger comparisons, the evidence MAYA computes on a training warrant, training dispatch and MAYA's reference refit, attested batch scoring, and restatement alerts. Everything here reads what the registry and the warrants already hold; the [warrants reference](/help/warrants) explains the instruments themselves.

## At a glance

| Screen | Where | What it is for |
|---|---|---|
| Findings & reviews | `/governance` | Every model you may read with its tier, next review and open findings; the findings register; the inventory export; the review sweep (administrators). |
| One model's governance | `/governance/models/<ns>/<name>` | Tier and its drivers, the questionnaire, the review schedule and history, the model's findings. |
| A finding | `/governance/findings/<id>` | The finding, its history, and the moves open to you. |
| Monitoring | `/monitoring` | Every sealed execution warrant, graded `ok`, `watch` or `breach`. |
| One warrant's monitoring | `/monitoring/warrants/<id>` | Its reported runs as series, with covenant bounds beside them. |
| Champion & challenger | `/governance/challenges` | Comparisons on a shared escrowed holdout, and the decisions. |

None of these has a CLI command. The SDK namespaces are `my.governance`, `my.monitoring`, `my.challenges` and `my.evidence`, alongside `my.execution` for restatements.

## The inventory and tiering

### Tiers

Every model has a tier from 1 (most material) to 3, **derived** from evidence and open to an **override** with a written reason. A model nobody has looked at still gets a tier from the drivers MAYA measures itself.

| Driver | Score 1 | Score 2 | Score 3 | Who supplies it |
|---|---|---|---|---|
| `use` | `internal`, or not declared | `business_decision` | `regulatory`, `financial_reporting` | the owner |
| `exposure` | below 10 million, or not declared | 10 million to 1 billion | 1 billion or more | the owner |
| `reach` | no live warrant | at least one live or suspended warrant | three or more live or suspended warrants, or 10,000 executions in total | measured by MAYA |
| questionnaire | per answer | per answer | per answer | the owner, under the firm's questionnaire |
| `transparency` | — | — | — | measured: a black box, or any version marked opaque, adds one to the score |

The score is the highest of the drivers, plus one for a black box, capped at 3; the tier is `4 − score`. One serious consideration is enough to make a model tier 1, and a model nobody can read is one tier more material than one that can be checked line by line.

`declared` is true only when the owner has declared both `use` and `exposure` and answered every question. The overview shows undeclared models as such, because a tier made only from what MAYA can measure is a floor, not an assessment.

### The materiality questionnaire

The questionnaire is the firm's own policy, in a file: `governance.tiering_questionnaire`, by default `config/tiering.yaml`. Each question has an `id`, its `text`, and `answers`, each scored 1 to 3. The file also sets the rule:

| Rule | Behaviour |
|---|---|
| `max` | Each answer joins the drivers on its own; the tier follows the highest. |
| `points` | Answers are summed and placed by `thresholds` (the total at or above which a score applies); the result joins the drivers as one score. |

A blank setting means no questionnaire: the measured drivers alone. The file is re-read when it changes. A question without an id, or an answer scored outside 1 to 3, is refused when the file is read, naming the question.

### Declaring and overriding

```python
# Declare what only the owner knows, and answer the questionnaire
import maya.sdk as maya

my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
prof = my.governance.set_profile(
    "credit/pd_logit",
    use="regulatory",
    exposure=2.5e9,
    answers={
        "automation": "reviewed_by_a_person",
        "customer_impact": "directly",
        "reporting": "external_reporting",
        "complexity": "standard_and_well_understood",
    },
)
print(prof["derived_tier"], prof["tier"], [d["driver"] for d in prof["drivers"]])
```

Setting the profile needs `update` on the model. Only the fields sent change (`PUT /governance/models/{namespace}/{name}`, or `my.governance.set_profile(ref, review_days=400)`): a field left out keeps its value, and a field sent as `null` (`None` in the SDK) is cleared. Clearing `tier_override` clears its reason too. `answers` replaces the questionnaire answers as a whole when it is sent.

| Rule | Refusal detail |
|---|---|
| `use` is one of `regulatory`, `financial_reporting`, `business_decision`, `internal` | "use is one of …" |
| `exposure` is not negative | "exposure is an amount, not negative" |
| `tier_override` is 1, 2 or 3 | "a tier is 1, 2 or 3" |
| an override has a reason | "overriding the derived tier needs a written reason" |
| `review_days` is between 30 and 1825 | "a review interval is between 30 days and five years" |
| each answer is one the questionnaire allows | "'…' is not an answer to '…'", with the allowed answers |

An override that makes a model **less** material than the evidence says is flagged `override_lowers: true`, because that is the direction in which an override needs explaining. Every change is audited as `governance.profile_set` with both tiers.

### Exporting the inventory

`GET /governance/inventory?format=csv&framework=sr11-7` (or **Export the model inventory** on `/governance`) returns one row per model as a file.

| Parameter | Values |
|---|---|
| `format` | `csv`, `json`, `xlsx` |
| `framework` | `sr11-7`, `ss1-23`, or `maya` for MAYA's own column keys |

The two frameworks label the same facts differently; SS1/23 adds the basis of tiering. The export is an inventory in an aligned layout, not a regulatory filing template, and its header says so. Only models you may read are exported, and the file states how many were left out — an inventory that silently omits what its reader cannot see reads as complete.

```python
# Save the inventory in the SS1/23 layout
out = my.governance.inventory(format="xlsx", framework="ss1-23")
open("inventory.xlsx", "wb").write(out["data"])
```

## Periodic review

### Intervals

The tier sets how long a model may go without being looked at again:

| Tier | Interval | Setting |
|---|---|---|
| 1 | 365 days | `governance.review_days_tier1` |
| 2 | 730 days | `governance.review_days_tier2` |
| 3 | 1,095 days | `governance.review_days_tier3` |

A per-model `review_days` (30 to 1,825) replaces the tier's interval. The clock starts at the last recorded review, or — for a model never reviewed — at the earliest approval of any of its versions. A model with no approved version has no due date and is never overdue.

### Recording a review

```python
# Record a periodic review; any review-overdue suspensions are lifted
out = my.governance.record_review(
    "credit/pd_logit",
    "needs_improvement",
    "Re-ran the blind score and segment evidence; the Q3 drift finding stays open",
)
print(out["next_review_due"], out["reinstated"])
```

| Rule | Behaviour |
|---|---|
| Outcome | `satisfactory`, `needs_improvement` or `unsatisfactory`. |
| Note | Required: "A review records what was looked at and what was concluded". |
| Who | A **model manager** or a **model validator** who can read the model, and never its owner: "A model's owner does not review their own model"; anyone else is refused with "A periodic review is recorded by a model manager or a model validator". A review lifts the sweep's suspensions, which is why reading the model is not enough. |
| Record | A row in the review history with the tier and the next due date at the time; audit `governance.reviewed`. |

The outcome is recorded, not acted on: an `unsatisfactory` review resets the clock like any other, and what follows from it is a separate, deliberate act.

### The sweep

Once an hour the scheduler runs the review sweep; an administrator can also run it at once with **Run the review sweep** on `/governance` or `POST /governance/sweep`. For every model whose review is overdue, it suspends every execution warrant of that model that is **live**, with the reason `Periodic review overdue since <date>`. The suspension is the same one a covenant breach uses: a `suspended` custody event by `governance-sweep`, the audit entry `warrant.suspended`, and every later token, bundle or report refused with `warrant_suspended` (423) and the reason. A model that is past its review keeps being licensed only if somebody looks at it.

A warrant already suspended for another reason is not touched.

### Reinstatement

Recording the review lifts exactly the suspensions the sweep made — those whose reason begins `Periodic review overdue` — and writes a `reinstated` custody event for each. A warrant suspended for a covenant breach stays suspended: a review is not a decision about a breach.

An owner or administrator can also lift a suspension by hand with `my.execution.reinstate(id, reason)`. That does not record a review, so while the review is still overdue the next sweep suspends the warrant again within the hour.

## Validation findings

A finding is a defect somebody found: its model (and optionally version), a title, a severity, where it came from, an owner and a due date. Every move is kept in the finding's own history and in the audit chain.

| Field | Values and defaults |
|---|---|
| `severity` | `low`, `medium`, `high`, `critical` |
| `source` | `validation` (default), `audit`, `monitoring`, `review`, `self-identified` |
| `owner` | Defaults to the model's owner. |
| `due_date` | Defaults by severity: critical 30 days, high 90, medium 180, low 365. |

```python
# Raise a finding, then move it
f = my.governance.raise_finding(
    "credit/pd_logit",
    "Holdout RMSE degrades on 2025 originations",
    "high",
    detail="Segment evidence shows MAE 1.4x overall for vintage 2025",
    version_no=3,
)
my.governance.move_finding(f["id"], "start")
my.governance.move_finding(f["id"], "remediated", "Refitted with the vintage term")
```

### States and moves

| Action | From | To | Needs a note |
|---|---|---|---|
| `start` | `open` | `remediating` | no |
| `remediated` | `open`, `remediating` | `remediated` | no |
| `close` | `remediated` | `closed` | yes |
| `reject` | `remediated` | `remediating` | yes |
| `accept` | `open`, `remediating`, `remediated` | `accepted` | yes |
| `reopen` | `closed`, `accepted` | `open` | yes |

| Rule | Refusal |
|---|---|
| A move from the wrong state | `not_approved`: "A finding that is '…' cannot be moved by '…'" |
| `close` or `reject` by whoever marked it remediated | `permission_denied`: "Whoever remediated a finding does not close it; an independent reviewer confirms the fix" |
| `accept` by the model's owner (unless an administrator) | `permission_denied`: "A model owner does not accept the risk in their own model" |

`GET /governance/findings?state=active` lists everything not yet `closed` or `accepted`, most urgent first; `overdue` is true for a live finding past its due date. Audit entries are `finding.raised` and `finding.<action>`.

## Monitoring live models

Monitoring reads the execution reports live warrants already receive, and writes nothing, so it cannot disagree with the covenants. It exists because covenants judge each run alone: a null rate creeping up across fifty runs breaches nothing until the fifty-first.

### Covenants and their kinds

Covenants are declared on the execution warrant and evaluated on every report (see the [warrants reference](/help/warrants) for the spec). The kinds are:

| Kind | Breached when |
|---|---|
| `input_null_rate` | the reported `null_rate` of `attr` exceeds `max` |
| `input_range` | the reported `min` of `attr` is below `min`, or its `max` above `max` |
| `output_range` | the same, against the output statistics. Left without an `attr`, MAYA fills in the model's only output, or refuses when there are several — a covenant that names nothing could never breach |
| `input_psi` | the population stability index of `attr`'s reported `histogram` against the baseline exceeds `max` (default 0.25, allowed up to 10) |
| `max_rows_per_day` | today's reported rows, including this report, exceed `max` |
| `staleness_days` | the reported `age_days` of `attr` exceeds `max` |

An `input_psi` covenant without its own baseline takes one from the training warrant's data when the execution warrant is created — the population the model was fitted on, fixed there so it cannot move later. A breach suspends the warrant at once, notifies its owner and increments `maya_covenant_breaches_total` by kind. Lifting it is `my.execution.reinstate(id, reason)` by the owner or an administrator, with a written reason; nothing lifts it automatically.

### Health grades

```python
# Every live model, worst first
for w in my.monitoring.overview(days=30)["warrants"]:
    print(w["health"], w["namespace"], w["name"], w["worst_psi"], [s["why"] for s in w["signals"]])
```

| Grade | When |
|---|---|
| `breach` | the warrant is suspended; or a covenant breached in the last 7 days; or an input's latest PSI is above its covenant's limit |
| `watch` | a PSI between 0.10 and the limit; or an input's latest null rate at least double its median over the window (with five or more points); or a live warrant that has reported nothing for 30 days |
| `ok` | none of those |

Silence is a signal: a model that is supposed to be running and reports nothing is itself worth a look. `my.monitoring.warrant(id, days=90)` returns one warrant's reports as series — runs and rows per day, each attribute's null rate, mean, range and PSI per run with the covenant bounds beside them, and the breaches on the same axis. At most 2,000 reports are read per window; `truncated` says when that limit was reached.

Monitoring grades only sealed warrants you may read, and only on what is reported to MAYA. Runs made from an offline bundle are unattested and never reported, so nothing here sees them.

## Champion and challenger

A challenge scores two training warrants on the **same** escrowed holdout and compares their per-row errors, which only MAYA holds.

```python
# Compare two warrants drawn on the same pin, split and seed
c = my.challenges.create(champion_warrant_id, challenger_warrant_id, metric="rmse")
r = c["result"]
print(r["difference"], r["interval"], r["challenger_wins"], r["verdict"])
my.challenges.decide(c["id"], "retain", "Interval straddles zero; no case for the change")
```

| Rule | Refusal detail |
|---|---|
| `metric` is `rmse` or `mae` | "metric is one of rmse, mae" |
| The two warrants differ | "A model is not challenged by itself" |
| Same holdout hash | "The two warrants were not drawn on the same escrowed holdout, so their scores are not comparable. Draw the challenger's warrant on the champion's feature set pin, with the same split and seed." |
| Same target | "The two warrants score different targets" |

The result holds both metrics, their difference (challenger minus champion; negative is better), a paired bootstrap 95% interval over 2,000 resamples with a fixed seed — so the same challenge gives the same interval anywhere — the share of rows on which the challenger's error is smaller, and a verdict: `challenger_better` only when the whole interval is below zero, `champion_better` only when it is above, otherwise `no_clear_difference`. Each side's scoring counts as a holdout attempt on its warrant.

The decision, `promote` or `retain`, needs a rationale and is refused to the challenger warrant's owner: "Whoever owns the challenger does not decide whether it replaces the champion". **Promoting records a decision and changes nothing else.** The champion's execution warrants keep running until someone draws the challenger's and retires the champion's: a comparison on a holdout is evidence for that change, not the change. Audit entries are `challenge.scored`, `challenge.promoted` and `challenge.retained`.

## Warrant evidence

`my.evidence.compute(warrant_id, ...)` computes fairness and explainability evidence on a training warrant's escrowed holdout. Nothing leaves but aggregates.

```python
# Segment metrics by region, and permutation importance
ev = my.evidence.compute(w["id"], parameter_set_id=ps["id"], segment="region", repeats=5)
s = ev["result"]["segments"]
print(s["mae_ratio"], s["flagged"], s["systematic"], ev["result"]["importance"][:3])
```

| Part | What it computes |
|---|---|
| Segments | For the column you name: each segment's RMSE, MAE, bias (mean error) and mean prediction; the worst-to-best MAE ratio and the widest bias gap. A segment is **flagged** when its MAE is more than 1.25 times the overall figure, and **systematic** when its bias is more than half its own MAE — wrong for that group mostly in one direction, which two groups with the same MAE can hide. |
| Suppression | A segment with fewer than `min_segment` rows (default 20, never below 5) is reported with no figures: a mean over three holdout rows is three holdout rows. At most 50 segments are compared. |
| Importance | Each input shuffled across the holdout `repeats` times (1 to 20, seeded) and the model re-scored; the rise in RMSE, its spread, and each input's share. It needs only predictions, so a black box works the same way through its sandboxed artifact. |

A run counts as one holdout attempt, like any scoring, and is stored with the parameters used; audit `warrant.evidence_computed`. The target cannot be the segment column. `my.evidence.list(warrant_id)` returns every stored result, including reference refits.

## Training dispatch and the reference refit

### Dispatch: MAYA runs nothing

`my.evidence.dispatch(warrant_id, image, entrypoint="python train.py", maya_url=...)` turns a training warrant into a job for your own compute. MAYA returns:

- a **manifest** — the warrant, the data and parameter paths, the target, seed and split — signed with the platform key;
- a **one-day API key** scoped to the warrant's namespace, shown once;
- a ready Kubernetes `Job` (the key read from a Secret) and a SageMaker `CreateTrainingJob` request.

Inside the job, `maya.sdk.trainer.fit_under_warrant(fit)` downloads the warrant's data, calls your `fit(train, target)` on the training rows and uploads the parameters with the data's checksum and the dispatch id among their metrics, so the parameter set says which run produced it. A sealed warrant is refused ("The warrant is sealed; its parameters are fixed"). Audit `warrant.training_dispatched`. MAYA does not submit, schedule or watch the job.

### Reference refit

`my.evidence.refit(warrant_id, parameter_set_id=...)` has MAYA fit the parameters itself on the warrant's **training** split — deterministic Levenberg–Marquardt least squares within the declared bounds, starting from the developer's values — and compare: both training RMSEs, the relative gap per parameter, and `agrees`. It needs a closed-form model with parameters and a declared target. It reads only the training split, so it is not a holdout attempt, and **it never becomes a parameter set**: MAYA checks a fit, it does not supply one. The result is stored as evidence (`reference_refit`); audit `warrant.reference_refit`.

## Attested batch scoring

MAYA does not serve models. What it will do is score a **pin** — data frozen by content — under a live execution warrant, as a job, so the batch is reproducible to the byte.

```python
# Score a pinned feature set under a live warrant, then fetch the output
job = my.evidence.batch_score(
    ew["id"], "maya://featureset/credit/pd_panel#month/2026-08-31", "prod"
)
done = my.wait(job)
out = my.evidence.batch_output(ew["id"], job["id"])
print(done["result"]["output_hash"], done["result"]["status_after"])
```

The warrant is checked on submission and again when the job runs. A formula model is evaluated from its IR with the warrant's approved parameters; a declared black box runs its validated artifact in the sandbox. At most 5,000,000 rows. Every batch is attested three ways at once:

- the output is sealed by its content hash and stored (the download carries it in `X-Maya-Content-Hash`);
- the run is **reported on the warrant** exactly as an external caller would report it, so covenants are evaluated and a breach suspends the warrant;
- the custody chain records `batch_scored` with the pin and the output hash.

Only whoever ran a batch, or an administrator, may download its output. A non-pin reference is refused: "Batch scoring reads a pin: maya://featureset/ns/name#pin/date".

## Restatement alerts

A restatement never touches a pin — that is the point of two clocks — which means a model fitted on a pin keeps running on the story the pin tells after the source has said that story was wrong. Restatement alerts act on it (`maya/services/restatements.py`).

### What is checked

When an ingest is recorded as a restatement (a feature upload or source run that corrects values already known), and `restatements.alerts` is true, a job looks at every execution warrant that is live or suspended and was drawn from a training warrant on a sealed feature set pin. For each, it resolves the pin's definition again — the same member feature versions, the same as-of date — with what is known **now**, and compares its content hash with the sealed pin's. Equal hashes mean nothing under that model moved, and nothing is said. The same corrected hash is never reported twice for one warrant.

### The impact record

When the data moved, MAYA measures the difference without showing anyone a row:

| Part | Contents |
|---|---|
| `rows` | compared, changed, changed in the holdout, added, dropped |
| `metrics_sealed`, `metrics_corrected` | the live parameters scored blind on the holdout both ways: RMSE, MAE, rows. MAYA's own check, not counted as a holdout attempt. |
| `shift` | the mean and largest absolute change in predictions over every row, and the share of rows that moved |

The impact is stored against the warrant with the trigger, both hashes and state `open`; it is audited as `restatement.impact` and counted in `maya_restatement_impacts_total`.

### Notifications and acknowledging

The warrant's owner, the model's owner and every model manager are notified with one line: rows changed, added and dropped, how far predictions moved, and the holdout RMSE before and after. **Nothing is suspended**: whether a correction invalidates a model is a judgement, and the impact is the evidence for it.

```python
# Read the impacts on a warrant and acknowledge one
for i in my.execution.restatements(ew["id"]):
    print(i["state"], i["rows"]["changed"], i["shift"]["max_abs"])
my.execution.acknowledge_restatement(
    impact_id, "Refitted as pd-2026q3; this warrant retires on seal"
)
```

Acknowledging needs a note ("Say what was done about it, or why it does not matter") and may be done once, by the warrant's owner, a model manager or an administrator; audit `restatement.acknowledged`. On the execution warrant's page the **Restated data** section lists impacts and takes the note.

### Check now

**Check now** on a live or suspended execution warrant's page, or `my.execution.check_restatements(id)`, queues the same assessment for that one warrant at once — for the same three kinds of people. It runs whatever `restatements.alerts` says; the setting only governs the automatic check after an ingest.

| Setting | Default | Meaning |
|---|---|---|
| `restatements.alerts` | `true` | After a restatement, check every live model's training pin against what is known now and tell its owners how far the result moves. |

A warrant drawn on a feature set **version** rather than a pin, or not drawn from a training warrant at all, has nothing to compare and is skipped silently. That is the price of not pinning, and one more reason to pin.

## What this does not do

- It does not decide. A tier, a verdict, an impact and a health grade are evidence; promotions, acceptances and reinstatements are recorded decisions by named people.
- Promoting a challenger does not replace a champion's warrants; acknowledging a restatement does not refit anything.
- The sweep suspends live execution warrants; it does not revoke them, and it does not touch training warrants.
- Monitoring sees only what is reported. Unattested offline use is invisible to it by construction.
- Dispatch prepares a job; MAYA never runs training.

## API summary

All paths are under `/api/v1`.

| Method and path | SDK |
|---|---|
| `GET /governance` | `my.governance.overview()` |
| `GET /governance/inventory` | `my.governance.inventory(format, framework)` |
| `GET`, `POST /governance/findings` | `my.governance.findings(model, state)`, `my.governance.raise_finding(...)` |
| `GET /governance/findings/{id}`, `POST /governance/findings/{id}/move` | `my.governance.finding(id)`, `my.governance.move_finding(id, action, note)` |
| `GET`, `PUT /governance/models/{ns}/{name}` | `my.governance.profile(ref)`, `my.governance.set_profile(ref, ...)` |
| `POST /governance/models/{ns}/{name}/reviews` | `my.governance.record_review(ref, outcome, note)` |
| `POST /governance/sweep` | `my.governance.sweep()` |
| `GET /monitoring`, `GET /monitoring/warrants/{id}` | `my.monitoring.overview(days)`, `my.monitoring.warrant(id, days)` |
| `GET`, `POST /challenges`; `GET /challenges/{id}`; `POST /challenges/{id}/decision` | `my.challenges.list()`, `.create(...)`, `.get(id)`, `.decide(id, decision, rationale)` |
| `GET`, `POST /warrants/training/{id}/evidence` | `my.evidence.list(id)`, `my.evidence.compute(id, ...)` |
| `POST /warrants/training/{id}/dispatch`, `POST /warrants/training/{id}/refit` | `my.evidence.dispatch(...)`, `my.evidence.refit(...)` |
| `POST`, `GET /warrants/execution/{id}/batches`; `GET …/batches/{job}/output` | `my.evidence.batch_score(...)`, `.batches(id)`, `.batch_output(id, job)` |
| `GET /warrants/execution/{id}/restatements`, `POST …/restatements/check` | `my.execution.restatements(id)`, `my.execution.check_restatements(id)` |
| `POST /restatements/{impact_id}/acknowledge` (body `{"reason": …}`) | `my.execution.acknowledge_restatement(impact_id, note)` |
