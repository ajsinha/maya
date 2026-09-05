---
title: An LLM application, end to end
slug: llm-end-to-end
section: Worked models
order: 54
icon: chat-square-text
summary: A complaints-triage assistant registered as a model — where P is a configuration you assembled rather than numbers you fitted, the base model is somebody else's and moves without telling you, and the governed artefact is the prompt, the corpus version, the tool list and the guardrails. Including where the weights go if you host them yourself.
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
| `P` is | base model id + prompt + corpus version + tool list + decoding params + guardrails |
| Filled by | configuration and retrieval, not fitting |
| `parameter_kind` | `llm_configuration` |
| `fit_procedure` | `configure` |
| Derived class | **T5** — configured |
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
                          "base_model":"claude-sonnet-5",
                          "prompt_digest":"sha256:7ac3…"},
                 "deterministic":false,
                 "input_schema":[{"name":"complaint_text","dtype":"text"}],
                 "output_schema":[{"name":"category","dtype":"categorical"},
                                  {"name":"severity","dtype":"categorical"},
                                  {"name":"citations","dtype":"structured"}]}}'
```

Two declarations there are doing load-bearing work.

**`prompt_digest`, not the prompt.** The prompt is an artifact — store it, hash
it, name the hash. A prompt edited in a config file is a model change that left
no trace, and this is the line where that stops being possible.

**`deterministic: false`.** Say so. The grammar knows `llm.prompt` is stochastic
and will refuse a determinism claim that nothing backs:

```json
{"error": "grammar_violation",
 "clause": "L-W6",
 "detail": "the warrant claims determinism for a stochastic runtime",
 "remediation": "declare it non-deterministic, or pin temperature to 0 and seed
                 the provider — and note that neither makes a hosted model
                 reproducible across its own version changes"}
```

The remediation is the honest part. Temperature 0 is not reproducibility when
the weights behind the endpoint can change on a Tuesday.

---

## 2 · The prompt and the corpus are artifacts

```bash
curl -u d.raman:dev-pw -X POST \
  "localhost:5006/api/v1/artifacts?format=json" \
  -H 'Content-Type: application/octet-stream' \
  --data-binary @triage_prompt_v4.json
```

```json
{"digest": "sha256:7ac3…", "size": 8412, "format": "json",
 "uri": "maya://artifact/sha256:7ac3…", "executes_on_load": false}
```

The retrieval corpus is governed as a **featureset version**, for exactly the
reason every other input is: a stable identifier over moving contents is the
failure this platform exists to prevent, and a RAG index is the easiest place in
a modern estate to reintroduce it.

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/featuresets \
  -H 'Content-Type: application/json' \
  -d '{"name":"complaints_policy_corpus","entity":"document_id",
       "owner":"person/j.okafor",
       "slots":{"passage":"text","embedding":"vector","effective_from":"timestamp"}}'
```

"Which version of the policy did it cite in March?" is then a query rather than
an archaeology project.

---

## 3 · The parameter set is the configuration

```bash
curl -u d.raman:dev-pw -X POST localhost:5006/api/v1/parameters \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/ops.complaints.triage","semver":"1.0.0",
       "name":"triage_cfg_v4","kind":"llm_configuration",
       "provenance":"declared",
       "values":{"base_model":"claude-sonnet-5",
                 "provider_version":"2026-08-14",
                 "prompt_digest":"sha256:7ac3…",
                 "corpus":"complaints_policy_corpus","corpus_version":11,
                 "retrieval":{"k":6,"reranker":"none","min_score":0.32},
                 "tools":["policy_lookup","account_status"],
                 "temperature":0.0,"top_p":1.0,"max_tokens":700,
                 "guardrails":["no_customer_pii_in_output",
                               "refuse_outside_complaint_taxonomy"]},
       "as_of":1755129600,
       "diagnostics":{"eval_set":"complaints_gold_v3","n":400,
                      "category_accuracy":0.88,"severity_accuracy":0.79,
                      "citation_precision":0.94,"refusal_rate":0.03}}'
```

`provenance: "declared"` — nothing was fitted. Somebody chose these, and the
register records who, when, and against which evaluation.

**Every field in `values` changes the output.** `k=6` versus `k=10` is a
different model; a tool added is a different model; a guardrail removed is
certainly a different model. If it is not in `P` it is not in the digest, and a
change to it leaves no trace.

---

## 4 · Somebody else's model moves under you

This is the governance problem that has no analogue in the other six tutorials.

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/monitors \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/ops.complaints.triage","kind":"score_drift",
       "test":"eval_regression","threshold":0.05,
       "reference":{"eval_set":"complaints_gold_v3",
                    "baseline":{"category_accuracy":0.88}}}'
