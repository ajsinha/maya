# Integrations reference

This reference is for platform engineers and model owners connecting MAYA to the systems around it: an MLflow tracking server or Amazon SageMaker where models are trained and served, and an OpenLineage consumer such as Marquez where lineage is collected. MAYA is a register. It does not train, run or serve models, so its integrations go in two directions only — models trained elsewhere come **in** as governed drafts, and MAYA's decisions and lineage go **out** to the platforms that act on them. The code is `maya/services/integrations.py`; the screen is **Models → Import a model** (`/integrations`).

## At a glance

| Integration | Direction | What moves | Settings |
|---|---|---|---|
| MLflow import | in | An `MLmodel` file, uploaded or fetched from the configured tracking server, becomes a black-box draft | `integrations.mlflow.tracking_uri`, `integrations.mlflow.token_env` |
| MLflow live alias | out | An alias on every MLflow model version with a live execution warrant, removed when it stops being live | `integrations.mlflow.live_alias` |
| SageMaker import | in | A `DescribeModelPackage` document becomes a black-box draft | — |
| OpenLineage | out | MAYA's lineage edges as OpenLineage `RunEvent`s, downloaded or posted | `integrations.openlineage.url`, `integrations.openlineage.api_key_env`, `integrations.openlineage.namespace` |

Elsewhere, and not repeated here: the event stream and signed webhooks are in the [operations guide](/help/operations); single sign-on (OIDC and SAML, with provisioning on first login) and outbound-connection rules are in the [security guide](/help/security); read-only SQL sources are in the [features reference](/help/features); email, Slack and Teams notification settings are in the [configuration reference](/help/guides/configuration-reference). MAYA has no SCIM endpoint.

!!! warning "Tested against published documents, not live accounts"
    None of these connectors has been exercised against a live MLflow server, a SageMaker account or a hosted OpenLineage consumer by this code base's tests. They are tested against the documents those systems publish and against a recorded HTTP exchange. The `/integrations` page says the same.

## Models in: what an import produces

Every import produces the same thing: a **draft model of kind `black_box`** in the namespace you name, whose input contract comes from the source, with the source's provenance sealed into the model's IR under `black_box.provenance`. From there it is an ordinary black box — reviewed, warranted and blind-scored like any other (see the [models reference](/help/models) on black boxes). Importing needs `create` on models in the namespace, exactly as creating the model by hand does.

Every import needs a sentence saying what the model estimates. The refusal is "Say in a sentence what the model estimates; a black box is reviewed on it" — a reviewer cannot read a black box's mathematics, so what it claims to estimate is the thing they judge it against. Each import is audited as `model.imported` with its source and, where there is one, the MLflow run id, the model URI or the SageMaker ARN.

An import is a registration, not an approval. Whatever standing the model had in MLflow or SageMaker — a stage, an alias, an approval status — does not carry over: the model starts at `draft` in MAYA. (SageMaker's approval status is kept in the provenance as a fact; MLflow's stages and aliases are not read at all.)

## MLflow

### Importing from an MLmodel file

A model logged with MLflow carries an `MLmodel` file: its flavours, the run that produced it, and — if it was logged with one — a **signature** naming its input and output columns. MAYA reads the signature as the input contract.

```python
# Import from an MLmodel file you have on disk
import maya.sdk as maya

my = maya.connect(base_url="https://maya.example.com", api_key="maya_prod_…")
m = my.integrations.import_mlflow(
    "credit",
    "pd_gbm",
    mlmodel=open("mlruns/1/abc123/artifacts/model/MLmodel").read(),
    estimates="Twelve-month probability of default for retail mortgages",
)
print(m["imported_from"]["flavors"], m["imported_from"]["run_id"])
```

| What MAYA takes | From |
|---|---|
| Inputs | The signature's input columns, one `feature` input each. Types map `double`/`float` → `float64`, `long`/`integer` → `int64`, `boolean` → `bool`, `string`, `datetime`, `binary`; anything else is `float64`. A column without a name becomes `col_<n>`. |
| Outputs | The signature's output columns, or one `prediction` (`float64`) if it has none. |
| Provenance | `source: mlflow`, the flavours, `run_id`, `model_uuid`, creation time, MLflow version, the `python_function` loader module, and the model URI when it was fetched. |

| Refusal | Why |
|---|---|
| "Not an MLmodel file: it has no 'flavors'" | It is not an MLmodel file. |
| "This MLflow model was logged without a signature, so its input columns are not recorded. Log it with a signature (mlflow.models.infer_signature), or register it in MAYA as a black box and declare the inputs yourself." | MAYA's contract checks need the input names, and guessing them would make every later check a check of the guess. |
| "The signature is tensor-based; MAYA's contract is column-based, one named input per column" | A tensor signature has no column names to bind. |

