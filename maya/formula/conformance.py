"""
Spec–code conformance testing (§29.7).

Differentially tests an uploaded implementation against the reference
semantics of the documented mathematics, on sampled inputs, and reports the
concrete rows where they part company. Sampled agreement is not proof, and
the report says so.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from maya.formula.evaluate import evaluate

STATEMENT = (
    "Sampled agreement is not proof: the implementation agreed with the "
    "documented mathematics on {agreed} of {total} sampled inputs to a "
    "relative tolerance of {rtol:g}."
)


def _output(result: Any, name: str) -> np.ndarray:
    if isinstance(result, dict):
        result = result[name] if name in result else next(iter(result.values()))
    return np.asarray(result, dtype=float).reshape(-1)


def conformance_test(
    ir: dict[str, Any],
    predict_callable: Callable[..., Any],
    samples: dict[str, np.ndarray],
    params: dict[str, Any] | None = None,
    rtol: float = 1e-9,
    atol: float = 1e-12,
    max_counterexamples: int = 10,
) -> dict[str, Any]:
    """Compare ``predict_callable(samples, params)`` with the IR's own evaluation."""
    params = dict(params or {})
    if "black_box" in ir:
        return {
            "agreed": 0,
            "total": 0,
            "counterexamples": [],
            "skipped": True,
            "statement": "Skipped: the model is a declared black box with no documented "
            "closed form to test against.",
        }
    out_name = ir["outputs"][0]["name"]
    expected = _output(evaluate(ir, samples, params), out_name)
    actual = _output(
        predict_callable({k: np.asarray(v) for k, v in samples.items()}, params), out_name
    )
    if actual.shape != expected.shape:
        return {
            "agreed": 0,
            "total": int(expected.size),
            "counterexamples": [],
            "statement": f"Shape mismatch: implementation returned {actual.shape}, "
            f"specification {expected.shape}.",
        }
    both_nan = np.isnan(expected) & np.isnan(actual)
    close = np.isclose(actual, expected, rtol=rtol, atol=atol) | both_nan
    bad = np.flatnonzero(~close)
    counter = []
    for idx in bad[:max_counterexamples]:
        row = {k: float(np.asarray(v).reshape(-1)[idx]) for k, v in samples.items()}
        row.update({"_expected": float(expected[idx]), "_actual": float(actual[idx])})
        counter.append(row)
    agreed, total = int(close.sum()), int(close.size)
    degenerate = _degenerate(expected)
    statement = STATEMENT.format(agreed=agreed, total=total, rtol=rtol)
    if degenerate:
        statement += (
            " The comparison was degenerate: the specification's output barely varied over "
            "the sampled inputs (saturated or constant), so agreement here cannot tell a "
            "right implementation from a wrong one. Run it over a feature set's own values."
        )
    return {
        "agreed": agreed,
        "total": total,
        "counterexamples": counter,
        "skipped": False,
        "rtol": rtol,
        "degenerate": degenerate,
        "statement": statement,
    }


def _degenerate(expected: np.ndarray) -> bool:
    """Whether the reference output is too flat for agreement to mean anything: almost every
    finite value is the same number (a saturated logistic returns 1.0 to the last bit)."""
    finite = expected[np.isfinite(expected)]
    if finite.size < 10:
        return True
    values, counts = np.unique(np.round(finite, 12), return_counts=True)
    return bool(counts.max() / finite.size > 0.9 or values.size < 5)


def sample_inputs(
    ir: dict[str, Any], columns: dict[str, np.ndarray], n: int = 10_000, seed: int = 0
) -> dict[str, np.ndarray]:
    """Draw ``n`` rows by resampling the bound feature set's own values."""
    rng = np.random.default_rng(seed)
    out = {}
    for item in ir.get("inputs", []):
        if item.get("role", "feature") != "feature":
            continue
        values = np.asarray(columns[item["name"]], dtype=float)
        values = values[~np.isnan(values)]
        out[item["name"]] = rng.choice(values, size=n, replace=True) if values.size else np.zeros(n)
    return out
