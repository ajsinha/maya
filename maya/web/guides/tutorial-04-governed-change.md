# Tutorial 4 — A governed change

Real work is mostly change: a vendor starts sending outliers, a rule needs
tightening, a column is added. In MAYA a change to an approved definition is a
new version that goes through review like the first one. Before submitting it,
you can rehearse it in a **workspace**: stage the proposed definition, preview
it, list everything downstream, and replay every dependent model on the old and
new data to see how far it moves. The reviewer then gets the replay report and a
challenger's memo alongside the diff.

This tutorial continues from [Tutorial 3](/help/guides/tutorial-03-warrants-and-bundles):
`eq/signals@v1` feeds `eq/panel`, which a sealed training warrant and a live
execution warrant depend on. It takes about twenty minutes.

## The change

The desk decides that `x` should be capped at 5: values above are treated as
outliers. In the definition that is one transform step:

```python
# The proposed definition of eq/signals: v1 plus a clip step
import copy

proposed = copy.deepcopy(signals)  # the v1 definition from Tutorial 2
proposed["transform"] = [{"op": "clip", "attr": "x", "lo": 0, "hi": 5}]
```

## Step 1: Open a workspace and stage the change

A workspace is a copy-on-write branch of the catalog. Staging stores the
proposal for an existing feature or feature set and copies nothing else.

```python
# dana opens a workspace and stages the proposal
ws = dana.workspaces.create("clip-x", description="Clip x at 5")
print(ws["name"], ws["state"])
ch = dana.workspaces.stage(ws["id"], "feature", "eq/signals", proposed, note="cap outliers")
print(ch["object_ref"], "based on v%d" % ch["base_version_no"])
```

```text
# Expected output
clip-x open
maya://feature/eq/signals based on v1
```

Staging needs only read access; submitting will need update. The proposal is
validated like any definition, so a mistake is refused here, not at review.

In the UI: **Workbench → Workspaces** (`/workbench/workspaces`).

## Step 2: Preview inside the workspace

Inside the workspace every resolution uses the proposal in place of the version
it would replace: directly, through derived features and through feature sets.

```python
# Resolve eq/signals as the workspace sees it
pv = dana.workspaces.preview(ws["id"], "maya://feature/eq/signals")
print(pv["total_rows"], pv["plan"])
```

```text
# Expected output
180 ['maya://feature/eq/signals@v1: read ingest log (180 source rows)', 'knowledge-time cut at now; grid as_is; rules per attribute', 'transform pipeline: 1 step(s)']
```

The plan shows the extra transform step that v1 does not have.

## Step 3: What is downstream?

```python
# Everything the change can reach, from the lineage graph
impact = dana.workspaces.impact(ws["id"])
for d in impact["downstream"]:
    print(d["kind"], d["ref"])
print(impact["warrants"])
```

```text
# Expected output
execution maya://execution/053156bf-…/dev
feature maya://feature/eq/signals#q1/2026-02-28
featureset maya://featureset/eq/panel#q1/2026-02-28
featureset maya://featureset/eq/panel@v1
parameters maya://parameters/bda32468-…
warrant maya://warrant/exec/eq/linear_live@v1
warrant maya://warrant/train/eq/linear_fit@v1
['maya://warrant/exec/eq/linear_live@v1', 'maya://warrant/train/eq/linear_fit@v1']
```

The sealed pins are listed because they descend from the feature, but they will
never change: a pin is immutable. What can change is anything that resolves
`eq/signals` live, and any warrant drawn afresh.

## Step 4: Shadow replay

Shadow replay answers the reviewer's real question: *how much does it move?*
Each dependent training warrant's feature set version is resolved twice —
current definitions, then the workspace's — and scored with the warrant's own
model and parameters.

```python
# Run the replay and read the report
job = dana.workspaces.shadow_replay(ws["id"])
dana.wait(job)
report = dana.workspaces.get(ws["id"])["replay"]
print(report["summary"])
for w in report["warrants"]:
    print(
        w["warrant"],
        w["replayed"],
        w.get("reason")
        or {
            k: w[k]
            for k in (
                "rows_compared",
                "median_abs_shift",
                "p95_abs_shift",
                "max_abs_shift",
                "worst_row",
                "rows_over_materiality",
            )
        },
    )
```

