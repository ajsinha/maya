# Case study 13 — A trained network that has to earn its opacity

> **The demo in one sentence.** MAYA will not take a machine-learned model's
> word for it: T3's evidence requirement is *a benchmark against a simpler
> incumbent*, so the linear model is registered too, the comparison lives on the
> parameter set, and the artifact's digest — not its description — is what says
> which model was approved.

```bash
pip install -r requirements-dev.txt     # for `onnx`; MAYA needs only onnxruntime
.venv/bin/python case_studies/13_load_forecast_trained/build.py
```

Independent of the other case studies. Runs in about a minute — most of it is
training.

---

## 1. The theory

### The problem

A grid operator forecasts system load an hour ahead, to size spinning reserve
and schedule dispatch. Under-forecast and you buy expensive balancing power;
over-forecast and you pay to keep plant spinning that nobody needs.

Four drivers:

| Feature | Why |
|---|---|
| `temperature_c` | the dominant one, and **non-linear** |
| `hour_sin`, `hour_cos` | the daily cycle, encoded as a circle so midnight is not a cliff |
| `is_weekend` | commercial load falls about 620 MW |

### Why the temperature response defeats a linear model

Electricity load is **U-shaped in temperature**:

```
load                                     
  │╲                                    ╱
  │ ╲                                  ╱     ← cooling: air conditioning
  │  ╲                                ╱
  │   ╲__________________________ ___╱
  │       ↑ heating           ↑ flat
  └────────────────────────────────────────  temperature
   -5        15            22          35
```

Below about 15 °C people heat. Above about 22 °C they cool. Between the two the
response is roughly flat. **A linear model must fit one slope to a relationship
that has two**, and the error it makes is not noise — it is structure, and it is
worst exactly where the grid is most stressed.

That is a genuinely good reason to reach for something opaque, and it is the
kind of reason that is usually asserted rather than measured.

### What T3's fibre actually demands

MAYA's fibre for a machine-learned model asks for soundness evidence as:

> *"why the opacity was worth it, evidenced by a benchmark against a simpler
> incumbent"*

and for outcomes as *"held-out replay; stability under perturbation; subgroup
performance"*, and names the monitoring answer as *"score drift as the leading
indicator, **because the labels arrive late**"*.

Read that first clause again. It is not "document the model". It is: **justify
the opacity, with a measurement, against something simpler.** Most institutions
skip this, or satisfy it with a sentence.

So this case study **registers the incumbent as a model in its own right** —
its own version, its own coefficients, its own approval, its own recorded
limitation. A benchmark that lives in a validation document is a claim. A
benchmark that is a registered, approved, parameterised model is something a
reviewer can re-run next year and disagree with.

```
linear:  R² = 0.7648   RMSE = 384.7 MW
network: R² = 0.9946   RMSE =  58.2 MW
RMSE improvement over the incumbent: 84.9%
```

**Had that been 2%, the honest conclusion would be to ship the linear model.**
The script computes it before anybody claims it, and the number goes on the
network's parameter set as `benchmark_against_incumbent`.

The two models are related in the register with `benchmark_for` — which is
deliberately **non-propagating**: the network does not read the linear model's
output, so a change to the incumbent does not appear in the network's blast
radius. It is how somebody thinks about the two models, not a dependency
between them.

### The U-shape, read out of the trained model

```
    temp C   network MW   linear MW  linear error
        -5         7007        6102          -871
         0         6692        6012          -651
         5         6376        5922          -431
        10         6053        5832          -211
        15         5786        5742            +9
        18         5755        5688           -45
        22         5760        5616          -117
        26         6086        5544          -525
        30         6417        5472          -933
        35         6830        5382         -1443
```

The linear model is **right in the middle and wrong at both ends**, which is
exactly what one slope does to a U. At 35 °C it under-forecasts by 1,443 MW —
on the day the system is closest to its limit.

---

## 2. The artifact is the model

A T3 model's parameters are not a row anybody reads. They are bytes.

```
load-forecast.onnx: 756 bytes, sha256 9255aaa4ac4c095b08fd3671...
```

MAYA stores it by **content address**:

```python
maya.artifacts.put(artifact, format="onnx")
# → digest sha256:9255aaa4..., 756 bytes, stored=False
```

`stored=False` means those bytes were already held. The same file uploaded
twice is stored once — because the store is keyed on what the file *is*, not
on what it was called.

The version is then registered **against the digest**, and MAYA fills in the
rest itself:

```python
maya.versions.create(SHORT, semver="1.0.0", kernel=NETWORK_KERNEL,
                     artifact_digest=f"sha256:{digest}")
```

No `artifact_uri`. The store is the authority on its own contents and supplies
where the bytes are, how big they are and what format they are.

