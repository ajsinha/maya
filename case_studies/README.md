# MAYA case studies

Three worked models, each registered in MAYA end to end, each with a script you
can run in front of an audience and a README written to be talked through.

| | Model | Class | What it is for showing |
|---|---|---|---|
| **1** | [Black--Scholes European call](01_black_scholes/) | **T1** — calibrated | A model with *no training data*. The whole pricer, normal CDF included, lives in the register as an expression |
| **2** | [Home price regression](02_home_price_regression/) | **T2** — estimated | *Real public data*, from its authoritative source — and the clock the source did not have |
| **3** | [Mortgage prepayment curve](03_prepayment_nonlinear/) | **T2** — estimated | *Non-linear* in the inputs, linear in the parameters: an exponential seasoning ramp and a cubic incentive response |
| **4** | [Merton distance to default](04_merton_distance_to_default/) | **T0** — nothing to fit | A model with *no parameters at all*. Asking to train it is a **type error**, and MAYA refuses it as one |
| **5** | [IFRS 9 expected credit loss](05_ifrs9_ecl_reuse/) | **T2** — estimated | **Reuse.** Five features it did not define, a *composed* featureset, and an `input_to` edge that makes the blast radius real |
| **6** | [HELOC origination eligibility](06_heloc_eligibility_rules/) | **T8** — authored | A *policy rulebook* governed as a model: checked, trialled, published, approved by a second person — and every decision carrying the rule that made it |
| **7** | [LLM model documentation](07_llm_model_documentation/) | **AI Tier B** | An LLM drafting a validation-pack section. The platform **removes** the claim citing evidence it does not hold, refuses a Tier C capability outright, and refuses the requester attesting their own draft |
| **8** | [Vendor bureau score](08_vendor_bureau_score/) | **T6** — opaque | Governing a model nobody here can inspect. A fit refused for three reasons at once, reverse-engineered coefficients refused, and the three things that *can* still be governed |
| **9** | [Polygenic risk score](09_polygenic_risk_score/) | **T2** — estimated | **Genomics.** A clinical model whose most important fact is that it works far less well in some ancestries — quantified on the parameter set, so it is read at the same moment as the numbers |
| **10** | [SEIR epidemic model](10_seir_epidemic/) | **T1** — calibrated | **Epidemiology.** The same outbreak data on the same day gives R₀ = 2.04 or 2.34 depending on how the *reporting delay* is treated. The rejected number is recorded beside the chosen one |
| **11** | [RAG customer assistant](11_rag_assistant_config/) | **T5** — configured | **Generative AI.** The system prompt is a parameter. Then the vendor reversions, the bank changes nothing, and the guardrail pass rate falls from 100% to 57% — so the provider change becomes a formal amendment |
| **12** | [Climate transition scorecard](12_climate_transition_elicited/) | **T7** — elicited | **Climate risk.** Weights from a panel, because the transition has not happened and there is nothing to estimate from. The dissent is on the parameter set, priced — and a judgment claiming to have been *fitted* is refused |
| **13** | [Load forecast network](13_load_forecast_trained/) | **T3** — trained | **Energy.** The opacity has to be EARNED: the linear incumbent is registered too, and beating it by 85% is the evidence. The artifact's digest is the model's identity — same code, new seed, different model |

**Order matters twice.** Run 4 before 5, and 2 before 6 — each of those pairs
shares features and an `input_to` edge. Everything else is independent.

Every README opens with a **theory** section: the mathematics of the model, its
assumptions, and where it is known to be wrong — before any of the governance.

### Coverage beyond banking

Case study 9 is the first outside financial services, and the ones after it are
there to make a specific point rather than for variety: **change the vocabulary
and every control is the same.**

| Industry | Case | The control, in that vocabulary |
|---|---|---|
| Genomics | 9 | two clocks with a laboratory in the gap; a limitation quantified on the parameter set; an approval that names the population it is approved *for* |
| Public health | 10 | a reporting delay instead of a servicer lag, with a school closure on the other end instead of a prepayment forecast |
| Climate risk | 12 | parameters that cannot be estimated because the thing has not happened, so a panel — and the dissent travels with the number |
| Energy | 13 | an opacity that has to be earned against a registered incumbent, and an artifact whose digest is its identity |

The two-clock rule appears in every one of them at a different timescale:
fifteen minutes for grid telemetry, five days for notifiable disease, twenty
days for a genotype call, nine months for an emissions disclosure. It is the
same rule.

### Coverage of the taxonomy

MAYA derives a model's **trainability class** from how its parameter object is
inhabited, and the class decides which operations are admissible. Eight of the
nine classes are now covered:

| Class | Parameters come from | Covered by |
|---|---|---|
| **T0** | theory — there are none | case study 4 |
| **T1** | calibration to observables | case studies 1, 10 |
| **T2** | estimation from a sample | case studies 2, 3, 5, 9, 13 (the incumbent) |
| **T3** | iterative training — the artifact IS the parameters | case study 13 |
| T4 | adaptation in production | **deliberately not covered** |
| **T5** | configuration of a generative assembly | case study 11 |
| **T6** | a vendor's parameters you cannot see | case study 8 |
| **T7** | elicitation from a panel | case study 12 |
| **T8** | authoring — a rule set somebody wrote | case study 6 |

