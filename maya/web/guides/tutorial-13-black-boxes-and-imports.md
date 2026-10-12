# Tutorial 13 · Black boxes and models from MLflow

Not every model has a formula. A bought vendor score, a gradient-boosted tree
trained in a notebook, a model already registered in MLflow: none can be written
as an equation, and MAYA does not pretend otherwise. It registers them as
**black boxes**, with a declared input contract and a mandatory statement of
what they estimate, and says plainly which checks it cannot perform. In this
tutorial you register a vendor's credit-spread model, validate its scoring code
in the sandbox, score it blind on an escrowed holdout, import a second model
from an MLflow `MLmodel` file, and put the control that remains, covenants, on
an execution warrant.

## Time to complete

30 minutes.

## Before you start

- [Tutorials 1 to 6](/help/guides/tutorial-01-first-15-minutes): the people
  **dana** and **mick** (features), **devi** (model developer), **mona** (model
  designer) and **mgr** (model manager), and how features, feature sets, pins
  and model review work.
- The admin password, to add a namespace and one person.
- A terminal in a working directory. The tutorial writes `obligors.csv` and
  `MLmodel` there.

## What you will learn

- How to declare a black box, and what MAYA refuses to do for one.
- How a code artifact is validated, and what the sandbox tier on its report
  means.
- How a black box is scored blind: its code runs in the sandbox on the holdout's
  inputs, and only metrics come out.
- How an MLflow model's signature becomes an input contract.
- Why covenants on an execution warrant are the main control on a model nobody
  can read.

## Step 1 · Reconnect, and set up the vendor data

The vendor's model, *AcmeSpread*, estimates the fair credit spread of a
corporate borrower, in basis points, from two ratios: **leverage** (debt over
earnings) and interest **cover** (earnings over interest). The bank keeps a
monthly file of forty borrowers with both ratios and the spread the market
actually charged. That gives MAYA something to score the vendor against.

The bank adds a namespace, `vendor`, and a second model manager, **ines**,
because an execution warrant needs two managers: one submits, the other
approves.

```python
# reconnect; the admin adds the vendor namespace and ines
import os

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


admin = connect_as("admin", "maya-dev-admin")  # your admin password, if you changed it
admin.namespaces.create("vendor", preset="standard")
admin.admin.create_user("ines", password=PW, roles=["model_manager"])
dana, mick, devi = connect_as("dana"), connect_as("mick"), connect_as("devi")
mona, mgr, ines = connect_as("mona"), connect_as("mgr"), connect_as("ines")
```

The data follows tutorials 2 and 4: dana defines and ingests the feature, mick
approves it, devi builds the set, and mick pins it with a cascade.

```python
# forty borrowers over six month ends: leverage, cover, and the observed spread
MONTHS = ["2026-01-30", "2026-02-27", "2026-03-31", "2026-04-30", "2026-05-29", "2026-06-30"]
with open("obligors.csv", "w") as fh:
    fh.write("date,obligor,leverage,cover,spread,kt\n")
    for i, month in enumerate(MONTHS):
        for k in range(40):
            leverage = 1.0 + (k % 8) * 0.5 + 0.02 * i
            cover = 1.5 + (k % 5) * 1.0
            noise = (k * 7 + i * 3) % 11 - 5
            spread = 80 + 45 * leverage - 12 * cover + 60 * max(leverage - 3, 0) + noise
            fh.write(
                f"{month},OB{k:03d},{leverage:.2f},{cover:.2f},{spread:.1f},{month}T20:00:00Z\n"
            )

obligors = {
    "index": ["date", "obligor"],
    "index_types": {"date": "date", "obligor": "string"},
    "schema": [
        {"name": "leverage", "type": "float64", "unit": "ratio"},
        {"name": "cover", "type": "float64", "unit": "ratio"},
        {"name": "spread", "type": "float64", "unit": "bp"},
    ],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "spread"}],
}
dana.features.create("vendor", "obligors", obligors)
with open("obligors.csv", "rb") as fh:
    rows = dana.features.ingest("vendor/obligors", fh.read(), fmt="csv")["rows"]
dana.features.transition("vendor/obligors", 1, "submit")
mick.features.transition("vendor/obligors", 1, "approve")

inputs = {
    "index": ["date", "obligor"],
    "members": [
        {"attr": a, "ref": "maya://feature/vendor/obligors@v1", "source_attr": a}
        for a in ("leverage", "cover", "spread")
    ],
}
devi.featuresets.create("vendor", "inputs", inputs)
devi.featuresets.transition("vendor/inputs", 1, "submit")
mick.featuresets.transition("vendor/inputs", 1, "approve")
out = mick.featuresets.pin(
    "vendor/inputs", version_no=1, pin_name="h1", as_of="2026-06-30", cascade=True
)
print(rows, "rows ingested;", mick.wait(out["job"]["id"])["result"]["rows"], "rows pinned")
```