```

The gold-set evaluation runs on a schedule and on **every provider version
change**, because the provider version is in `P`: when the gateway reports a new
one, the recorded configuration no longer matches the running one, and that is a
finding rather than a silent upgrade.

Three postures are available and the platform makes you pick one:

| Posture | Means | Cost |
|---|---|---|
| **Pin** the provider version | reproducible until the vendor retires it | you carry the deprecation |
| **Float** with monitoring | current, and the eval tells you when it moved | a gap between change and detection |
| **Self-host** | you own the weights and nothing moves | you own the weights |

If you self-host, this becomes
[the neural network tutorial](/tutorials/neural-network-end-to-end): the
checkpoint goes into the artifact store as `safetensors` or `gguf`, addressed by
its hash, and `held_by_maya` on the warrant becomes true. The 8 GiB cap is
deliberate — a governance platform is not a model store of last resort, and
somebody should have to think before putting a foundation-model checkpoint in
one. Adapters are a different matter: a LoRA is small, it *is* the thing you
trained, and it belongs in the store beside the prompt it was tuned for.

---

## 5 · Serving, and the output nobody has to believe

```bash
curl -u svc/complaints:svc-pw -X POST localhost:5006/api/v1/execute \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/ops.complaints.triage#champion","environment":"prod",
       "principal":"svc/complaints","declared_use":"complaint_triage",
       "verb":"generate",
       "inputs":{"complaint_text":"I was charged twice for the same…"}}'
```

The verb is `generate`, and the grammar only allows it on a generative runtime.
A warrant asking a regression to `generate` is refused by clause, and one asking
an LLM to `score` is told to ask for `generate` instead.

```json
{"outputs": {"category": "billing.duplicate_charge", "severity": "medium",
             "citations": [{"corpus": "complaints_policy_corpus",
                            "version": 11, "passage_id": "P-3312"}]},
 "generation_id": "gen-77213",
 "status": "drafted"}
```

**`drafted`, not decided.** The output is a candidate until a person attests it:

```bash
curl -u ops.agent:agent-pw -X POST \
  localhost:5006/api/v1/assist/generations/gen-77213/attest \
  -H 'Content-Type: application/json' \
  -d '{"accept":true,"note":"category correct; severity raised to high"}'
```

---

## 6 · Where MAYA lets its own AI act

The same machinery governs the platform's own assistance, and the organising
question is not "is the model good enough" but **whether a human can check the
output more cheaply than producing it**.

| Tier | Means | Example here |
|---|---|---|
| **A — verified** | a formal property acts as an oracle; the check *is* the control | proposing a policy rule, then running its cases |
| **B — grounded** | every claim cites platform evidence; ungrounded claims are dropped; a human approves | drafting a validation summary from the evidence chain |
| **C — advisory** | neither. Not registrable | a person using a chat window |

Tier C is deliberately absent from the registry. A Tier C capability in a
registry is a Tier C capability that will one day be wired into a decision.

Two properties of the drafting path are worth copying into your own
LLM applications:

1. **The evidence is gathered first, from the register — not from the model and
   not from the prompt.** What may be cited is fixed *before* the model is
   asked, so a citation it invents has nowhere to land.
2. **A fraction of accepted drafts is pulled for independent review regardless
   of how good they looked.** Deliberate friction against automation bias: a
   reviewer who has approved forty correct drafts is not reviewing the
   forty-first.

---

## 7 · Validating something you cannot inspect

```bash
curl -u a.mehta:val-pw -X POST localhost:5006/api/v1/validations \
  -H 'Content-Type: application/json' \
  -d '{"urn":"maya://model/ops.complaints.triage","semver":"1.0.0","scope":"full",
       "plan":"gold-set accuracy by category and by subgroup; citation precision;
               adversarial prompts; refusal behaviour; PII leakage;
               human override rate in the first 60 days"}'
```

The last item is the one people leave out, and it is the most informative. A
triage assistant overridden 40% of the time is not helping; one overridden 2% of
the time is being rubber-stamped. Both are findings, and only the run record can
tell you which you have.

Adversarial testing is a **sequence** test, not a case test — the same lesson as
[the GARCH](/tutorials/garch-end-to-end#4-scoring-and-the-state-problem) and
[the simulation](/tutorials/monte-carlo-end-to-end): an agent that carries
conversation state cannot be characterised one question at a time.

---

## The end of the series

Seven models, seven media, one definition. What actually differed:

| | `P` | Medium | Class |
|---|---|---|---|
| [Regression](/tutorials/linear-regression-end-to-end) | coefficients | a record | T3 |
| [GARCH](/tutorials/garch-end-to-end) | ω, α, β | a record | T3 |
| [Pricer](/tutorials/derivative-pricing-end-to-end) | empty | — | T0 |
| [Hull–White](/tutorials/hull-white-end-to-end) | a calibration set | a record, daily | T1 |
| [Monte Carlo](/tutorials/monte-carlo-end-to-end) | parameters + seed | a record | T1 |
| [Neural network](/tutorials/neural-network-end-to-end) | weights | an **artifact** | T4 |
| [LLM application](/tutorials/llm-end-to-end) | a configuration | a record + artifacts | T5 |

Nothing in the register had to be special-cased for any of them. That is the
argument for defining a model as `f : P ⊗ X → D(Y)` and deriving everything else
from how `P` is inhabited — and the reason the seventh one fitted without a
redesign is the only evidence for it that counts.
