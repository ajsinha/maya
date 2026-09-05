---
title: Warrants by model family
slug: warrants-by-family
section: The platform
order: 50
icon: diagram-2
summary: Two warrants over the same library, treated completely differently — and the reason is a coordinate rather than a category. One document shape across thirteen worked examples, fourteen admissibility laws that refuse over it, and the thing that genuinely can be templated, which is the request.
audience: Engineers, Quants
---

# Warrants by model family

Start with the pair that makes the argument.

Two warrants ship in `examples/warrants/`. Both are QuantLib. Both name
`"runtime": "quantlib"`. Both are about interest rates. The grammar treats them
completely differently, and nothing about the library, the asset class or the
team decided that.

**`01-quantlib-swaption-price.json`** — a Black swaption price.
`"kind": "none"`, so `P` is the terminal object and the class is **T0**. Ask for
`fit` and it is refused before the signature:

```json
{"law": "L-W1", "path": "operation.verb",
 "detail": "a T0 model cannot be fitted: its parameters come from theory, not
            from data — there is nothing to fit",
 "remediation": "ask for 'score', 'validate' or 'explain'; if this model really
                 is fitted, its parameter_kind and fit_procedure are wrong"}
```

**`02-quantlib-hullwhite-calibrate.json`** — a Hull–White calibration.
`"kind": "calibration_set"`, `fit_procedure: calibrate`, so **T1**. `fit` is
exactly right, and the warrant carries the optimiser, the end criteria and the
calibration helpers.

Same library. Same runtime value. Opposite verdicts, because the *parameter*
coordinate differs.

*Is it AI?* puts both in the same bucket and separates nothing. *How is the
parameter object inhabited?* separates them correctly — and the separation is
what makes the evidence expectations right for each, without anybody
maintaining a list of model types.

---

## One document, four coordinates

A warrant is the product of four independent vocabularies, published at
`GET /api/v1/grammar` rather than described here so an engine need not carry a
copy:

| Axis | Question | Values |
|---|---|---|
| `parameters.kind` | how `P` is inhabited | 8: `none`, `calibration_set`, `estimated_coefficients`, `learned_weights`, `llm_configuration`, `rule_set`, `elicited_weights`, `opaque` |
| `realisation.runtime` | how the kernel becomes callable | 18, including `descriptor_only` |
| `operation.verb` | what is asked of it | 10 |
| `data.*.binding` | where the data comes from | 12 |

The grammar is the **product** of those, not a union of special cases. A new
model technology is a new *value* in one vocabulary — usually a runtime — not a
new section, not a new document type, and not a change to anything that already
works.

`descriptor_only` matters most in a bank, and it is not a degenerate case: much
of the estate already runs inside engines nobody is going to replace, and for
those MAYA carries the governance and the engine carries the model.

---

## Thirteen worked warrants, and no exemptions

```bash
curl -u a.mehta:pw -X POST localhost:5006/api/v1/grammar/validate \
  -H 'Content-Type: application/json' \
  --data @examples/warrants/01-quantlib-swaption-price.json
```

```json
{"valid": true, "problem_count": 0, "problems": [],
 "detail": "conforms to the MAYA warrant grammar v1.0"}
```

Every one of the thirteen validates against the same grammar, which is the test
of whether the four axes were the right ones.

| Example | `parameters.kind` | class | runtime | verb | bindings |
|---|---|---|---|---|---|
| Swaption price | `none` | T0 | `quantlib` | `score` | `request`, `market_data` |
| Vanilla swap price | `none` | T0 | `quantlib` | `score` | `market_data`, `request` |
| Hull–White calibration | `calibration_set` | T1 | `quantlib` | `fit` | `dataset_snapshot` |
| VaR backtest | `calibration_set` | T1 | `python.callable` | `backtest` | `dataset_snapshot` |
| Behaviour scorecard | `estimated_coefficients` | T2 | `pmml` | `score` | `feature_namespace`, `request` |
| NJ linear — the fit | `estimated_coefficients` | T2 | `python.callable` | `fit` | `featureset` |
| NJ linear — the score | `estimated_coefficients` | T2 | `python.callable` | `score` | `request` |
| Gradient-boosting PD | `learned_weights` | T3 | `onnx` | `score` | `feature_namespace`, `request` |
| …being retrained | `learned_weights` | T3 | `python.callable` | `fit` | `dataset_snapshot` |
| KYC summariser | `llm_configuration` | T5 | `llm.prompt` | `generate` | `request`, `document_corpus` |
| Credit-memo agent | `llm_configuration` | T5 | `llm.agent` | `generate` | `request`, `document_corpus`, `feature_namespace` |
| Vendor AML score | `opaque` | T6 | `descriptor_only` | `score` | `stream`, `feature_namespace` |
| Treasury spreadsheet | `rule_set` | T8 | `spreadsheet` | `score` | `request` |

