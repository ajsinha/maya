# Worked warrants

Ten warrants spanning the model families a large bank actually runs. Every one
validates against the same grammar, with no special cases and no exemptions —
which is the test of whether the grammar's four axes were the right ones.

```bash
# check them all
python - <<'PY'
import json, pathlib
from core.execution.grammar import validate
for p in sorted(pathlib.Path("examples/warrants").glob("*.json")):
    doc = json.loads(p.read_text()); doc.pop("_comment", None)
    print(f"{'PASS' if validate(doc).valid else 'FAIL'}  {p.name}")
PY

# or over the API
curl -u a.mehta:pw -X POST localhost:5006/api/v1/grammar/validate \
  -H 'Content-Type: application/json' \
  --data @examples/warrants/01-quantlib-swaption-price.json
```

## The four coordinates

| File | parameters | runtime | verb | data |
|---|---|---|---|---|
| `01-quantlib-swaption-price` | `none` (T0) | `quantlib` | `score` | `market_data` |
| `02-quantlib-hullwhite-calibrate` | `calibration_set` (T1) | `quantlib` | `fit` | `dataset_snapshot` |
| `03-gbm-pd-score` | `learned_weights` (T3) | `onnx` | `score` | `feature_namespace` |
| `04-gbm-pd-fit` | `learned_weights` (T3) | `python.callable` | `fit` | `dataset_snapshot` |
| `05-logistic-scorecard-score` | `estimated_coefficients` (T2) | `pmml` | `score` | `feature_namespace` |
| `06-llm-kyc-summarise` | `llm_configuration` (T5) | `llm.prompt` | `generate` | `document_corpus` |
| `07-llm-agent-credit-memo` | `llm_configuration` (T5) | `llm.agent` | `generate` | `document_corpus` |
| `08-vendor-blackbox-score` | `opaque` (T6) | `descriptor_only` | `score` | `stream` |
| `09-spreadsheet-euc` | `rule_set` (T8) | `spreadsheet` | `score` | `request` |
| `10-var-backtest` | `calibration_set` (T1) | `python.callable` | `backtest` | `dataset_snapshot` |

Nothing there is a special case. Each row is a different point in one product
space.

## The pair worth reading first

`01` and `02` are the same library and the same runtime value, and the grammar
treats them completely differently — because the **parameter** axis differs.

The Black swaption pricer is T0: its parameters come from theory, so `fit` is a
type error and is refused. The Hull–White model is T1: its parameters *are*
inhabited, by solving against the swaption grid every morning, so `fit` is
exactly right and the warrant carries the optimiser and the end criteria.

"Is it AI?" would put both in the same bucket. "How is the parameter object
inhabited?" separates them correctly.

## Notes

- Each file carries a `_comment` explaining what it demonstrates. Underscore
  keys are annotations; the schema allows them and no engine acts on them.
- Digests and signatures are illustrative. A real warrant is signed by MAYA at
  resolution time.
- `tests/test_grammar.py` validates every file in this directory on every run,
  so an example that stops conforming fails the build.