### The demonstration that makes the point

```
seed 11: 9255aaa4ac4c095b08fd3671...  RMSE 58.2
seed 12: 7566cc936d1c71edb433a372...  RMSE 55.2
```

**Same data. Same code. Same architecture. Same hyperparameters. Different
bytes.**

Two models that perform within 3 MW of each other and are *not the same model*.
No description distinguishes them — "a dense 4-12-1 ReLU network trained for
4000 epochs with Adam at lr 0.05" is true of both.

**For a T3, the digest is the only reliable answer to "is this the model we
approved?"** That is why the parameter set's `values` are the digest, the byte
count and the architecture — not seventy-three floats that would be a second,
rotting copy of the file.

And it is why the kernel has **no `parameter_schema`**. For the formula models
in cases 1, 3, 10 and 12, P is a handful of named numbers and listing them is
right. Here P is the artifact.

### The export is verified, not assumed

```
onnxruntime against the numpy that trained it:
worst difference 0.000573 MW over 200 rows
```

That residual is float32 rounding. The check exists because **an export that
silently drops a layer produces a model of exactly the same shape as a good
one**, and nothing downstream can tell — the scores are plausible, the schema
matches, the digest is stable. The only way to know is to score both and
compare.

The scaling and output rescaling are nodes *in* the graph rather than folded
into the weights. Folding is a legitimate optimisation and it would have made
the exported bytes no longer contain the trained numbers. "The artifact is the
model" is a claim worth keeping literally true.

### What the execution warrant carries

```
          digest  sha256:9255aaa4ac4c095b08fd3671e312742...
          format  onnx
            size  756 bytes
    held by MAYA  True
executes on load  False
```

The warrant does **not** carry the model. It carries what an engine needs to
fetch it and check it is the right one — and a fact worth pausing on:

**`executes_on_load: false` is a security property, not a performance one.** An
ONNX graph is *data* an engine interprets. A pickle or a torchscript bundle is
*code*, and loading one in a scoring process runs whatever it contains. MAYA's
artifact store knows which formats are which — `torchscript` and `tar` load in
a sandbox and nowhere else, and there is no `pickle` at all — and the warrant
records which kind it just handed over.

---

## 3. Backtested on weather that happened

**This is the limitation that gets written as a sentence and should be a
number.**

```
on observed temperature: R² = 0.9946  RMSE =  58.2 MW
on forecast temperature: R² = 0.9777  RMSE = 118.4 MW
```

Every performance figure in §1 is measured on the temperature that
**occurred**. Production reads a **day-ahead forecast**, which carries about
1.8 °C of error. On the same held-out hours, with the same model, the error is
**103% higher** — it more than doubles.

Three things follow, and they are the reason this belongs on the record:

1. **The validation report is optimistic by construction**, and not because
   anyone cheated. Backtesting on observed drivers is the natural thing to do.
2. **It cannot be fixed by retraining.** It is a property of the deployment,
   not of the model. Training on forecast temperature would help a little and
   would not close it.
3. **Operational tolerances must be set from the forecast figure.** A reserve
   margin sized on 58 MW of expected error will be breached routinely.

The second-line reviewer's acceptance says exactly that:

> *"Note the forecast-weather degradation: operational tolerances must be set
> from the forecast figure, not the backtest."*

This is the same shape as case study 10's reporting delay and case study 3's
servicer lag: **the model is evaluated on information it will not have.**

---

## 4. Where the tier comes from

```
materiality=moderate (exposure 400,000,000 in band 'moderate',
                      purpose 'risk_management');
complexity=complex (class T3);
tau(moderate,complex)=Tier 2
```

`interpretable=False` is declared honestly — nobody can say why the network
produced this number and not another. Declaring `True` to get a friendlier tier
is precisely the lie the class exists to prevent.

A tier 2 version needs **two signatures in two roles**, which is why the case
studies create four people.

---

## 5. Setting up the people

The script creates them if they do not exist (`_common/casekit.py`):

| Login | Name | Role | Does here |
|---|---|---|---|
| `a.mehta` | Anika Mehta | `model_developer` | trains both models, delivers both parameter sets |
| `j.okafor` | Jide Okafor | `model_owner` | owns both |
| `s.iqbal` | Sana Iqbal | `model_risk_manager` | **accepts** both; signs the quorum |
| `v.chen` | Wei Chen | `validator` | second quorum signature |

Manually, if you prefer:

```bash
curl -s -XPOST localhost:5099/api/v1/principals -H 'Content-Type: application/json' \
  -d '{"login":"a.mehta","display_name":"Anika Mehta","roles":["model_developer"],
       "password":"quant-password-long"}'
```

---

