# Tutorial 12 · Champion, challenger and fairness evidence

Two questions a validator asks of every model, and could not answer without
seeing data they should not see. Is the new model actually better than the one
in use, on the same rows, by enough to matter? And does the model work equally
well for everyone it is used on? MAYA answers both on the escrowed holdout,
which nobody has seen, and returns only aggregates. Each answer reads the
holdout, so each counts as an attempt on the warrant.

In this tutorial **mona** writes a simpler challenger to the scorecard, **devi**
fits it under a warrant drawn exactly like the champion's, and **vera**
compares the two, then cuts the champion's errors by cohort and asks what
drives it.

## Time to complete

25 minutes.

## Before you start

- [Tutorial 7 · The training warrant and blind scoring](/help/guides/tutorial-07-training-warrant):
  the sealed champion warrant `credit/pd_fit_2024` (seed 11, 186 escrowed rows)
  on the pin `maya://featureset/credit/training_panel#fit/2024-06-30`.
- [Tutorial 11](/help/guides/tutorial-11-findings-tiers-reviews): **vera**, the
  validator. Also **mona**, **devi**, **mgr** and **lara** from earlier
  tutorials.

## What you will learn

- Why a fair comparison needs the same escrowed holdout, and how a warrant's
  pin, split and seed give it.
- What a paired bootstrap interval is, and how MAYA turns it into a verdict.
- Why a comparison across different holdouts is refused, and why the
  challenger's owner does not decide.
- How segment metrics flag a group the model serves worse, and a group it is
  wrong about in one direction.
- Why small segments are suppressed.
- What permutation importance says about what drives the model.

## Step 1 · Reconnect, and find the champion

```python
# reconnect, and read the champion warrant and its approved parameter set
import os

import numpy as np

import maya.sdk as maya

URL = os.environ.get("MAYA_URL", "http://127.0.0.1:8600")
PW = "Tutorial-pass-1"


def key_for(user, password=PW):
    """Sign in and create an API key for that person."""
    token = maya.Client(URL).auth.login(user, password)["token"]
    return maya.Client(URL, token=token).auth.create_api_key("tutorial")["api_key"]


def connect_as(user, password=PW):
    """Sign in, create an API key, and return a client acting as that person."""
    return maya.connect(base_url=URL, api_key=key_for(user, password))


mona, devi, mgr, lara, vera = (connect_as(u) for u in ("mona", "devi", "mgr", "lara", "vera"))

champion = next(w for w in devi.training.list() if w["name"] == "pd_fit_2024")
champion = devi.training.get(champion["id"])
champion_ps = next(p for p in champion["parameter_sets"] if p["state"] == "approved")["id"]
print(
    champion["name"],
    "| seed",
    champion["spec"]["seed"],
    "|",
    champion["holdout_rows"],
    "escrowed rows |",
    champion["holdout_attempts"],
    "attempts so far",
)
print(champion["featureset_ref"])
```

You should see the champion with its seed, its escrowed rows, the two attempts
devi made in tutorial 7, and the pin it was drawn on:

```text
pd_fit_2024 | seed 11 | 186 escrowed rows | 2 attempts so far
maya://featureset/credit/training_panel#fit/2024-06-30
```

## Step 2 · A challenger model

vera's question from tutorial 11 was whether debt to income earns its place.
mona writes the obvious challenger: the same scorecard without `dti`. It is a
model like any other, with a specification and an approval:

```python
# the challenger: the scorecard without debt to income
tex = r"""
s = \frac{bureau - 680}{60}
z = \beta_0 + \beta_1 \, utilisation + \beta_3 \, s
pd = \frac{1}{1 + e^{-z}}
"""
roles = {
    "utilisation": "feature",
    "bureau": "feature",
    "beta_0": "parameter",
    "beta_1": "parameter",
    "beta_3": "parameter",
}
mona.models.create(
    "credit", "pd_lite", formula=tex, roles=roles, description="12-month PD without debt to income"
)

sections = {
    "Purpose": "A simpler challenger to credit/pd: the same PD, without debt to income.",
    "Scope and Limitations": "As credit/pd.",
    "Mathematical Formulation": r"\mayaformula{body}",
    "Assumptions": "The log-odds are linear in utilisation and the centred bureau score.",
    "Data and Features Used": "utilisation and bureau of maya://featureset/credit/training_panel.",
    "Calibration Methodology": "Maximum likelihood under a warrant on the champion's pin and seed.",
    "Validation Evidence": "A champion-challenger comparison on the shared escrowed holdout.",
    "Known Weaknesses": "Ignores debt to income by design.",
    "Change Log": "v1: first version.",
}
spec = (
    "\\documentclass{article}\n\\begin{document}\n"
    + "".join(f"\\section{{{title}}}\n{text}\n" for title, text in sections.items())
    + "\\end{document}\n"
)
mona.models.get("credit/pd_lite")
mona.models.update_draft("credit/pd_lite", spec_latex=spec)
print(mona.models.transition("credit/pd_lite", 1, "submit")["state"])
print(mgr.models.transition("credit/pd_lite", 1, "approve", rationale="Challenger")["state"])
```

