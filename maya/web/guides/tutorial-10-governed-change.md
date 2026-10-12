# Tutorial 10 · A governed change

Most work is change, not creation. A vendor starts sending outliers, a rule
needs tightening, a column is added. In MAYA a change to an approved definition
is a new version, reviewed like the first. Before submitting it you can
rehearse it in a **workspace**: stage the proposal, preview it, list everything
downstream, and replay every dependent model on the old and the new data to see
how far its answers move. The reviewer then gets the replay, and a challenger's
memo, beside the diff.

In this tutorial dana caps `utilisation` at 100% under the live scorecard, and
mick reviews the change with the evidence in front of him.

## Time to complete

25 minutes.

## Before you start

- [Tutorial 7](/help/guides/tutorial-07-training-warrant) and
  [Tutorial 8](/help/guides/tutorial-08-execution-and-monitoring): the feature
  `credit/accounts` under the training panel, the sealed training warrant
  `credit/pd_fit_2024` and the live execution warrant `credit/pd_live`.
- **dana** (feature designer) and **mick** (feature manager), from
  [Tutorial 1](/help/guides/tutorial-01-first-15-minutes).

## What you will learn

- What a workspace is, and what staging a change does.
- How to preview a feature as the workspace sees it.
- How MAYA finds everything downstream of a change.
- How shadow replay measures how far each dependent model moves, and how to
  read its report.
- How submitting a workspace becomes an ordinary review, with the replay and a
  challenger's memo attached.
- Why nothing downstream moves until someone chooses to move it.

## Step 1 · Reconnect, and write the proposal

A balance above the limit makes utilisation exceed 1.0. Risk decides these are
an artefact of fees posted before payments, and that utilisation should be
capped at 1.0. In the definition that is one transform step:

```python
# reconnect; the proposal is version 1 plus a clip step
import copy
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


dana, mick = connect_as("dana"), connect_as("mick")

current = dana.features.get("credit/accounts")["versions"][0]
print(
    "v" + str(current["version_no"]),
    current["state"],
    "transform:",
    current["definition"]["transform"],
)
proposed = copy.deepcopy(current["definition"])
proposed["transform"] = [{"op": "clip", "attr": "utilisation", "lo": 0, "hi": 1.0}]
print("proposed transform:", proposed["transform"])
```

You should see version 1 with no transform, and the proposal:

```text
v1 approved transform: []
proposed transform: [{'op': 'clip', 'attr': 'utilisation', 'lo': 0, 'hi': 1.0}]
```

## Step 2 · Open a workspace and stage the change

A workspace is a copy-on-write branch of the catalogue. Staging stores the
proposal for an existing feature or feature set, and copies nothing else.

```python
# dana opens a workspace and stages the proposal
ws = dana.workspaces.create("cap-utilisation", description="Cap utilisation at 100%")
change = dana.workspaces.stage(
    ws["id"], "feature", "credit/accounts", proposed, note="over-limit balances are an artefact"
)
print(ws["name"], ws["state"])
print(change["object_ref"], "based on v" + str(change["base_version_no"]))
```

You should see the workspace open, and the change staged against version 1:

```text
cap-utilisation open
maya://feature/credit/accounts based on v1
```

Staging needs only read access; submitting will need update. The proposal is
validated like any definition, so a mistake is refused here, not at review. On
screen: **Workbench → Workspaces** (`/workbench/workspaces`).

## Step 3 · Preview inside the workspace

Inside the workspace every resolution uses the proposal in place of the version
it would replace: directly, through derived features, and through feature sets.

```python
# resolve credit/accounts as the workspace sees it
pv = dana.workspaces.preview(ws["id"], "maya://feature/credit/accounts")
print(pv["total_rows"], "rows")
for step in pv["plan"]:
    print(" ", step)
```

You should see every row, and a plan with the transform step that version 1
does not have:

```text
1218 rows
  maya://feature/credit/accounts@v1: read ingest log (1219 source rows)
  knowledge-time cut at now; grid as_is; rules per attribute
  transform pipeline: 1 step(s)
```

1,218 rows: the 2024 history, the 2026 rows from tutorial 4, and one more
source row than rows, because tutorial 8's correction replaced a value rather
than adding a key.

## Step 4 · What is downstream?