```text
# Expected output
moves 1 of 2 replayed dependent model(s); maya://warrant/train/eq/linear_fit@v1: median |Δ| 0, p95 6.01, 48.3% of rows over materiality (0.0001, default)
maya://warrant/exec/eq/linear_live@v1 True {'rows_compared': 180, 'median_abs_shift': 0.0, 'p95_abs_shift': 6.009999999999996, 'max_abs_shift': 7.800000000000001, 'worst_row': {'date': '2026-03-01 00:00:00', 'symbol': 'CCC'}, 'rows_over_materiality': 87}
maya://warrant/train/eq/linear_fit@v1 True {'rows_compared': 180, 'median_abs_shift': 0.0, 'p95_abs_shift': 6.009999999999996, 'max_abs_shift': 7.800000000000001, 'worst_row': {'date': '2026-03-01 00:00:00', 'symbol': 'CCC'}, 'rows_over_materiality': 87}
```

Read it the way a reviewer would:

* **Most rows do not move** (median shift 0): `x` is below 5 for them.
* **Nearly half move materially**: every row where `x` exceeded 5 now predicts
  `2·5 + 0.5 = 10.5`. The worst is CCC on 1 March, where `x` was 8.9 and the
  prediction falls by 7.8.
* **The execution warrant moves with it.** An execution warrant is replayed
  through the training warrant it was issued from — that warrant's feature set
  and bindings, scored with the execution warrant's own model version and sealed
  parameters — so the production number is measured and not inferred.
* **`(0.0001, default)`** names the threshold and where it came from. A model
  version that declares its own `shadow_materiality` is judged by that instead,
  then the namespace's, then this configured default: a rate in basis points and a
  price are not material at the same number, and a report that used the wrong one
  would read as "nothing moved".

| Report field | Meaning |
|---|---|
| `sample_rows` | rows replayed per warrant, the most recent (`workspaces.shadow.sample_rows`, default 5000) |
| `materiality`, `materiality_from` | the absolute shift counted as material, and whether it came from the `model`, the `namespace` or the configured `default` |
| `rows_added`, `rows_removed` | keys that appear or disappear under the proposal |
| `median_abs_shift`, `p95_abs_shift`, `max_abs_shift` | the size of the move |
| `worst_row` | the index key of the largest move |
| `rows_over_materiality`, `share_over_materiality` | how much of the sample moved materially |
| `rows_compared`, `rows_available`, `coverage` | how many rows were replayed, how many matched in all, and the share that covers |
| `coverage` (report) | the same totals across every warrant, with the sampling named |
| `budget` | what a replay may cost each namespace per day in row comparisons, and what this one spent |
| `basis` | how the replay was done, ending "Sampled agreement is not proof" |

!!! note "Replaying costs compute, and the bill is per namespace"
    Each namespace may spend `workspaces.shadow.budget_rows` row comparisons a
    day, or its own `shadow_budget_rows`, charged against what the audit log says
    earlier replays spent. A warrant whose namespace has spent its budget is
    reported unreplayed, with the figures, rather than quietly counted as
    unmoved. Zero anywhere means no ceiling.

!!! note "A new stage clears the report"
    Staging another change, or restaging this one, empties the replay report: a
    stale report is no report. Run the replay again before submitting.

## Step 5: Submit the workspace

Submitting is the merge request. Each staged change becomes a new draft version,
is submitted through the ordinary workflow, and gets a comment carrying the
replay summary for the reviewer.

```python
# Submit: each change becomes a submitted draft
out = dana.workspaces.submit(ws["id"])
print(out["submitted"])
```

```text
# Expected output
[{'kind': 'feature', 'ref': 'maya://feature/eq/signals', 'version_no': 2, 'version_id': 'be3e501c-…', 'state': 'in_review'}]
```

