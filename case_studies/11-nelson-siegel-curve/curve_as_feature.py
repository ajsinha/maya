"""
Step 7 — the same curve, on the other side of the fence.

    .venv/bin/python case_studies/11-nelson-siegel-curve/curve_as_feature.py

This is the step the study exists for. MAYA's restricted expression language has arithmetic
and ``exp``, which is everything Nelson–Siegel needs, so the curve that steps 3 to 6 governed
as a model can also be written as a **derived feature** over the published pillars — with the
four calibrated numbers inlined as literals. It resolves, it pins, it has a version, an
approval, a definition hash, a quality contract and a place in the lineage graph.

The step does three things. It builds that feature. It checks, row by row against MAYA's own
evaluation of the approved model, that the two produce the **same numbers**. And then it reads
back what MAYA holds about each of the two objects, so the difference is a list rather than an
opinion.

Nothing here is a trick of the demonstration: it is what the platform actually offers, and a
bank's zero curve arrives on the feature side of that fence every morning.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from maya_demo import Narrator, step_script  # noqa: E402
from study import (  # noqa: E402
    DESCRIPTIONS,
    CURVE_FEATURE,
    EXTRA_USERS,
    LIVE,
    MODEL,
    NS,
    WARRANT,
    Cast,
    curve_expression,
    evaluate_curve,
    find_warrant,
    parameter_set,
    rmse_bp,
)

TITLE = "Case study 11, step 7 — is a curve a feature or a model?"
CURVE_SET = "ns-window-2606"
REF = f"maya://feature/{NS}/{CURVE_FEATURE}@v1"


def definition(expr: str) -> dict[str, Any]:
    """The curve as a derived feature: the model's mathematics, the model's numbers."""
    return {
        "index": ["date", "tenor"],
        "index_types": {"date": "date", "tenor": "string"},
        "schema": [
            {"name": "tau", "type": "float64"},
            {"name": "nsYield", "type": "float64"},
        ],
        "source": {
            "type": "derived",
            "derivation": {
                "operator": "transform",
                "operands": [f"maya://feature/{NS}/zero_yields@v1"],
                "options": {"pipeline": [{"op": "derive", "name": "nsYield", "expr": expr}]},
            },
        },
        "resolution": {"grid": "as_is", "rules": {}},
        "transform": [],
        "quality": [{"check": "range", "attr": "nsYield", "min": -0.01, "max": 0.25}],
    }


def frame_of(cast: Cast, ref: str) -> pd.DataFrame:
    """The feature's rows, downloaded the way any consumer of a feature would take them."""
    got = cast.mick.features.download(ref, format="csv")
    # MAYA writes its manifest — the columns, their types, the axes — as a comment line
    # above the header, so an export is self-describing wherever it ends up.
    return pd.read_csv(io.BytesIO(got["data"]), comment="#")


