---
title: An LLM application, end to end
slug: llm-end-to-end
section: Worked models
order: 54
icon: chat-square-text
summary: A complaints-triage assistant registered as a model — where P is a configuration you assembled rather than numbers you fitted, the base model is somebody else's and moves without telling you, and law L-W13 refuses a warrant that names a family of weights instead of a build. Including what MAYA does not run, and how its own machine assistance is governed differently from yours.
audience: Model developers, Model risk managers, Validators
---

# An LLM application, end to end

The hardest question here is not technical. It is: **what is "the model"?**

Not the base model — you did not train it, cannot inspect it, and it will be
replaced under you. Not the prompt alone, which does nothing by itself. The
governed object is the **assembly**, and once you say so the rest follows.

**What you are building.** A complaints-triage assistant: it reads an inbound
customer complaint, proposes a category and a severity, and cites the policy
paragraphs it relied on. A human decides.

| | |
|---|---|
| `P` is | base model + build + prompt + corpus version + tools + decoding + guardrails |
| Filled by | configuration and retrieval, not fitting |
| `parameter_kind` | `llm_configuration` |
| `fit_procedure` | `configure` |
| Derived class | **T5** — foundation / pretrained |
| Runtime | `llm.prompt` (or `llm.agent` if it acts) |
| The catch | the base model moves, and it is not yours |

---

## 1 · Register the assembly

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/models \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/ops.complaints.triage","name":"Complaints triage",
       "model_class":"ops.classification","domain":"operations",
       "owner":"person/j.okafor","legal_entity":"LE-UK-01",
       "purpose":"Propose a complaint category and severity for human decision"}'

curl -u d.raman:dev-pw -X POST \
  localhost:5006/api/v1/models/ops.complaints.triage/versions \
  -H 'Content-Type: application/json' \
  -d '{"semver":"1.0.0",
       "kernel":{"parameter_kind":"llm_configuration","fit_procedure":"configure",
                 "runtime":"llm.prompt",
                 "entry":{"provider":"internal-gateway",
                          "base_model":"gw-instruct-l",
                          "base_model_version":"2026-08-14.3",
                          "prompt_digest":"sha256:7ac3…"},
                 "deterministic":false,
                 "input_schema":[{"name":"complaint_text","dtype":"text"}],
                 "output_schema":[{"name":"category","dtype":"categorical"},
                                  {"name":"severity","dtype":"categorical"},
                                  {"name":"citations","dtype":"structured"}]}}'

curl -u j.okafor:owner-pw -X POST \
  localhost:5006/api/v1/models/ops.complaints.triage/assess \
  -H 'Content-Type: application/json' \
  -d '{"exposure":0,"purpose_class":"risk_management",
       "feature_count":0,"uses_alternative_data":true,"interpretable":false}'
```

```json
{"tier": 2, "materiality": "low", "complexity": "advanced",
 "rationale": "materiality=low (exposure 0 in band negligible, purpose
               risk_management); complexity=advanced (class T5);
               tau(low,advanced)=Tier 2 under ruleset 2026.09.1"}