If someone had approved another version of `eq/signals` since you staged, the
submit would be refused as a conflict: rebase by staging again on the new base.

## Step 6: Review the change

mick sees `eq/signals@v2` in **Workflow**. First, what changed and how it is
classed:

```python
# The definition diff between v1 and v2
print(mick.features.compare("eq/signals", 1, 2))
```

```text
# Expected output
{'change_class': 'behavioral', 'diff': [{'what': 'transform', 'change': "[] → [{'op': 'clip', 'attr': 'x', 'lo': 0, 'hi': 5}]"}]}
```

`behavioral`: the index and attributes are unchanged, but values will differ.
The same comparison is on screen at `/catalog/features/eq/signals/compare`, and
from the CLI as `python -m maya.cli feature diff eq/signals 1 2`.

Next, the comment the workspace left, and the challenger's memo:

```python
# The replay comment and the challenger memo
v2_id = out["submitted"][0]["version_id"]
for c in mick.workflow.comments("feature_version", v2_id):
    print(c["author"], "-", c["body"][:90], "…")
for m in mick.assistant.memos("feature_version", v2_id):
    print(m["provider"], m["model"], m["state"], "-", m["summary"], m["findings"])
```

```text
# Expected output
dana - Rehearsed in workspace 'clip-x' (3503e189-…). Shadow replay: moves 1 of 1 replayed d …
rules rules/1 ready - No findings. []
```

Every submission gets a memo from the recorded challenger. With the default
`rules` provider it holds deterministic findings; with `assistant.provider: llm`
(any model profile, through the AI gateway) or `claude` it adds the model's
challenge, attributed to the exact provider and model. The memo can
never approve, block or edit anything: no check reads it. What is recorded is the
reviewer's response to it:

```python
# mick records a stance on the memo
memo = mick.assistant.memos("feature_version", v2_id)[0]
print(mick.assistant.respond(memo["id"], "agree")["stance"])
```

```text
# Expected output
agree
```

A stance of `partly` or `disagree` needs a note of at least ten characters, and
the author of the change may not grade the challenge to their own work.

## Step 7: Approve

```python
# mick approves v2
r = mick.features.transition("eq/signals", 2, "approve", rationale="Replay reviewed")
print(r["state"], [(c["check"], c["passed"]) for c in r["checks"]])
```

```text
# Expected output
approved [('definition_valid', True), ('quality_passes', True), ('no_open_blocking_comments', True)]
```

## What changed, and what did not

| Object | After the approval |
|---|---|
| `maya://feature/eq/signals@v2` | approved, with the clip |
| `maya://feature/eq/signals@v1` | unchanged, still approved |
| `maya://featureset/eq/panel@v1` | unchanged: it names `eq/signals@v1` |
| the `q1` pins | unchanged: sealed |
| the training and execution warrants | unchanged: bound to the sealed panel pin |

Nothing downstream moved on its own, because everything referenced a version or
a pin. To adopt the change, the panel gets a new version naming
`eq/signals@v2`; it is reviewed, pinned under a new date or series, and a new
training warrant is drawn on it (or the existing one cloned with
`my.training.clone(warrant_id, featureset=…)`). Each step is governed.

## On screen

| Step | Screen |
|---|---|
| Workspaces, staging, preview, impact, replay, submit | **Workbench → Workspaces** (`/workbench/workspaces`, `/workbench/workspaces/{id}`) |
| Review queue and the review page | **Workflow** (`/workflow`, `/workflow/review/feature_version/{id}`) |
| Version comparison | `/catalog/features/eq/signals/compare` |
| Lineage | **Lineage** (`/lineage`) |

## What you learned

* A workspace rehearses a change against the real catalog without touching it.
* Impact comes from the lineage graph; shadow replay measures the move on each
  dependent training warrant, with its sample and basis stated.
* Submitting a workspace is a merge request through the ordinary workflow.
* The challenger's memo is a record the reviewer responds to, never a gate.
* Pins and version references keep everything downstream still until someone
  chooses to move it.