```python
# everything the change can reach, from the lineage graph
impact = dana.workspaces.impact(ws["id"])
kinds = {}
for d in impact["downstream"]:
    kinds[d["kind"]] = kinds.get(d["kind"], 0) + 1
print(kinds)
for d in impact["downstream"]:
    if d["kind"] == "featureset":
        print(" ", d["ref"])
print(impact["warrants"])
```

You should see what the change can reach by kind (the live execution, two
feature pins, the two sets and their pins, two parameter sets, three warrants),
the feature sets by name, and the warrants:

```text
{'execution': 1, 'feature': 2, 'featureset': 4, 'parameters': 2, 'warrant': 3}
  maya://featureset/credit/panel#h1/2026-06-30
  maya://featureset/credit/panel@v1
  maya://featureset/credit/training_panel#fit/2024-06-30
  maya://featureset/credit/training_panel@v1
['maya://warrant/exec/credit/pd_live@v1', 'maya://warrant/train/credit/pd_fit_2024@v1', 'maya://warrant/train/credit/pd_fit_naive@v1']
```

The sealed pins are listed because they descend from the feature, but they will
never change: a pin is immutable. What can change is anything that resolves
`credit/accounts` live, and any warrant drawn afresh.

## Step 5 · Shadow replay

Shadow replay answers the reviewer's real question: *how much does it move?*
For each dependent training warrant, MAYA resolves its feature set version
twice, with the current definitions and with the workspace's, and scores both
with the warrant's own model and parameters. An execution warrant is replayed
through the training warrant it was issued from, with its own sealed
parameters, so the production number is measured, not inferred.

```python
# run the replay, then read the report
dana.wait(dana.workspaces.shadow_replay(ws["id"]))
report = dana.workspaces.get(ws["id"])["replay"]
for w in report["warrants"]:
    if not w["replayed"]:
        print(w["warrant"], "| not replayed:", w["reason"])
        continue
    print(
        w["warrant"],
        "|",
        w["rows_compared"],
        "rows compared,",
        w["rows_over_materiality"],
        "over materiality",
        f"({w['materiality']}, {w['materiality_from']})",
    )
    print(
        "   median",
        w["median_abs_shift"],
        "| max",
        round(w["max_abs_shift"], 4),
        "| worst",
        w["worst_row"],
    )
```

You should see both the live warrant and its training warrant replayed on all
1,218 rows, with three rows moving materially and a largest move of about 0.4
percentage points of PD, and the naive warrant from tutorial 7 not replayed:

```text
maya://warrant/exec/credit/pd_live@v1 | 1218 rows compared, 3 over materiality (0.0001, default)
   median 0.0 | max 0.0042 | worst {'date': '2024-01-31 00:00:00', 'account': 'A0119'}
maya://warrant/train/credit/pd_fit_2024@v1 | 1218 rows compared, 3 over materiality (0.0001, default)
   median 0.0 | max 0.0042 | worst {'date': '2024-01-31 00:00:00', 'account': 'A0119'}
maya://warrant/train/credit/pd_fit_naive@v1 | not replayed: no parameter set to score with yet
```

Read it as a reviewer would:

- **Almost nothing moves.** Only three account-months had utilisation above 1.0,
  and capping them changes their PD by at most 0.42 points. A contained change.
- **The live model moves exactly as the training warrant does**, because it runs
  the same parameters on the same panel.
- **`(0.0001, default)`** names the materiality threshold and where it came
  from. A model version can declare its own `shadow_materiality`, then the
  namespace, then this configured default: a PD and a price are not material at
  the same number.
- **Nothing is hidden.** The naive warrant has no parameters, so it could not be
  scored, and the report says so rather than counting it as unmoved.

Replays cost compute, so each namespace has a daily budget of row comparisons,
and a warrant over budget is reported unreplayed with the figures. Staging
another change clears the report: a stale report is no report.

## Step 6 · Submit, and review with the evidence

Submitting is the merge request. Each staged change becomes a new draft version,
submitted through the ordinary workflow, with a comment carrying the replay
summary for the reviewer.

```python
# dana submits the workspace; mick reads the diff, the comment and the memo
out = dana.workspaces.submit(ws["id"])
submitted = out["submitted"][0]
print(submitted["ref"], "v" + str(submitted["version_no"]), submitted["state"])
v2_id = submitted["version_id"]

print(mick.features.compare("credit/accounts", 1, 2))
comment = mick.workflow.comments("feature_version", v2_id)[0]
print(
    comment["author"],
    "-",
    comment["body"].split(" (")[0],
    "... Shadow replay:",
    "Shadow replay" in comment["body"],
)
memo = mick.assistant.memos("feature_version", v2_id)[0]
print("memo:", memo["provider"], memo["state"], "-", memo["summary"])
```