**T4 is left uncovered on purpose.** Nothing in this repository adapts in
production, and a case study demonstrating a class the platform has never
carried would be a demonstration of the documentation.

**AI capabilities are governed by a parallel scheme** — tiers A, B and C rather
than T0…T8 — and case study 7 covers Tier B while noting, honestly, that the
design says an AI capability *is* a model while the implementation registers it
beside models rather than as one.

The ends of the range are the interesting ones to show together. **T0** has no
parameters at all and refuses a fit as a type error. **T3** has parameters
nobody can read, so its identity is a digest and its evidence is a benchmark
against something simpler. **T7** has parameters no data produced, so its
evidence is a panel and a dissent. Each refuses a different thing, for a
different reason, in its own words.

---

## The one idea these are built around

**MAYA is a register. It does not train models and it does not run them.**

That is not a limitation to apologise for in a demo — it is the design, and
every script here is written to make the boundary visible. Each one plays the
part of the bank's own modelling engine: it fits in its own process, with its
own arithmetic, and talks to MAYA only to ask permission and to record what it
did.

Read the console output of any of the three and you will see two markers:

```
    ✓ MAYA: ...            something the REGISTER now holds
    ⚙ engine (not MAYA):   something the SCRIPT computed
```

Every fit, every calibration, every prediction is on the `⚙` side. Nothing
crosses.

### The loop, in five steps

Every case study runs the same governed loop. It is worth saying out loud
before running one, because the rest is detail:

1. **Ask MAYA for a training warrant.** Authority *before* any data is read.
   A read performed under an authority that turns out not to exist has already
   happened.
2. **Fit the model locally**, outside MAYA, in the bank's own environment.
3. **Deliver the parameters back** to MAYA under that warrant. They land
   **proposed**, not approved.
4. **Somebody else accepts them.** A number one person can both produce and
   bless is a preference, not an estimate.
5. **Ask MAYA for an execution warrant** — a signed descriptor naming the
   approved parameter set by id and digest — and then **run the model locally**
   under it.

---

## Before you run anything

### 1. Start MAYA

```bash
cd /path/to/maya
.venv/bin/python run_maya_web.py
```

It listens on **5006** by default. Check it:

```bash
curl -s http://127.0.0.1:5006/health
```

To run the case studies against a throwaway instance instead — recommended if
you have an estate you care about — start one on another port with its own data
directory:

```bash
PORT=5099 .venv/bin/python run_maya_web.py --config /tmp/maya-demo/application.yaml
```

...where that config is a copy of `config/application.yaml` with `data.dir`
pointed somewhere disposable.

### 2. Users and roles

**The scripts create the people they need.** You do not have to do this by
hand — `ensure_cast()` in `_common/casekit.py` runs on every build and is
idempotent. But you should know who exists and why, because every interesting
refusal in these demos is a *segregation of duties* refusal, and you cannot
show one with a single administrator account.

| Username | Password | Role | Why they exist |
|---|---|---|---|
| `admin` | `maya-admin-dev` | `admin` | Registers features, models and versions |
| `a.mehta` | `quant-password-long` | `model_developer` | Builds and calibrates. **May not approve their own work** |
| `j.okafor` | `owner-password-long` | `model_owner` | Owns the model record; signs the attestation |
| `s.iqbal` | `mrm-password-long` | `model_risk_manager` | Second line. Signs the version quorum, accepts parameter sets |
| `v.chen` | `validator-password-long` | `validator` | Second line. The other half of a tier 1/2 quorum |

The four roles are **built into MAYA** — you are not creating roles, only
people who hold them. To see them:

```bash
curl -s -u admin:maya-admin-dev http://127.0.0.1:5006/api/v1/roles
```

If you would rather create the people yourself before running a script:

```python
import sys; sys.path.insert(0, "sdk/python")
from maya_sdk import Maya

maya = Maya("http://127.0.0.1:5006", "admin", "maya-admin-dev")
maya.principals.create(username="a.mehta", display_name="Anika Mehta",
                       roles=["model_developer"], password="quant-password-long")
maya.principals.create(username="s.iqbal", display_name="Sana Iqbal",
                       roles=["model_risk_manager"], password="mrm-password-long")
maya.principals.create(username="v.chen", display_name="Wei Chen",
                       roles=["validator"], password="validator-password-long")
maya.principals.create(username="j.okafor", display_name="Jide Okafor",
                       roles=["model_owner"], password="owner-password-long")
```

Or with `curl`:

```bash
curl -s -u admin:maya-admin-dev -X POST \
  http://127.0.0.1:5006/api/v1/principals \
  -H 'content-type: application/json' \
  -d '{"username":"s.iqbal","display_name":"Sana Iqbal",
       "roles":["model_risk_manager"],"password":"mrm-password-long"}'
```

> **Passwords are checked against the platform's floor at creation**, not only
> when they are changed. The long passwords above are not decoration — a short
> one is refused, and the moment a weak password is most likely to be chosen is
> the moment the account is made.

### 3. Run a case study