You should see it submitted and approved:

```text
in_review
approved
```

## Step 3 · The challenger's warrant, on the same pin and seed

A comparison is only fair if both models are scored on exactly the same rows.
The holdout is decided by the pin, the split and the seed, so devi draws the
challenger's warrant on the champion's pin with seed 11, fits it on the
training partition, and has the parameters approved:

```python
# draw the challenger's warrant exactly as the champion's was drawn
challenger = devi.training.create(
    "credit",
    "pd_challenger",
    "credit/pd_lite@v1",
    champion["featureset_ref"],
    spec={
        "target": "default_12m",
        "seed": 11,
        "metrics": ["rmse", "mae"],
        "leakage_justification": champion["spec"]["leakage_justification"],
    },
)
print(
    "same holdout:",
    challenger["holdout_hash"] == champion["holdout_hash"],
    "|",
    challenger["holdout_rows"],
    "rows",
)

# fit it on its training partition, as in tutorial 7
table, manifest = devi.training_data(challenger["id"])
train = table.to_pandas().query("_split == 'train'")
X = np.column_stack([np.ones(len(train)), train["utilisation"], (train["bureau"] - 680.0) / 60.0])
y = train["default_12m"].to_numpy(dtype=float)
b = np.zeros(3)
for _ in range(25):
    p = 1 / (1 + np.exp(-X @ b))
    b = b + np.linalg.solve(X.T @ (X * (p * (1 - p))[:, None]), X.T @ (y - p))
fitted = {
    "beta0": round(float(b[0]), 4),
    "beta1": round(float(b[1]), 4),
    "beta3": round(float(b[2]), 4),
}
print(fitted)

ps = devi.training.upload_parameters(challenger["id"], fitted, data_checksum=manifest["checksum"])
devi.training.parameter_transition(ps["id"], "submit")
print(mgr.training.parameter_transition(ps["id"], "approve")["state"])
```

You should see the two holdouts identical, the challenger's coefficients, and
its parameters approved:

```text
same holdout: True | 186 rows
{'beta0': -2.6959, 'beta1': 2.475, 'beta3': -0.913}
approved
```

The holdout hash is a content hash of the escrowed rows. Equal hashes mean the
same rows in the same order, and neither side has seen them.

## Step 4 · The challenge

vera asks MAYA to compare them. MAYA scores both on the holdout and compares
the *per-row* errors, which only it holds:

```python
# champion against challenger, on RMSE, with the approved parameter sets
c = vera.challenges.create(
    champion["id"],
    challenger["id"],
    metric="rmse",
    champion_parameter_set_id=champion_ps,
    challenger_parameter_set_id=ps["id"],
)
r = c["result"]
print(c["champion"]["model"], "vs", c["challenger"]["model"], "on", r["rows"], "rows")
print(
    "RMSE:",
    round(r["champion"], 4),
    "vs",
    round(r["challenger"], 4),
    "| difference",
    round(r["difference"], 4),
)
print("95% interval:", [round(x, 4) for x in r["interval"]], "|", r["bootstrap"])
print("challenger closer on", f"{r['challenger_wins']:.0%}", "of rows")
print("verdict:", r["verdict"], "| state:", c["state"])
print(
    "attempts:",
    devi.training.get(champion["id"])["holdout_attempts"],
    devi.training.get(challenger["id"])["holdout_attempts"],
)
```

You should see the challenger slightly worse on average, an interval that
straddles zero, and the verdict that there is no clear difference; one more
attempt on each warrant:

```text
pd@v1 vs pd_lite@v1 on 186 rows
RMSE: 0.3959 vs 0.3974 | difference 0.0015
95% interval: [-0.0019, 0.0051] | {'draws': 2000, 'seed': 20260926, 'level': 0.95}
challenger closer on 49% of rows
verdict: no_clear_difference | state: scored
attempts: 3 1
```

The difference is challenger minus champion; for RMSE negative is better. The
**paired bootstrap** resamples the 186 rows 2,000 times, with a fixed seed so
the same challenge gives the same interval anywhere, and recomputes the
difference each time. The verdict is `challenger_better` only when the whole
interval lies below zero, `champion_better` only when it lies above, and
`no_clear_difference` otherwise. A challenger better on average whose interval
straddles zero has not shown it.

## Step 5 · Two refusals, and the decision

Suppose devi had drawn the challenger with another seed. Its holdout would be
different rows, and any comparison meaningless:

```python
# a warrant with a different seed has a different holdout
other = devi.training.create(
    "credit",
    "pd_challenger_seed12",
    "credit/pd_lite@v1",
    champion["featureset_ref"],
    spec={
        "target": "default_12m",
        "seed": 12,
        "leakage_justification": champion["spec"]["leakage_justification"],
    },
)
try:
    vera.challenges.create(champion["id"], other["id"], champion_parameter_set_id=champion_ps)
except maya.ValidationFailed as exc:
    print(type(exc).__name__, exc)

# devi owns the challenger, so she does not decide; lara does
try:
    devi.challenges.decide(c["id"], "promote", "It is simpler")
except maya.PermissionDenied as exc:
    print(type(exc).__name__, exc)
decided = lara.challenges.decide(
    c["id"], "retain", "No clear difference; DTI stays, it costs nothing to keep"
)
print(decided["state"], "| by", decided["decided_by"], "|", decided["rationale"])
```

You should see the comparison refused, devi refused, and lara retaining the
champion with her reason:

```text
ValidationFailed The two warrants were not drawn on the same escrowed holdout, so their scores are not comparable. Draw the challenger's warrant on the champion's feature set pin, with the same split and seed.
PermissionDenied Whoever owns the challenger does not decide whether it replaces the champion
retained | by lara | No clear difference; DTI stays, it costs nothing to keep
```

The decision is a person's, in writing, by someone without a stake in the
challenger. Promoting records the decision and nothing more: the champion's
execution warrant keeps running until someone draws the challenger's and
retires the champion's.

## Step 6 · Fairness by segment

Does the scorecard work equally well across the book? vera cuts the champion's
holdout errors by a segment column. The training panel has no region or
product, so she uses the observation month, a cohort: a model that is worse for
one month's applicants is worth knowing about.

```python
# segment metrics and permutation importance on the champion's holdout
ev = vera.evidence.compute(champion["id"], parameter_set_id=champion_ps, segment="date", repeats=5)
result = ev["result"]
seg = result["segments"]
print(
    "overall MAE",
    round(seg["overall_mae"], 4),
    "| MAE ratio",
    round(seg["mae_ratio"], 2),
    "| bias gap",
    round(seg["bias_gap"], 4),
)
print("flagged:", seg["flagged"], "| systematic:", seg["systematic"])
for s in seg["segments"]:
    print(
        " ",
        s["segment"],
        s["rows"],
        "rows | MAE",
        round(s["mae"], 3),
        "| bias",
        round(s["bias"], 3),
        "| flagged" if s["flagged"] else "",
        "| systematic" if s["systematic"] else "",
    )
```

You should see six cohorts, none flagged for a high error, and January 2024
marked systematic:

```text
overall MAE 0.3127 | MAE ratio 1.61 | bias gap 0.2395
flagged: [] | systematic: ['2024-01-31']
  2024-01-31 23 rows | MAE 0.328 | bias 0.174  | systematic
  2024-02-29 29 rows | MAE 0.388 | bias -0.065  
  2024-03-31 35 rows | MAE 0.306 | bias -0.035  
  2024-04-30 33 rows | MAE 0.24 | bias 0.108  
  2024-05-31 36 rows | MAE 0.338 | bias -0.059  
  2024-06-30 30 rows | MAE 0.285 | bias 0.001  
```