You should see all 240 rows ingested and pinned:

```text
240 rows ingested; 240 rows pinned
```

## Step 2 · Declare the black box

There is no formula to write, so mona declares what can be known: the inputs,
the output, and a `black_box` block saying what the model **estimates** and its
**architecture**. Both are mandatory. Because AcmeSpread is bought, the model's
kind is `vendor`, and the vendor's name, product, version and documentation are
recorded with it.

```python
# mona declares the vendor model
ACME = {
    "inputs": [{"name": "leverage", "type": "float64"}, {"name": "cover", "type": "float64"}],
    "outputs": [{"name": "spread"}],
    "black_box": {
        "estimates": "the fair credit spread, in basis points, of a corporate obligor",
        "architecture": "vendor-hosted gradient-boosted trees, 300 estimators",
    },
}
VENDOR = {
    "name": "Acme Analytics",
    "product": "AcmeSpread",
    "version": "4.1.0",
    "documentation": "AcmeSpread 4.1 model card, section 3: inputs and output",
}
m = mona.models.create(
    "vendor",
    "acme_spread",
    kind="vendor",
    ir=ACME,
    vendor=VENDOR,
    description="AcmeSpread as licensed",
)
v = mona.models.get("vendor/acme_spread")["versions"][0]
print(m["kind"], "opaque:", v["opaque"], [c["name"] for c in v["input_contract"]])

for name, call in [
    ("reference code", lambda: mona.models.reference_code("vendor/acme_spread", 1)),
    ("conformance", lambda: mona.models.conformance("vendor/acme_spread", 1)),
]:
    try:
        call()
    except maya.ValidationFailed as exc:
        print(name, "->", type(exc).__name__, exc)
```

You should see an opaque model with its input contract, no reference code, and
no conformance test yet, because there is no code to test:

```text
vendor opaque: True ['leverage', 'cover']
reference code -> ValidationFailed only closed-form models have a compute kernel
conformance -> ValidationFailed No code artifact to test against the specification
```

The input contract works exactly as it does for a formula: a training or
execution warrant checks it against the feature set. What is missing is the
mathematics, so there is nothing to generate code from.

## Step 3 · The vendor's scoring code, in the sandbox

The licence includes the vendor's scoring code. It must have the same shape as
any implementation in MAYA: a class `Model` with `fit` and `predict`. A bought
model has nothing to fit, so `fit` returns no parameters. MAYA puts the code
through its validation ladder: it parses, has the right entry point, imports
only allowed modules, uses no files, network or dynamic code, runs on a sample
in the **sandbox**, and gives the same answer twice.

```python
# attach the vendor's code and read the validation report
ACME_CODE = """
import numpy as np


class Model:
    def fit(self, X, y, ctx):
        return {}

    def predict(self, X, params, ctx):
        lev = np.asarray(X["leverage"], dtype=float)
        cov = np.asarray(X["cover"], dtype=float)
        return {"spread": 80 + 45 * lev - 12 * cov + 60 * np.maximum(lev - 3, 0)}
"""
mona.models.get("vendor/acme_spread")
out = mona.models.upload_artifact("vendor/acme_spread", ACME_CODE)
mona.wait(out["job"]["id"])
report = mona.models.get("vendor/acme_spread")["versions"][0]["artifact_report"]
for rung in report["rungs"]:
    print(rung["rung"], rung["name"], rung["passed"])
print("passed:", report["passed"], "| sandbox tier:", report["tier"])
print(mona.models.conformance("vendor/acme_spread", 1))
```

