# Tutorial 2 — A feature set and a model

A model reads a panel, not a feature. In this tutorial you build a feature with
two attributes, map it into a feature set, pin the set and its member together
with a cascade, then write a model in LaTeX, complete its specification document
and take it through review. Tutorial 3 trains this model under a warrant.

It takes about twenty-five minutes. Outputs are those MAYA returned when the
tutorial was run; ids and hashes will differ.

## What you will build

| Object | Reference |
|---|---|
| A feature with `x` and `y` | `maya://feature/eq/signals@v1` |
| A feature set | `maya://featureset/eq/panel@v1` |
| A cascade pin | `maya://featureset/eq/panel#q1/2026-02-28` |
| A model | `maya://model/eq/linear@v1` |

| Person | Role | Does |
|---|---|---|
| dana | `feature_designer` | writes the feature |
| mick | `feature_manager` | approves features and sets, pins |
| devi | `model_developer` | builds the feature set |
| mona | `model_designer` | writes the model and its specification |
| mgr | `model_manager` | approves the model |

## Step 1: Set up

This continues from [Tutorial 1](/help/guides/tutorial-01-first-feature): the
server is running, `eq` exists, and `connect_as` is defined. Add the new people:

```python
# Three more people
for user, roles in [
    ("devi", ["model_developer"]),
    ("mona", ["model_designer"]),
    ("mgr", ["model_manager"]),
]:
    admin.admin.create_user(user, password=PW, roles=roles)
devi, mona, mgr = connect_as("devi"), connect_as("mona"), connect_as("mgr")
```

## Step 2: A feature with two attributes

`signals.csv` holds 60 days for three symbols, with `y = 2x + 0.5` exactly, and a
`known_at` column giving each row's publication time. Generate it:

```python
# Write signals.csv
import datetime as dt

lines = ["date,symbol,x,y,known_at"]
for i in range(60):
    day = dt.date(2026, 1, 1) + dt.timedelta(days=i)
    for j, s in enumerate(("AAA", "BBB", "CCC")):
        x = 1.0 + i * 0.1 + j
        lines.append(f"{day},{s},{x:.3f},{2.0 * x + 0.5:.3f},{day}T18:00:00Z")
open("signals.csv", "w").write("\n".join(lines) + "\n")
```

Because the definition names `knowledge_time_column`, every row gets its own
knowledge time from `known_at`, which is what the leakage certificate in
Tutorial 3 will check.

```python
# Define, ingest, submit, approve
signals = {
    "index": ["date", "symbol"],
    "index_types": {"date": "date", "symbol": "string"},
    "schema": [{"name": "x", "type": "float64"}, {"name": "y", "type": "float64"}],
    "source": {"type": "csv", "knowledge_time_column": "known_at"},
    "resolution": {"grid": "as_is", "rules": {}},
    "transform": [],
    "quality": [{"check": "not_null", "attr": "x"}],
}
dana.features.create("eq", "signals", signals)
print(dana.features.ingest("eq/signals", open("signals.csv", "rb").read(), fmt="csv")["rows"])
dana.features.transition("eq/signals", 1, "submit")
print(mick.features.transition("eq/signals", 1, "approve")["state"])
```

```text
# Expected output
180
approved
```

## Step 3: Map it into a feature set

A feature set names each output attribute, the member feature it comes from and
the member's attribute. This one is simple: both attributes from one member,
aligned on `[date, symbol]`.

```python
# devi defines the panel
panel = {
    "index": ["date", "symbol"],
    "grid": "as_is",
    "alignment": {"mode": "inner"},
    "members": [
        {"attr": "x", "ref": "maya://feature/eq/signals@v1", "source_attr": "x"},
        {"attr": "y", "ref": "maya://feature/eq/signals@v1", "source_attr": "y"},
    ],
}
fs = devi.featuresets.create("eq", "panel", panel)
print(fs["name"], fs["status"])
```

```text
# Expected output
panel draft
```

Preview it. The manifest says, for every attribute, which rule filled it and from
which layer of the precedence the rule came:

```python
# Preview the draft set
pv = devi.featuresets.draft_preview("eq/panel")
print(pv["total_rows"], pv["columns"])
print(pv["rows"][0])
print(pv["manifest"]["attributes"]["x"])
print(pv["manifest"]["plan"])
```

