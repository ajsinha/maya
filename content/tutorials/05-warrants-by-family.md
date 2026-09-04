---
title: Warrants by model family
slug: warrants-by-family
section: The platform
order: 50
icon: diagram-2
summary: The same ten-section document for a QuantLib pricer, a Hull–White calibration, a gradient-boosting model, a scorecard, an LLM, an agent, a vendor black box and a spreadsheet.
audience: Engineers, Quants
---

# Warrants by model family

Ten worked warrants ship in `examples/warrants/`. Every one validates against
the same grammar, with no special cases and no exemptions — which is the test of
whether the four axes were the right ones.

```bash
curl -u a.mehta:pw -X POST localhost:5006/api/v1/grammar/validate \
  -H 'Content-Type: application/json' \
  --data @examples/warrants/01-quantlib-swaption-price.json
# → {"valid": true, "detail": "conforms to the MAYA warrant grammar v1.0"}
```

## The four coordinates of each

| Example | parameters | runtime | verb | data binding |
|---|---|---|---|---|
| Swaption pricing | `none` (T0) | `quantlib` | `score` | `market_data` |
| Hull–White calibration | `calibration_set` (T1) | `quantlib` | `fit` | `dataset_snapshot` |
| Gradient-boosting PD | `learned_weights` (T3) | `onnx` | `score` | `feature_namespace` |
| ...being retrained | `learned_weights` (T3) | `python.callable` | `fit` | `dataset_snapshot` |
| Behaviour scorecard | `estimated_coefficients` (T2) | `pmml` | `score` | `feature_namespace` |
| KYC summariser | `llm_configuration` (T5) | `llm.prompt` | `generate` | `document_corpus` |
| Credit-memo agent | `llm_configuration` (T5) | `llm.agent` | `generate` | `document_corpus` |
| Vendor AML | `opaque` (T6) | `descriptor_only` | `score` | `stream` |
| Treasury spreadsheet | `rule_set` (T8) | `spreadsheet` | `score` | `request` |
| VaR backtest | `calibration_set` (T1) | `python.callable` | `backtest` | `dataset_snapshot` |

Nothing in that table is a special case. Each row is a different point in the
same product space.

## The QuantLib pair is the argument

Two warrants, same library, same runtime value, and the grammar treats them
completely differently — because the *parameter* axis differs.

**Black swaption pricing (T0).** Parameters come from theory. `fit` is refused:

```json
{"law": "L-W1",
 "detail": "a T0 model cannot be fitted: its parameters come from theory, not
            from data — there is nothing to fit",
 "remediation": "ask for 'score', 'validate' or 'explain'; if this model really
                 is fitted, its parameter_kind and fit_procedure are wrong"}
```

**Hull–White calibration (T1).** Parameters *are* inhabited — solved against the
swaption grid every morning. `fit` is exactly right, and the warrant carries the
optimiser, the end criteria and the calibration helpers.

This is why the taxonomy earns its place. "Is it AI?" would put both in the same
bucket. "How is the parameter object inhabited?" separates them correctly, and
the separation is what makes the evidence expectations right for each.

## What the grammar refuses, and why

| Law | Refuses | Because |
|---|---|---|
| L-W1 | `fit` on T0 or T6 | nothing to fit; or nothing reachable to fit |
| L-W2 | `generate` on a non-generative runtime | ONNX does not produce prose |
| L-W3 | training from a non-bitemporal source | it cannot be shown not to have leaked |
| L-W4 | a `fit` with nowhere for the parameters to go | a fit produces a new parameter object |
| L-W5 | claimed determinism from an LLM with no seed | it would be believed |
| L-W6 | `fit` on a descriptor-only model | you cannot reach its parameters |
| L-W7 | a `backtest` with no outcomes | that is a re-score wearing a backtest's name |

## Generating one

From the interface: open a model and press **Generate** on the Warrants card.
Pick a verb, a principal and a declared use, and the resolved warrant appears in
full.

From the API — the same two calls the button makes:

```bash
curl -u j.okafor:pw -X POST localhost:5006/api/v1/warrants -d '{...}'
curl -u j.okafor:pw -X POST "localhost:5006/api/v1/resolve?verb=score" -d '{...}'
```

## Validating one in your own engine

The JSON Schema is generated from the vocabulary and published, so an engine in
any language can check a warrant before acting on it:

```bash
curl -u svc/engine:pw localhost:5006/api/v1/grammar/schema > warrant.schema.json
```

A contract nobody can check is a convention. See
[the warrant grammar](/help/warrant-grammar) for the design.