You should see six rungs passed, the sandbox tier this machine delivers, and a
conformance test that is skipped and says why:

```text
1 parse True
2 entry point True
3 import allowlist True
4 static ban True
5 smoke run True
6 determinism True
passed: True | sandbox tier: strong
{'skipped': True, 'statement': 'declared black box: nothing to compare'}
```

**The sandbox tier depends on your machine.** MAYA measures it by probing for
an escape, rather than assuming it. `strong` needs Linux, with a separate user,
no network, a read-only root and a seccomp filter; this machine has it. A Mac
reports `moderate` (a kernel sandbox profile, no separate user), and Windows
reports `minimal` (a time limit only). In a development estate every step of
this tutorial still runs at a lower tier, and the tier is written on every
report and every score so a reviewer knows what protected the run. Outside
`dev`, MAYA refuses to start below `sandbox.min_tier`, which is `strong` by
default.

Conformance is skipped, not passed. With no documented closed form there is
nothing to compare the code against, and MAYA says so instead of reporting an
agreement it never measured.

## Step 4 · Review

The vendor model goes through the same review as any other. mona writes the
specification, with every section filled in, and submits:

```python
# a specification for a bought model: what is known, and what is not
SECTIONS = {
    "Purpose": "Estimate the fair credit spread of corporate obligors, to price new "
    "facilities and challenge desk quotes.",
    "Scope and Limitations": "Investment-grade and crossover corporates with leverage "
    "below 6. Not for financials or sovereigns.",
    "Mathematical Formulation": "Not available: AcmeSpread is a licensed black box. "
    "The vendor states gradient-boosted trees, 300 estimators.",
    "Assumptions": "The vendor's training population resembles our book.",
    "Data and Features Used": "leverage and cover from maya://featureset/vendor/inputs.",
    "Calibration Methodology": "Calibrated by the vendor; not refitted by the bank.",
    "Validation Evidence": "Blind RMSE against observed spreads on an escrowed holdout, "
    "scored in MAYA's sandbox.",
    "Known Weaknesses": "Opaque; cannot be conformance-tested; controlled by covenants "
    "on its inputs and outputs.",
    "Change Log": "v1: AcmeSpread 4.1.0 as licensed.",
}
spec = (
    "\\documentclass{article}\n\\begin{document}\n"
    + "".join(f"\\section{{{name}}}\n{text}\n" for name, text in SECTIONS.items())
    + "\\end{document}\n"
)
mona.models.get("vendor/acme_spread")
mona.models.update_draft("vendor/acme_spread", spec_latex=spec)
r = mona.models.transition("vendor/acme_spread", 1, "submit")
for c in r["checks"]:
    print(" ", c["check"], c["passed"], "-", c["detail"])
print(
    mgr.models.transition(
        "vendor/acme_spread", 1, "approve", rationale="Declared, validated, contract matches"
    )["state"]
)
```

You should see the code checks answered honestly for a black box, and the model
approved:

```text
  formula_typechecks True - IR validates and typechecks
  spec_document_complete True - all required sections present
  code_artifact_validated True - validated under sandbox tier 'strong'
  code_matches_specification True - declared black box: there is no closed form to compare against
approved
```

## Step 5 · Score it blind

A training warrant binds the model to the pinned set, as for any model. A bought
model is not trained, but the warrant still checks the contract, certifies the
data against leakage, and escrows a holdout. Blind scoring then runs the
vendor's validated code **in the sandbox**, on the holdout's input columns only,
never the target, and MAYA computes the metrics itself:

```python
# a warrant on the pinned set, then two blind scores on the escrowed holdout
pin = "maya://featureset/vendor/inputs#h1/2026-06-30"
tw = devi.training.create(
    "vendor", "acme_check", "vendor/acme_spread@v1", pin, spec={"target": "spread", "seed": 5}
)
print(
    tw["contract_report"]["ok"],
    tw["leakage_certificate"]["status"],
    tw["holdout_rows"],
    "rows escrowed",
)

score = devi.training.score_holdout(tw["id"])
m = score["metrics"]
print(
    "attempt",
    score["attempt"],
    "| rmse",
    round(m["rmse"], 2),
    "bp | mae",
    round(m["mae"], 2),
    "bp |",
    m["rows"],
    "rows |",
    m["scored_in"],
    m["sandbox_tier"],
)
print(sorted(score))
print("attempt", devi.training.score_holdout(tw["id"])["attempt"])
```