Nothing in that table is a special case. Each row is a different point in one
product space. The two NJ rows are worth looking at together: same model, same
version, same runtime — the fit binds `to_be_fitted` and reads a featureset, the
score binds `parameter_set` with a digest and reads the request. **L-W8** refuses
each in the other's position.

---

## Fourteen refusals, before the signature

A warrant can be well-formed and still be nonsense. These are the rules that
make such a document a refusal at issuance rather than a failure three layers
down inside an artifact loader.

| Law | Refuses | Because |
|---|---|---|
| `L-W0` | a malformed document | ten required sections, a known verb, a known runtime carrying its entry keys, known bindings and sinks carrying theirs. Shape runs first and short-circuits |
| `L-W1` | `fit` on T0 or T6 — **and** a class outside T0–T8 | nothing to fit; or nothing reachable to fit. The second half exists because a class of `"T6 "`, one trailing space, once matched no literal and admitted the fit |
| `L-W2` | `generate` on a non-generative runtime | an ONNX graph does not produce prose |
| `L-W3` | training from a non-bitemporal binding | it cannot be read as-of, so it cannot be shown leak-free |
| `L-W4` | a `fit` with no `parameter_object` sink | a fit produces a new parameter object and must say where it goes |
| `L-W5` | claimed determinism from a stochastic runtime with no seed | an LLM at 0.7 is not reproducible, and the claim would be believed |
| `L-W6` | `fit` on a `descriptor_only` model | you cannot inhabit what nothing on this side can reach |
| `L-W7` | a `backtest` with no outcomes | that is a re-score wearing a backtest's name |
| `L-W8` | a run that will not name its point of `P` | the number would be attributable to nothing. Only a `fit` may leave it unfilled, and a `fit` must bind `to_be_fitted` and nothing else |
| `L-W9` | a featureset **or feature namespace** read for training, unbounded in either clock | the set fixes the columns; the warrant must fix the period. A `dataset_snapshot` is exempt — it is bounded by construction |
| `L-W10` | a featureset that does not provide what the kernel declares it reads | contravariance in inputs — `L-12` one level out, and now literally the same comparison |
| `L-W11` | a calibrated run with no `as_of` | staleness would be silent |
| `L-W12` | parameters bound to an artifact, with no digest | *what ran is what was approved* becomes an assumption |
| `L-W13` | a generative runtime naming a model family but no build | the weights move underneath it, invisibly |

**Thirteen of the fourteen are checked over the document alone.** `L-W10` cannot
be, and the reason is structural rather than incidental: it compares a
*featureset version's* resolved slots against a *model version's* declared input
schema, and neither is in the document being validated. So it is discharged at
issuance, against the register, and refused as `schema_not_satisfied`:

```
409 — 'sb_core' does not provide region, which this version declares it reads.
Bind a featureset whose schema covers the kernel's inputs, or create a model
version whose input schema matches this set — adding a regressor is a model
change, not a data change.
```

---

## Why the last three are the answer to "template warrants per model type"

The recurring ask is that warrants should differ by kind of model. **They
already do — as refusals over one document, never as different documents.**

L-W11, L-W12 and L-W13 are the newest three and the clearest illustration,
because each is keyed on a fact the platform *derives* rather than a category
anybody attached:

**L-W11** keys on `parameters.kind == "calibration_set"`. A calibration
reproduces a market rather than summarising a history, so the moment it was
solved for *is* part of what it means. Two warrants naming the same parameter
set on different mornings are not the same run. Without the stamp, yesterday's
swaption fit prices today's book, produces an entirely ordinary-looking number,
and nothing in the record says which market it came from. The law requires the
age to be **statable**, not small — how old is too old depends on the cadence,
and that is a policy gate's question.