## 6. What the script does

| Step | Who | What |
|---|---|---|
| 1 | ⚙ engine | Generate 2,400 hours; hold out 600 |
| 2 | ⚙ engine | Fit the **incumbent first** — it is the benchmark |
| 3 | ⚙ engine | Train the network; measure the improvement |
| 4 | ⚙ engine | Export to ONNX; **verify** it against the training code |
| 5 | ⚙ engine | Retrain with a different seed → **a different digest** |
| 6 | ⚙ engine | Re-score on **forecast** temperature |
| 7–10 | ✓ MAYA | People; features; load with both clocks; featureset |
| 11 | ✓ MAYA | **Register the incumbent properly** — version, tier, approval, coefficients, acceptance |
| 12 | ✓ MAYA | Store the artifact by content address |
| 13–14 | ✓ MAYA | Register the network and its version **against the digest**; tier it |
| 15 | ✓ MAYA | Relate them with `benchmark_for` (non-propagating) |
| 16–18 | ✓ MAYA | Quorum approval; record in force; grants |
| 19 | ✓ MAYA | **Training warrant** |
| 20–21 | ✓ MAYA | Deliver the parameter set (the digest); a second person accepts |
| 22 | ✓ MAYA | Execution warrant, carrying the artifact's identity |
| 23 | ⚙ engine | Forecast across the temperature range **locally, through ONNX** |
| 24 | — | Write the LaTeX specification |

MAYA never trains and never scores. **MAYA does have a captive ONNX engine**, and
this case study deliberately does not use it — the boundary being demonstrated
is the one where the bank runs its own models.

---

## 7. The data

**Synthetic**, from a data-generating process written out in `true_load()`: a
piecewise-linear heating and cooling response, two Fourier terms for the daily
cycle, a weekend offset, and 55 MW of Gaussian noise as the irreducible floor.

The network's held-out RMSE is 58.2 MW against that 55 MW floor, so it is
close to optimal — which is the point of stating the floor. A model that beats
its noise floor has been given a look at the answer.

The temperature response shape and the rough breakpoints are realistic; the
coefficients are not calibrated to any real grid.

---

## 8. Things to try live

**Make the world linear.** Set `cooling = 0` in `true_load()` and re-run. The
incumbent's R² jumps, the improvement collapses, and the case for the network
evaporates — which is exactly what the benchmark is *for*. Then ask what the
organisation would have done with a 3% improvement and a sunk quarter of work.

**Widen the forecast error.** Push `FORECAST_SD_C` to 3.0 and watch the
deployed error grow again. The backtest never moves.

**Change `interpretable` to `True`** and re-tier. Watch the tier fall. Nothing
in the platform catches it — tiering reads what it is told.

**Retrain and re-upload without bumping the version.** MAYA holds the new bytes
under a new address; the approved version still points at the old digest, and
the warrant still fetches the model that was approved. That is the control
working: **you cannot swap a T3's weights underneath its approval.**

**Ask what `benchmark_for` does to the blast radius.** Nothing, on purpose. Then
ask what `input_to` would have done, and why using it here would have been
wrong.

---

## 9. Questions this case study answers well

**"How do you govern a model nobody can explain?"**
By making it earn the opacity against something simpler, with a number, on the
record. Interpretability is not the only control — *justified* opacity is.

**"What are a neural network's parameters, for governance purposes?"**
The artifact, identified by digest. Not a description of the architecture, which
is true of infinitely many different models.

**"We retrain weekly. Does that mean a new version every week?"**
A new *parameter set* every week, against the same version, each delivered under
a warrant and accepted by a second person. A new version only when the kernel
changes — the architecture, the inputs, the output. And the digest is what makes
"which weights were live on the 14th?" a question with an answer.

**"Why does the fibre want score drift rather than performance?"**
Because the labels arrive late. You learn the actual load an hour later, and for
most machine-learned models in a bank you learn the outcome in months. The
distribution of the scores moves first, and it is observable immediately.

---

## 10. What was not done

Named, because the same fibre asks for them:

- **Subgroup performance** by season and by weekday.
- **Stability under input perturbation.**

Both are recorded on the parameter set under `not_measured` rather than left to
be discovered. A T3 model whose diagnostics claim only the things that went well
is a T3 model nobody has finished validating.

---

## 11. Files this produces

| File | What it is |
|---|---|
| `load-forecast.onnx` | The artifact — 756 bytes, and the model itself |
| `warrant-training.json` | The training warrant |
| `warrant-execution.json` | The execution warrant, carrying the artifact's identity |
| `load-forecast-specification.tex` | Specification, with the benchmark and both error figures |

```bash
pdflatex load-forecast-specification.tex     # 3 pages
```