```

**Tier 2 on a model with no exposure at all.** Complexity carries it: T5 scores
on four components of the meet — an opaque class, generative uncertainty,
unstructured source data, and no claim of interpretability — which is the
ceiling. A drafting assistant that touches no money still gets independent
validation, quarterly monitoring and full documentation, because the control
depth follows the two orders rather than the money alone.

Three declarations in that kernel are doing load-bearing work, and the runtime
vocabulary demands two of them: `RUNTIME_ENTRY["llm.prompt"]` is exactly
`("provider", "base_model", "prompt_digest")`, so a version missing any of the
three is malformed before it is signed. (`llm.agent` asks for
`provider`, `base_model`, `graph` and `max_steps` instead — an agent that can
loop must say how far.)

**`prompt_digest`, not the prompt.** The prompt is an artifact — store it, hash
it, name the hash. A prompt edited in a config file is a model change that left
no trace, and this is the line where that stops being possible.

**`base_model_version`, not just `base_model`.** This is **L-W13**, and it is the
law written for exactly this model shape:

```json
{"law": "L-W13", "path": "realisation.entry.base_model_version",
 "detail": "'gw-instruct-l' names a family of weights rather than a build, so
            this warrant cannot tell two different models apart",
 "remediation": "pin the provider's version alongside the model name; if the
                 provider will not expose one, say so by recording the date the
                 configuration was evaluated, and expect the drift monitor to be
                 your only warning"}
```

`base_model` names a family. The weights behind that name are replaced by
whoever hosts them, on their schedule, and the replacement is not announced in
the answer — so a warrant carrying only the family name describes a model that
can change under it between two runs **while every field in the document stays
identical**. That is the failure this platform exists to prevent, wearing
generative clothes: a stable identifier over moving contents. It is the same
failure the two clocks prevent in data, and the same one content addressing
prevents in
[the neural network's weights](/tutorials/neural-network-end-to-end#1-where-the-bytes-actually-live).

Pinning does not stop the vendor retiring a build. It makes the retirement
visible as a **mismatch** rather than as a drift.

**`deterministic: false`.** Say so, because here the grammar can actually check
it. `STOCHASTIC_RUNTIMES` holds exactly `llm.prompt` and `llm.agent`, so a
determinism claim on this runtime with no seed is refused by **L-W5**:

```json
{"law": "L-W5", "path": "operation.seed",
 "detail": "the 'llm.prompt' runtime is not deterministic unless it is pinned,
            but this operation claims determinism",
 "remediation": "set operation.seed, or declare determinism as 'stochastic'"}
```

This is the *only* one of the seven tutorials where that law fires. The
[Monte Carlo engine](/tutorials/monte-carlo-end-to-end#1-the-seed-is-a-parameter-not-a-setting)
declares `deterministic: true` on a `container` and is signed without complaint,
because MAYA cannot derive that a container is stochastic. It can derive it here,
from the runtime, so it does.

And the remediation is the honest part. Temperature 0 is not reproducibility
when the weights behind the endpoint can change on a Tuesday. Pinning the seed
buys you reproducibility *within a build*; `L-W13` is what tells you the build
moved.

---

## 2 · The prompt is an artifact; the corpus is a binding

```bash
curl -u d.raman:dev-pw -X POST \
  "localhost:5006/api/v1/artifacts?format=json" \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @triage_prompt_v4.json
```

```json
{"digest": "sha256:7ac3…", "size": 8412, "format": "json",
 "uri": "maya://artifact/sha256:7ac3…",
 "means": "a JSON document: a rule set, a scorecard, a configuration",
 "executes_on_load": false, "stored": true, "detail": "0.0 MB"}
```

Same store, same eight formats, same closed list as the network's weights — and
the same guarantee falls out for free: an edited prompt is a different address,
so a prompt cannot be changed in place, and two versions that share a prompt
share one stored copy.

The retrieval corpus is **not** an artifact and **not** a featureset. The
grammar has a binding for it:

```json
"data": {"inputs": [{"name": "policy", "binding": "document_corpus",
                     "corpus": "complaints_policy", "revision": 11},
                    {"name": "complaint", "binding": "request"}]}
```

`document_corpus` carries `corpus` and `revision`, and the `revision` is what
makes *"which version of the policy did it cite in March?"* a query rather than
an archaeology project. A RAG index is the easiest place in a modern estate to
reintroduce a stable identifier over moving contents, and this is the field that
stops it.

---

## 3 · The parameter set is the configuration

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/ops.complaints.triage","semver":"1.0.0",
       "name":"triage_cfg_v4","kind":"llm_configuration",
       "provenance":"declared",
       "values":{"base_model":"gw-instruct-l",
                 "base_model_version":"2026-08-14.3",
                 "prompt_digest":"sha256:7ac3…",
                 "corpus":"complaints_policy","corpus_revision":11,
                 "retrieval_k":6,"reranker":"none","min_score":0.32,
                 "tools":"policy_lookup,account_status",
                 "temperature":0.0,"top_p":1.0,"max_tokens":700,
                 "guardrail_no_pii":1,"guardrail_taxonomy_only":1},
       "as_of":1755129600,
       "diagnostics":{"eval_set":"complaints_gold_v3","n":400,
                      "category_accuracy":0.88,"severity_accuracy":0.79,
                      "citation_precision":0.94,"refusal_rate":0.03}}'
```

**`provenance: "declared"`, and it is the only one of the three that fits.**
`fitted` means estimated or trained from data under a warrant MAYA issued;
`calibrated` means solved against market instruments; `declared` means asserted
by a person — parameters from theory, elicited weights, an authored rule set, or
this. Only `fitted` is required to name a warrant, and only `declared` may arrive
without one, because a fit is evidence and a declaration is an assertion. The
register records who asserted it, when, and against which evaluation.

Try `fitted` here and MAYA will take it, which is worth knowing: the refusals
guarding provenance are `nothing_to_fit` for a terminal `P` and
`parameters_not_reachable` for an opaque one. A `llm_configuration` is neither,
so the honesty of this field is a discipline rather than a check.

**Every value in there changes the output.** `retrieval_k` of 6 versus 10 is a
different model; a tool added is a different model; a guardrail removed is
certainly a different model. If it is not in `P` it is not in the digest, and a
change to it leaves no trace. Note the flattening: the register holds up to
4,096 values inline and stores integers rather than booleans throughout, so
`guardrail_no_pii: 1` rather than a nested object with a `true` in it.

Four eyes apply here exactly as they do to a fitted set — `self_approval`
refuses whoever recorded it — and a **training record** compiles against this
parameter set just as it does for a Hull–White solve:

```bash
curl -u a.mehta:val-pw -X POST \
  localhost:5006/api/v1/parameter-sets/ps-9911/review \
  -H 'Content-Type: application/json' \
  -d '{"accept":true,"note":"gold-set v3, 400 items; citation precision 0.94"}'

curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/training-records/ps-9911
```

Its authority section will read *"Declared rather than fitted: these values were
chosen and recorded, not produced by reading data, so there is no fit warrant
behind them"* — a filled section rather than a gap, because the record knows the
difference between an absent warrant and a warrant that was never needed.

---

## 4 · Somebody else's model moves under you

This is the governance problem with no analogue in the other six tutorials.

Three postures are available and the platform makes you pick one:

| Posture | Means | Cost |
|---|---|---|
| **Pin** the provider version | reproducible until the vendor retires the build | you carry the deprecation, and a retirement arrives as a hard mismatch |
| **Float** with monitoring | current, and the eval tells you when it moved | a gap between the change and the detection, which is however long your cadence is |
| **Self-host** | you own the weights and nothing moves | you own the weights |

`L-W13` does not force the first. It forces you to *say which*: a warrant that
carries `base_model_version` is pinned, and one that carries only the date the
configuration was evaluated is floating and admits it. What the law refuses is
the third state — the one that looks pinned and is not.

The gold-set evaluation runs on a schedule and on **every provider version
change**, because the provider version is in `P`: when the gateway reports a new
one, the recorded configuration no longer matches the running one, and that is a
finding rather than a silent upgrade.

If you self-host, this becomes
[the neural network tutorial](/tutorials/neural-network-end-to-end): the
checkpoint goes into the artifact store as `safetensors` or `gguf`, addressed by
its hash, `held_by_maya` on the warrant becomes true, and `L-W12` starts applying
instead of `L-W13`. The 8 GiB cap is deliberate — *a governance platform is not a
model store of last resort*, as the refusal itself says — and somebody should
have to think before putting a foundation-model checkpoint in one. Adapters are a
different matter: a LoRA is small, it *is* the thing you trained, and it belongs
in the store beside the prompt it was tuned for.

---

## 5 · Serving it — and what MAYA does not do

```bash
curl -u j.okafor:owner-pw -X POST localhost:5006/api/v1/warrants \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/ops.complaints.triage#champion","environment":"prod",
       "principal":"svc/complaints","declared_use":"complaint_triage"}'

curl -u svc/complaints:svc-pw -X POST \
  "localhost:5006/api/v1/resolve?verb=generate" \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/ops.complaints.triage#champion",
       "environment":"prod","principal":"svc/complaints",
       "declared_use":"complaint_triage"}'
```

The verb is `generate`, passed as a query parameter, and **L-W2** allows it only
on a generative runtime:

```json
{"law": "L-W2", "path": "operation.verb",
 "detail": "'generate' asks for free-form output, which the 'onnx' runtime does
            not produce",
 "remediation": "use one of llm.agent, llm.prompt, or ask for 'score'"}
```

> **The converse is not a law, and it should not be read as one.** Nothing
> refuses a `score` warrant on `llm.prompt`. The grammar constrains what a
> runtime must be able to *do*, not what somebody may sensibly ask of it — and
> "give me the point estimate from a language model" is a coherent request that
> a caller may have good reasons for. Coherence is not the same as wisdom, and
> the grammar only rules on the first.

**Then MAYA hands the descriptor over and stops.** The captive engine implements
five runtimes — bound callables, ONNX, PMML, QuantLib and the estimator — and no
generative one, so `POST /api/v1/execute` on this model is refused by name:

```json
{"error": "no_runtime",
 "detail": "this engine does not implement the 'llm.prompt' runtime",
 "remediation": "it implements callable, estimator, onnx, pmml, quantlib; route
                 this warrant to an engine that has the runtime, or register the
                 version against one of these"}
```

That is not an apology. **MAYA does not run models**; it issues a signed,
expiring, entitlement-bound contract, and your gateway acts on it. The
convenience engine exists so a deployment works out of the box, and it is
precise about its boundary rather than fluent about it. Your gateway is what
holds the API key, applies the guardrails, retrieves from the corpus revision the
warrant names, and returns the answer.

What the descriptor gives it is the pinned build, the prompt digest, the corpus
revision, the io contract, the entitlement, and sixty seconds of validity. What
it gives *you* is that the answer can be traced to all of them.

---

## 6 · The output nobody has to believe

The application's answer is a **candidate**. Whether it becomes a decision is a
question about your workflow, and the useful discipline is that a person's
agreement is recorded as its own event rather than inferred from the absence of
a complaint.

Two properties of MAYA's own drafting path are worth copying into yours, and
they are both in `core/assist/`:

1. **The evidence is gathered first, from the register — not from the model and
   not from the prompt.** What may be cited is fixed *before* the model is asked,
   so a citation it invents has nowhere to land. Ungrounded claims are dropped
   rather than flagged, and if nothing survives the generation is refused
   outright with `nothing_grounded`: *"a Tier B capability's output is its
   grounded claims; there is nothing left to record."*
2. **A fraction of accepted drafts is pulled for independent review regardless of
   how good they looked.** Deliberate friction against automation bias: a
   reviewer who has approved forty correct drafts is not reviewing the
   forty-first.

The second has a detail that took a bug to get right, and it generalises. The
sampling is **deterministic, seeded on the capability's own generation count**,
not on the clock. Seeded on the clock the sequence was unrepeatable, so no test
could depend on it — and, worse, a drafter watching which of their own drafts
were sampled could infer the rate and time their work around it. A review sample
an author can predict is not a review sample.

---

## 7 · Where MAYA lets its own AI act

The same machinery governs the platform's own assistance, and it is worth being
clear that this is a **different subsystem from the model you just registered**.
Your triage assistant is an entry in the register, governed by warrants. MAYA's
own drafting is governed by capabilities, and the organising question is not
"is the model good enough" but **whether a human can check the output more
cheaply than producing it**.

| Tier | Means | Example |
|---|---|---|
| **A — verified** | a formal property acts as an oracle; the check *is* the control | proposing a policy rule, then running its own cases against it |
| **B — grounded** | every claim cites platform evidence, ungrounded claims are dropped, a human attests | drafting a validation summary from the evidence chain |
| **C — advisory** | neither. **Not registrable** | a person using a chat window |

`TIERS` in `core/assist/common.py` is literally `("A", "B")`. Tier C is not a
tier you may register and fail to use well; there is no field to put it in. *"A
Tier C capability in a registry is a Tier C capability that will one day be
wired into a decision."*

A Tier A generation whose oracle rejects it is **not recorded at all** —
`oracle_failed`, because for a Tier A capability the check is the control and
there is nothing to keep. And attestation has its own segregation:

```json
{"error": "self_attestation",
 "detail": "a.mehta requested this generation and cannot also attest it",
 "remediation": "attestation is a person taking responsibility for machine
                 output; it must be somebody other than whoever asked for it"}
```

Until somebody attests it, a generation carries **no weight anywhere in the
platform**. Attestation is the only transition that gives it any, and it records
the edit distance between what was drafted and what was signed — crude on
purpose, because the absolute number means little and the trend for a given
reviewer means a great deal.

---

## 8 · Validating something you cannot inspect

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/validations \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/ops.complaints.triage","semver":"1.0.0",
       "kind":"initial","validators":["a.mehta","r.oyelaran"],
       "scope":["gold_set","citations","adversarial","leakage","override"],
       "plan":{"gold_set":"accuracy by category and by subgroup, gold v3",
               "citations":"precision against the pinned corpus revision",
               "adversarial":"prompt-injection sequences, not single prompts",
               "leakage":"PII in output, over the full gold set",
               "override":"human override rate over the first 60 days"}}'