### Fetching from the tracking server

With `integrations.mlflow.tracking_uri` set, MAYA can fetch a registered model version's `MLmodel` itself: give the registered model's name and version instead of the file.

```python
# Fetch a registered version from the configured tracking server
m = my.integrations.fetch_mlflow(
    "credit",
    "pd_gbm",
    model_name="pd-gbm",
    version="7",
    estimates="Twelve-month probability of default for retail mortgages",
)
print(m["imported_from"]["uri"])  # models:/pd-gbm/7
```

```bash
# The same over REST
curl -s -X POST https://maya.example.com/api/v1/integrations/mlflow/fetch \
  -H "Authorization: Bearer $MAYA_API_KEY" -H "Content-Type: application/json" \
  -d '{"namespace": "credit", "name": "pd_gbm", "model_name": "pd-gbm", "version": "7",
       "estimates": "Twelve-month probability of default for retail mortgages"}'
```

MAYA asks the server for the model version, then fetches its `MLmodel` from the server's artifact store (an `mlflow-artifacts:/` source, or a run's artifacts). A model whose artifacts live somewhere the tracking server does not serve is refused: "The model's artifacts live at '…', which the tracking server does not serve; upload its MLmodel file instead". A transport or HTTP error is refused as "The MLflow tracking server refused or failed: …".

**Only the configured server is contacted.** There is no field for a URL: a URL typed into a form is how a server is made to fetch from somewhere it should not. Without a tracking URI, fetching is refused with "No MLflow tracking server is configured (integrations.mlflow.tracking_uri); upload the model's MLmodel file instead". If the server needs a bearer token, `integrations.mlflow.token_env` names the environment variable that holds it; the token itself is never configuration.

### The live alias

MAYA does not serve models, so its decisions have to reach the platform that does. For MLflow that is an **alias**: MAYA points `integrations.mlflow.live_alias` (default `maya-live`) at the live version of each imported MLflow registered model, and removes it from a registered model none of whose versions is live. A serving platform that deploys `models:/pd-gbm@maya-live` then deploys only what MAYA currently licenses.

| Aspect | Behaviour |
|---|---|
| Which versions | Model versions imported by **fetching**, whose provenance carries a `models:/<name>/<version>` URI. A version imported from an uploaded file has no registry address and is not synced. |
| What "live" means | At least one of the version's execution warrants has status `live`. A suspended, expired or revoked warrant is not live — so a covenant breach, a revocation, an expiry and an overdue periodic review all take the alias off the same way. |
| When | Every five minutes on its own, and on demand: **Sync now** on `/integrations`, `POST /integrations/mlflow/sync`, or `my.integrations.sync_mlflow()` (administrators). |
| Per registered model | An MLflow alias names one version of a registered model, so the decision is per registered model: set it on the live version, or delete it when no version is live. A version that is not live never removes it from a live sibling. If several versions of one registered model are live at once, the alias names the newest. |
| Calls | MLflow's registered-model alias API. Deleting an alias that is already absent counts as removed. |
| Changes only | Each pass compares what should be true with what it last made true, and calls MLflow only for the differences. That memory is per process and starts empty, so the first pass after a restart sends everything again. |
| Failures | Listed in the result under `failed` and retried on the next pass. |
| Record | Audit `integration.mlflow_synced` with what was set, removed and failed, whenever something changed. |

Without a tracking URI the sync does nothing and says so (`configured: false`). The sync is a reconciler rather than a hook in every warrant transition, which is why a suspension reaches MLflow within one interval rather than at once.

```python
# Push MAYA's live/not-live decisions to MLflow now (administrators)
print(
    my.integrations.sync_mlflow()
)  # {'configured': True, 'alias': 'maya-live', 'set': [...], 'removed': [...], 'failed': []}
```

## Amazon SageMaker

A SageMaker model package's `DescribeModelPackage` document names the image, the model data, the approval status and any metrics, but **not the inputs** — SageMaker does not record them. So the importer takes the input names from you, or from a `maya:inputs` customer metadata property (comma-separated), and records which one it used.

```python
# Import from the output of aws sagemaker describe-model-package
import json

pkg = json.load(open("describe-model-package.json"))
m = my.integrations.import_sagemaker(
    "credit",
    "pd_xgb",
    pkg,
    estimates="Twelve-month probability of default for credit cards",
    inputs=["utilisation", "months_on_book", "delinquencies_12m"],
)
print(m["imported_from"]["arn"], m["imported_from"]["approval"], m["imported_from"]["inputs_from"])
```

| What MAYA takes | From |
|---|---|
| Inputs | The names you pass, else `maya:inputs`; each a `float64` feature. |
| Outputs | The names you pass, else one `prediction`. |
| Description | The package's `ModelPackageDescription`. |
| Provenance | `source: sagemaker`, the ARN, group, version, approval status, images, model data URLs, framework, and `inputs_from` (`caller` or `maya:inputs metadata`). |

