# Tutorial 1 — Your first governed feature

In this tutorial you take one small CSV of closing prices all the way to an
approved, pinned, downloadable feature. You will see MAYA fill a gap and report
it, refuse a self-approval, block a pin whose quality check fails, and keep a
sealed pin unchanged when the vendor restates a price. Every step is shown three
ways where they exist: the Python SDK, the command line and the screen.

It takes about twenty minutes. The outputs shown are what MAYA returned when this
tutorial was run; ids, hashes and timestamps will differ on your machine.

## What you will build

| Object | Reference |
|---|---|
| A namespace | `eq` |
| A feature, version 1 | `maya://feature/eq/prices@v1` |
| A sealed pin | `maya://feature/eq/prices#eom/2026-01-09` |

Two people take part, because MAYA separates duties: **dana**, a feature
designer who writes and submits, and **mick**, a feature manager who approves and
pins. An administrator sets them up.

## Step 1: Start MAYA

```bash
# Start the server (SQLite by default)
python run_maya_web.py
```

Open `http://127.0.0.1:8600`. Signed out, that is the landing page; take
**Sign in** from it and sign in as `admin` with the development password
`maya-dev-admin`. MAYA asks you to change it in the browser.

## Step 2: Create the people and the namespace

In the UI: **Admin → Users** (`/admin/users`) creates the two users with their
roles, and **Admin → Namespaces** (`/admin/namespaces`) creates `eq` with the
`standard` preset. Or do it from Python. The helper below signs a user in and
creates an API key for them, which is what each person would otherwise do under
**Account → API keys** (`/account/keys`).

```python
# setup.py: users, a namespace and one SDK client per person
import maya.sdk as maya

URL = "http://127.0.0.1:8600"
PW = "Tutorial-pass-1"


def connect_as(user, password=PW):
    token = maya.Client(URL).auth.login(user, password)["token"]
    key = maya.Client(URL, token=token).auth.create_api_key("tutorial")["api_key"]
    return maya.connect(base_url=URL, api_key=key)


admin = connect_as("admin", "maya-dev-admin")  # use your new admin password
admin.admin.create_user("dana", password=PW, roles=["feature_designer"])
admin.admin.create_user("mick", password=PW, roles=["feature_manager"])
ns = admin.namespaces.create("eq", preset="standard")
print(ns["name"], ns["preset"], ns["production"])

dana, mick = connect_as("dana"), connect_as("mick")
```

```text
# Expected output
eq standard False
```

!!! note "Passwords and keys"
    With `auth.password.force_change` on, a user created this way must change their
    password at their first browser sign-in (the API accepts it meanwhile); it is off
    by default. An API key is shown once. In real use
    each person creates their own key and keeps it in `MAYA_API_KEY`.

## Step 3: Write the definition

The feature has one attribute, `close`, indexed by `date` (the event time) and
`symbol`. It lies on the Monday-to-Friday calendar, fills at most three missing
days forward but never from a price more than five days old, and must never be
null or negative.

```python
# The definition
definition = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "schema": [{"name": "close", "type": "float64", "unit": "USD"}],
    "source": {"type": "csv"},
    "resolution": {
        "grid": {"calendar": "ISO_business_days"},
        "rules": {"close": "forward_fill(limit=3, max_age=5)"},
    },
    "transform": [],
    "quality": [
        {"check": "not_null", "attr": "close"},
        {"check": "range", "attr": "close", "min": 0, "max": 100000},
    ],
}
```

