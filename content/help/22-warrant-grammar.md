---
title: The warrant grammar
slug: warrant-grammar
section: Execution
order: 105
icon: braces
summary: Four independent vocabularies whose product covers every model a bank runs — and the laws that say which combinations mean anything.
audience: Engineers, Quants
---

# The warrant grammar

A warrant is a JSON document an execution engine acts on. It has to describe a
Black–Scholes closed form, a Hull–White calibration, a gradient-boosted PD model,
a logistic scorecard, a prompt bundle, an agent with tools, a credit policy
rulebook, a spreadsheet and a vendor black box — and it has to do it without
becoming a union of special cases, because a union of special cases is a format
that breaks the first time somebody brings a model nobody anticipated.

## The four axes

Every model a bank runs differs along exactly four **independent** axes:

| Axis | Field | Vocabulary |
|---|---|---|
| How the parameter object is inhabited | `parameters.kind` | none, calibration_set, estimated_coefficients, learned_weights, llm_configuration, rule_set, elicited_weights, opaque |
| How the kernel becomes runnable | `realisation.runtime` | quantlib, onnx, pmml, python.callable, container, sql, spreadsheet, rules, solver, llm.prompt, llm.agent, sas, r, matlab, rest, pfa, descriptor_only |
| What is being asked of it | `operation.verb` | score, fit, validate, backtest, explain, simulate, stress, optimise, generate, monitor |
| Where its data comes from | `data.*.binding` | request, inline, feature_namespace, dataset_snapshot, delta_table, sql_query, stream, market_data, document_corpus, scenario_set, artifact |

The grammar is the **product** of those four, not their union. A QuantLib pricer
is `(none, quantlib, score, market_data)`. The Hull–White calibration behind it
is `(calibration_set, quantlib, fit, market_data)` — same runtime, three
different coordinates. An XGBoost PD model is
`(learned_weights, onnx, score, feature_namespace)`. An LLM summariser is
`(llm_configuration, llm.prompt, generate, document_corpus)`.

One structure. Different coordinates.

And it extends the right way: a new model technology is a new **value** in one
vocabulary — almost always a runtime — not a new section, not a new document
type, and not a change to anything that already works.

## The ten sections

Each answers exactly one question.

```json
{
  "maya_warrant": "1.0", "warrant_id": "wrt_…", "issued_at": 1767225600.0,
  "subject":     { …which model and version this is about },
  "operation":   { …what is being asked of it },
  "parameters":  { …where the parameter object comes from },
  "realisation": { …how to obtain and invoke the artifact },
  "data":        { …where inputs come from and where outputs go },
  "io_contract": { …the input and output schemas },
  "constraints": { …the operating boundary and resource limits },
  "authority":   { …who may do this, for what, until when },
  "governance":  { …the state of the record at the moment of issue },
  "signature":   { …integrity }
}
```

An absent section is not an empty one: all ten are required, and a missing one is
reported by name.

## The admissibility laws

A warrant can be well-formed and still be nonsense. These are the rules that make
such a document a refusal rather than a runtime failure — and the important ones
are not invented, they fall out of the algebra already in the platform.

**L-W1 — you cannot fit what has nothing to fit.** The trainability class is
*derived* from how the parameter object is inhabited, and T0 (parameters from
theory) and T6 (parameters inside a vendor black box) are precisely the classes
for which fitting is a type error.

```json
{"law": "L-W1", "path": "operation.verb",
 "detail": "a T0 model cannot be fitted: its parameters come from theory, not
            from data — there is nothing to fit",
 "remediation": "ask for 'score', 'validate' or 'explain'; if this model really
                 is fitted, its parameter_kind and fit_procedure are wrong"}
```

**L-W2 — `generate` needs a generative runtime.** An ONNX graph does not produce
prose.

**L-W3 — training data must be readable as-of.** A training set assembled from a
source with no transaction time cannot be shown point-in-time correct, so it
cannot be shown not to have leaked. Only `dataset_snapshot` and
`feature_namespace` qualify.

**L-W4 — a `fit` must say where its parameters go.** It produces a *new*
parameter object rather than editing the old one, so it needs an output whose
sink is `parameter_object`.

**L-W5 — claimed determinism must be pinned.** An LLM at temperature 0.7 is not
reproducible, and a warrant asserting that it is will be believed by whatever
reads the result. Claim determinism from a stochastic runtime and you must
supply a seed.

**L-W6 — a descriptor-only model cannot be fitted.** Descriptor-only is a
legitimate state: the bank holds the licence, the engine holds the artifact, MAYA
holds the governance. What it cannot carry is an instruction to inhabit a
parameter object nothing on this side can reach.

**L-W7 — a backtest needs outcomes.** Otherwise it is a re-score wearing a
backtest's name.

## Checking a warrant

The grammar is published rather than documented, because a contract nobody can
check is a convention:

```bash
GET  /api/v1/grammar          # the four vocabularies, and what each verb means
GET  /api/v1/grammar/schema   # JSON Schema, generated from the vocabulary
POST /api/v1/grammar/validate # check a document; every problem, not just the first
```

The schema is generated rather than hand-written. A schema maintained separately
from the vocabulary it describes will disagree with it, and the disagreement is
discovered by whoever trusted the schema.

Validation reports **every** problem. Whoever is writing a warrant by hand wants
the whole list, and fixing one error to be told about the next is the worst
possible interface for a document with ten sections.

## Where validation happens

MAYA validates every warrant **before signing it**, never after. A signature over
a non-conforming document would be an assurance that the document is authentic
and not that it is usable, and engines would reasonably read it as both.

So an engine that trusts the signature can also trust the shape.

## Worked examples

Ten of them ship in `examples/warrants/`, spanning QuantLib pricing and
calibration, gradient boosting scored and refitted, a regression scorecard, an
LLM summariser, an agent, a vendor black box, a spreadsheet and a VaR backtest.
Each carries a `_comment` explaining what it demonstrates.

See [warrants by model family](/tutorials/warrants-by-family) for the walkthrough.