You should see the contract satisfied, the data certified, forty rows escrowed,
then the score: metrics only, scored in the sandbox, and the attempt counter
moving on the second call:

```text
True certified 40 rows escrowed
attempt 1 | rmse 3.05 bp | mae 2.58 bp | 40 rows | sandbox strong
['attempt', 'metrics', 'note']
attempt 2
```

The vendor's model is about 3 basis points from the market on rows nobody
looked at. No prediction and no holdout row left MAYA: the result has metrics, an
attempt number and a note, nothing else. Every attempt is counted on the
warrant, so scoring again and again until a number looks good is visible to the
reviewer. The score also records the artifact's hash and the sandbox tier.

## Step 6 · A model from MLflow

The bank's own data scientists keep their models in MLflow. Every logged model
has an `MLmodel` file, and if it was logged with a signature, that file lists
the input columns and their types. MAYA reads it: the signature becomes the
input contract, the flavours become the architecture, and the run id is kept as
provenance. You say what the model estimates; MLflow does not record that.

```python
# an MLmodel file, as MLflow writes it beside a logged model
MLMODEL = """\
artifact_path: model
flavors:
  python_function:
    env:
      conda: conda.yaml
    loader_module: mlflow.sklearn
    model_path: model.pkl
    python_version: 3.11.4
  sklearn:
    pickled_model: model.pkl
    serialization_format: cloudpickle
    sklearn_version: 1.4.2
mlflow_version: 2.12.1
model_uuid: 3b8f1f0e2a8c4e6f9d0b7a6c5e4d3c2b
run_id: 9f1c2d3e4b5a69788796a5b4c3d2e1f0
signature:
  inputs: '[{"type": "double", "name": "leverage", "required": true}, {"type": "double", "name": "cover", "required": true}]'
  outputs: '[{"type": "double", "name": "spread", "required": true}]'
  params: null
utc_time_created: '2026-05-04 10:21:33.120000'
"""
with open("MLmodel", "w") as fh:
    fh.write(MLMODEL)

with open("MLmodel") as fh:
    mona.integrations.import_mlflow(
        "vendor",
        "spread_gbm",
        fh.read(),
        estimates="the fair credit spread of a corporate obligor, in basis points",
    )
model = mona.models.get("vendor/spread_gbm")
bb = model["versions"][0]["formula_ir"]["black_box"]
print(model["kind"], [c["name"] for c in model["versions"][0]["input_contract"]])
print(bb["architecture"])
print(bb["provenance"]["source"], bb["provenance"]["run_id"], bb["provenance"]["loader"])

# a model logged without a signature cannot be imported: its inputs are unknown
try:
    mona.integrations.import_mlflow(
        "vendor", "spread_unsigned", "flavors:\n  python_function: {}\n", estimates="a spread"
    )
except maya.ValidationFailed as exc:
    print(type(exc).__name__, exc)
```

You should see a black box with the signature's inputs, the flavours as its
architecture, the MLflow run it came from, and the unsigned model refused with
advice:

```text
black_box ['leverage', 'cover']
MLflow model; flavours python_function, sklearn
mlflow 9f1c2d3e4b5a69788796a5b4c3d2e1f0 mlflow.sklearn
ValidationFailed This MLflow model was logged without a signature, so its input columns are not recorded. Log it with a signature (mlflow.models.infer_signature), or register it in MAYA as a black box and declare the inputs yourself.
```

The imported model is a draft like any other: it needs a specification and an
approval, and, to be scored blind, a code artifact that passes the ladder. MAYA
never loads the pickled model itself. With `integrations.mlflow.tracking_uri`
configured, `mona.integrations.fetch_mlflow(...)` reads the same file straight
from the MLflow server by model name and version.

## Step 7 · Covenants, the control that remains

For a formula model, MAYA can check the code against the mathematics. For a
black box it cannot, so the main control is on what goes in and what comes out.
An **execution warrant** authorises running the model and carries
**covenants**: here, leverage must stay within the range the vendor documents,
and the spread within what is plausible. A reported run that breaks either
suspends the warrant.