```text
# Expected output
180 ['date', 'symbol', 'x', 'y', '_knowledge_time']
{'date': '2026-01-01T00:00:00', 'symbol': 'AAA', 'x': 1.0, 'y': 2.5, '_knowledge_time': '2026-01-01T18:00:00+00:00'}
{'member': 'maya://feature/eq/signals@v1', 'source_attr': 'x', 'rule': 'none', 'layer': 'default', 'source': 'system'}
['maya://feature/eq/signals@v1: read ingest log (180 source rows)', 'knowledge-time cut at now; grid as_is; rules per attribute', 'alignment: inner', "join member 'maya://feature/eq/signals@v1' on ['date', 'symbol']"]
```

No layer set a rule, so the system default applies: leave gaps null. The
[Feature set reference](/help/guides/featuresets-reference) lists all six layers.

In the UI: **Workbench → Feature set builder** (`/workbench/featuresets/new`).

## Step 4: Review the set

```python
# devi submits, mick approves
print(devi.featuresets.transition("eq/panel", 1, "submit")["state"])
r = mick.featuresets.transition("eq/panel", 1, "approve")
print(r["state"], [c["check"] for c in r["checks"]])
```

```text
# Expected output
in_review
approved ['definition_valid', 'members_approved', 'no_open_blocking_comments']
```

`members_approved` passed because `eq/signals@v1` is approved. Had it been a
draft, the approval would have been blocked, naming it.

## Step 5: Pin the set with a cascade

A training warrant should bind to data that cannot move. mick pins the set as of
28 February. A plain pin is refused, because the member is referenced by version
and could still move:

```python
# A pin without the cascade
mick.featuresets.pin("eq/panel", version_no=1, pin_name="q1", as_of="2026-02-28")
```

```text
# The call raises
NotApproved: A feature set refuses to pin unless every member is pinned. Unpinned: maya://feature/eq/signals@v1. Use cascade pin to pin them together.
```

With `cascade=True`, MAYA pins the member under the same series and date, then
the set, in one job. If any part failed, all of it would be rolled back.

```python
# The cascade pin
out = mick.featuresets.pin(
    "eq/panel", version_no=1, pin_name="q1", as_of="2026-02-28", cascade=True
)
print(mick.wait(out["job"])["result"])
```

```text
# Expected output
{'pin_id': '68fd4ff9-…', 'content_hash': '8d27823ea118…', 'rows': 177, 'cascaded_member_pins': 1}
```

```bash
# The same from the CLI (as mick)
python -m maya.cli featureset pin eq/panel --version 1 --name q1 --as-of 2026-02-28 --cascade
```

Why 177 rows and not 180? The data runs to 1 March; a pin as of 28 February
ends there, so the last day's three rows are outside it. Two pins now exist:
`maya://feature/eq/signals#q1/2026-02-28` and
`maya://featureset/eq/panel#q1/2026-02-28`.

## Step 6: Write the model in LaTeX

mona writes the model as it would appear in a paper. `a` and `b` are trained
parameters; every other free name is a feature the set must supply.

```python
# Create the model from LaTeX
m = mona.models.create(
    "eq",
    "linear",
    formula=r"y_{hat} = a \cdot x + b",
    roles={"a": "parameter", "b": "parameter"},
    description="y on x",
)
v = mona.models.get("eq/linear")["versions"][0]
print(v["formula_ir"]["latex"])
print([(i["name"], i["role"]) for i in v["formula_ir"]["inputs"]])
print(v["input_contract"])
print(v["maturity"], v["state"])
```

```text
# Expected output
\mathit{yhat} = a\,x + b
[('a', 'parameter'), ('b', 'parameter'), ('x', 'feature')]
[{'name': 'x', 'type': 'float64', 'unit': None, 'role': 'feature'}]
experimental draft
```

The subscript folded into the name (`y_{hat}` → `yhat`). The input contract is
what any bound feature set must provide: one float attribute called `x`. The
plain text `yhat = a*x + b` produces the identical IR and the identical IR
hash. In the UI: **Models → New model** (`/models/new`).

## Step 7: The specification document blocks submission

Every model version carries a LaTeX specification, seeded from a template. Try
to submit now:

