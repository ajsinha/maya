"""
Fairness and explainability evidence, computed on a warrant's escrowed holdout.

Two questions a validator is asked about every model and could not answer from MAYA:

* **Does it work equally well for everyone it is used on?** The holdout is cut by a segment
  column the validator names -- a region, a product, a protected characteristic where the
  firm is allowed to hold one -- and each segment gets its own error, bias (mean error) and
  mean prediction. The spread across segments is summarised as the ratio of the worst
  segment's MAE to the best's and the widest gap in bias. A segment is *flagged* when its
  MAE is more than a quarter above the overall figure, and *systematic* when its bias is
  more than half its own MAE -- when the model is wrong for that group mostly in one
  direction, which two groups with the same MAE can hide completely. A segment with fewer than
  ``min_segment`` rows is reported as suppressed, with no figures: a mean over three rows
  of an escrowed holdout is three rows of the holdout.
* **What drives it?** Permutation importance: each input is shuffled across the holdout
  (with a fixed seed, several times) and the model re-scored; the rise in error is how much
  the model leans on that input. It needs nothing but predictions, so it works the same for
  a black box, whose predictions come from its artifact in the sandbox.

Computing either reads the holdout, so a run counts as one holdout attempt on the warrant,
like any scoring. The evidence is stored against the warrant with the parameters used, and
nothing leaves but aggregates.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import builtins
from typing import Any

import numpy as np

from maya.core.errors import ValidationFailed
from maya.security.authz import Principal

MIN_SEGMENT = 20
MAX_SEGMENTS = 50
REPEATS = 5
MAX_REPEATS = 20
FLAG_RATIO = 1.25
SYSTEMATIC_SHARE = 0.5
SEED = 20260926


def _rmse(err: np.ndarray) -> float:
    return float(np.sqrt(np.nanmean(err**2)))


def _mae(err: np.ndarray) -> float:
    return float(np.nanmean(np.abs(err)))


def segments(
    groups: np.ndarray, err: np.ndarray, pred: np.ndarray, min_rows: int = MIN_SEGMENT
) -> dict[str, Any]:
    """Per-segment error, bias and mean prediction, and the disparity across segments."""
    overall = _mae(err)
    labels = [str(g) for g in groups]
    names = sorted(set(labels))
    if len(names) > MAX_SEGMENTS:
        raise ValidationFailed(
            f"The segment column has {len(names)} distinct values; at most {MAX_SEGMENTS} "
            "segments are compared. Choose a coarser column."
        )
    arr = np.asarray(labels)
    rows: list[dict[str, Any]] = []
    shown: list[dict[str, Any]] = []
    for name in names:
        mask = arr == name
        n = int(mask.sum())
        if n < min_rows:
            rows.append({"segment": name, "rows": n, "suppressed": True})
            continue
        e, pr = err[mask], pred[mask]
        row: dict[str, Any] = {
            "segment": name,
            "rows": n,
            "suppressed": False,
            "rmse": _rmse(e),
            "mae": _mae(e),
            "bias": float(np.nanmean(e)),
            "mean_prediction": float(np.nanmean(pr)),
        }
        row["flagged"] = bool(overall > 0 and row["mae"] > FLAG_RATIO * overall)
        row["systematic"] = bool(
            row["mae"] > 0 and abs(row["bias"]) > SYSTEMATIC_SHARE * row["mae"]
        )
        rows.append(row)
        shown.append(row)
    maes = [float(r["mae"]) for r in shown]
    biases = [float(r["bias"]) for r in shown]
    return {
        "overall_mae": overall,
        "segments": rows,
        "compared": len(shown),
        "suppressed": len(rows) - len(shown),
        "min_segment": min_rows,
        "mae_ratio": (max(maes) / min(maes)) if len(maes) > 1 and min(maes) > 0 else None,
        "bias_gap": (max(biases) - min(biases)) if len(biases) > 1 else None,
        "flagged": [r["segment"] for r in shown if r["flagged"]],
        "systematic": [r["segment"] for r in shown if r["systematic"]],
    }


class EvidenceService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    def compute(
        self,
        p: Principal,
        warrant_id: str,
        *,
        parameter_set_id: str | None = None,
        segment: str | None = None,
        importance: bool = True,
        repeats: int = REPEATS,
        min_segment: int = MIN_SEGMENT,
    ) -> dict[str, Any]:
        """Segment metrics and permutation importance on the holdout, stored as evidence."""
        if not segment and not importance:
            raise ValidationFailed("Ask for segment metrics, importance, or both")
        repeats = max(1, min(int(repeats), MAX_REPEATS))
        min_segment = max(5, int(min_segment))
        w = self.p.warrants
        h = w.holdout(p, warrant_id, parameter_set_id=parameter_set_id)
        test, y = h["test"], h["y"]
        pred, provenance = h["predict"](test)
        err = pred - y
        result: dict[str, Any] = {
            "rows": int(len(test)),
            "rmse": _rmse(err),
            "mae": _mae(err),
            **provenance,
        }
        if segment:
            if segment not in test.columns:
                raise ValidationFailed(
                    f"'{segment}' is not a column of the holdout",
                    columns=sorted(c for c in test.columns if not c.startswith("_")),
                )
            if segment == h["target"]:
                raise ValidationFailed("The target is not a segment")
            result["segments"] = {
                "column": segment,
                **segments(test[segment].to_numpy(), err, pred, min_segment),
            }
        if importance:
            result["importance"] = self._importance(h, err, repeats)
        spec = {
            "segment": segment,
            "importance": importance,
            "repeats": repeats,
            "min_segment": min_segment,
            "seed": SEED,
        }
        w.record_attempt(
            p,
            warrant_id,
            {"rmse": result["rmse"], "mae": result["mae"], "rows": result["rows"]},
            parameter_set_id=parameter_set_id,
            purpose="fairness-explainability evidence",
        )
        with self.p.uow(p.username) as uow:
            row = uow.repo("warrant_evidence").add(
                {
                    "training_warrant_id": warrant_id,
                    "parameter_set_id": parameter_set_id,
                    "kind": "fairness_explainability",
                    "spec": spec,
                    "result": result,
                }
            )
            uow.audit(
                "warrant.evidence_computed",
                object_type="training_warrant",
                object_ref=warrant_id,
                detail={
                    "segment": segment,
                    "flagged": (result.get("segments") or {}).get("flagged"),
                    "importance": importance,
                },
            )
            return row

    @staticmethod
    def _importance(h: dict[str, Any], err: np.ndarray, repeats: int) -> builtins.list[Any]:
        """Rise in RMSE when each input is shuffled, averaged over ``repeats`` seeded draws."""
        mv, test, y = h["model_version"], h["test"], h["y"]
        names = [c["name"] for c in mv["input_contract"] or []]
        base = _rmse(err)
        rng = np.random.default_rng(SEED)
        out = []
        for name in names:
            column = h["bindings"].get(name, name)
            if column not in test.columns:
                continue
            rises = []
            for _ in range(repeats):
                shuffled = test.copy()
                shuffled[column] = rng.permutation(shuffled[column].to_numpy())
                pred, _ = h["predict"](shuffled)
                rises.append(_rmse(pred - y) - base)
            out.append(
                {
                    "input": name,
                    "column": column,
                    "rmse_increase": float(np.mean(rises)),
                    "spread": float(np.std(rises)),
                }
            )
        total = sum(max(r["rmse_increase"], 0.0) for r in out) or 1.0
        for r in out:
            r["share"] = max(r["rmse_increase"], 0.0) / total
        return sorted(out, key=lambda r: -r["rmse_increase"])

    def list(self, p: Principal, warrant_id: str) -> builtins.list[dict[str, Any]]:
        with self.p.uow() as uow:
            w, _ = self.p.warrants._load(uow, warrant_id)
            self.p.access.require(uow, p, "read", "training_warrant", w)
            return uow.repo("warrant_evidence").list(
                training_warrant_id=warrant_id, order_by=["-created_at"]
            )
