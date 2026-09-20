# Models and the formula IR reference

A model version in MAYA holds its mathematics as a **formula IR**: a typed
expression tree of inputs, intermediate lets and one output. You never author
the tree by hand. You write the formula as text or LaTeX, lift it from a Python
function or an Excel workbook, or declare that there is no closed form. The IR
then type-checks against a feature set, renders the specification's equations,
produces a semantic diff, generates reference code, and is the yardstick an
implementation is tested against. This page documents all of it.

## Model kinds

| Kind | Mathematics | Typical use |
|---|---|---|
| `formula` (default) | a closed-form IR | pricing formulas, scorecards, regressions |
| `black_box` | none; a mandatory prose statement and an architecture | trees, networks |
| `vendor` | as a black box, with the vendor's details recorded | a purchased library |
| `composite` | a DAG of other model versions plus a combine expression | ensembles, pipelines |

```python
# Create a formula model from text
import maya.sdk as maya

my = maya.connect(base_url="http://127.0.0.1:8600", api_key="maya_…")
my.models.create(
    "eq",
    "linear",
    kind="formula",
    description="y on x",
    formula="yhat = a*x + b",
    roles={"a": "parameter", "b": "parameter"},
)
```

`create` takes `kind`, `description` and one way of giving the mathematics:
`formula` (with `roles`), `python_source`, or `ir`. `vendor` takes a dict of
vendor details. `update_draft` takes the same mathematics arguments plus
`spec_latex` and `maturity`. An unknown kind is refused: `kind must be one of formula, black_box, composite, vendor`.

## Writing formulas

A model is one or more statements, `name = expression`. Every statement but the
last defines a **let**; the last defines the **output**. Statements are
separated by new lines, `;` or LaTeX's `\\`. Lines starting with `#` or `%` are
comments; LaTeX alignment (`&=`, `&`) is ignored.

```latex
% Black–Scholes call, as written in a paper
d_1 = \frac{\ln(S/K) + (r + \sigma^2/2) T}{\sigma \sqrt{T}}
d_2 = d_1 - \sigma \sqrt{T}
C = S N(d_1) - K e^{-rT} N(d_2)
```

The same parser reads plain text:

```text
# The same model in plain text
d1 = (log(S/K) + (r + sigma**2/2)*T) / (sigma*sqrt(T))
d2 = d1 - sigma*sqrt(T)
C = S*ncdf(d1) - K*exp(-r*T)*ncdf(d2)
```

### Syntax

| Construct | Text form | LaTeX form | IR |
|---|---|---|---|
| Numbers | `2`, `0.5`, `1e-3` | same | `const` |
| Names | `sigma`, `d1`, `base.y` | `\sigma`, `d_1`, `d_{12}` | `ref` |
| Add, subtract | `a + b`, `a - b` | same | `add`, `sub` |
| Multiply | `a*b` | `a \cdot b`, `a \times b`, `a b` (adjacent) | `mul` |
| Divide | `a/b` | `\frac{a}{b}` | `div` |
| Power | `a**b`, `a^b` | `a^{b}` | `pow` |
| Exponential | `exp(x)` | `e^{x}`, `\exp{x}` | `exp` |
| Logarithm (natural) | `log(x)`, `ln(x)` | `\ln(x)`, `\log(x)` | `log` |
| Square root | `sqrt(x)` | `\sqrt{x}` | `sqrt` |
| Absolute value | `abs(x)`, or `x` between vertical bars | same | `abs` |
| Normal CDF | `ncdf(x)`, `N(x)`, `Phi(x)` | `\Phi(x)`, `N(x)` | `ncdf` |
| Normal PDF | `npdf(x)` | same | `npdf` |
| Maximum, minimum | `max(a, b, …)`, `min(…)` | `\max(a, b)`, `\min(…)` | `max`, `min` |
| Conditional | `where(c, a, b)` | same | `where` |
| Comparison | `< > <= >= ==` | `\le \ge \leq \geq` | `lt gt le ge eq` |
| Unary minus | `-x` | same | `neg` (folded into a constant when possible) |