You should see version 2 in review, the diff classed as behavioural, dana's
comment with the replay, and the challenger's memo:

```text
maya://feature/credit/accounts v2 in_review
{'change_class': 'behavioral', 'diff': [{'what': 'transform', 'change': "[] → [{'op': 'clip', 'attr': 'utilisation', 'lo': 0, 'hi': 1.0}]"}]}
dana - Rehearsed in workspace 'cap-utilisation' ... Shadow replay: True
memo: rules ready - No findings.
```

`behavioral`: the index and attributes are unchanged, but values will differ.
Every submission gets a memo from the recorded **challenger**. With the default
`rules` provider it holds deterministic findings; with a language model
configured it adds that model's challenge, attributed to the exact provider and
model. The memo can never approve, block or edit anything: no check reads it.
What is recorded is the reviewer's response:

```python
# only a reviewer responds to the challenge, and disagreement needs a reason
try:
    dana.assistant.respond(memo["id"], "agree")
except maya.PermissionDenied as exc:
    print(type(exc).__name__, exc)
try:
    mick.assistant.respond(memo["id"], "partly", "ok")
except maya.ValidationFailed as exc:
    print(type(exc).__name__, exc)
print("mick:", mick.assistant.respond(memo["id"], "agree")["stance"])
```

You should see the author refused, a terse half-agreement refused, and mick's
stance recorded:

```text
PermissionDenied Only someone who may approve this object records a response to its challenge
ValidationFailed Say why, in at least 10 characters, when you do not fully agree with the challenge
mick: agree
```

## Step 7 · Approve, and see what did not move

```python
# mick approves version 2; then look downstream (devi reads the live warrant)
r = mick.features.transition(
    "credit/accounts", 2, "approve", rationale="Replay reviewed: three rows, contained"
)
print(r["state"], [(c["check"], c["passed"]) for c in r["checks"]])

members = mick.featuresets.get("credit/training_panel")["versions"][0]["definition"]["members"]
print(sorted({m["ref"] for m in members}))
devi = connect_as("devi")
live = next(w for w in devi.execution.list() if w["name"] == "pd_live")
print(devi.execution.bundle(live["id"], "dev")["status"])
```

You should see version 2 approved, the training panel still naming version 1,
and the live warrant untouched:

```text
approved [('definition_valid', True), ('quality_passes', True), ('no_open_blocking_comments', True)]
['maya://feature/credit/accounts@v1', 'maya://feature/credit/bureau@v1', 'maya://feature/credit/defaults@v1']
live
```

Nothing downstream moved on its own, because everything referenced a version or
a pin:

| Object | After the approval |
|---|---|
| `credit/accounts@v2` | approved, with the cap |
| `credit/accounts@v1` | unchanged, still approved |
| `credit/panel@v1`, `credit/training_panel@v1` | unchanged: they name `credit/accounts@v1` |
| the `h1` and `fit` pins | unchanged: sealed |
| the training and execution warrants | unchanged: bound to the sealed pin |

To adopt the change, a feature set gets a new version (or a new set) naming
`credit/accounts@v2`; it is reviewed, pinned, and a new training warrant is
drawn on it, or the existing one cloned with
`devi.training.clone(warrant_id, featureset=...)`. Each step is governed.

## Next steps

- [Tutorial 11 · Findings, tiers and periodic review](/help/guides/tutorial-11-findings-tiers-reviews)
  puts the scorecard under model-risk management.
- [Workflow](/help/workflow) explains review, checks and the challenger.
- [Workspaces](/help/workspaces) covers staging, impact and replay in full.

## If something goes wrong

| What you see | Why | What to do |
|---|---|---|
| The proposal is refused when staged | It is not a valid definition | Read the error: it names the key |
| `Conflict` on submit | Another version was approved since you staged | Stage again on the new base, and replay again |
| The replay report is empty | A change was staged or restaged after the replay | Run the replay again before submitting |
| A warrant `not replayed` | It has no parameters, or its namespace's replay budget is spent | Read `reason`; the figures are in the entry |
| `Only someone who may approve this object records a response` | The author tried to grade the challenge to their own work | The reviewer responds |
