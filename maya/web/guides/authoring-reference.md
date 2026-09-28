# What each designer expects

This page lists what MAYA needs from you on each authoring screen: the model, a feature, a feature set, and the two warrants. The same points appear as a short **What this needs** panel on each screen, and each panel links to its section here. Everything below is checked by MAYA itself. When something is wrong, the message names the rule and, for code, the line.

## Models

A model has two parts, and they are checked separately. The **definition** is the mathematics MAYA can read and evaluate. The **artifact** is the code that actually runs. For a model with a formula, MAYA compares the two. For a declared black box there is no formula, and the artifact is what MAYA runs to score it.

### Defining the mathematics

There are four ways to define it, chosen on the **New model** screen.

| Way | What you supply |
|---|---|
| Formula text | Lines like `d1 = (log(S/K) + r*T) / (sigma*sqrt(T))`, ending with the output, e.g. `price = S*ncdf(d1) - K*exp(-r*T)*ncdf(d2)`. Python-like or LaTeX-lite. |
| Python function | One function, pasted or loaded from a `.py` file (rules below). |
| Excel workbook | An `.xlsx` whose cells hold the formula, and a roles list. |
| JSON IR | The intermediate representation itself, for tools that generate it. |

**Roles.** Every name the formula uses is an *input*. By default an input is a **feature**, a column that comes from data. List the others in the roles box, one per line: `sigma: parameter` for something fitted, `r: constant` for something fixed.

### The Python function rules

MAYA reads the function and turns it into its own formula. It does not run it. So the function must be simple enough to read as mathematics:

- **one function**, whose body is **assignments followed by a single `return`**. Docstrings are fine.
- **no loops, no `if` statements, no other calls or attribute access.** Use `where(condition, a, b)` for a choice.
- **functions it understands:** `exp`, `log`, `sqrt`, `abs`, `max`/`maximum`, `min`/`minimum`, `where`, and the normal distribution's `cdf`/`ncdf`, `ppf`/`ncdfinv` and `pdf`/`npdf`. These can be written plain (`exp(x)`) or with a module prefix (`math.exp(x)`, `np.exp(x)`, `norm.cdf(x)`). `math.pi` and `math.e` are constants.
- **features** are plain names, or `X["name"]`. **Parameters** are written `params["name"]` (`theta[...]` or `p[...]` also work).
- the output is called `y`.

```python
def pd_logit(income, utilisation, params):
    z = params["b0"] + params["b1"] * log(income) + params["b2"] * utilisation
    return 1 / (1 + exp(-z))
```

Anything else is refused with the line number rather than approximated.

### The Python artifact

The artifact is the implementation your team actually runs. It is uploaded on the model's page, pasted or loaded from a `.py` file. It must contain a **class named `Model`** with exactly these two methods and argument names:

```python
import numpy as np


class Model:
    def fit(self, X, y, ctx):
        """Return the fitted parameters as a dict. MAYA does not call this itself."""
        return {}

    def predict(self, X, params, ctx):
        """One prediction per row."""
        return params["a"] * X["x"] + params["b"]
```

- **`X`** is a dict of column name to NumPy array, one entry per model input, all the same length.
- **`params`** is a dict of parameter name to value, the approved parameter set.
- **`ctx.seed`** is an integer seed. Use it for any randomness, so the same input gives the same output.
- **`predict` returns** one value per row: an array or list. For a model with several outputs, return a dict of output name to array.
- **Imports allowed:** `math`, `statistics`, `random`, `itertools`, `functools`, `collections`, `dataclasses`, `typing`, `json`, `decimal`, `fractions`, `numpy`, `pandas`, `polars`, `pyarrow`, `scipy`, `sklearn`, `statsmodels`.
- **Not allowed:** files, processes, the network and dynamic code. That means no `os`, `sys`, `subprocess`, `socket`, `pathlib`, `io`, `pickle`, `threading` or `urllib`, and no `open`, `eval`, `exec`, `compile`, `__import__`, `getattr` or double-underscore attributes.
- **Limits:** it runs in a sandbox with about 10 seconds of CPU, 1 GB of memory and 20 seconds of wall time per run, and no network.

On upload MAYA runs a six-step ladder: parse, the `Model` class and method signatures, the import allowlist, the static ban, a smoke run on a sample, and a repeatability check (the smoke run twice, compared). When the model has a formula, it then compares `predict` with the formula on sampled inputs and reports any rows where they disagree.

## Features

A feature is a governed column (or several) of data, with a time index, a source and rules.