def main(maya: Any, n: Narrator) -> None:  # noqa: PLR0915 - one narrated step per paragraph
    cast = Cast(maya)
    warrant = find_warrant(cast.mgr, WARRANT)
    values = parameter_set(warrant, CURVE_SET)["values"]
    version = cast.mgr.models.get(f"{NS}/{MODEL}")["versions"][0]

    n.step("The governed model's mathematics, as an expression a feature may carry")
    expr = curve_expression(values)
    n.say(f"  nsYield = {expr}")
    n.say("Four literals where the model has four parameters. Everything else is identical,")
    n.say("because MAYA's expression language has arithmetic and exp, and that is all the")
    n.say("curve needs.")

    n.step("Defining it as a derived feature over the published pillars")
    cast.dana.features.create(
        NS, CURVE_FEATURE, definition(expr), description=DESCRIPTIONS[CURVE_FEATURE]
    )
    cast.dana.features.transition(f"{NS}/{CURVE_FEATURE}", 1, "submit")
    cast.mick.features.transition(f"{NS}/{CURVE_FEATURE}", 1, "approve")
    got = cast.mick.features.get(f"{NS}/{CURVE_FEATURE}")
    feature_version = got["versions"][0]
    n.fact("feature", f"{NS}/{CURVE_FEATURE} v1, {feature_version['state']}")
    n.fact("definition hash", f"{feature_version['definition_hash'][:16]}…")
    n.fact("source", feature_version.get("source_text") or "derived over zero_yields@v1")
    n.fact("approved by", "mick, a feature manager")

    n.step("Do the two produce the same numbers?")
    curve = frame_of(cast, REF)
    as_model = evaluate_curve(version["formula_ir"], curve["tau"].to_numpy(), values)
    difference = np.abs(curve["nsYield"].to_numpy() - as_model)
    n.fact("rows compared", f"{len(curve):,}")
    n.fact("largest disagreement", f"{difference.max() * 1e4:.3g} bp")
    n.fact("root mean square disagreement", f"{rmse_bp(difference):.3g} bp")
    n.fact("feature at 10Y", f"{curve[curve['tau'] == 10.0]['nsYield'].iloc[0] * 100:.6f}%")
    n.fact(
        "model at 10Y",
        f"{evaluate_curve(version['formula_ir'], np.array([10.0]), values)[0] * 100:.6f}%",
    )
    n.say("The same mathematics, the same four numbers, the same answer to a ten-millionth of")
    n.say("a basis point — and two completely different amounts of governance, chosen by")
    n.say("nothing more than which subsystem the author typed it into.")
    n.say("The disagreement is not quite zero, and the reason is the whole point in miniature:")
    n.say("the feature carries the factors as *text*, rounded to nine figures, while the")
    n.say("parameter set holds them as numbers. Text has a precision nobody declared.")

    n.step("What MAYA holds about each of them")
    conformance = (version["artifact_report"] or {}).get("conformance") or {}
    execution = [w for w in cast.mgr.execution.list() if w["name"] == LIVE]
    rows = (
        ("a specification document", f"{len(version['completeness'])} required sections", "—"),
        ("mathematics MAYA can read", f"IR {version['ir_hash'][:12]}…", "an expression string"),
        (
            "code tested against it",
            f"{conformance.get('agreed')} of {conformance.get('total')}",
            "—",
        ),
        ("bounds on the numbers", "4 parameters bounded", "—"),
        (
            "the numbers as an object",
            f"{len(warrant['parameter_sets'])} parameter sets",
            "4 literals",
        ),
        ("a licence to compute", f"1 training + {len(execution)} execution warrant", "—"),
        ("a blind score", f"{warrant['holdout_attempts']} escrowed attempts", "—"),
        ("covenants", "input_range, output_range", "—"),
        ("a version and an approval", f"v1 {version['state']}", f"v1 {feature_version['state']}"),
        (
            "a definition hash",
            f"{version['ir_hash'][:12]}…",
            f"{feature_version['definition_hash'][:12]}…",
        ),
        ("a quality contract", "—", "1 range check"),
        ("a knowledge time", "—", "inherited from zero_yields"),
        ("a place in lineage", "yes", "yes"),
    )
    print(f"    {'':<28}{'as a model':<34}{'as a feature'}")
    for what, model_has, feature_has in rows:
        print(f"    {what:<28}{model_has:<34}{feature_has}")

    n.step("And what it costs to move the curve tomorrow")
    moved = {**values, "beta0": float(values["beta0"]) + 0.0015}
    cast.dana.features.new_draft(f"{NS}/{CURVE_FEATURE}")
    cast.dana.features.update_draft(f"{NS}/{CURVE_FEATURE}", definition(curve_expression(moved)))
    cast.dana.features.transition(f"{NS}/{CURVE_FEATURE}", 2, "submit")
    cast.mick.features.transition(f"{NS}/{CURVE_FEATURE}", 2, "approve")
    diff = cast.mick.features.compare(f"{NS}/{CURVE_FEATURE}", 1, 2)
    v2 = cast.mick.features.get(f"{NS}/{CURVE_FEATURE}")["versions"][0]
    n.fact("new feature version", f"v2 {v2['state']}, change class {diff['change_class']}")
    n.fact("what changed", ", ".join(sorted({item["what"] for item in diff["diff"]})))
    n.say("MAYA classifies it as 'behavioral' and shows the approver the whole source binding,")
    n.say("before and after — which is the right diff for a source and a poor one for a number:")
    n.say("the fifteen basis points that moved are one digit inside a two-hundred-character")
    n.say("string. The same move as a parameter set is four numbers, bounds-checked, tied to")
    n.say("a data checksum, blind-scored and approved by a model manager, because on that side")
    n.say("of the fence the numbers are an object and here they are punctuation.")
    n.say("")
    n.say("That asymmetry is the argument, and the README takes a position on it.")


if __name__ == "__main__":
    sys.exit(step_script(TITLE, NS, main, extra_users=EXTRA_USERS))