```

The last item is the one people leave out, and it is the most informative. A
triage assistant overridden 40% of the time is not helping; one overridden 2% of
the time is being rubber-stamped. Both are findings, and only the run record can
tell you which you have.

**Adversarial testing is a sequence test, not a case test** — the same lesson as
[the GARCH scorer](/tutorials/garch-end-to-end#4-scoring-and-the-state-problem)
and [the simulation](/tutorials/monte-carlo-end-to-end), and stronger here than
in either. An `llm.agent` carries conversation state, so it is an artefact that
remembers, and a prompt injection that fails on turn one and succeeds on turn
four is invisible to any suite whose elements have length one.

Monitoring, once it is live:

```bash
curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/ops.complaints.triage","name":"agreement AUC",
       "kind":"performance","test_key":"discrimination.auc",
       "threshold":{"min":0.80},"owner":"person/j.okafor",
       "cadence_days":7,"label_delay_days":2,
       "breach_severity":"High","escalate_after":2}'

curl -u s.iqbal:mrm-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/ops.complaints.triage","name":"confidence PSI",
       "kind":"score_drift","test_key":"stability.psi",
       "threshold":{"max":0.2},"owner":"person/j.okafor","cadence_days":1,
       "reference":{"sample":[0.41,0.55,0.63,0.71,0.78,0.84,0.91]}}'