| Refusal | Why |
|---|---|
| "Not a model package description: it has no ModelPackageArn" | It is not a `DescribeModelPackage` document. |
| "SageMaker does not record a model package's inputs. Name them, or add a 'maya:inputs' customer metadata property listing them, comma-separated." | No input names from either place. |

MAYA does not call AWS for an import: you supply the document. SageMaker's `ModelApprovalStatus` is recorded and not acted on; there is no alias sync for SageMaker.

## OpenLineage

MAYA's lineage edges, grouped by what they produce, become OpenLineage `RunEvent` documents: one job per produced object, its sources as inputs, its output the object itself.

| Field | Value |
|---|---|
| `eventType` | `COMPLETE` |
| `eventTime` | The latest edge into the object. |
| `run.runId` | A UUID derived from the object and that time, so the same graph gives the same ids. |
| `job` | `namespace` from `integrations.openlineage.namespace` (default `maya`), `name` the object's MAYA reference, and a `maya` facet listing the edge types. |
| `inputs`, `outputs` | Datasets named by MAYA reference in the same namespace. |

```python
# Download the events, or post them to the configured endpoint (administrators)
events = my.integrations.openlineage_events()
print(len(events), events[0]["job"]["name"])
print(my.integrations.emit_openlineage())  # {'events': …, 'sent': …, 'failed': [...]}
```

| Action | Where | Behaviour |
|---|---|---|
| Download | **Download events** on `/integrations`, or `GET /integrations/openlineage/events` | Every event as JSON. |
| Send | **Send to the configured endpoint**, or `POST /integrations/openlineage/emit` | Posts each event to `integrations.openlineage.url` followed by `/api/v1/lineage`, with a bearer token from the variable `integrations.openlineage.api_key_env` names. Returns the count sent and each failure; audit `lineage.openlineage_emitted`. Without a URL: "No OpenLineage endpoint is configured (integrations.openlineage.url); download the events instead". |

Both are for administrators: "Exporting the whole lineage graph is for administrators". The export is the whole graph, and it does not apply per-object read permissions, so it is not something to hand to anyone who can read one model. Every send posts every event again; there is no incremental export and no push on each change.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `integrations.mlflow.tracking_uri` | empty | The MLflow tracking server models may be fetched from; blank means upload only, and no alias sync. |
| `integrations.mlflow.token_env` | empty | Environment variable holding a bearer token for the MLflow server, if it needs one. |
| `integrations.mlflow.live_alias` | `maya-live` | The MLflow alias MAYA points at each model version with a live execution warrant. |
| `integrations.openlineage.url` | empty | An OpenLineage endpoint (for example Marquez) lineage is posted to; blank means download only. |
| `integrations.openlineage.api_key_env` | empty | Environment variable holding the OpenLineage endpoint's bearer token, if any. |
| `integrations.openlineage.namespace` | `maya` | The OpenLineage namespace MAYA's jobs and datasets are reported under. |

## Related: training jobs for your own compute

A training warrant can be turned into a ready Kubernetes `Job` and a SageMaker `CreateTrainingJob` request, with a signed manifest and a one-day key, by `POST /warrants/training/{id}/dispatch`. MAYA prepares the job and runs nothing; the [model risk governance reference](/help/model-risk) describes it.

## What this does not do

- MAYA does not deploy, serve or call a model in MLflow or SageMaker. The live alias is the only thing it writes to another platform, and what the serving side does with the alias is that platform's business.
- The alias follows execution warrants only. It says nothing about whether a model version is approved but not yet licensed, and a model imported by upload never gets one.
- Imports copy metadata, not models: MAYA stores no weights from MLflow or SageMaker. Scoring a black box needs its code artifact uploaded and validated in MAYA like any other.
- OpenLineage export is outbound only; MAYA does not read lineage from an OpenLineage consumer.

## API summary

All paths are under `/api/v1`.

| Method and path | SDK |
|---|---|
| `POST /integrations/mlflow/import` | `my.integrations.import_mlflow(namespace, name, mlmodel, estimates, description)` |
| `POST /integrations/mlflow/fetch` | `my.integrations.fetch_mlflow(namespace, name, model_name, version, estimates, description)` |
| `POST /integrations/mlflow/sync` | `my.integrations.sync_mlflow()` |
| `POST /integrations/sagemaker/import` | `my.integrations.import_sagemaker(namespace, name, package, estimates, inputs, outputs)` |
| `GET /integrations/openlineage/events` | `my.integrations.openlineage_events()` |
| `POST /integrations/openlineage/emit` | `my.integrations.emit_openlineage()` |