Every key is explained in the [Feature definition reference](/help/features#reference).

## Step 4: Create the feature

```python
# dana creates eq/prices; it starts as a draft
f = dana.features.create("eq", "prices", definition, description="Daily closes")
print(f["name"], f["status"])
```

```text
# Expected output
prices draft
```

In the UI this is **Workbench → Feature designer** (`/workbench/features/new`).

## Step 5: Ingest the data

Save this as `prices.csv`. Note that 7 January is missing.

```text
# prices.csv
date,symbol,close
2026-01-05,AAA,100.0
2026-01-05,BBB,50.0
2026-01-06,AAA,101.5
2026-01-06,BBB,50.5
2026-01-08,AAA,102.0
2026-01-08,BBB,51.0
2026-01-09,AAA,103.0
2026-01-09,BBB,51.2
```

The vendor published this file on the evening of 9 January, so say so: the
knowledge time is what later lets MAYA answer "what did we know then?".

```python
# Ingest with the real publication time
out = dana.features.ingest(
    "eq/prices",
    open("prices.csv", "rb").read(),
    fmt="csv",
    filename="prices.csv",
    knowledge_time="2026-01-09T18:00:00Z",
)
print(out["rows"], out["knowledge_time"], out["restatement"])
```

```text
# Expected output
8 2026-01-09T18:00:00+00:00 False
```

```bash
# The same from the CLI (with MAYA_URL and MAYA_API_KEY set for dana)
python -m maya.cli feature upload eq/prices prices.csv --knowledge-time 2026-01-09T18:00:00Z
```

```text
# CLI output
ingested 8 rows
```

In the UI: the feature's **Ingest** page (`/workbench/features/eq/prices/ingest`).

## Step 6: Preview the draft

Before anyone reviews it, see what the definition does to the data.

```python
# Resolve the draft live
pv = dana.features.draft_preview("eq/prices")
print(pv["total_rows"], pv["columns"])
for row in pv["rows"][4:6]:
    print(row)
print(pv["fill_report"]["attributes"]["close"])
print(pv["plan"])
```

```text
# Expected output
10 ['date', 'symbol', 'close', '_knowledge_time']
{'date': '2026-01-07T00:00:00', 'symbol': 'AAA', 'close': 101.5, '_knowledge_time': 'NaT'}
{'date': '2026-01-07T00:00:00', 'symbol': 'BBB', 'close': 50.5, '_knowledge_time': 'NaT'}
{'rule': 'forward_fill(limit=3, max_age=5)', 'filled': 2, 'longest_run': 1, 'non_causal': False}
['maya://feature/eq/prices (draft): read ingest log (8 source rows)', 'knowledge-time cut at now; grid ISO_business_days; rules per attribute']
```

The calendar created 7 January for both symbols, and the rule filled them from
6 January. The fill report counts it (`filled: 2`) and the filled rows carry no
knowledge time of their own. The same page in the UI is
`/workbench/features/eq/prices/preview`.

## Step 7: Submit for review

```python
# dana submits version 1
r = dana.features.transition("eq/prices", 1, "submit")
print(r["state"], [(c["check"], c["passed"]) for c in r["checks"]])
```

```text
# Expected output
in_review [('definition_valid', True)]
```

Submitting froze the definition, computed its hash and put it in mick's queue
(**Workflow**, `/workflow`).

Could dana approve their own work? No:

```python
# A designer cannot approve
dana.features.transition("eq/prices", 1, "approve")
```

```text
# The call raises
PermissionDenied: You may not approve this object: role ceiling: no 'A' on feature in roles feature_designer
```

## Step 8: Approve

```python
# mick reviews and approves
r = mick.features.transition("eq/prices", 1, "approve", rationale="Checked")
print(r["state"])
for c in r["checks"]:
    print(" ", c["check"], c["passed"], "-", c["detail"])
```

```text
# Expected output
approved
  definition_valid True - definition is valid and typed
  quality_passes True - 2 quality check(s) pass on current data
  no_open_blocking_comments True - no open blocking comments
```

In the UI mick opens the item from **Workflow** (`/workflow/review/…`), reads the
definition and the challenger's memo, and presses **Approve**.

## Step 9: Pin it, and watch a pin fail

A pin seals one resolution as immutable, content-addressed data. mick first
tries a month-end pin:

```python
# Pin as of 31 January
out = mick.features.pin("eq/prices", version_no=1, pin_name="eom", as_of="2026-01-31")
mick.wait(out["job"])
```

```text
# The wait raises
MayaError: Job feature.pin failed: QualityCheckFailed: Pin blocked by the quality contract
```

Why? The calendar grid runs to the pin date, so 12–30 January exist as rows,
and the forward fill may not reach them: `max_age=5` stops it. The `not_null`
check found the gaps, and a failing check blocks the pin; it never warns and
seals anyway. The pin records exactly what happened:

```python
# Read the failed pin
p = mick.features.get("eq/prices")["pins"][0]
print(p["state"], "-", p["failure"])
```

```text
# Expected output
failed - quality check(s) failed: not_null(close): 24 null value(s)
```

The data only runs to 9 January, so pin as of 9 January. A failed series and
date may be reused:

```python
# Pin as of 9 January
out = mick.features.pin("eq/prices", version_no=1, pin_name="eom", as_of="2026-01-09")
print(mick.wait(out["job"])["result"])
```

```text
# Expected output
{'pin_id': 'c38edee4-…', 'content_hash': '5d6539b3ad9d9a96585cadd95e9c0228a78528968c3a731e2626f471cac16bb2', 'rows': 10, 'bytes_new': 272}
```

```bash
# The same from the CLI (as mick)
python -m maya.cli feature pin eq/prices --version 1 --name eom --as-of 2026-01-09
```

```text
# CLI output, after the job's progress lines
sealed 5d6539b3ad9d9a96585cadd95e9c0228a78528968c3a731e2626f471cac16bb2 (10 rows, 272 new bytes)
```

In the UI: **Catalog → Features → eq/prices → Pins** (`/catalog/features/eq/prices`).

## Step 10: Download the pin

```python
# Download the sealed pin as CSV
d = mick.features.download("maya://feature/eq/prices#eom/2026-01-09", format="csv")
print(d["manifest"]["content_hash"][:12], d["manifest"]["rows"])
print(d["data"].decode()[:300])
```

```text
# Expected output
5d6539b3ad9d 10
# maya-manifest: {"axes": {}, "columns": {"_knowledge_time": "timestamp", "close": "float64", "date": "date", "symbol": "string"}, "encoding": null}
date,symbol,close,_knowledge_time
2026-01-05,AAA,100.0,2026-01-09 18:00:00+00:00
2026-01-05,BBB,50.0,2026-01-09 18:00:00+00:00
2026-01-06,AAA,101.5,2026-01-09 18:00:00+00:00
```

```bash
# The same from the CLI
python -m maya.cli feature download "maya://feature/eq/prices#eom/2026-01-09" \
    --out prices-eom.csv --format csv
```

```text
# CLI output
prices-eom.csv: 10 rows, content hash 5d6539b3ad9d9a96585cadd95e9c0228a78528968c3a731e2626f471cac16bb2
```

The first line of the CSV is a manifest naming every column's type, so the file
describes itself. The download was audited.

## Step 11: A restatement

On 12 January the vendor corrects AAA's close for 6 January to 101.7. Ingest the
correction with its own knowledge time:

```python
# Ingest the correction
out = dana.features.ingest(
    "eq/prices",
    b"date,symbol,close\n2026-01-06,AAA,101.7\n",
    fmt="csv",
    knowledge_time="2026-01-12T09:00:00Z",
)
print(out["rows"], out["restatement"])
```

```text
# Expected output
1 True
```

Nothing was overwritten. Ask for the value now, and as it was known on
10 January:

```python
# Two readings of the same day
ref = "maya://feature/eq/prices@v1"
now = dana.features.preview(ref, start="2026-01-06", end="2026-01-06")["rows"]
then = dana.features.preview(
    ref, as_of_known="2026-01-10T00:00:00Z", start="2026-01-06", end="2026-01-06"
)["rows"]
print([(r["symbol"], r["close"]) for r in now])
print([(r["symbol"], r["close"]) for r in then])
```

```text
# Expected output
[('AAA', 101.7), ('BBB', 50.5)]
[('AAA', 101.5), ('BBB', 50.5)]
```

And the pin? It is sealed, so it still returns exactly what it returned before:

```python
# The pin did not move
d2 = mick.features.download("maya://feature/eq/prices#eom/2026-01-09", format="csv")
print(d2["manifest"]["content_hash"] == d["manifest"]["content_hash"])
```

```text
# Expected output
True
```

To capture the correction, pin again under a new date or series.

## The same journey on screen

| Step | Screen |
|---|---|
| Users, namespace | **Admin → Users** (`/admin/users`), **Admin → Namespaces** (`/admin/namespaces`) |
| Create | **Workbench → Feature designer** (`/workbench/features/new`) |
| Ingest | `/workbench/features/eq/prices/ingest` |
| Preview | `/workbench/features/eq/prices/preview` |
| Submit, approve, pin | **Catalog → Features** (`/catalog/features/eq/prices`) |
| Review queue | **Workflow** (`/workflow`) |
| API key | **Account → API keys** (`/account/keys`) |

## What you learned

* The first index column is event time; MAYA adds `_knowledge_time`.
* A calendar grid creates the missing days, the rule fills them within its
  bounds, and the fill report says so.
* Designers submit and managers approve; the checks are shown on every move.
* A pin runs the quality contract and seals only on success.
* A restatement appends. Previews can look back with `as_of_known`; pins never
  change.

Next: [Tutorial 2 — A feature set and a model](/help/guides/tutorial-02-featureset-and-model).
