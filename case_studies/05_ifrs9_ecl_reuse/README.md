# Case study 5 — IFRS 9 ECL: reusing features and featuresets across models

> **The demo in one sentence.** A second model over the same entity that
> **reuses five features it did not define**, **composes** its featureset from
> another model's, and **reads that model's output** — so MAYA can answer "what
> breaks if the Merton model changes" from the graph rather than from a
> spreadsheet.

```bash
# Case study 4 first — this one reuses what it registers.
.venv/bin/python case_studies/04_merton_distance_to_default/build.py
.venv/bin/python case_studies/05_ifrs9_ecl_reuse/build.py
```

The script checks, and stops with instructions if you have not.

---

## 1. Why this one exists

Case studies 1–4 each register a model in isolation. Real estates are not like
that: the same `obligor` is described by features a dozen models read, and the
output of one model is the input of the next. **That is where model risk
actually lives** — not in any single model, but in what depends on what.

This case study is about three kinds of reuse, and they are different things.

---

## 2. Reuse #1 — features, shared not copied

`asset_value`, `debt_face`, `asset_vol`, `risk_free`, `horizon` already exist.
Case study 4 registered them against the `obligor` entity. This script does not
redefine them:

```
[1] Find what case study 4 already registered
    ↻ reusing asset_value — already in the catalogue, not redefined
    ↻ reusing debt_face — already in the catalogue, not redefined
    ↻ reusing asset_vol — already in the catalogue, not redefined
    ↻ reusing risk_free — already in the catalogue, not redefined
    ↻ reusing horizon — already in the catalogue, not redefined
```

**Why not just define them again?** Because a second definition of `asset_vol`
is a second answer to *"what is this obligor's asset volatility"*. The two
would drift, the drift would be invisible, and two models would disagree about
one fact while both looked correct. Preventing that is the entire reason a
feature catalogue exists rather than each model carrying its own columns.

Ask MAYA who uses a feature:

```bash
curl -s -u admin:maya-admin-dev \
  http://127.0.0.1:5006/api/v1/features/asset_vol
```

---

## 3. Reuse #2 — the featureset is composed, not rewritten

```python
maya.featuresets.define(
    name="ecl_inputs", entity="obligor", slots={},
    composes=["merton_inputs"],
    operations=[{"op": "add", "name": "pd_horizon", "value": "numeric"},
                {"op": "add", "name": "lgd",        "value": "numeric"},
                {"op": "add", "name": "ead",        "value": "numeric"},
                {"op": "add", "name": "gdp_growth", "value": "numeric"}])
```

```
✓ MAYA: resolved to 9 slots: asset_value, asset_vol, debt_face, ead,
        gdp_growth, horizon, lgd, pd_horizon, risk_free
```

Five of those nine were never typed out in this script. **That is the
difference between reuse and copying**: change `merton_inputs` and this set
changes with it, by construction rather than by somebody remembering.

### The operations are total

MAYA refuses an operation that would change nothing. The script demonstrates it:

```
✓ refused as it should be: adding a slot the composed set already has
  [feature_refused] operation 0: cannot add 'asset_vol' — a parent already has
  it. say 'override' if replacing it is what is meant; the two read differently
  to a reviewer and should
```

An `add` of a slot that exists, a `drop` of one that does not, an `override`
that changes nothing — each is refused, because **an operation that silently
did nothing is one somebody believes happened**. `add` and `override` read
differently to a reviewer, so MAYA makes you say which you mean.

### The featureset carries more than this model reads

Nine slots; the ECL kernel reads four. That is fine and it is the normal case:
**L-W10 checks that the featureset *covers* the kernel's inputs, not that the
two are equal.** A shared analytical dataset serves several models, each
reading its own subset.

---

## 4. Reuse #3 — one model's output is another's input

The ECL is `PD × LGD × EAD`, scaled by a macro overlay:

```
ECL = pd_horizon · LGD · EAD · (1 − β_g · g)
```

`pd_horizon` is **read**, not recomputed. The engine ran the Merton model,
wrote its output back as a feature, and the ECL reads it — which is how a bank
actually wires two models together.

### MAYA refused the first attempt, and was right

An earlier draft of this script inlined the whole Merton formula into the ECL
expression. MAYA rejected the `input_to` edge:

```
maya://model/wholesale.credit.merton_dd does not compose with
maya://model/wholesale.credit.ifrs9_ecl: it produces pd_horizon and
...ifrs9_ecl reads asset_value, debt_face, asset_vol, risk_free, horizon, lgd,
ead, gdp_growth, so this edge carries nothing. An `input_to` edge asserts that
an output arrives where an input is read; one that supplies no field the target
reads is a wire to nowhere, and the blast radius would follow it
```

**This is the best refusal in the whole set.** Most platforms let you draw any
arrow you like on a lineage diagram. MAYA type-checks the edge: the source's
output schema must intersect the target's input schema, or the edge is a lie
that the blast radius would then propagate.

### And then the blast radius is real