Two different signals:

- A segment is **flagged** when its MAE is more than a quarter above the
  overall figure: the model serves that group worse. None is here; February
  comes closest.
- A segment is **systematic** when its bias (mean of prediction minus outcome)
  is more than half its own MAE: the model is wrong for that group mostly in
  one direction. January's applicants were given PDs 17 percentage points too high on
  average. Two groups with the same MAE can hide this completely.

With 23 rows, January could be chance. That is a judgement for vera, and the
evidence is stored against the warrant, with the parameters used, for whoever
reads it next.

## Step 7 · Small segments are suppressed

A mean over a handful of rows of an escrowed holdout is, in effect, those rows.
So a segment smaller than `min_segment` (20 by default) is reported with its
size and no figures. Raise the threshold to see it:

```python
# the same cut with a higher threshold: small cohorts are suppressed
strict = vera.evidence.compute(
    champion["id"], parameter_set_id=champion_ps, segment="date", importance=False, min_segment=33
)
for s in strict["result"]["segments"]["segments"]:
    print(
        " ",
        s["segment"],
        s["rows"],
        "rows",
        "| suppressed" if s["suppressed"] else f"| MAE {s['mae']:.3f}",
    )

# and a column with too many values is refused
try:
    vera.evidence.compute(
        champion["id"], parameter_set_id=champion_ps, segment="account", importance=False
    )
except maya.ValidationFailed as exc:
    print(type(exc).__name__, exc)
print("attempts:", devi.training.get(champion["id"])["holdout_attempts"])
```

You should see three cohorts suppressed, `account` refused, and the attempt
counter up by two:

```text
  2024-01-31 23 rows | suppressed
  2024-02-29 29 rows | suppressed
  2024-03-31 35 rows | MAE 0.306
  2024-04-30 33 rows | MAE 0.240
  2024-05-31 36 rows | MAE 0.338
  2024-06-30 30 rows | suppressed
ValidationFailed The segment column has 127 distinct values; at most 50 segments are compared. Choose a coarser column.
attempts: 5
```

Each evidence run read the holdout, so each counts; the refused one did not
get that far. A segment per account would be one row each: no evidence, and a
leak.

## Step 8 · What drives it: permutation importance

The same evidence run in step 6 also shuffled each input across the holdout,
five times with a fixed seed, and re-scored. The rise in error is how much the
model leans on that input:

```python
# permutation importance, from the evidence computed in step 6
for item in result["importance"]:
    print(
        " ",
        item["input"],
        "| RMSE rises by",
        round(item["rmse_increase"], 4),
        "±",
        round(item["spread"], 4),
        "|",
        f"{item['share']:.0%}",
    )
```

You should see the bureau score carrying most of the weight, utilisation a
quarter, and debt to income almost nothing:

```text
  bureau | RMSE rises by 0.0576 ± 0.0047 | 74%
  utilisation | RMSE rises by 0.0193 ± 0.0076 | 25%
  dti | RMSE rises by 0.0012 ± 0.0011 | 1%
```

This agrees with the challenge: dropping `dti` made no clear difference,
because the model barely uses it. Permutation importance needs nothing but
predictions, so it works the same for a black box, scored in the sandbox
(tutorial 13).

## Next steps

- [Tutorial 13 · Black boxes and models from MLflow](/help/guides/tutorial-13-black-boxes-and-imports)
  governs models with no formula.
- [Model risk](/help/model-risk) explains challenges and evidence in full.

## If something goes wrong

| What you see | Why | What to do |
|---|---|---|
| `not drawn on the same escrowed holdout` | The warrants differ in pin, split or seed | Draw the challenger on the champion's pin, with the same split and seed |
| `no value supplied for 'beta0'` from a challenge or evidence run | No parameter set was named, and MAYA does not pick the approved one for you | Pass `champion_parameter_set_id`, `challenger_parameter_set_id` or `parameter_set_id` |
| `Whoever owns the challenger does not decide` | The challenger's owner tried to decide | Another manager decides |
| `This challenge was already decided` | A challenge is decided once | Raise a new challenge |
| A segment shows no figures | It has fewer rows than `min_segment` | Use a coarser segment; lowering the threshold below 5 is not allowed |
| `at most 50 segments are compared` | The column is too fine | Choose a coarser column |