```bash
.venv/bin/python case_studies/01_black_scholes/build.py
.venv/bin/python case_studies/02_home_price_regression/build.py
.venv/bin/python case_studies/03_prepayment_nonlinear/build.py
.venv/bin/python case_studies/04_merton_distance_to_default/build.py
.venv/bin/python case_studies/05_ifrs9_ecl_reuse/build.py        # after 4
.venv/bin/python case_studies/06_heloc_eligibility_rules/build.py # after 2
.venv/bin/python case_studies/07_llm_model_documentation/build.py # after 4
.venv/bin/python case_studies/08_vendor_bureau_score/build.py
.venv/bin/python case_studies/09_polygenic_risk_score/build.py
.venv/bin/python case_studies/10_seir_epidemic/build.py
.venv/bin/python case_studies/11_rag_assistant_config/build.py
.venv/bin/python case_studies/12_climate_transition_elicited/build.py
.venv/bin/python case_studies/13_load_forecast_trained/build.py   # needs `onnx`
```

**Two of them want something extra.** Case study 2 downloads the Ames housing
data from its authoritative source on first run (`--offline` skips it), and
case study 13 builds an ONNX graph, which needs the `onnx` *authoring* library:

```bash
pip install -r requirements-dev.txt        # brings in `onnx`
```

Worth knowing which is which: **`onnxruntime` executes a graph and is what MAYA
needs**, and it is in `requirements.txt`. **`onnx` authors one** and is only
needed to build the case study's artifact. Nothing about running MAYA requires
it.

Options, on every script:

| Flag | Default | Meaning |
|---|---|---|
| `--url` | `http://127.0.0.1:5006` | Which MAYA instance |
| `--user` / `--password` | `admin` / `maya-admin-dev` | Who registers |
| `--out` | the case study's folder | Where the LaTeX and warrants are written |
| `--offline` | off | Case study 2 only: do not reach the network |

Each writes three files into its own folder:

- `warrant-training.json` — the training warrant, as issued
- `warrant-execution.json` — the execution warrant, as issued
- `*-specification.tex` — the model specification, with the equation **derived
  by MAYA** from the expression it stores

```bash
cd case_studies/01_black_scholes && pdflatex black-scholes-specification.tex
```

**Every one of them is re-runnable.** Run one twice and it will tell you what was
already there rather than failing or silently duplicating.

---

## Three things worth pausing on in a demo

### The equation in the document is not transcribed

MAYA derives LaTeX and Python from the syntax tree it stores, at request time,
and stores neither:

```bash
curl -s -u admin:maya-admin-dev \
  "http://127.0.0.1:5006/api/v1/mathematics?urn=maya://model/alm.prepayment.cpr&semver=1.0.0"
```

A `latex` field somebody filled in would be a second description of one model,
and two descriptions drift — with the one nobody executes drifting first. This
is why the specification PDF and the platform cannot disagree about what the
model is.

Case study 1 pushes this as far as it goes: the *entire* Black--Scholes pricer,
including a rational approximation of the standard normal CDF, is one
expression in the register. There is no artifact to lose and no library version
to argue about, and the script checks it against `math.erf` before registering
it.

### Every case study makes a control refuse

Not "here is the happy path". Each script deliberately asks for something it
should not get, and prints the refusal with its remediation:

| | The refusal shown |
|---|---|
| 1 | A calibration warrant naming a featureset that does not exist; and the author of a parameter set trying to approve it |
| 2 | A training warrant whose read is bounded in only one clock (**L-W9**) |
| 3 | A training warrant against a featureset that does not carry what the kernel reads (**L-W10**) |
| 4 | A training warrant for a model with no parameters — a **type error**, refused twice by two independent layers |
| 5 | An `add` of a featureset slot a parent already has; and an `input_to` edge that would carry nothing |
| 6 | A rule reading a field the version does not declare — refused at `check`, before anybody can approve it |
| 7 | Registering a **Tier C** capability — advisory AI, which is deliberately not registrable; and the principal who asked for a draft attesting it themselves |
| 8 | A fit on an **opaque** model — refused for three independent reasons; and filing reverse-engineered coefficients as that model's parameters |

A control nobody has watched refuse is a control nobody has tested.

### The class and the tier are derived, never declared

Nothing in these scripts says "this is T1" or "this is tier 2". MAYA works both
out — the trainability class from how the parameter object is inhabited, the
tier from exposure, purpose and interpretability — and a script that declared
either would be storing a second opinion beside the platform's.

---

## What these case studies do *not* show

Stated because a demo that only shows what works is a sales pitch.

- **No monitoring, validation or findings.** These build a model up to its first
  approved parameter set. What happens over its life — drift, breaches,
  revalidation, the worklist — is a separate demo.
- **No real market data in case studies 1 and 3.** Both are synthetic, from
  data-generating processes stated in the scripts, and both say so. Only case
  study 2 uses a real public source.
- **Nothing is deployed.** A version is approved and a warrant is issued;
  no engine is wired to anything.
- **The captive engine is deliberately unused.** MAYA ships one for
  demonstrations. Using it here would teach the opposite of the boundary these
  case studies exist to draw.
