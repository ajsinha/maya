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
| `11-nj-linear-fit-from-featureset` | `estimated_coefficients` (T2) | `python.callable` | `fit` | `featureset` |
| `12-nj-linear-score-on-parameters` | `estimated_coefficients` (T2) | `python.callable` | `score` | `request` |
| `13-quantlib-swap-price` | `none` (T0) | `quantlib` | `score` | `market_data` |

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


---

## The pair at the end

`11` and `12` are one cycle rather than two examples, and they are the clearest
statement of what the grammar is for.

**11 fits.** It names `nj_home_core@v1` — a featureset — rather than enumerating
six columns. That is the whole point of naming a presentation of X: the same
selection can train another model, and two warrants differing only in their
featureset are an honest A/B on data rather than two scripts somebody hopes
agree. The featureset fixes the columns; the warrant fixes the period, which is
why `window` and `as_of` are here and not in the set.

**12 scores.** Fitting did not change the kernel; it inhabited `P`. So `12` runs
the *same model version* at a **named point in the parameter object**, pinned by
digest. Model version and parameter set together determine the run: same kernel,
same point in P, same input, same answer.

Read the two `parameters.source` blocks against each other. `11` binds
`to_be_fitted` — it produces the parameter object and cannot also read one. `12`
binds `parameter_set` and names the digest a second person approved. Law **L-W8**
refuses each of those in the other's position, because a run that will not say
which inhabitant of P it is using produces a number attributable to nothing.


## The one the engine can run

`13` is the first QuantLib warrant this platform can **execute** rather than
describe. Everything the valuation reads is in the document: the evaluation date,
the curve, and the single past fixing the first floating period needs.

That is not tidiness. A valuation that reads today's date is not reproducible
tomorrow, and a backtest of it is a backtest of nothing — so the engine refuses a
warrant that does not say when. A valuation that fetched its curve would put an
unversioned input into a governed computation — so the engine refuses one that
does not carry it. And a swap whose first fixing predates the evaluation date
needs that fixing supplied, because inventing it would be the same failure in
miniature:

> **`missing_fixing`** — the instrument needs a past fixing the warrant does not
> carry. *Supply fixings alongside the curve; a valuation that invented one would
> put an unversioned number into a governed computation.*

Note `parameters.kind: none`. This is **T0**: the parameter object is terminal,
the constants come from theory, and law **L-W1** refuses to warrant it for
fitting. That refusal is the trainability class working rather than a limitation.