```python
# Submit with the template untouched
mona.models.transition("eq/linear", 1, "submit")
```

```text
# The call raises
NotApproved: Blocked by check(s): spec_document_complete — required sections empty: Purpose, Scope and Limitations, Assumptions, Calibration Methodology, Validation Evidence, Known Weaknesses, Change Log
```

The template already filled two sections for you: *Mathematical Formulation*
holds `\mayaformula{body}`, which renders the equation from the IR, and *Data and
Features Used* lists the inputs. Save `linear_spec.tex`:

```latex
% linear_spec.tex
\documentclass{article}
\begin{document}
\section{Purpose}
Predict y from the signal x with a straight line.
\section{Scope and Limitations}
Daily panel of three symbols; not for use outside the fitted range of x.
\section{Mathematical Formulation}
\mayaformula{body}
\section{Assumptions}
The relation between x and y is linear with homoscedastic errors.
\section{Data and Features Used}
The attribute x of maya://featureset/eq/panel, pinned as q1.
\section{Calibration Methodology}
Ordinary least squares on the training split of the warrant's data.
\section{Validation Evidence}
Blind RMSE on the escrowed holdout, recorded on the warrant.
\section{Known Weaknesses}
No intercept shift over time; sensitive to outliers in x.
\section{Change Log}
v1: first version.
\end{document}
```

```python
# Save the specification and submit again
mona.models.update_draft("eq/linear", spec_latex=open("linear_spec.tex").read())
r = mona.models.transition("eq/linear", 1, "submit")
print(r["state"])
for c in r["checks"]:
    print(" ", c["check"], "-", c["detail"])
```

```text
# Expected output
in_review
  formula_typechecks - IR validates and typechecks
  spec_document_complete - all required sections present
  code_artifact_validated - no code artifact attached (formula-only model)
```

!!! tip "The document follows the mathematics"
    The specification is bound to the IR hash it was saved against. If the
    formula changes later, the document is marked for re-review and the check
    fails until someone saves it again, so the prose cannot silently drift from
    the equations.

## Step 8: Approve the model

mona cannot approve (a model designer has no approval right), so mgr does:

```python
# mgr approves
r = mgr.models.transition("eq/linear", 1, "approve", rationale="Spec and IR reviewed")
print(r["state"])
print([c["check"] for c in r["checks"]])
print(mgr.models.get("eq/linear")["versions"][0]["maturity"])
```

```text
# Expected output
approved
['formula_typechecks', 'spec_document_complete', 'code_artifact_validated', 'spec_true_build', 'composite_members_mature', 'no_open_blocking_comments']
candidate
```

Approval moved the maturity from `experimental` to `candidate`. The
`spec_true_build` check passed with "no PDF rendered yet (not required in dev)":
outside the `dev` environment a true LaTeX build of the specification is
required before approval (`my.models.render_spec("eq/linear", 1)`).

## Step 9: Reference code

MAYA generates Python from the IR. It is the yardstick an implementation is
tested against:

```python
# The generated reference implementation
print(mgr.models.reference_code("eq/linear", 1)["source"])
```

```python
# Its predict function (the file also defines normal CDF and PDF helpers)
def predict(X, params):
    v_a = params["a"]
    v_b = params["b"]
    v_x = np.asarray(X["x"], dtype=float)
    return {"yhat": ((v_a * v_x) + v_b)}
```

## On screen

| Step | Screen |
|---|---|
| Feature set builder and preview | `/workbench/featuresets/new`, `/workbench/featuresets/eq/panel/preview` |
| Set versions, transitions, cascade pin | **Catalog → Feature sets** (`/catalog/featuresets/eq/panel`) |
| New model | **Models → New model** (`/models/new`) |
| Equations, IR, contract, specification, transitions | `/models/eq/linear` |
| Review queue | **Workflow** (`/workflow`) |

## What you learned

* A feature set maps attributes onto member features and records, per
  attribute, which rule filled it and why.
* A set pins only over pinned members; a cascade pins them together or not at
  all.
* A model is written as mathematics; roles separate features from parameters;
  the input contract falls out of the formula.
* The specification document is a gate, and it stays bound to the IR.

Next: [Tutorial 3 — Warrants, parameters and a bundle](/help/guides/tutorial-03-warrants-and-bundles).