```
· before: changing the Merton model reaches 0 other model(s)
✓ MAYA: merton_dd --input_to--> ifrs9_ecl
✓ MAYA: after: reaches 1 model(s), worst tier 2
    → maya://model/wholesale.credit.ifrs9_ecl  (tier 2, distance 1, attested)
· a change here reaches 1 model(s), the most material at tier 2. that is what
  the change process has to cover, and it is computed from the graph rather
  than remembered
```

Not every relation propagates, which is why MAYA makes you name the kind:

| Kind | Propagates? | Means |
|---|---|---|
| `input_to` | **yes** | its output is read as an input by that model |
| `calibrated_by` | yes | its parameters are solved by that model |
| `derives_from` | no | built from it — lineage, not dependency |
| `challenger_of` | no | built to argue with it |
| `benchmark_for` | no | a reference point to judge it against |

A challenger counted as a dependency would inflate every blast radius it
appeared in — which is how dependency graphs become the thing nobody trusts.

---

## 5. The model itself

One estimated parameter: the macro sensitivity `β_g`, regressed on eight
quarters of realised loss multiplier against GDP growth, in this script, under
a training warrant.

```
⚙ engine (not MAYA): b_macro = 0.0614 per point of GDP growth (R²=0.9565, n=8)
```

The output, over the shared book:

```
obligor                 PD %    LGD      EAD      ECL
ACME-INDUSTRIALS        0.01   0.35    180.0     0.00
BOREAL-MINING          37.41   0.55    240.0    51.81
CALDER-RETAIL          41.21   0.62     95.0    25.47
DELTA-UTILITIES         0.00   0.28    410.0     0.00
EASTPORT-SHIPPING      50.50   0.48     70.0    17.80
FENWICK-PHARMA          0.00   0.40    150.0     0.00
GRANITE-REIT            5.02   0.30    320.0     5.06
HARROW-AIRLINES        63.76   0.58     60.0    23.28
```

Portfolio ECL: **123.42** USD millions.

Worth pointing at: `DELTA-UTILITIES` has the largest exposure (410) and
contributes nothing, while `HARROW-AIRLINES` has the smallest (60) and
contributes 23. ECL is a product, and the PD term dominates it.

### Two stated limitations, both on the parameter set

- **The scenario is a single path.** IFRS 9 requires a probability-weighted set
  of forward-looking scenarios. This is one, and the register says so rather
  than implying compliance it does not have.
- **Eight observations** is a small sample for a macro sensitivity, so `n`
  travels with the coefficient instead of being available on request.

---

## 6. What the script does

| Step | What happens | Who does it |
|---|---|---|
| 1 | Find what case study 4 registered; refuse to continue if absent | script |
| 2 | Register only the four features that are **new** | MAYA |
| 3 | Load loss terms + the Merton PD written back as a feature | MAYA |
| 4 | **Compose** `ecl_inputs` from `merton_inputs` | MAYA |
| 5 | **Show a refusal**: an `add` that would change nothing | MAYA |
| 6 | Register the model | MAYA |
| 7 | **Relate the models**; blast radius before and after | MAYA |
| 8–9 | Approve the version; put the record in force | quorum |
| 10–11 | Grants, then the **training warrant** | MAYA |
| 12 | **Estimate the macro sensitivity** | **script** |
| 13 | Deliver it; s.iqbal accepts it | MAYA |
| 14 | **Execution warrant** | MAYA |
| 15 | **Compute the ECL locally** over the joined features | **script** |
| 16 | Write the LaTeX specification | script |

---

## 7. Things to try live

**Retire the Merton view and watch MAYA stop you.**

```bash
curl -s -u admin:maya-admin-dev \
  "http://127.0.0.1:5006/api/v1/feature-views/corporate_balance_sheets/retirable?version=1"
```

It names who is pinning it. A view version a featureset version pins cannot be
retired out from under it.

**Ask the blast radius from the other end.**

```bash
curl -s -u admin:maya-admin-dev -X POST \
  http://127.0.0.1:5006/api/v1/blast-radius \
  -H 'content-type: application/json' \
  -d '{"urn":"maya://model/wholesale.credit.merton_dd"}'
```

**Draw a false edge.** Try `challenger_of` between two unrelated models and
then check the blast radius — it does not move, because that kind does not
propagate.

**Add a sixth model reading `asset_vol`** and watch the feature's consumer list
grow without anybody editing a diagram.

---

## 8. Questions this case study answers well

**"How do we stop the same field being defined five times?"**
Define it once as a feature. This script shows the second model finding it
rather than redefining it.

**"Our models feed each other. Can the platform see that?"**
Yes, and it type-checks the claim. An edge that carries no field the target
reads is refused.

**"What has to be re-approved when we change a model?"**
Ask the blast radius. It is computed from the graph, names the tier of every
model reached, and is therefore an answer rather than a recollection.

**"Does the featureset have to match the model exactly?"**
No — it must *cover* it. One shared dataset, several models, each reading its
own subset.

---

## 9. Files this produces

| File | What it is |
|---|---|
| `warrant-training.json` | The training warrant, naming all nine slots |
| `warrant-execution.json` | The execution warrant |
| `ifrs9-ecl-specification.tex` | Specification, with the reuse table |

```bash
pdflatex ifrs9-ecl-specification.tex     # 2 pages
```