LaTeX spacing and sizing commands (`\left`, `\right`, `\,`, `\;`, `\!`,
`\quad`, `\displaystyle`, `\mathrm`) are ignored. Greek letter commands become
names (`\sigma` → `sigma`). Subscripts are folded into the name (`d_1` → `d1`).

!!! note "Implicit multiplication in LaTeX"
    When the text contains a backslash or a brace, it is read as LaTeX, and a
    multi-letter name that is neither a Greek letter nor a name listed in
    `roles` is read as adjacent single letters multiplied: `rT` is `r·T`. Give
    multi-letter inputs a role (or a subscript such as `d_1`) to keep them
    whole. In plain text, `rate` is always one name.

Anything the parser cannot read is refused with the position, never guessed:
`unexpected '*' at position 3`, `unsupported LaTeX command '\foo' at position 0`,
`expected 'name = expression', got 'a + b'`.

### Roles

Every free name (not a let) becomes an input. Its role says where the value
comes from.

| Role | Supplied by | Notes |
|---|---|---|
| `feature` (default) | the bound feature set, per row | forms the **input contract** |
| `parameter` | a parameter set trained under a warrant | may carry `bounds: [lo, hi]` |
| `constant` | a fixed value | may carry `value`; otherwise the parameter set supplies it |

Inputs parsed from a formula are typed `float64`. The output is `float64`
unless `output_type` is given to the parser.

## The IR document

```json
# The IR of yhat = a*x + b, with a and b as parameters
{
  "outputs": [{"name": "yhat", "type": "float64"}],
  "inputs": [{"name": "a", "type": "float64", "role": "parameter"},
             {"name": "b", "type": "float64", "role": "parameter"},
             {"name": "x", "type": "float64", "role": "feature"}],
  "lets": {},
  "body": {"op": "add", "args": [
    {"op": "mul", "args": [{"ref": "a"}, {"ref": "x"}]},
    {"ref": "b"}]},
  "latex": "\\mathit{yhat} = a\\,x + b"
}
```

| Key | Meaning |
|---|---|
| `outputs` | at least one `{name, type}`; the first is the model's output |
| `inputs` | `{name, type, role}`, optionally `unit`, `bounds`, `value` (constants only) |
| `lets` | name → node; evaluated in dependency order |
| `body` | the output's node |
| `latex` | rendered from the tree; cosmetic |
| `lifted_from` | present when lifted from a workbook (see below) |
| `black_box` | replaces `lets` and `body` for an opaque model |
| `composite` | replaces `lets` and `body` for a composite |
| `constraints` | joint conditions over the model's own parameters (below) |

### Joint parameter constraints

`bounds` are per parameter and some conditions are not. A GARCH model is
stationary only if $\alpha + \beta < 1$: each coefficient may sit anywhere in
$[0, 1]$ while the pair forecast a conditional variance with no finite long-run
mean, and every value-at-risk number computed from it is then meaningless. An
AR(2) is stationary only inside a triangle in $(\phi_1, \phi_2)$. A
Nelson–Siegel curve's instantaneous short rate is $\beta_0 + \beta_1$, which has
to be non-negative however plausible either coefficient looks alone.

A version may therefore declare `constraints`, a list of:

| Key | Meaning |
|---|---|
| `expr` | a node over **parameters only** — `params_of(expr)` must all be declared parameter inputs |
| `op` | `lt`, `le`, `gt` or `ge` |
| `rhs` | a number |
| `why` | what the constraint means, and **mandatory**: it is the only thing a modeller sees when the constraint fires |

```json
{"expr": {"op": "add", "args": [{"param": "alpha"}, {"param": "beta"}]},
 "op": "lt", "rhs": 1, "why": "stationarity: a GARCH(1,1) has a finite long-run variance only if alpha + beta < 1"}
```

