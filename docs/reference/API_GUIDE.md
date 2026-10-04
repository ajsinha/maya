# MAYA REST API guide

This guide is for anyone writing a program that talks to MAYA over HTTP: a scheduler that
pins data every night, a notebook that fits a model under a warrant, a production service
that checks its warrant before it scores, or a script in a language MAYA has no SDK for.

It is written to be followed, not just read. Every `bash` and `python` example below is
executed, in order, against a freshly started MAYA by `tests/test_api_guide.py`; if an
example stops working, the build fails. Copy them as they are.

**Contents**

1. [Before you start](#1-before-you-start)
2. [How the API works, in five minutes](#2-how-the-api-works-in-five-minutes)
3. [First contact with curl](#3-first-contact-with-curl)
4. [A small Python client](#4-a-small-python-client)
5. [The whole lifecycle, step by step](#5-the-whole-lifecycle-step-by-step)
6. [The same things with curl](#6-the-same-things-with-curl)
7. [Conventions every client needs](#7-conventions-every-client-needs)
8. [Errors, and what to do about each](#8-errors-and-what-to-do-about-each)
9. [Troubleshooting](#9-troubleshooting)
10. [Appendix: every endpoint](#10-appendix-every-endpoint)

---

## 1. Before you start

You need:

| What | Why | Check |
|---|---|---|
| A running MAYA | The API is served by the same process as the web UI | `python run_maya_web.py` in the checkout (see the [README](../../README.md#getting-started)) |
| Its address | Every example reads it from `MAYA_URL` | `export MAYA_URL=http://127.0.0.1:8600` |
| `curl` and `jq` | For the shell examples | `curl --version && jq --version` |
| Python 3.13 with `httpx`, `numpy`, `pandas`, `pyarrow` | For the Python examples | MAYA's own environment has Python 3.13 and all four |
| A user who may do what you ask | Every call runs as a person or a key, with their roles | the bootstrap administrator is `admin` / `maya-dev-admin` on a fresh install |

**Use a scratch MAYA to follow this guide.** Section 5 creates users, a namespace called
`demo`, a feature, a feature set, a model and two warrants. On a fresh install nothing gets
in the way; on an estate that already has a `demo` namespace or those users, the create
calls answer `409 conflict`.

> On a fresh install the administrator's password is the published default. MAYA lets it
> sign in so that you can set up the first users, and asks for it to be changed; do that
> before the instance holds anything real.

## 2. How the API works, in five minutes

- **One base path.** Everything is under `$MAYA_URL/api/v1`. The version is in the path, and
  a breaking change would be a new path, never a silent change to this one.
- **JSON in, JSON out.** Requests send `Content-Type: application/json`, except file
  uploads, which are `multipart/form-data`. Responses are JSON, except downloads (Parquet,
  CSV, Excel, PDF), which say what they are in `Content-Type`.
- **Every call is somebody.** Send `Authorization: Bearer <token>` with either a session
  token from `POST /auth/login` or an API key. The call runs with that person's roles and
  grants, and is recorded in the audit chain under their name. There is no anonymous
  write.
- **Things have names and versions.** A feature, feature set or model is addressed by
  `namespace/name` in the URL, and its versions by number. In request bodies the same things
  are written as references: `maya://feature/demo/xy@v1` is version 1 of feature `xy` in
  namespace `demo`, and `maya://featureset/demo/panel#q1/2026-02-28` is the pin named `q1`
  of feature set `panel`, as of 28 February 2026.
- **Changes of state are transitions.** Drafts are submitted, reviewed and approved by
  `POST …/versions/{n}/transitions/{name}`. MAYA refuses a transition the caller may not
  take, most often because the person who submitted something may not also approve it.
- **Slow work is a job.** Pinning data, validating an artifact and other long operations
  answer `202 Accepted` at once with a job, and you poll `GET /jobs/{id}` until it finishes.
- **Failures are problem documents.** Anything that goes wrong comes back as
  `application/problem+json` with a machine-readable `type` and a sentence in `detail` that
  says what to do. Section 8 lists them.

The live, generated reference for every endpoint is served by MAYA itself at
`$MAYA_URL/api/v1/docs` (interactive) and `$MAYA_URL/api/v1/openapi.json` (the OpenAPI
document). This guide explains how to use them together; that reference is the last word on
every field.

## 3. First contact with curl

Is it up? These two need no credential: `/healthz` answers as soon as the process runs,
`/readyz` only once the database and storage are ready (a load balancer should use it).

```bash
MAYA_URL=${MAYA_URL:-http://127.0.0.1:8600}
curl -s "$MAYA_URL/healthz"; echo
curl -s -o /dev/null -w "readyz: %{http_code}\n" "$MAYA_URL/readyz"
```

Sign in, keep the token, and ask who you are:

```bash
MAYA_URL=${MAYA_URL:-http://127.0.0.1:8600}
TOKEN=$(curl -s -X POST "$MAYA_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "maya-dev-admin"}' | jq -r .token)
curl -s "$MAYA_URL/api/v1/auth/me" -H "Authorization: Bearer $TOKEN" | jq '{username, roles}'
```

The login answer carries `token` and also `must_change_password` and `mfa`. When `mfa` is
`challenge` or `enroll` the session can do nothing but finish the second factor
(`POST /auth/mfa/verify` with `{"code": "123456"}`); section 7 has the details.

Send the token on every call. Without it, MAYA says so:

```bash
MAYA_URL=${MAYA_URL:-http://127.0.0.1:8600}
curl -s "$MAYA_URL/api/v1/namespaces" | jq .
```

## 4. A small Python client

Everything in section 5 uses this one function. It adds the credential, sends the request,
turns a problem document into an exception that carries it, and returns JSON (or the raw
response for downloads). It is the whole client; there is nothing hidden.

```python
import datetime as dt
import io
import json
import os
import time

import httpx

MAYA = os.environ.get("MAYA_URL", "http://127.0.0.1:8600")
API = f"{MAYA}/api/v1"


class MayaError(Exception):
    """A problem document (RFC 7807) the API returned instead of a result."""

    def __init__(self, status, problem):
        super().__init__(f"{status} {problem.get('type')}: {problem.get('detail')}")
        self.status, self.problem = status, problem


def call(method, path, token=None, **kwargs):
    """One request to the API: JSON back, or a MayaError naming what went wrong."""
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = httpx.request(method, API + path, headers=headers, timeout=120, **kwargs)
    if r.status_code >= 400:
        raise MayaError(r.status_code, r.json())
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json()
    return r  # a download: the caller reads r.content and r.headers
```

> Prefer Python? MAYA ships a full SDK (`from maya.sdk import connect`) with a method for
> every endpoint, paging helpers, retries and a read cache. This guide uses raw HTTP on
> purpose, because that is what a client in any other language sees.

## 5. The whole lifecycle, step by step

The example is deliberately small so that every number can be checked by eye: a daily
series `x` and `y` for three symbols, where `y = 2x + 0.5`. It walks the full chain MAYA
governs: **data → feature → feature set → pin → model → training warrant → parameters →
blind score → execution warrant → live use → governance.**

### 5.1 Set up people and a namespace (administrator)

Separation of duties is enforced, so the lifecycle needs several people: somebody designs a
feature and somebody else approves it; somebody fits a model and somebody else signs it off.
The administrator creates them and a namespace to work in. The `standard` preset staffs the
namespace with the usual review chain.

```python
ADMIN = call("POST", "/auth/login", json={"username": "admin", "password": "maya-dev-admin"})[
    "token"
]

PASSWORD = "Guide-Pass-2026!"
for username, roles in {
    "dana": ["feature_designer"],  # designs features and uploads data
    "mick": ["feature_manager"],  # approves features and pins them
    "mona": ["model_designer"],  # writes models
    "devi": ["model_developer"],  # fits models under a warrant
    "mgr": ["model_manager"],  # approves models and warrants
    "mgr2": ["model_manager"],  # a second approver for live use
}.items():
    call("POST", "/users", ADMIN, json={"username": username, "password": PASSWORD, "roles": roles})

call("POST", "/namespaces", ADMIN, json={"name": "demo", "preset": "standard"})
```

### 5.2 Sign everybody in

When `auth.password.force_change` is on, a password set by an administrator must be changed
at first sign-in (`must_change_password` in the login answer); it is off by default. The
helper changes it either way, since the administrator knows it, and returns a session token.

```python
NEW_PASSWORD = "Guide-Pass-2026-changed!"


def first_sign_in(username):
    """Sign in with the administrator-set password, change it, and sign in again."""
    first = call("POST", "/auth/login", json={"username": username, "password": PASSWORD})
    call(
        "POST",
        "/auth/password",
        first["token"],
        json={"old_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    return call("POST", "/auth/login", json={"username": username, "password": NEW_PASSWORD})[
        "token"
    ]


DANA, MICK, MONA, DEVI, MGR, MGR2 = (
    first_sign_in(u) for u in ("dana", "mick", "mona", "devi", "mgr", "mgr2")
)
```

### 5.3 Define a feature and load data into it (Dana)

A feature's definition says what one row is (the `index`), what it holds (`schema`), where
the data comes from, and what quality checks it must pass. `knowledge_time_column` names
the column that says when each value became known: MAYA keeps both clocks, which is what
later lets it prove a model never saw the future.

```python
definition = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "schema": [{"name": "x", "type": "float64"}, {"name": "y", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "kt"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "x"}],
}
call("POST", "/features", DANA, json={"namespace": "demo", "name": "xy", "definition": definition})

rows = ["date,symbol,x,y,kt"]
for i in range(60):
    day = dt.date(2026, 1, 1) + dt.timedelta(days=i)
    for j, symbol in enumerate(("AAA", "BBB", "CCC")):
        x = 1.0 + i * 0.1 + j
        rows.append(f"{day},{symbol},{x:.3f},{2 * x + 0.5:.3f},{day}T18:00:00Z")
csv_bytes = ("\n".join(rows) + "\n").encode()

ingest = call(
    "POST",
    "/features/demo/xy/ingest",
    DANA,
    files={"file": ("xy.csv", csv_bytes, "text/csv")},
    data={"fmt": "csv"},
)
print("rows ingested:", ingest["rows"])  # 180
```

An upload is appended to the feature's ingest log with the moment it arrived; uploading a
correction later adds to the log rather than overwriting it.

### 5.4 Submit and approve (Dana, then Mick)

```python
submitted = call("POST", "/features/demo/xy/versions/1/transitions/submit", DANA, json={})
approved = call(
    "POST",
    "/features/demo/xy/versions/1/transitions/approve",
    MICK,
    json={"rationale": "quality checks pass"},
)
print(submitted["state"], "->", approved["state"])  # in_review -> approved
```

Had Dana tried to approve her own submission, the answer would have been
`403 permission_denied` naming the separation-of-duties rule.

### 5.5 Assemble a feature set and pin it (Devi, then Mick)

A feature set maps feature attributes to the columns a model reads. A **pin** freezes it as
of a date into an immutable table sealed by a content hash; `cascade` pins the member
features in the same step. Pinning is a job.

```python
panel = {
    "index": ["date", "symbol"],
    "grid": "as_is",
    "alignment": {"mode": "inner"},
    "members": [
        {"attr": "x", "ref": "maya://feature/demo/xy@v1", "source_attr": "x"},
        {"attr": "y", "ref": "maya://feature/demo/xy@v1", "source_attr": "y"},
    ],
}
call("POST", "/featuresets", DEVI, json={"namespace": "demo", "name": "panel", "definition": panel})
call("POST", "/featuresets/demo/panel/versions/1/transitions/submit", DEVI, json={})
call(
    "POST", "/featuresets/demo/panel/versions/1/transitions/approve", MICK, json={"rationale": "ok"}
)

pin_request = {"version_no": 1, "pin_name": "q1", "as_of": "2026-02-28", "cascade": True}
accepted = call(
    "POST",
    "/featuresets/demo/panel/pins",
    MICK,
    json=pin_request,
    headers={"Idempotency-Key": "demo-panel-q1"},
)
print(accepted["pin"]["state"], accepted["job"]["state"])  # materializing queued
```

The `Idempotency-Key` makes the request safe to retry. If the answer was lost on the
network, sending the same request with the same key returns the same pin and the same job
instead of creating another, before and after the job has finished:

```python
retry = call(
    "POST",
    "/featuresets/demo/panel/pins",
    MICK,
    json=pin_request,
    headers={"Idempotency-Key": "demo-panel-q1"},
)
assert retry["job"]["id"] == accepted["job"]["id"] and retry["replayed"]
```

Wait for the job, then read the pin back:

```python
def wait_for(job_id, token, timeout=120):
    """Poll a job until it finishes; raise unless it succeeded."""
    deadline = time.monotonic() + timeout
    while True:
        job = call("GET", f"/jobs/{job_id}", token)
        if job["state"] in ("succeeded", "failed", "cancelled", "dead_letter"):
            break
        if time.monotonic() > deadline:
            raise TimeoutError(f"job {job_id} is still {job['state']}")
        time.sleep(0.5)
    if job["state"] != "succeeded":
        raise RuntimeError(f"job {job_id} {job['state']}: {job.get('error')}")
    return job


job = wait_for(accepted["job"]["id"], MICK)
print("sealed with hash", job["result"]["content_hash"][:16], "rows", job["result"]["rows"])

feature_set = call("GET", "/featuresets/demo/panel", MICK)
print([(p["pin_name"], p["as_of_date"], p["state"]) for p in feature_set["pins"]])
```

The content hash is a function of the data alone: pin the same data again anywhere and you
get the same hash, which is how a result can be reproduced years later.

### 5.6 Write the model and its specification (Mona, then the manager)

A model is written as mathematics, `yhat = a*x + b`, with each symbol's role declared. It
cannot be approved without a specification document covering nine required sections: MAYA
checks they are all there.

```python
SECTIONS = (
    "Purpose",
    "Scope and Limitations",
    "Mathematical Formulation",
    "Assumptions",
    "Data and Features Used",
    "Calibration Methodology",
    "Validation Evidence",
    "Known Weaknesses",
    "Change Log",
)
spec = (
    "\\documentclass{article}\n\\begin{document}\n"
    + "".join(
        f"\\section{{{s}}}\nThe {s.lower()} of the linear model, stated in full.\n"
        for s in SECTIONS
    )
    + "\\end{document}\n"
)

call(
    "POST",
    "/models",
    MONA,
    json={
        "namespace": "demo",
        "name": "linear",
        "formula": "yhat = a*x + b",
        "roles": {"a": "parameter", "b": "parameter"},
        "description": "y as a straight line in x",
    },
)
call("PUT", "/models/demo/linear/draft", MONA, json={"spec_latex": spec})
call("POST", "/models/demo/linear/versions/1/transitions/submit", MONA, json={})
model = call(
    "POST",
    "/models/demo/linear/versions/1/transitions/approve",
    MGR,
    json={"rationale": "specification complete"},
)
print("model:", model["state"])  # approved
```

### 5.7 Draw a training warrant (Devi)

A training warrant binds one approved model version to one pinned feature set, and fixes
the train/holdout split. On creation MAYA checks the model's inputs are all there (the
contract report) and that no value in the data was known after the date it describes (the
leakage certificate, signed).

```python
tw = call(
    "POST",
    "/warrants/training",
    DEVI,
    json={
        "namespace": "demo",
        "name": "calibrate-linear",
        "model": "maya://model/demo/linear@v1",
        "featureset": "maya://featureset/demo/panel#q1/2026-02-28",
        "spec": {"target": "y", "seed": 7},
    },
)
print(
    "contract ok:", tw["contract_report"]["ok"], "| leakage:", tw["leakage_certificate"]["status"]
)
```

### 5.8 Download the data, fit, and upload the parameters (Devi)

The download is Parquet: the training split only, the holdout is escrowed and never leaves
MAYA. The `X-Maya-Manifest` header carries a checksum; sending it back with the parameters
proves they were fitted on exactly this data.

```python
import numpy as np
import pandas as pd

download = call("GET", f"/warrants/training/{tw['id']}/data", DEVI)
manifest = json.loads(download.headers["X-Maya-Manifest"])
train = pd.read_parquet(io.BytesIO(download.content))
print(len(train), "training rows; checksum", manifest["checksum"][:16])

a, b = np.polyfit(train["x"], train["y"], 1)  # least squares, on the training split only
residual = a * train["x"] + b - train["y"]
params = call(
    "POST",
    f"/warrants/training/{tw['id']}/parameters",
    DEVI,
    json={
        "values": {"a": float(a), "b": float(b)},
        "metrics": {"rmse": float(np.sqrt(np.mean(residual**2)))},
        "data_checksum": manifest["checksum"],
    },
)
print("verified against the data:", params["verified_data"])  # True
```

### 5.9 Approve the parameters, score blind, seal (Devi and the manager)

Blind scoring evaluates the parameters on the escrowed holdout inside MAYA and returns
metrics only. Every attempt is counted and shown on the warrant, because twenty tries
against a holdout is overfitting by another name.

```python
call("POST", f"/parameters/{params['id']}/transitions/submit", DEVI, json={})
call(
    "POST",
    f"/parameters/{params['id']}/transitions/approve",
    MGR,
    json={"rationale": "fitted on the warrant's data"},
)

score = call(
    "POST", f"/warrants/training/{tw['id']}/score", DEVI, json={"parameter_set_id": params["id"]}
)
print("holdout RMSE:", score["metrics"]["rmse"], "attempt", score["attempt"])

call("POST", f"/warrants/training/{tw['id']}/transitions/submit", DEVI, json={})
call(
    "POST",
    f"/warrants/training/{tw['id']}/transitions/approve",
    MGR,
    json={"rationale": "holdout clean"},
)
sealed = call("POST", f"/warrants/training/{tw['id']}/seal", MGR)
print("training warrant sealed:", sealed["sealed_at"] is not None)
```

### 5.10 License it to run: the execution warrant (the managers)

An execution warrant licenses one set of approved parameters to run, in named
environments, until a date, under covenants that are checked every time a run is reported.
A second manager approves it.

```python
ew = call(
    "POST",
    "/warrants/execution",
    MGR,
    json={
        "namespace": "demo",
        "name": "linear-live",
        "training_warrant_id": tw["id"],
        "parameter_set_id": params["id"],
        "spec": {
            "environments": ["dev"],
            "contact": "model-risk@example.com",
            "valid_days": 90,
            "covenants": [{"kind": "input_null_rate", "attr": "x", "max": 0.05}],
        },
    },
)
call("POST", f"/warrants/execution/{ew['id']}/transitions/submit", MGR, json={})
call(
    "POST",
    f"/warrants/execution/{ew['id']}/transitions/approve",
    MGR2,
    json={"rationale": "second pair of eyes"},
)
call("POST", f"/warrants/execution/{ew['id']}/seal", MGR)
```

### 5.11 Use it in production: fetch, run, report (a service)

A production service asks for the bundle before it scores. MAYA answers only while the
warrant is live, in an environment it covers; the bundle carries the formula and the
approved parameter values.

```python
bundle = call("GET", f"/warrants/execution/{ew['id']}/bundle", DEVI, params={"environment": "dev"})
print(bundle["status"], bundle["attestation"])  # live attested

p = bundle["parameters"]
todays_x = [1.5, 2.0, 2.5]
predictions = [p["a"] * x + p["b"] for x in todays_x]  # yhat = a*x + b
print("predictions:", [round(v, 6) for v in predictions])  # [3.5, 4.5, 5.5]

report = call(
    "POST",
    f"/warrants/execution/{ew['id']}/report",
    DEVI,
    json={
        "environment": "dev",
        "rows": len(todays_x),
        "input_stats": {"x": {"null_rate": 0.0, "mean": 2.0, "min": 1.5, "max": 2.5}},
        "output_stats": {"yhat": {"mean": sum(predictions) / len(predictions)}},
    },
)
print("after the report:", report["status"], report["breaches"])  # live []
```

A report that breaks a covenant suspends the warrant on the spot, and every later call for
the bundle **fails closed**, naming the person to contact:

```python
bad = call(
    "POST",
    f"/warrants/execution/{ew['id']}/report",
    DEVI,
    json={"environment": "dev", "rows": 100, "input_stats": {"x": {"null_rate": 0.3}}},
)
print(bad["status"], [b["detail"] for b in bad["breaches"]])  # suspended

try:
    call("GET", f"/warrants/execution/{ew['id']}/bundle", DEVI, params={"environment": "dev"})
except MayaError as refused:
    print(refused.status, refused.problem["type"])  # 423 warrant_suspended
    print(refused.problem["detail"])

# Only an explicit, audited decision lifts a suspension.
call(
    "POST",
    f"/warrants/execution/{ew['id']}/reinstate",
    ADMIN,
    json={"reason": "vendor file was late"},
)
```

### 5.12 Governance: findings, tiering, inventory, monitoring

```python
finding = call(
    "POST",
    "/governance/findings",
    MGR,
    json={"model": "demo/linear", "title": "No challenger model", "severity": "medium"},
)
print("finding owned by", finding["owner"], "due", finding["due_date"])

call(
    "PUT",
    "/governance/models/demo/linear",
    MONA,
    json={"use": "business_decision", "exposure": 25000000},
)
profile = call("GET", "/governance/models/demo/linear", MGR)
print("tier", profile["tier"], "- next review due", profile["next_review_due"])

inventory = call(
    "GET", "/governance/inventory", MGR, params={"format": "csv", "framework": "ss1-23"}
)
print(inventory.text.splitlines()[2][:60])  # the header row of the SS1/23 layout

print("monitoring:", call("GET", "/monitoring", MGR)["counts"])
```

That is the complete chain. Everything above is also visible in the web UI, with the audit
trail, the lineage graph and the custody chain of each warrant.

## 6. The same things with curl

Any step above is a plain HTTP request. These run against the estate section 5 built.

Upload a file (multipart) to a new feature, as Dana would. `-F file=@…` sends the file,
`-F fmt=csv` the form field:

```bash
MAYA_URL=${MAYA_URL:-http://127.0.0.1:8600}
TOKEN=$(curl -s -X POST "$MAYA_URL/api/v1/auth/login" -H "Content-Type: application/json" \
  -d '{"username": "dana", "password": "Guide-Pass-2026-changed!"}' | jq -r .token)

curl -s -X POST "$MAYA_URL/api/v1/features" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d @- <<'JSON' | jq '{name, status}'
{"namespace": "demo", "name": "prices",
 "definition": {"index": ["date", "symbol"], "index_types": {"date": "date", "symbol": "string"},
                "schema": [{"name": "close", "type": "float64"}], "source": {"type": "csv"},
                "resolution": {"grid": "as_is", "rules": {}}, "transform": [], "quality": []}}
JSON

printf 'date,symbol,close\n2026-01-02,AAA,101.5\n2026-01-02,BBB,99.0\n' > /tmp/maya-prices.csv
curl -s -X POST "$MAYA_URL/api/v1/features/demo/prices/ingest" -H "Authorization: Bearer $TOKEN" \
  -F file=@/tmp/maya-prices.csv -F fmt=csv | jq '{rows, knowledge_time}'
```

List features one page at a time, and read one feature:

```bash
MAYA_URL=${MAYA_URL:-http://127.0.0.1:8600}
TOKEN=$(curl -s -X POST "$MAYA_URL/api/v1/auth/login" -H "Content-Type: application/json" \
  -d '{"username": "dana", "password": "Guide-Pass-2026-changed!"}' | jq -r .token)
curl -s "$MAYA_URL/api/v1/features?namespace=demo&page_size=1&total=true" \
  -H "Authorization: Bearer $TOKEN" | jq '{total, next_cursor, first: .items[0].name}'
curl -s "$MAYA_URL/api/v1/features/demo/xy" -H "Authorization: Bearer $TOKEN" | jq '{name, status}'
```

Check a warrant from a production job before scoring — a non-200 answer means *do not run*:

```bash
MAYA_URL=${MAYA_URL:-http://127.0.0.1:8600}
TOKEN=$(curl -s -X POST "$MAYA_URL/api/v1/auth/login" -H "Content-Type: application/json" \
  -d '{"username": "devi", "password": "Guide-Pass-2026-changed!"}' | jq -r .token)
EW=$(curl -s "$MAYA_URL/api/v1/warrants/execution" -H "Authorization: Bearer $TOKEN" \
  | jq -r '.[] | select(.name == "linear-live") | .id')
STATUS=$(curl -s -o /tmp/maya-bundle.json -w "%{http_code}" \
  "$MAYA_URL/api/v1/warrants/execution/$EW/bundle?environment=dev" -H "Authorization: Bearer $TOKEN")
if [ "$STATUS" = "200" ]; then jq '{status, parameters}' /tmp/maya-bundle.json; else echo "do not run: $STATUS"; fi
```

Export the model inventory as Excel:

```bash
MAYA_URL=${MAYA_URL:-http://127.0.0.1:8600}
TOKEN=$(curl -s -X POST "$MAYA_URL/api/v1/auth/login" -H "Content-Type: application/json" \
  -d '{"username": "mgr", "password": "Guide-Pass-2026-changed!"}' | jq -r .token)
curl -s -o /tmp/maya-inventory.xlsx \
  "$MAYA_URL/api/v1/governance/inventory?format=xlsx&framework=sr11-7" -H "Authorization: Bearer $TOKEN"
head -c 2 /tmp/maya-inventory.xlsx; echo "  <- an .xlsx file starts with PK (it is a zip)"
```

## 7. Conventions every client needs

### 7.1 API keys for programs

A person signs in; a program should use an **API key**. A key is created by a signed-in
user, is shown once, and can only be narrower than its owner: fewer roles, some namespaces,
some actions, some networks, an expiry.

```python
key = call(
    "POST",
    "/auth/api-keys",
    DEVI,
    json={"name": "nightly-report", "namespaces": ["demo"], "actions": ["read"], "days": 30},
)
API_KEY = key["api_key"]  # shown once: store it in your secret manager now
print("a key for", call("GET", "/auth/me", API_KEY)["username"])

try:  # the key may read, and nothing else
    call(
        "POST",
        "/featuresets",
        API_KEY,
        json={"namespace": "demo", "name": "x2", "definition": panel},
    )
except MayaError as e:
    print("refused:", e.status, e.problem["type"])  # 403 permission_denied
```

Keys are revoked with `DELETE /auth/api-keys/{key_id}`. A key is valid in one
environment only: a `dev` key is refused by a `prod` MAYA.

### 7.2 Paging

List endpoints accept `page_size` and return a page with a `next_cursor`; pass it back as
`cursor` for the next page, until it is `null`. `total=true` adds a count (it costs a
query). `sort` names the order where an endpoint offers several.

```python
def every(path, token, **params):
    """Every item of a paged listing, following next_cursor."""
    cursor = None
    while True:
        page = call("GET", path, token, params={**params, "page_size": 100, "cursor": cursor})
        yield from page["items"]
        cursor = page["next_cursor"]
        if not cursor:
            return


print([f["name"] for f in every("/features", DANA, namespace="demo")])
```

### 7.3 Conditional reads: ETag and If-None-Match

Reads carry an `ETag`. Send it back as `If-None-Match` and MAYA answers `304 Not Modified`
with no body when nothing changed, so polling costs a round trip, not a payload.

```python
auth = {"Authorization": f"Bearer {DANA}"}
first = httpx.get(API + "/features/demo/xy", headers=auth)
again = httpx.get(
    API + "/features/demo/xy", headers={**auth, "If-None-Match": first.headers["ETag"]}
)
print(first.status_code, again.status_code)  # 200 304
```

### 7.4 Guarded writes: If-Match

To make sure you are not overwriting somebody else's edit, send the `ETag` you read as
`If-Match` on the write. If the object changed in between, the write is refused with
`409 conflict` and you re-read before trying again.

```python
call(
    "POST",
    "/models",
    MONA,
    json={
        "namespace": "demo",
        "name": "draft_demo",
        "formula": "y = c*x",
        "roles": {"c": "parameter"},
    },
)
auth = {"Authorization": f"Bearer {MONA}"}
tag = httpx.get(API + "/models/demo/draft_demo", headers=auth).headers["ETag"]

call(
    "PUT",
    "/models/demo/draft_demo/draft",
    MONA,
    json={"description": "first edit"},
    headers={"If-Match": tag},
)
try:  # the same, stale, ETag again: somebody (we) changed it since
    call(
        "PUT",
        "/models/demo/draft_demo/draft",
        MONA,
        json={"description": "second"},
        headers={"If-Match": tag},
    )
except MayaError as e:
    print("refused:", e.status, e.problem["type"])  # 409 conflict
```

### 7.5 Idempotency

Any request that starts a job (pins, cascades, artifact validation) accepts an
`Idempotency-Key` header. Retrying with the same key returns the original job — and, for a
pin, the original pin — however many times the request arrives; a *different* key asking
for the same pin is a genuine `409 conflict`. Use a key that names the intent, such as
`nightly-pin-2026-02-28`, not a random one per attempt, or a retry is not recognised as one.

### 7.6 Jobs

`GET /jobs/{id}` returns `state` (`queued`, `running`, `succeeded`, `failed`, `cancelled`,
`dead_letter`), `progress` (0–100), `message`, `result` when done and `error` when not.
`POST /jobs/{id}/cancel` asks a running job to stop; `POST /jobs/{id}/retry` re-runs a failed
one. `GET /jobs` lists yours. A server-sent event stream of progress is at
`/jobs/{id}/events` for clients that prefer pushing to polling.

### 7.7 Dates and times

Dates are ISO 8601 (`2026-02-28`). Times are ISO 8601 in UTC with an offset
(`2026-09-26T21:19:58.020153+00:00`). An `as_of` is a date in the data's own calendar; an
`as_of_known` is a moment in time and defaults to now: together they answer *what did we
know about that day, at that moment*.

### 7.8 Limits

Each MAYA process allows, by default, 6,000 requests per minute per caller with bursts of
1,200, 128 requests in flight, a 256 MiB request body and a 120-second request. Past them
you get `429` (rate), `503` with `Retry-After` (too busy), `413` (too large) or `504` (too
slow). The `api.limits.*` settings change them. Back off and retry on `429` and `503`;
never retry `4xx` otherwise without changing the request.

### 7.9 Second factor and single sign-on

When the login answer says `"mfa": "challenge"`, finish with `POST /auth/mfa/verify` and
`{"code": "<six digits>"}` using the same token; until then that session can only reach the
MFA endpoints and `/auth/me`. Where MAYA is configured for single sign-on (`auth.mode:
sso`), people sign in through the browser and programs use API keys; password login is
refused.

## 8. Errors, and what to do about each

Every failure is a problem document:

```python
try:
    call("GET", "/features/demo/does_not_exist", DANA)
except MayaError as e:
    print(json.dumps(e.problem, indent=2))
```

```text
{
  "type": "not_found",
  "title": "NotFound",
  "status": 404,
  "detail": "feature 'demo/does_not_exist' does not exist",
  "context": {"ref": "maya://feature/demo/does_not_exist"}
}
```

Branch on `type`, show `detail` to a person, and read `context` for the specifics.

| Status | `type` | Means | Do |
|---|---|---|---|
| 400 | `maya_error` | A request MAYA could not act on, for a reason `detail` gives | Fix the request |
| 400 | `invalid_cursor` | A paging cursor that is stale or not MAYA's | Start the listing again without a cursor |
| 401 | `not_authenticated` | No credential, or it expired | Sign in again, or check the key |
| 403 | `permission_denied` | You may not do this: a role, a grant, a key's scope, separation of duties | Ask for access, or have someone else act; `detail` says which rule |
| 404 | `not_found` | No such object, or you may not see it | Check the name; `context.ref` shows what was looked up |
| 409 | `conflict` | It already exists, or it changed since you read it | Re-read and decide |
| 409 | `not_approved` | The object is not in a state that allows this | Take the missing transition first; `detail` names it |
| 410 | `warrant_expired` | The warrant's validity ended | Draw a new execution warrant |
| 413 | `payload_too_large` | The body is over `api.limits.max_body_bytes` | Send less, or raise the limit |
| 422 | `validation_failed` | A field is missing or wrong | Fix the fields `detail` lists |
| 422 | `contract_mismatch` | The data does not supply what the model needs | `detail` names every missing input |
| 422 | `quality_check_failed` | The data failed one of the feature's quality checks | `detail` names the check and the rows |
| 423 | `warrant_suspended` | A covenant breach or an overdue review suspended it | Do not run; contact the person named in `detail` |
| 429 | `rate_limited` | Too many requests from this caller | Wait `Retry-After` seconds, then retry |
| 429 | `quota_exceeded` | The namespace's storage quota is full | Free space or ask for a larger quota |
| 451 | `licence_breach` | A data licence forbids this use or export | `detail` names the licence and who imposed it |
| 500 | `integrity_error`, `configuration_error` | Something MAYA itself found wrong | Report it; `detail` says what |
| 503 | `overloaded` | The process is at its concurrency limit | Retry after `Retry-After` |
| 503 | `capability_refused` | An optional component this needs is not installed or configured | `detail` names it |
| 504 | `request_timeout` | The request ran past `api.limits.timeout_seconds` | Retry; committed work is not undone |

The SDK raises one Python exception class per `type` (`maya.core.errors`), so SDK and raw
HTTP clients see the same distinctions.

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 not_authenticated` on every call | Missing `Bearer ` prefix, or an expired session (30 minutes idle, 12 hours at most) | Sign in again; use an API key for long-running programs |
| `403 permission_denied` on an approve | You submitted it yourself | A different person with the approving role must approve |
| `409 not_approved` creating a warrant | The model version or feature set is still a draft or in review | Approve it first, then pin the feature set |
| `422 contract_mismatch` creating a training warrant | The feature set lacks a column the model reads | Add the member, or bind the model input to an existing column in `spec.bindings` |
| A pin job `failed` | A quality check failed on the data as of that date | `GET /jobs/{id}` → `error` says which check and how many rows |
| `423 warrant_suspended` | A reported run breached a covenant, or the model's periodic review is overdue | See `detail`; an administrator or the model owner reinstates with a reason |
| `405 Method Not Allowed` with an empty `type` | The path exists but not for that method | Check the appendix below; this one comes from the web framework, not MAYA |
| Connection refused | MAYA not running, or a different port | `curl $MAYA_URL/healthz`; the port is `server.port` (8600 by default) |

## 10. Appendix: every endpoint

Kept by hand and checked against the OpenAPI document: `tests/test_api_guide.py` fails if an endpoint is
added without appearing here. Paths are relative to `/api/v1`.

### auth

| Method | Path | What it does |
|---|---|---|
| `GET` | `/auth/api-keys` | List Keys |
| `POST` | `/auth/api-keys` | Create Key |
| `GET` | `/auth/api-keys/report` | Keys to rotate or revoke, each with its reason. |
| `DELETE` | `/auth/api-keys/{key_id}` | Revoke Key |
| `POST` | `/auth/api-keys/{key_id}/rotate` | Issue a successor, keep both working for the overlap window, retire this one. |
| `GET` | `/auth/client-credentials` | Client Credentials |
| `POST` | `/auth/client-credentials` | A client credential for a service account: the secret is shown once. |
| `POST` | `/auth/login` | Login |
| `POST` | `/auth/logout` | End this session. After a SAML sign-in with single logout configured, |
| `GET` | `/auth/me` | Whoami |
| `GET` | `/auth/mfa` | Mfa Status |
| `POST` | `/auth/mfa/confirm` | Mfa Confirm |
| `POST` | `/auth/mfa/enroll` | Mfa Enroll |
| `POST` | `/auth/mfa/verify` | Mfa Verify |
| `GET` | `/auth/mfa/webauthn` | Webauthn Keys |
| `POST` | `/auth/mfa/webauthn/options` | Webauthn Options |
| `POST` | `/auth/mfa/webauthn/register` | Webauthn Register |
| `POST` | `/auth/mfa/webauthn/register/options` | Webauthn Register Options |
| `POST` | `/auth/mfa/webauthn/verify` | Webauthn Verify |
| `DELETE` | `/auth/mfa/webauthn/{key_id}` | Webauthn Remove |
| `POST` | `/auth/password` | Change Password |
| `POST` | `/auth/password-reset` | Ask for a password reset. The answer is the same whether or not the account |
| `POST` | `/auth/password-reset/complete` | Redeem a reset token: once, before it expires, and never again. |
| `POST` | `/auth/password-reset/token` | Issue the token, shown once, for an administrator to hand over out of band. |
| `GET` | `/auth/sessions` | Sessions |
| `DELETE` | `/auth/sessions/{session_id}` | End Session |
| `POST` | `/auth/sso/callback` | Sso Callback |
| `GET` | `/auth/sso/config` | Public: which sign-in methods this deployment offers. |
| `POST` | `/auth/sso/oidc/backchannel-logout` | Public, server to server: the IdP POSTs a signed logout token (form field |
| `POST` | `/auth/sso/saml/acs` | Public: validate the IdP's posted Response and open a session. |
| `GET` | `/auth/sso/saml/metadata` | Public: MAYA's service-provider metadata, for registering MAYA at the IdP. |
| `POST` | `/auth/sso/saml/sls` | Public: single logout — the IdP's LogoutResponse to MAYA, or its signed |
| `POST` | `/auth/sso/saml/start` | Public: the IdP URL carrying a fresh AuthnRequest, recorded server-side. |
| `POST` | `/auth/sso/start` | Public: state, nonce and PKCE verifier for the caller to keep, and the IdP URL. |
| `POST` | `/auth/token` | The OAuth2 client-credentials grant (RFC 6749 §4.4), form encoded as that |

### access

| Method | Path | What it does |
|---|---|---|
| `GET` | `/access/recertification` | Recertification |
| `GET` | `/grants` | Grants |
| `POST` | `/grants` | Grant |
| `DELETE` | `/grants/{grant_id}` | Revoke Grant |
| `GET` | `/namespaces` | Namespaces |
| `POST` | `/namespaces` | Create Namespace |
| `PATCH` | `/namespaces/{name}` | Update Namespace |
| `POST` | `/namespaces/{name}/purge` | Remove a namespace and everything in it, rows and lake data. Development environments only, administrators only, and `confirm` must repeat the name. The purge is audited. |

### admin

| Method | Path | What it does |
|---|---|---|
| `GET` | `/groups` | Groups |
| `POST` | `/groups` | Create Group |
| `GET` | `/roles` | Roles |
| `POST` | `/roles` | Create Role |
| `GET` | `/users` | Users |
| `POST` | `/users` | Create User |
| `PATCH` | `/users/{username}` | Update User |
| `POST` | `/users/{username}/mfa-reset` | Mfa Reset |
| `POST` | `/users/{username}/password-reset` | Reset Password |
| `PUT` | `/users/{username}/roles` | Set Roles |

### assistant

| Method | Path | What it does |
|---|---|---|
| `POST` | `/assistant/drafts/feature` | A proposed feature definition from a description and a sample file (§29.8). Nothing |
| `GET` | `/assistant/drafts/spec` | Drafts for the specification sections nobody has written yet (§29.8). |
| `GET` | `/assistant/memos` | Memos |
| `POST` | `/assistant/memos` | Request Memo |
| `POST` | `/assistant/memos/{memo_id}/stance` | Respond |

### audit

| Method | Path | What it does |
|---|---|---|
| `GET` | `/audit` | Audit |
| `GET` | `/audit/verify` | Audit Verify |

### catalog

| Method | Path | What it does |
|---|---|---|
| `GET` | `/catalog/browse` | The catalog you may read, narrowed by the §16.2 facets: type, namespace, owner, |
| `GET` | `/catalog/dependents` | What would break: every dependent object downstream of ``ref``, and who owns it. |
| `GET` | `/catalog/facets` | What each facet can be set to, for this object type. |
| `GET` | `/catalog/nodes` | What is known about each of ``refs`` (comma separated), in one call: type, owner, |
| `GET` | `/search` | Search |
| `DELETE` | `/subscriptions` | Unsubscribe |
| `GET` | `/subscriptions` | Subscriptions |
| `POST` | `/subscriptions` | Subscribe |

### custody

| Method | Path | What it does |
|---|---|---|
| `POST` | `/custody/anchor` | Anchor |
| `GET` | `/custody/anchors` | Anchors |
| `GET` | `/custody/verify` | Verify |
| `GET` | `/licences` | The effective licence of a feature or feature set, and who imposed each term. |

### events

| Method | Path | What it does |
|---|---|---|
| `GET` | `/events` | Events after a sequence number; ``type`` is a prefix (``pin.`` for every pin event). |
| `GET` | `/events/stream` | Server-sent events from ``after`` onward; reconnect with the last id seen. |
| `GET` | `/webhooks` | Webhooks |
| `POST` | `/webhooks` | Create Webhook |
| `DELETE` | `/webhooks/{webhook_id}` | Delete Webhook |
| `GET` | `/webhooks/{webhook_id}/deliveries` | Deliveries |
| `POST` | `/webhooks/{webhook_id}/ping` | Ping |

### features

| Method | Path | What it does |
|---|---|---|
| `GET` | `/feature-data` | A feature version's or pin's rows. Resumable: send ``Range`` with the ``If-Range`` |
| `GET` | `/feature-data/preview` | Feature Preview |
| `GET` | `/features` | The features you may read. Opt-in cursor paging: pass ``page_size`` or ``cursor``. |
| `POST` | `/features` | Create Feature |
| `POST` | `/features/infer` | Infer Schema |
| `POST` | `/features/quick` | Quick Feature |
| `GET` | `/features/{namespace}/{name}` | The feature's definition and history. Its ``ETag`` is what a draft edit sends back |
| `POST` | `/features/{namespace}/{name}/clone` | Clone Feature |
| `GET` | `/features/{namespace}/{name}/compare` | Compare Feature |
| `PUT` | `/features/{namespace}/{name}/draft` | Update Feature Draft |
| `POST` | `/features/{namespace}/{name}/draft-preview` | Feature Draft Preview |
| `POST` | `/features/{namespace}/{name}/drafts` | New Feature Draft |
| `POST` | `/features/{namespace}/{name}/ingest` | Ingest Feature |
| `POST` | `/features/{namespace}/{name}/pin-preview` | What a pin would produce before the button becomes active (§16.4): rows, the fill |
| `GET` | `/features/{namespace}/{name}/pins` | A feature's pins, paged; sort is -as_of (default), as_of, series, -series. |
| `POST` | `/features/{namespace}/{name}/pins` | Pin Feature |
| `POST` | `/features/{namespace}/{name}/pull` | Snapshot an sql-sourced feature's reviewed query into its ingest log. |
| `POST` | `/features/{namespace}/{name}/versions/{version_no}/transitions/{transition}` | Feature Transition |
| `POST` | `/pins/{pin_id}/approve` | Approve Pin |
| `POST` | `/pins/{pin_id}/retire` | Retire Pin |

### featuresets

| Method | Path | What it does |
|---|---|---|
| `GET` | `/featureset-data` | A feature set version's or pin's rows, in the shape asked for. Resumable, as |
| `GET` | `/featureset-data/preview` | Featureset Preview |
| `GET` | `/featuresets` | List Featuresets |
| `POST` | `/featuresets` | Create Featureset |
| `GET` | `/featuresets/{namespace}/{name}` | Get Featureset |
| `GET` | `/featuresets/{namespace}/{name}/diff` | Two versions of a feature set, member by member and policy by policy (§6.7). |
| `PUT` | `/featuresets/{namespace}/{name}/draft` | Update Featureset Draft |
| `POST` | `/featuresets/{namespace}/{name}/draft-preview` | Featureset Draft Preview |
| `POST` | `/featuresets/{namespace}/{name}/drafts` | New Featureset Draft |
| `POST` | `/featuresets/{namespace}/{name}/fork` | A new feature set starting from this one's definition (§6.7). Not an `extends`: a |
| `POST` | `/featuresets/{namespace}/{name}/pins` | Pin Featureset |
| `POST` | `/featuresets/{namespace}/{name}/versions/{version_no}/transitions/{transition}` | Featureset Transition |

### governance

| Method | Path | What it does |
|---|---|---|
| `GET` | `/challenges` | Challenges |
| `POST` | `/challenges` | Score a champion and a challenger on their shared escrowed holdout and compare them. |
| `GET` | `/challenges/{challenge_id}` | Challenge |
| `POST` | `/challenges/{challenge_id}/decision` | Decide Challenge |
| `GET` | `/governance` | Every model the caller may read, with its tier, next review and open findings. |
| `GET` | `/governance/findings` | The register. ``state=active`` is everything not yet closed or accepted. |
| `POST` | `/governance/findings` | Raise Finding |
| `GET` | `/governance/findings/{finding_id}` | Finding |
| `POST` | `/governance/findings/{finding_id}/move` | Move Finding |
| `GET` | `/governance/inventory` | The model inventory as a file, in an SR 11-7 or SS1/23 aligned layout (or MAYA's own |
| `GET` | `/governance/models/{namespace}/{name}` | Tier and its drivers, review schedule, findings and review history for one model. |
| `PUT` | `/governance/models/{namespace}/{name}` | Set Profile |
| `POST` | `/governance/models/{namespace}/{name}/reviews` | Record Review |
| `POST` | `/governance/sweep` | Suspend the live warrants of every model whose periodic review is overdue. |
| `GET` | `/monitoring` | Every sealed execution warrant the caller may read, graded ok, watch or breach. |
| `GET` | `/monitoring/warrants/{ew_id}` | One warrant's reported executions read as series: volume, null rates, ranges, PSI. |
| `GET` | `/warrants/training/{warrant_id}/evidence` | Fairness and explainability evidence computed on this warrant's holdout. |
| `POST` | `/warrants/training/{warrant_id}/dispatch` | A job definition for your own compute (Kubernetes, SageMaker), a signed manifest and a one-day key. MAYA runs nothing. |
| `POST` | `/warrants/training/{warrant_id}/evidence` | Segment metrics and permutation importance on the holdout; counts as one attempt. |
| `POST` | `/warrants/training/{warrant_id}/refit` | MAYA's own least-squares fit on the training split, compared with a parameter set. |
| `GET` | `/ai/status` | Every model profile — where it came from, where it points, whether it looks usable — which one is the default and who chose it, and every provider on offer. Nothing is called. |
| `POST` | `/ai/default` | Make a profile the default, at once and for every process; null returns the choice to the configuration. Administrators only; audited. |
| `POST` | `/ai/profiles/{name}/test` | Ask the profile's model one short question: the reply, the time, the tokens, or why not. Administrators only. |
| `PUT` | `/ai/profiles/{name}` | Create or replace a profile: provider, model, max_tokens, temperature, options, description. Options name a key's environment variable; they never hold a key. Administrators only; audited. |
| `DELETE` | `/ai/profiles/{name}` | Remove a profile saved from the UI; one from the profiles file is edited there. Administrators only; audited. |
| `GET` | `/documents/templates` | The document templates on offer: the built-ins, and the firm's own in documents.template_dir, which replace a built-in of the same name. |
| `POST` | `/models/{namespace}/{name}/documents` | Generate a model card, validation report or model documentation from the model's record, as a job. Sections the template drafts with a language model are labelled as drafted. |
| `GET` | `/models/{namespace}/{name}/documents` | The documents generated for a model. |
| `GET` | `/documents/{doc_id}` | One document, with its template, facts hash, provider and model, and its text with drafted sections labelled. |
| `GET` | `/documents/{doc_id}/render` | The document as Markdown, HTML or PDF, with each drafted section labelled. |
| `DELETE` | `/documents/{doc_id}` | Delete a draft document (an approved one is part of the record and stays). |
| `POST` | `/documents/{doc_id}/approve` | Approve a document, drafted sections and all: someone other than whoever generated it. |
| `POST` | `/warrants/execution/{ew_id}/batches` | Score a pin under a live execution warrant, as a job: output sealed by hash, the run reported and covenants evaluated, the custody chain updated. |
| `GET` | `/warrants/execution/{ew_id}/batches` | The batches scored under an execution warrant. |
| `GET` | `/warrants/execution/{ew_id}/batches/{job_id}/output` | The batch's output as Parquet; its content hash is in X-Maya-Content-Hash. |

### inbox

| Method | Path | What it does |
|---|---|---|
| `GET` | `/inbox` | Inbox |
| `POST` | `/inbox/read` | Mark Read |

### integrations

| Method | Path | What it does |
|---|---|---|
| `POST` | `/integrations/mlflow/fetch` | The same, fetching the registered version's MLmodel from the configured server. |
| `POST` | `/integrations/mlflow/import` | Register a black-box draft from an MLflow ``MLmodel`` file; its signature is the |
| `POST` | `/integrations/mlflow/sync` | Point the live alias at MLflow versions with a live warrant, and remove it elsewhere (administrators; also runs every five minutes on its own). |
| `POST` | `/integrations/openlineage/emit` | Post the events to the configured OpenLineage endpoint (administrators). |
| `GET` | `/integrations/openlineage/events` | MAYA's lineage as OpenLineage RunEvents (administrators). |
| `POST` | `/integrations/sagemaker/import` | Register a black-box draft from a SageMaker ``DescribeModelPackage`` document. |

### jobs

| Method | Path | What it does |
|---|---|---|
| `GET` | `/jobs` | Jobs |
| `GET` | `/jobs/{job_id}` | Job |
| `POST` | `/jobs/{job_id}/cancel` | Cancel Job |
| `GET` | `/jobs/{job_id}/events` | Server-sent events of a job's progress until it reaches a terminal state. |
| `POST` | `/jobs/{job_id}/retry` | Retry Job |

### lineage

| Method | Path | What it does |
|---|---|---|
| `GET` | `/lineage` | Lineage |

### llm

| Method | Path | What it does |
|---|---|---|
| `GET` | `/llm/apps` | Apps |
| `POST` | `/llm/apps` | Create App |
| `GET` | `/llm/apps/{namespace}/{name}` | The application with its versions, evaluation sets and runs. |
| `PUT` | `/llm/apps/{namespace}/{name}/draft` | Edit the draft version, or open a new one when the latest is no longer a draft. |
| `PUT` | `/llm/apps/{namespace}/{name}/eval-sets` | Save Eval Set |
| `POST` | `/llm/apps/{namespace}/{name}/versions/{version_no}/decision` | Decide |
| `POST` | `/llm/apps/{namespace}/{name}/versions/{version_no}/runs` | Score a version: ``responses`` for a recorded run, none for a live one. |
| `POST` | `/llm/apps/{namespace}/{name}/versions/{version_no}/submit` | Submit |

### models

| Method | Path | What it does |
|---|---|---|
| `POST` | `/formula/kernel` | Translate written mathematics into the formula IR and a one-function kernel. |
| `GET` | `/models` | List Models |
| `POST` | `/models` | Create Model |
| `POST` | `/models/workbook/lift` | Preview the formula IR an Excel workbook lifts to (§29.9). Nothing is stored. |
| `GET` | `/models/{namespace}/{name}` | Get Model |
| `POST` | `/models/{namespace}/{name}/artifact` | Upload Artifact |
| `GET` | `/models/{namespace}/{name}/diff` | Model Diff |
| `PUT` | `/models/{namespace}/{name}/draft` | Update Model Draft |
| `POST` | `/models/{namespace}/{name}/drafts` | New Model Draft |
| `POST` | `/models/{namespace}/{name}/versions/{version_no}/conformance` | Conformance |
| `GET` | `/models/{namespace}/{name}/versions/{version_no}/reference` | Reference Code |
| `POST` | `/models/{namespace}/{name}/versions/{version_no}/render` | Render Spec |
| `GET` | `/models/{namespace}/{name}/versions/{version_no}/spec.pdf` | Spec Pdf |
| `POST` | `/models/{namespace}/{name}/versions/{version_no}/transitions/{transition}` | Model Transition |
| `GET` | `/models/{namespace}/{name}/versions/{version_no}/workbook.xlsx` | Workbook |
| `POST` | `/models/{namespace}/{name}/workbook` | Lift a workbook into the model's editable draft, keeping the workbook itself. |

### ops

| Method | Path | What it does |
|---|---|---|
| `GET` | `/blobs/{digest}` | A blob this principal exported or uploaded (bundles, estates); audited. |
| `POST` | `/search/reindex` | Reindex Search |
| `GET` | `/system/cold-pins` | Cold Pins |
| `GET` | `/system/config` | System Config |
| `GET` | `/system/estate` | Estate |
| `GET` | `/system/extensions` | §25's extension points, what is registered at each, and which notification channels |
| `POST` | `/system/fragments/collect` | Remove fragments no pin references (§29.3). A dry run by default: an operator should |
| `GET` | `/system/health` | System Health |
| `POST` | `/system/integrity` | Integrity |
| `POST` | `/system/lake/maintain` | Lake Maintain |
| `PUT` | `/system/log-level` | Set Log Level |
| `GET` | `/system/pins/{pin_id}/archive` | The archive's manifest, and whether its rows still hash to the sealed pin. The rows |
| `POST` | `/system/pins/{pin_id}/archive` | Archive Pin |
| `GET` | `/system/restore-drills` | Restore Drills |
| `POST` | `/system/restore-drills` | Record Restore Drill |
| `GET` | `/system/storage` | Storage |

### sources

| Method | Path | What it does |
|---|---|---|
| `GET` | `/sql-connections` | Connections |
| `POST` | `/sql-connections` | Create Connection |
| `DELETE` | `/sql-connections/{name}` | Delete Connection |
| `POST` | `/sql-connections/{name}/test` | Test Connection |

### warrants

| Method | Path | What it does |
|---|---|---|
| `POST` | `/bundles/verify` | Verify Bundle |
| `POST` | `/parameters/{parameter_set_id}/transitions/{transition}` | Parameter Transition |
| `POST` | `/restatements/{impact_id}/acknowledge` | Say what was done about a restatement: refitted, or why it does not matter. |
| `GET` | `/warrants/execution` | List Execution |
| `POST` | `/warrants/execution` | Create Execution |
| `GET` | `/warrants/execution/{ew_id}` | Get Execution |
| `GET` | `/warrants/execution/{ew_id}/bundle` | What the SDK needs to run the warrant. ``offline=true``: a copy to run without |
| `GET` | `/warrants/execution/{ew_id}/manifest.pdf` | §9.2's human-readable execution manifest: what can be run, on what inputs, by whom, |
| `POST` | `/warrants/execution/{ew_id}/reinstate` | Reinstate Execution |
| `POST` | `/warrants/execution/{ew_id}/report` | Execution Report |
| `GET` | `/warrants/execution/{ew_id}/restatements` | What corrections to the data under this warrant's training pin changed, newest first. |
| `POST` | `/warrants/execution/{ew_id}/restatements/check` | Queue a check of the training pin against what is known now. |
| `POST` | `/warrants/execution/{ew_id}/revoke` | Revoke Execution |
| `POST` | `/warrants/execution/{ew_id}/seal` | Seal Execution |
| `POST` | `/warrants/execution/{ew_id}/token` | Execution Token |
| `POST` | `/warrants/execution/{ew_id}/transitions/{transition}` | Execution Transition |
| `GET` | `/warrants/training` | List Training |
| `POST` | `/warrants/training` | Create Training |
| `GET` | `/warrants/training/{warrant_id}` | Get Training |
| `POST` | `/warrants/training/{warrant_id}/bundle` | Export Bundle |
| `POST` | `/warrants/training/{warrant_id}/clone` | Clone Training |
| `GET` | `/warrants/training/{warrant_id}/data` | Training Data |
| `POST` | `/warrants/training/{warrant_id}/parameters` | Upload Parameters |
| `POST` | `/warrants/training/{warrant_id}/revoke` | Revoke Training |
| `POST` | `/warrants/training/{warrant_id}/score` | Score Holdout |
| `POST` | `/warrants/training/{warrant_id}/seal` | Seal Training |
| `POST` | `/warrants/training/{warrant_id}/transitions/{transition}` | Training Transition |

### workflow

| Method | Path | What it does |
|---|---|---|
| `GET` | `/workflow/access-check` | Whether you may take ``action``, and in the words of the rule that decided — what |
| `GET` | `/workflow/access-requests` | Access Requests |
| `POST` | `/workflow/access-requests` | Request Access |
| `POST` | `/workflow/access-requests/{request_id}/decide` | Decide Access Request |
| `POST` | `/workflow/access-requests/{request_id}/withdraw` | Withdraw Access Request |
| `GET` | `/workflow/aging` | Aging |
| `GET` | `/workflow/break-glass` | Break Glass |
| `GET` | `/workflow/campaigns` | Campaigns |
| `POST` | `/workflow/campaigns` | Run Campaign |
| `GET` | `/workflow/comments` | Comments |
| `POST` | `/workflow/comments` | Add Comment |
| `POST` | `/workflow/comments/{comment_id}/resolve` | Resolve Comment |
| `GET` | `/workflow/delegations` | Delegations |
| `POST` | `/workflow/delegations` | Delegate |
| `DELETE` | `/workflow/delegations/{delegation_id}` | Revoke Delegation |
| `GET` | `/workflow/history` | History |
| `GET` | `/workflow/policies` | Policies |
| `POST` | `/workflow/policies` | Draft Policy |
| `POST` | `/workflow/policies/import` | Import Policy |
| `POST` | `/workflow/policies/validate` | Validate Policy |
| `GET` | `/workflow/policies/{policy_id}` | Policy |
| `POST` | `/workflow/policies/{policy_id}/activate` | Activate Policy |
| `GET` | `/workflow/policies/{policy_id}/yaml` | Policy Yaml |
| `GET` | `/workflow/population/{object_type}` | Population |
| `GET` | `/workflow/queue` | Queue |
| `GET` | `/workflow/review` | Everything the review screen shows (§10.3, §10.6): the semantic diff against the |
| `POST` | `/workflow/transitions` | Transition |

### workspaces

| Method | Path | What it does |
|---|---|---|
| `GET` | `/workspaces` | List Workspaces |
| `POST` | `/workspaces` | Create Workspace |
| `GET` | `/workspaces/{ws_id}` | Get Workspace |
| `POST` | `/workspaces/{ws_id}/abandon` | Abandon |
| `PUT` | `/workspaces/{ws_id}/changes` | Stage |
| `DELETE` | `/workspaces/{ws_id}/changes/{change_id}` | Unstage |
| `GET` | `/workspaces/{ws_id}/impact` | Impact |
| `GET` | `/workspaces/{ws_id}/preview` | Preview |
| `POST` | `/workspaces/{ws_id}/replay` | Replay |
| `POST` | `/workspaces/{ws_id}/submit` | Submit |