```python
# seal the training warrant; issue an execution warrant with two covenants
devi.training.transition(tw["id"], "submit")
mgr.training.transition(tw["id"], "approve")
mgr.training.seal(tw["id"])

ew = mgr.execution.create(
    "vendor",
    "acme_live",
    training_warrant_id=tw["id"],
    spec={
        "environments": ["dev"],
        "contact": "credit-risk@example.com",
        "covenants": [
            {"kind": "input_range", "attr": "leverage", "min": 0, "max": 6},
            {"kind": "output_range", "min": 0, "max": 600},
        ],
    },
)
print([(c["kind"], c["attr"], c["min"], c["max"]) for c in ew["spec"]["covenants"]])
mgr.execution.transition(ew["id"], "submit")
try:
    mgr.execution.transition(ew["id"], "approve")
except maya.PermissionDenied as exc:
    print(type(exc).__name__, exc)
print(ines.execution.transition(ew["id"], "approve")["state"])
mgr.execution.seal(ew["id"])
```

You should see the output covenant filled in with the model's one output, mgr
refused as the person who submitted, and ines approving:

```text
[('input_range', 'leverage', 0, 6), ('output_range', 'spread', 0, 600)]
PermissionDenied segregation of duties (two_person): you created, submitted or last modified this object, so you cannot approve it
approved
```

Now the calling system reports two runs: an ordinary month, then a month with a
borrower at leverage 9.5, far outside what the vendor's model has seen:

```python
# a healthy run, then a run outside the vendor's range
ok = devi.execution.report(
    ew["id"],
    "dev",
    rows=40,
    input_stats={"leverage": {"min": 1.0, "max": 4.6}},
    output_stats={"spread": {"min": 60, "max": 330}},
)
print(ok["status"], ok["breaches"])
bad = devi.execution.report(
    ew["id"],
    "dev",
    rows=40,
    input_stats={"leverage": {"min": 1.0, "max": 9.5}},
    output_stats={"spread": {"min": 60, "max": 640}},
)
print(bad["status"], [b["detail"] for b in bad["breaches"]])
try:
    devi.execution.bundle(ew["id"], "dev")
except maya.WarrantSuspended as exc:
    print(type(exc).__name__, exc)
```

You should see the first run accepted, the second suspend the warrant naming
both breaches, and the next request for the model refused:

```text
live []
suspended ["'leverage' max 9.5 above 6", "'spread' max 640 above 600"]
WarrantSuspended Warrant suspended: 'leverage' max 9.5 above 6; 'spread' max 640 above 600. Contact credit-risk@example.com.
```

The model fails closed. Until the model owner or an administrator reinstates
the warrant with a written reason, nothing may call it. For a model whose
insides nobody can inspect, that is the guarantee that matters: it is used only
on inputs like those it was validated on, and its answers stay in range.

## Next steps

- [Models](/help/models) covers black boxes, vendor models and composites, and
  how opacity carries into a composite.
- [Integrations](/help/integrations) covers MLflow, SageMaker and OpenLineage.
- [Warrants](/help/warrants) explains every covenant kind, limits and
  reinstatement.
- [Tutorial 14 · LLM applications](/help/guides/tutorial-14-llm-applications)
  governs a model of another kind again: a large language model.

## If something goes wrong

| What you see | Why | What to do |
|---|---|---|
| `estimates` named when submitting | The black box does not say what it estimates | Fill in `black_box.estimates` and `architecture` |
| `no artifact that passed` when scoring | The model has no validated code artifact | Upload one with `models.upload_artifact` and wait for the ladder |
| A rung fails in the artifact report | The code imports a banned module, reads files, or fails on the sample | Read the rung's `detail`; fix the code and upload again |
| The tier says `moderate` or `minimal` | Your machine lacks the strong Linux sandbox | Fine for learning in `dev`; production needs `strong` |
| `logged without a signature` | MLflow did not record the inputs | Log the model with a signature, or declare the black box yourself |
| `segregation of duties (two_person)` | The person who submitted the warrant tried to approve it | Ask another model manager |