```

The label is *whether the human agreed*, which for this application is the only
outcome there is, and it arrives in about two days. The score-drift monitor needs
no labels at all and moves first — a provider build change usually shows up as
the confidence distribution shifting days before the agreement rate does.

> **What is not built.** The gold-set evaluation itself is not a MAYA test. The
> catalogue holds eight statistical tests and none of them is "run 400 prompts
> and score the categories" — you run that in your own harness and deliver the
> numbers as parameter-set diagnostics, as in §3, or as a `finding` when it
> regresses. What MAYA gives you is the place the eval set's identity is pinned
> and the second signature that says somebody looked, not the harness.

---

## The end of the series

Seven models, seven media, one definition. What actually differed:

| | `P` | Medium | Class | The law that bites |
|---|---|---|---|---|
| [Regression](/tutorials/linear-regression-end-to-end) | coefficients | a record | T2 | `L-W10` — the featureset must provide what the kernel reads |
| [GARCH](/tutorials/garch-end-to-end) | ω, α, β | a record | T2 | `L-W9` — bounded in both clocks |
| [Pricer](/tutorials/derivative-pricing-end-to-end) | empty | — | T0 | `L-W1` — fitting is a type error |
| [Hull–White](/tutorials/hull-white-end-to-end) | a calibration set | a record, daily | T1 | `L-W11` — a calibration must state its `as_of` |
| [Monte Carlo](/tutorials/monte-carlo-end-to-end) | parameters + seed | a record | T1 | `L-W11`, and `L-W5` deliberately *not* |
| [Neural network](/tutorials/neural-network-end-to-end) | weights | an **artifact** | T3 | `L-W12` — an artifact binding needs a digest |
| [LLM application](/tutorials/llm-end-to-end) | a configuration | a record + artifacts | T5 | `L-W13` — pin the build, not the family |

**One warrant document across all seven.** What differs is which laws refuse, and
every one of those laws quantifies over a fact the platform *derives* —
`trainability_class`, `parameters.kind`, `parameters.source.binding`,
`realisation.runtime` — rather than over a category somebody attached. That is
why the seventh fitted without a redesign, and it is the only evidence for the
definition that counts.

The last column is also an argument about coverage. `L-W12` bites hardest on the
network and applies just as hard to a PMML scorecard, which is T2. `L-W5` does
not fire for the simulation, and the tutorial says so rather than implying it
does. A law keyed on a *class* would have got both of those wrong, and the
mistake would have looked like coverage.