They are checked where §8.4 says parameters are checked — **on upload of a
parameter set** — so a set that is individually plausible and jointly impossible
is refused with the arithmetic and the reason:

```text
constraint < 1 is violated: alpha=0.15 + beta=0.9 gives 1.05 — stationarity: a
GARCH(1,1) has a finite long-run variance only if alpha + beta < 1
```

A constraint that reads a feature is refused when the IR is validated, because a
constraint has to hold before any data is seen. Black boxes and composites may
declare them too: both declare parameters, and for a GARCH model — a black box
precisely because its variance is a state carried between rows — stationarity is
the one thing about it a reviewer can still check arithmetically.

A declared bound on a value that is **not** a number is refused rather than
skipped: a scalar bound on an array means one of the two is wrong, and a model
whose parameter genuinely is an array — a black box's weight matrix — declares
no bound on it.

### Node forms

| Form | Meaning |
|---|---|
| `{"op": NAME, "args": [node, …]}` | an operation |
| `{"ref": NAME}` | an input, a let, or `alias.output` inside a composite |
| `{"const": NUMBER}` | a number |
| `{"param": NAME}` | a trained parameter (must be declared as a `parameter` input) |

Each node has exactly one of `op`, `ref`, `const`, `param`.

### Operations

| Op | Arity | Meaning |
|---|---|---|
| `add` | 2 or more | sum |
| `sub` | 2 | difference |
| `mul` | 2 or more | product |
| `div` | 2 | quotient |
| `pow` | 2 | power |
| `neg` | 1 | negation |
| `exp` | 1 | eˣ |
| `log` | 1 | natural logarithm |
| `sqrt` | 1 | square root |
| `abs` | 1 | absolute value |
| `ncdf` | 1 | standard normal CDF |
| `npdf` | 1 | standard normal PDF |
| `max` | 2 or more | maximum |
| `min` | 2 or more | minimum |
| `where` | 3 | `where(condition, if_true, if_false)` |
| `gt`, `lt`, `ge`, `le`, `eq` | 2 | comparisons |
| `and`, `or` | 2 or more | logic |
| `na` | 0 | not available (Excel's `#N/A`); evaluates to NaN |

### Validation

`validate_ir` reports every structural error at once; a draft update with an
invalid IR is refused with the list.

| Error | Cause |
|---|---|
| `node must have exactly one of op/ref/const/param` | a malformed node |
| `unknown op 'foo'` | an op not in the table |
| `op 'div' takes 2 args, got 3` | wrong arity |
| `body: unknown ref 'z'` | a name that is neither an input nor a let |
| `cycle among lets: a -> b -> a` | lets that depend on each other |
| `param 'k' is used but not declared as a parameter input` | a `param` node without a declaration |
| `input 'a' declared twice` | duplicate inputs |
| `input 'q': only a constant carries a value, and it is a number` | `value` on a non-constant |
| `input 'a': bounds must be [lo, hi] with lo <= hi` | bad bounds |
| `at least one output is required` | no outputs |

### The IR hash

The IR hash is SHA-256 over the canonical JSON (sorted keys, no whitespace) of
the IR **without** `latex`. Reformatting an equation, or writing it in LaTeX
instead of text, does not change the hash: `y_{hat} = a \cdot x + b` and
`yhat = a*x + b` produce the same IR. A model version's definition hash covers
the IR hash, the code artifact's hash and the input contract.

## Lifting from Python

A function whose body is assignments followed by one `return` of an expression
can be lifted. Names read from `params["…"]` become parameters; names from
`X["…"]` become features. Calls to `exp`, `log`, `sqrt`, `abs`/`fabs`,
`maximum`/`max`, `minimum`/`min`, `where`, `norm.cdf`/`cdf`/`ncdf`/`norm_cdf`,
and `pdf`/`npdf` (from `math`, `numpy` or `scipy.stats.norm`) map onto IR
operations. Loops, branches, attribute access and unknown calls are refused
with the line named. The output is named `y`.

```python
# A liftable function
def predict(X, params):
    signal = X["momentum"] - X["reversal"]
    return params["beta"] * signal + params["alpha"]
```

```python
# Create the model from it
my.models.create("quant", "tilt", python_source=open("tilt.py").read())
```

## Lifting from a spreadsheet

MAYA walks the formula graph back from one output cell. Numeric cells it reaches
become inputs, formula cells become lets, and defined names name them.

| Supported | Refused (by cell, never approximated) |
|---|---|
| `+ - * / ^`, unary minus, `%`, comparisons | text, dates, `&` |
| `SUM`, `PRODUCT`, `MIN`, `MAX`, `AVERAGE` (ranges allowed) | array formulas |
| `ABS`, `SQRT`, `EXP`, `LN`, `LOG`, `LOG10`, `POWER` | `INDEX`/`MATCH`, `INDIRECT` and other lookups |
| `IF`, `AND`, `OR`, `NOT`, `TRUE`, `FALSE` | volatile and financial functions |
| `NORM.S.DIST`, `NORMSDIST`, `NORM.DIST` | circular references |
| `VLOOKUP`, `HLOOKUP` over a table of constants, exact or approximate (a miss is `na`) | — |
| named cells and ranges | — |

An empty cell reads as 0, as in Excel, and the report says which. A workbook is
limited to 20 MB and 5,000 formula cells in the lifted graph. Unnamed cells are
named by address (`B3`), prefixed with the sheet name (`Inputs_B3`) when the
model spans sheets. `TRUE` and `FALSE` become 1 and 0.

The lift is **checked against the workbook itself**: Excel stores each formula's
last result, and MAYA compares the lifted IR, evaluated at the workbook's own
inputs, with those results.

| Check status | Meaning | Effect |
|---|---|---|
| `agreed` | every cached result reproduced | none |
| `disagreed` | cells listed with both values | the `formula_typechecks` check blocks submit; the CLI exits 1 |
| `unchecked` | the file carries no cached results (never recalculated in Excel) | stated, not assumed |

The lift has been checked against a real spreadsheet engine. Every supported construct, the lookups (including a miss) and a multi-sheet model with named cells were recalculated by LibreOffice Calc, and each lift agrees with its results (`tests/test_spreadsheet_libreoffice.py`). That check found one fix: LibreOffice saves the literal `TRUE` as `TRUE()`, which the lift now reads as the literal. Workbooks saved by Microsoft Excel have not been checked yet.

```python
# Preview the lift, then import it into a draft
data = open("mortgage.xlsx", "rb").read()
preview = my.models.lift_workbook(data, output="Model!B7", roles={"rate": "parameter"})
print(preview["lifted_from"]["workbook"]["check"]["statement"])
my.models.create("credit", "mortgage_payment")
my.models.import_workbook(
    "credit/mortgage_payment",
    data,
    output="Model!B7",
    roles={"rate": "parameter"},
    filename="mortgage.xlsx",
)
```

```bash
# The same from the CLI (--preview stores nothing)
python -m maya.cli model import-workbook credit/mortgage_payment mortgage.xlsx \
    --output Model!B7 --role rate=parameter --preview
```

`lifted_from.workbook` records `filename`, `sha256`, `output`, `cells` (name →
address), `lookups`, `warnings`, the `check` (`status`, `checked`,
`formula_cells`, `disagreements`, `statement`) and, after an import, the stored
workbook's `blob`. The original downloads from the model page, or with
`my.models.workbook(ref, version_no)`.

## Black boxes and vendor models

With no closed form, the IR declares what it can:

```json
# A declared black box
{"outputs": [{"name": "pd", "type": "float64"}],
 "inputs": [{"name": "leverage", "type": "float64", "role": "feature"}],
 "black_box": {"estimates": "12-month probability of default for a corporate obligor",
               "architecture": "gradient-boosted trees, 400 estimators, depth 4"}}
```

Both `estimates` and `architecture` are mandatory. A black box has no reference
code, cannot be scored by MAYA on a warrant's holdout, and its conformance
report says "Skipped" rather than implying a check. Opacity propagates into any
composite that contains it.

## Composites

```json
# An ensemble of two approved models
{"outputs": [{"name": "y", "type": "float64"}],
 "inputs": [],
 "composite": {
   "kind": "ensemble",
   "members": [{"alias": "base", "ref": "maya://model/eq/linear@v1"},
               {"alias": "skew", "ref": "maya://model/eq/skew@v2", "binding": "pinned"}],
   "combine": {"op": "add", "args": [
     {"op": "mul", "args": [{"const": 0.7}, {"ref": "base.yhat"}]},
     {"op": "mul", "args": [{"const": 0.3}, {"ref": "skew.y"}]}]},
   "train": {"mode": "sequential", "order": ["base", "skew"]}}}
```

| Key | Values | Default |
|---|---|---|
| `kind` | `ensemble`, `pipeline`, `router`, `residual`, `hierarchical` | — |
| `members[].alias`, `members[].ref` | a unique alias and a model version | — |
| `members[].binding` | `pinned`, `tracking` | `pinned` |
| `members[].frozen` | true to reuse a member's parameters; then `borrowed_parameter_set` is required | false |
| `combine` | a node over `alias.output` references and the combiner's own names | — |
| `train.mode` | `sequential`, `parallel`, `joint` | `sequential` |
| `train.order` | every alias exactly once | declaration order |

Rules: members run in `train.order`, and in a `pipeline` each member also sees
earlier members' outputs as `alias.output`. Member parameters are namespaced by
alias (`base.a`); the combiner's are bare. The input contract is the union of
the members' contracts; one name wanted with two types is a `ContractMismatch`.
Cycles are refused and nesting is capped at depth 4. A composite's maturity can
never exceed its least mature member's, and approval is blocked while any member
is still `experimental` (`composite_members_mature`).

## Maturity

| Maturity | Meaning |
|---|---|
| `experimental` | the default for a new version |
| `candidate` | set automatically when an experimental version is approved |
| `approved` | set explicitly on the version |
| `restricted` | limited use, set explicitly |
| `deprecated` | superseded, set explicitly |
| `retired` | out of use, set explicitly |

Set it with `my.models.update_draft(ref, maturity="candidate")`.

## The specification document

Every version carries a LaTeX specification, seeded from a template. Submission
requires every section to be present and non-empty.

| Required section |
|---|
| Purpose |
| Scope and Limitations |
| Mathematical Formulation |
| Assumptions |
| Data and Features Used |
| Calibration Methodology |
| Validation Evidence |
| Known Weaknesses |
| Change Log |

| Macro | Expands to |
|---|---|
| `\mayaformula{body}` (or `\mayaformula{}`) | the output equation, rendered from the IR |
| `\mayaformula{full}` | every let and the output |
| `\mayaformula{let:NAME}` | one let |
| `\mayaref{maya://…}` | a reference to another MAYA object |

The document is bound to the IR hash it was last saved against. When the IR
changes under it, the document is marked for re-review and the spec check fails
until it is saved again. `my.models.render_spec(ref, v)` typesets it (Tectonic
when available, otherwise a marked draft render), and `my.models.spec_pdf(ref, v)`
returns the PDF. Outside the `dev` environment, or when
`typeset.require_true_build` is true, approval requires a true LaTeX build
(`spec_true_build`).

### Writing it: the editor

The Specification tab is a split pane — source on the left, a preview on the
right that follows the source within about 200 ms, with KaTeX for the maths.
Around it:

* **Outline and completeness** lists every section in order with its word count,
  marks an empty one, and jumps the editor to a section when you click it.
* **Find and replace** opens with the button or <kbd>Ctrl</kbd>+<kbd>F</kbd>,
  counts the matches, and replaces one or all of them.
* **Bracket matching** marks the pair under the cursor and flags an unmatched
  bracket, in the LaTeX and the Python editors alike.
* **Spell check** is the browser's own, on the prose editor only; the Python
  editor is left alone, because underlining every identifier teaches you to
  ignore the underlines.
* **Insert a figure** embeds the image in the document as base64 comment lines
  and writes the `figure` environment for you, so a figure versions, diffs and
  travels with the text that discusses it. Keep it under 200 kB. The environment
  is guarded with `\IfFileExists`: where the typesetter writes the embedded image
  out, the figure appears; where it does not — which is every build today — the
  PDF prints a labelled box saying the image is in the source, rather than
  failing the build.
* **Bibliography (BibTeX)** keeps the entries in a `filecontents` block inside
  the document and adds `\bibliography{refs}`. `\cite{key}` is numbered in the
  preview against those entries, and built by BibTeX in the PDF.
* **Diff** shows the document side by side, line by line, alongside the
  mathematical diff, with the unchanged stretches counted rather than paged
  through.

The Code tab's editor reports, before you upload, what rung 4 of the ladder
below would refuse — the filesystem, a subprocess, a socket, `eval` or `exec` —
naming the line. The sandbox still has the last word.

## Code artifacts and the validation ladder

A model may carry a Python implementation: a class `Model` with
`fit(self, X, y, ctx)` and `predict(self, X, params, ctx)`.

```python
# model.py: an artifact for the linear model
import numpy as np


class Model:
    def fit(self, X, y, ctx):
        a, b = np.polyfit(np.asarray(X["x"]), np.asarray(y), 1)
        return {"a": float(a), "b": float(b)}

    def predict(self, X, params, ctx):
        return {"yhat": params["a"] * np.asarray(X["x"]) + params["b"]}
```

```bash
# Attach it to the draft
python -m maya.cli model push eq/linear model.py
```

The upload is stored by hash and validated by a job, rung by rung:

| Rung | Passes when |
|---|---|
| 1 parse | the source parses (and `ruff`, when installed, finds no undefined names or syntax errors) |
| 2 entry point | `Model` exists with exactly those `fit` and `predict` signatures |
| 3 import allowlist | every import is on the allowlist: `math`, `statistics`, `random`, `itertools`, `functools`, `collections`, `dataclasses`, `typing`, `json`, `decimal`, `fractions`, `__future__`, `numpy`, `pandas`, `polars`, `pyarrow`, `scipy`, `sklearn`, `statsmodels` |
| 4 static ban | no `open`, `eval`, `exec`, `compile`, `__import__`, `input`, `breakpoint`, `globals`, `locals`, `vars`, `memoryview`, no dynamic `getattr`, no dunder access, no `os`, `sys`, `subprocess`, `socket` and similar modules |
| 5 smoke run | `predict` runs in the sandbox on a sample (10 s CPU, 1 GB, 20 s wall) |
| 6 determinism | a second run gives identical output (a warning, not a failure) |

The artifact passes when rungs 1–5 pass; the report records the sandbox tier.
While validation runs, and if it fails, the `code_artifact_validated` check
blocks submission.

## Conformance: implementation against specification

```python
# Differential test of the artifact against the IR
report = my.models.conformance("eq/linear", 1, n=500)
print(report["statement"])
```

MAYA samples inputs, evaluates the IR, runs the artifact's `predict` in the
sandbox on the same inputs and parameters, and compares them with a relative
tolerance of 1e-9 (absolute 1e-12); both NaN counts as agreement. The report
gives `agreed`, `total`, up to ten `counterexamples` with expected and actual
values, and a statement that begins "Sampled agreement is not proof". A black
box is skipped with that said.

## Semantic diff and reference code

```bash
# What changed in the mathematics between versions
python -m maya.cli model diff quant/bs_call 1 2
```

```text
# Expected output for adding a dividend yield q
- constant 'q' added
- let 'd1' changed: $…$ → $…$ (now uses q)
- output equation changed: $…$ → $…$ (now uses q)
```

The diff (`my.models.diff(ref, v1, v2)`) also reports whether the artifact or
the specification changed. `my.models.reference_code(ref, v)["source"]` returns
Python generated from the IR, **one `predict(X, params)` function** with its
imports and any helpers nested inside it:

```python
# Generated reference code for yhat = a*x + b
def predict(X, params):
    """Compute `yhat`. Generated by MAYA from the formula IR; do not edit.

    X       x
    params  a, b
    returns {'yhat': value}, one entry per row of the inputs.
    """
    import numpy as np

    v_a = params["a"]
    v_b = params["b"]
    v_x = np.asarray(X["x"], dtype=float)
    return {"yhat": ((v_a * v_x) + v_b)}
```

Nothing is left at module scope but `predict`. The generator used to put
`import math`, `import numpy as np` and the normal-distribution helpers
`_erfc`, `_ncdf` and `_npdf` beside it — six names, three of which will collide
with something in whatever codebase the file is pasted into. A composite's
members are nested the same way, each becoming a function *of* `predict` rather
than a sibling beside it, and the callers are unchanged because the one name any
of them asks for is still `predict`.

## The compute-kernel wizard

Everything above assumes a model version exists to hold the mathematics. The
wizard is that translation on its own, before anything is created:
**Models → Design your compute kernel** (`/models/kernel`), or
`my.models.kernel(text, roles=…, name="price")`.

Mathematics goes in — the same notation the designer takes, one equation per
line, intermediates allowed — and four things come back:

| Key | What it is |
|---|---|
| `latex` | the LaTeX rendered **from the tree MAYA parsed**, not from the text you typed, so a misreading is visible before it is stored |
| `ir`, `ir_hash` | the typed IR a version would hold, and its hash |
| `inputs`, `lets`, `output` | the symbols MAYA found, the role it gave each one, the intermediates in evaluation order, and the output |
| `python` | one self-contained function that computes it, named by `name` |

It creates nothing and reads nothing, so any signed-in person may use it. A
formula MAYA cannot read is refused here, with the reason — which is the point,
because the alternative is finding out at `models.create`. When the translation
is right, one button carries the formula and the roles into the designer.

The `python` it returns is deliberately **not** the reference module above:
`to_python_kernel` names the function after the kernel rather than `predict`, so
the whole thing moves as one object into a notebook or somebody else's codebase.
Both generators read the same tree, and a test runs one against the other,
because two generators over one tree that disagree are a bug in one of them.

The four worked examples on the page are chosen for one thing each: Black–Scholes
for a closed form with named intermediates and the normal CDF; a logistic
probability of default for the link function every scorecard ends in;
Nelson–Siegel for the trap that τ is — LaTeX reads an undeclared `tau` as
t·a·u, so a multi-letter symbol has to be declared in the roles to be one
symbol; and a level mortgage payment, one line whose only subtlety is the order
of operations.

## Review, approval and deprecation

| Transition | Checks (default policy) |
|---|---|
| `submit` | `formula_typechecks`, `spec_document_complete`, `code_artifact_validated` |
| `approve` (one `model_manager`) | the three above, plus `spec_true_build`, `composite_members_mature`, `no_open_blocking_comments` |
| `deprecate` | needs a `successor` or a `rationale`; every warrant owner depending on the version is notified |

A failed check names itself: `Blocked by check(s): spec_document_complete — required sections empty: Purpose, …`.

## In the UI

* **Models → Design your compute kernel** (`/models/kernel`): translate
  mathematics into the IR and a Python function without creating anything, then
  carry it into the designer.
* **Models → New model** (`/models/new`): paste equations, lift a workbook, or
  declare a black box.
* **Models** (`/models/{ns}/{name}`): the rendered equations, the input
  contract, the IR, the specification, the artifact report, conformance and
  transitions; **Diff** at `/models/{ns}/{name}/diff`.

[Tutorial 2](/help/guides/tutorial-02-featureset-and-model) takes a model from
LaTeX to approval.
