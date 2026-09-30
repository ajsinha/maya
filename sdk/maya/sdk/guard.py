"""
A guard for the code that scores a model: check the licence before, report the run after.

MAYA does not serve models. Whatever does -- a batch job, a SageMaker endpoint, a function
in a service -- wraps its scoring call in a ``WarrantGuard``::

    guard = WarrantGuard(client, execution_warrant_id, environment="prod")
    predictions = guard.score(model.predict, frame)

Before the call the guard asks MAYA whether the warrant is live in that environment (and
remembers the answer for ``recheck_seconds``); a suspended, revoked or expired warrant raises
the same errors the bundle endpoint raises, naming whom to contact, and the model is not run.
After the call it reports the run: rows, and per input and output the null rate, mean,
minimum and maximum -- and, for every input a population-stability covenant watches, the
histogram over the covenant's own bin edges, so drift is judged exactly as the covenant was
drawn. A report that breaks a covenant suspends the warrant, and the next call is refused.

Runs scored through a guard are attested; the monitoring dashboards and the covenants see
them without anybody remembering to report.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable

import numpy as np


def _columns(data: Any) -> dict[str, np.ndarray]:
    if hasattr(data, "columns") and hasattr(data, "__getitem__"):  # a pandas DataFrame
        return {str(c): np.asarray(data[c]) for c in data.columns}
    if isinstance(data, dict):
        return {str(k): np.asarray(v) for k, v in data.items()}
    return {"output": np.asarray(data)}


def _stats(values: np.ndarray, edges: list[float] | None = None) -> dict[str, Any]:
    try:
        arr = values.astype(float)
    except (TypeError, ValueError):
        return {"null_rate": float(np.mean([v is None for v in values])) if len(values) else 0.0}
    finite = arr[~np.isnan(arr)]
    out: dict[str, Any] = {"null_rate": float(1 - len(finite) / len(arr)) if len(arr) else 0.0}
    if len(finite):
        out.update(mean=float(finite.mean()), min=float(finite.min()), max=float(finite.max()))
    if edges and len(finite):
        counts, _ = np.histogram(np.clip(finite, edges[0], edges[-1]), bins=edges)
        out["histogram"] = [int(c) for c in counts]
    return {k: v for k, v in out.items() if not (isinstance(v, float) and math.isnan(v))}


class WarrantGuard:
    def __init__(
        self, client: Any, warrant_id: str, environment: str, recheck_seconds: float = 60.0
    ) -> None:
        self.client, self.warrant_id, self.environment = client, warrant_id, environment
        self.recheck_seconds = recheck_seconds
        self._checked_at = -math.inf
        self._edges: dict[str, list[float]] = {}

    def check(self) -> None:
        """Raise unless the warrant is live in this environment (cached briefly)."""
        if time.monotonic() - self._checked_at < self.recheck_seconds:
            return
        from maya.sdk._shared.errors import (
            NotApproved,
            PermissionDenied,
            WarrantExpired,
            WarrantSuspended,
        )

        ew = self.client.execution.get(self.warrant_id)
        spec, status = ew["spec"], ew["status"]
        contact = spec.get("contact") or "the model owner"
        if status == "suspended":
            raise WarrantSuspended(
                f"Warrant suspended: {ew.get('suspend_reason')}. Contact {contact}."
            )
        if status == "expired":
            raise WarrantExpired(
                f"Warrant expired on {str(ew.get('valid_to'))[:10]}. Contact {contact}."
            )
        if status != "live":
            raise NotApproved(f"Warrant is '{status}', not sealed and live. Contact {contact}.")
        if self.environment not in spec.get("environments", []):
            raise PermissionDenied(f"Warrant is not valid in '{self.environment}'")
        self._edges = {
            c["attr"]: c["bin_edges"]
            for c in spec.get("covenants", [])
            if c.get("kind") == "input_psi" and c.get("bin_edges")
        }
        self._checked_at = time.monotonic()

    def score(self, fn: Callable[[Any], Any], inputs: Any) -> Any:
        """Check the licence, run ``fn(inputs)``, report the run, return what ``fn`` returned."""
        self.check()
        result = fn(inputs)
        cols = _columns(inputs)
        rows = len(next(iter(cols.values()))) if cols else 0
        report = self.client.execution.report(
            self.warrant_id,
            environment=self.environment,
            rows=rows,
            input_stats={k: _stats(v, self._edges.get(k)) for k, v in cols.items()},
            output_stats={k: _stats(v) for k, v in _columns(result).items()},
        )
        if report.get("status") != "live":
            self._checked_at = -math.inf  # the next call asks MAYA again, and is refused
        return result