**L-W12** keys on the *source binding* being `artifact`. When the parameter
object **is** the file, *which numbers did this run at* and *which bytes did it
load* are the same question, and an undigested binding answers neither. Notice
it is deliberately **not** written in terms of the class: it bites hardest on a
neural network, and a PMML scorecard is T2 with exactly the same exposure —
keying it on the trainability class would have missed that, and the miss would
have looked like coverage.

**L-W13** keys on the *runtime* being generative. `base_model` names a family
whose weights the host replaces on their own schedule, unannounced and not
mentioned in the answer. A warrant carrying only the family name describes a
model that can change between two runs while every field in the document stays
identical.

That is why the shape holds. If a T3 warrant had a different *shape* from a T2
warrant, every engine, replay path and audit query would have to branch on model
type before it could read anything, and the branch would grow a case per model
family forever. Instead there is one shape, and which laws apply depends on
facts nobody had to declare.

---

## What *can* be templated: the request

Retyping the same verb and the same ceiling for every warrant of a shape is real
tedium. A **warrant profile** answers it by filling holes in the *request*
before the builder runs — never by changing the document the builder produces.

```bash
curl -u j.okafor:pw -X POST localhost:5006/api/v1/warrant-profiles \
  -H 'Content-Type: application/json' \
  -d '{"name": "trained_artifact_prod",
       "when": {"trainability_class": ["T3"], "environment": ["prod"]},
       "defaults": {"verb": "score", "max_seconds": 3}}'
```

Ask what it would do before you rely on it:

```bash
curl -u j.okafor:pw -X POST localhost:5006/api/v1/warrant-profiles/preview \
  -H 'Content-Type: application/json' \
  -d '{"urn": "maya://model/fraud.card.nn", "environment": "prod"}'
```

The answer carries the **derivation**: which facts were read off the version,
which profiles matched, and which profile version supplied each filled value. A
default whose origin cannot be named is a value nobody can argue with later.

Profiles fold the way featuresets do — left to right, rightmost wins per key,
`{}` the identity, ordered by specificity so the most specific speaks last. That
is a monoid, and saying so is what makes `(A ∘ B) ∘ C` and `A ∘ (B ∘ C)` the
same set rather than a question about declaration order.

Three constraints keep a profile from becoming a taxonomy, and each is a refusal
at creation rather than a convention:

| It cannot | Refusal | Because |
|---|---|---|
| select on a category you attached | `unknown_profile_fact` | a declared taxonomy beside a derived one is two answers to one question, with no rule for which wins. Selecting on derived facts means a profile *cannot* disagree with the truth, because the truth is what chose it |
| supply a principal, a declared use, an environment, a URN or a TTL | `authority_not_defaultable` | 403, not 422 — it is not a malformed profile, it is one trying to be a different kind of object |
| carry an obligation | `not_defaultable` | a default is something you can drop. *A T3 warrant in prod must carry a digest* is a law (L-W12) or a policy gate, and both refuse rather than suggest |

And it never overrides a caller. A value the caller supplied is theirs, including
one identical to the default — *the caller asked for this* and *nobody said, so
we chose* are different facts, and only one of them is the caller's
responsibility.

The two lists are published at `GET /api/v1/warrant-profile-vocabulary`, because
the lists **are** the design. See [profiles](/help/warrants#profiles-templating-the-request-never-the-warrant).

---

## Checking one in your own engine

The JSON Schema is generated from the vocabulary rather than kept beside it, so
it cannot drift from what actually validates:

```bash
curl -u svc/engine:pw localhost:5006/api/v1/grammar/schema > warrant.schema.json
```

```python
report = maya.warrants.validate(document)
for problem in report["problems"]:
    print(problem["law"], problem["path"], problem["detail"])
```

Every problem comes back at once. Fixing one to be told about the next is the
worst possible interface for a document with ten sections.

A contract nobody can check is a convention. See [the four
axes](/help/warrants#the-four-axes) for the design, and [every kind of model,
worked](/tutorials/every-kind-of-model) for the seven families one at a time.