- **Kind of definition:** *from a source* (an upload, a Delta table, a SQL query or a Python producer); *derived* (an algebra operator over other features); or *extends a parent* (store only the difference from another feature's version).
- **Index:** the columns that identify a row. The **first index column is the event date**, when the value is true of the world. Others, such as `symbol` or `account`, make it a panel.
- **Schema:** each attribute's name and type. Types include `float64`, `int64`, `bool`, `string`, `date`, `timestamp`, `decimal(18,6)`, `list<float64>`, and fixed vectors and tensors.
- **Knowledge-time column (optional):** the source's own publication time. Without one, the value is known from the moment you upload it. This second clock is what makes a pin point-in-time.
- **Rules** fill gaps, one per attribute or a default: `forward_fill(limit=3, max_age=5)`, `constant(v=0)`, `zero`, `mean_of_window(n=5)`, `last_known_as_of(lag=1)`, `previous_period` or `none`. `backward_fill`, `linear_interp` and `spline_interp` are **non-causal**: they use the future, and a training warrant refuses them unless the warrant carries a written justification.
- **Quality contract:** a JSON list of checks, each blocking a pin when it fails. The checks are `not_null`, `unique_on_index`, `range`, `allowed_values`, `monotonic`, `max_daily_change`, `row_count_between` and `freshness_within`. For example, `[{"check": "not_null", "attr": "close"}, {"check": "range", "attr": "close", "min": 0}]`.
- **A SQL source** is one `SELECT`, with parameters written `:name`. It is reviewed at approval.
- **A Python source** is a function **`produce(params)`** at module level, taking exactly one argument. It returns columns (`{"date": [...], "close": [...]}`) or records (`[{"date": ..., "close": ...}]`). It runs in the same sandbox as an artifact, under the same import rules plus `datetime` and `calendar`. It can compute but cannot fetch.

## Feature sets

A feature set joins features on a shared index, so a model reads one table.

- **Members:** each row maps an **attribute name** in the set to a **feature reference** and the source attribute in that feature. It can also carry a type cast and a fill rule.
- **Index:** the set's key columns, comma-separated, e.g. `date, symbol`. Every member must carry them, or be aligned to them.
- **Grid:** `as_is` keeps the rows the data has. A calendar (`ISO_business_days`, `NYSE`, `LSE`, `TARGET`, `natural_days`) puts every key on that calendar.
- **Alignment:** `inner` keeps keys every member has, `outer` keeps keys any member has, and `left` follows one driving member. `asof` joins the other members to the driving member's dates within a tolerance in days, looking `backward` (the usual choice) or `forward`.
- **Pinning:** a feature set can only be pinned when every member is pinned. **Cascade** pins the members under the same name and date in one job, and rolls them all back if one fails.

## Training warrants

A training warrant licenses a fit before it happens. It is also the only way to download training data.

- **Model version:** an approved one.
- **Feature set:** a **sealed pin** is best, e.g. `maya://featureset/ns/panel#q1/2026-03-31`, because it never moves.
- **Target:** the attribute the model is fitted to predict.
- **Bindings (JSON):** only where a model input's name differs from the feature set attribute, e.g. `{"income": "gross_income"}`.
- **Split:** train, validation and test fractions that **add up to 1**. The default is 0.7, 0.15 and 0.15. Rows are assigned by hashing the seed and the row's key, so the split is the same anywhere.
- **Seed:** fixes the split and anything random in the fit.
- **Holdout:** `escrowed` (the default) keeps the test rows sealed. Scoring on them is counted per warrant. Choose `none` only when there is no holdout.
- **Leakage lag (days):** how late a value may be known after its event date. Rows known later are violations on the **leakage certificate**, which must be clean, or carry a written justification, before the warrant goes forward.
- **Non-causal fills:** refused unless you allow them and write why.

## Execution warrants

An execution warrant licenses a trained model to run, where, and until when.

- **What runs:** a sealed training warrant and its **approved parameter set**. For a model with nothing to fit, name the model version instead.
- **Environments:** where it may run, e.g. `dev, prod`. A call from any other environment is refused.
- **Escalation contact:** named in every refusal, so the person who hits one knows who to call.
- **Valid (days):** after this it expires, and every call fails closed.
- **Covenants (JSON list):** conditions checked on every reported run. A breach **suspends the warrant at once**.

```json
[
  {"kind": "input_null_rate", "attr": "income", "max": 0.05},
  {"kind": "input_range",     "attr": "utilisation", "min": 0, "max": 1.5},
  {"kind": "input_psi",       "attr": "income", "max": 0.25},
  {"kind": "output_range",    "min": 0, "max": 1},
  {"kind": "max_rows_per_day", "max": 1000000},
  {"kind": "staleness_days",  "attr": "income", "max": 5}
]
```

An `input_psi` covenant with no baseline gets one from the data the training warrant was drawn on. **Limits** (`max_calls_per_day`, `max_rows_per_call`, `max_rows_per_day`) cap use rather than suspend: once today's allowance is spent, no token or bundle is issued until tomorrow.
