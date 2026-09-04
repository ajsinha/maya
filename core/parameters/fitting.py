"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Running a fit, and recording what it produced.

The register could always take delivery of a parameter set and refuse one that
no warrant authorised. What it could not do was *produce* one, and the gap
mattered more than it looked: a governed path with a hole in the middle is a
path nobody has walked end to end, and every control on either side of the hole
was therefore untested against a real fit.

This is the piece that joins them. It is deliberately thin, and each of the four
steps is somebody else's job done in the right order:

  1. the warrant is resolved for the verb ``fit`` -- authority first, before any
     data is read, because a read performed under an authority that turns out
     not to exist has already happened;
  2. the training set is read back at the Delta version the snapshot pinned, not
     at the head, so a fit run twice on the same snapshot sees the same bytes
     even if the table has been written to since;
  3. the estimator runs in the captive engine, under the same runtime dispatch
     every other operation uses;
  4. the result is recorded through the ordinary register, which means it lands
     as PROPOSED and still needs somebody other than whoever fitted it to
     approve it. A fit that approved its own output would have removed the one
     control the parameter object exists to carry.

**What this does not do.** It does not decide whether the fit is any good. The
diagnostics travel with the parameter set so a validator can, and an unconverged
fit is refused by the estimator rather than recorded with a flag -- but "the
condition number is four thousand" is a judgement, and the platform's job is to
put the number in front of somebody who can make it.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from core.execution.runtimes import Invocation
from core.log import get_logger
from core.parameters.common import FITTED, ParameterError

logger = get_logger(__name__)

# What a fit is called when the caller does not say. Named rather than left to a
# literal, because it becomes the parameter set's name in the register and a set
# called "None" is one nobody will find again.
DEFAULT_NAME = "fitted"


class FittingService:
    """Fits a parameter object under a warrant, and records the result."""

    def __init__(self, engine, warrants, parameters, features, snapshots,
                 delta, evidence):
        self.engine, self.warrants = engine, warrants
        self.parameters, self.features = parameters, features
        self.snapshots, self.delta, self.evidence = snapshots, delta, evidence

    # -------------------------------------------------------------------- fit
    def fit(self, urn: str, snapshot_id: str, environment: str, principal: str,
            declared_use: str, window: Optional[Dict[str, float]] = None,
            name: str = DEFAULT_NAME, kind: str = "coefficients",
            note: str = "", actor: str = "system") -> Dict[str, Any]:
        """Fit this version from that snapshot, and record the parameters.

        The window is the caller's to state and is not derived from the rows.
        Law L-W9 requires a fit to bound the period it covers, and the period a
        fit is *for* is a governance statement -- "this model was estimated over
        2019 to 2024" -- which happens to be reported by the data but is not
        defined by it. Reading it off whatever rows arrived would make the claim
        a description of the extract rather than a decision anybody made.
        """
        window = self._checked_window(window)
        snapshot = self._snapshot(snapshot_id)
        featureset = snapshot.get("featureset")
        featureset_version = snapshot.get("featureset_version")
        if not featureset or featureset_version is None:
            raise ParameterError(
                "snapshot_not_from_a_featureset",
                f"snapshot '{snapshot.get('name')}' does not name a featureset "
                f"version, so what schema these columns satisfy has no answer",
                "assemble the training set from a published featureset version "
                "rather than from a bare list of views")

        # Authority before data. A warrant that will not resolve should not have
        # caused a dataset to be read first.
        warrant = self.warrants.resolve_fit(
            urn, environment, principal, declared_use, featureset,
            featureset_version, window, snapshot["as_of"])
        grant = self._grant(urn, environment, principal, declared_use)

        rows = self._rows(snapshot)
        started = time.perf_counter()
        result = self.engine.runtimes.invoke(Invocation(warrant, {"rows": rows}))
        elapsed = round((time.perf_counter() - started) * 1000, 3)

        recorded = self.parameters.record(
            urn=urn, semver=warrant["subject"]["version"], name=name, kind=kind,
            values=result["values"], provenance=FITTED,
            diagnostics={**result.get("diagnostics", {}),
                         "family": result.get("family"),
                         "fitted_in_ms": elapsed,
                         "rows": len(rows),
                         "snapshot": snapshot.get("name"),
                         # The pinned version, not the current one. A replay of
                         # this fit reads these bytes or it is not a replay.
                         "delta_version": snapshot.get("delta_version"),
                         "pit_verified": bool(snapshot.get("pit_verified"))},
            featureset=featureset, featureset_version=featureset_version,
            window=window, as_of=snapshot["as_of"],
            snapshot_id=snapshot_id,
            warrant_id=grant["id"],
            note=note, actor=actor)

        self.evidence.append(
            "parameter_set_fitted", "version",
            warrant["subject"]["version_id"],
            {"parameter_set": recorded["id"], "family": result.get("family"),
             "featureset": f"{featureset}@v{featureset_version}",
             "snapshot": snapshot.get("name"), "rows": len(rows),
             "warrant": warrant["warrant_id"]}, actor=actor)
        logger.info("fitted %s parameters for %s from %s (%d rows, %.1fms)",
                    result.get("family"), urn, snapshot.get("name"),
                    len(rows), elapsed)
        # `warrant_id` on the row is the GRANT -- the standing entitlement MAYA
        # persists and can vouch for. The descriptor is minted per call and
        # never stored, so it travels under its own name rather than
        # overwriting the one thing the register can check later.
        return {**recorded, "family": result.get("family"),
                "descriptor_id": warrant["warrant_id"],
                "fitted_from": {"snapshot": snapshot.get("name"),
                                "rows": len(rows),
                                "featureset": featureset,
                                "featureset_version": featureset_version}}

    # ------------------------------------------------------------------ parts
    def _snapshot(self, snapshot_id: str) -> Dict[str, Any]:
        snapshot = self.snapshots.one(id=snapshot_id)
        if snapshot is None:
            raise ParameterError(
                "no_snapshot", f"there is no training snapshot {snapshot_id}",
                "assemble one from a featureset version first")
        return snapshot

    def _rows(self, snapshot: Dict[str, Any]):
        """The rows as the snapshot pinned them, or a refusal saying why not."""
        table = snapshot["delta_table"]
        if not self.delta.exists(table):
            raise ParameterError(
                "snapshot_storage_missing",
                f"the snapshot's table '{table}' is not in storage, so the rows "
                f"it was built from cannot be read",
                "the fit cannot be run against a dataset that is no longer there")
        frame = self.delta.read(table, snapshot.get("delta_version"))
        rows = frame.to_dict(orient="records")
        if not rows:
            raise ParameterError(
                "snapshot_is_empty",
                f"snapshot '{snapshot.get('name')}' holds no rows at the version "
                f"it was pinned to",
                "assemble it again against a spine that matches the window")
        return rows

    @staticmethod
    def _checked_window(window: Optional[Dict[str, float]]) -> Dict[str, float]:
        """Both ends present, and the right way round."""
        window = window or {}
        if window.get("from") is None or window.get("to") is None:
            raise ParameterError(
                "window_required",
                "a fit must say which period it covers; law L-W9 refuses a "
                "featureset read for training that does not bound one",
                "pass window={'from': ..., 'to': ...} as epoch seconds")
        if float(window["to"]) <= float(window["from"]):
            raise ParameterError(
                "window_inverted",
                f"the window ends at {window['to']} and starts at "
                f"{window['from']}, which covers no period at all",
                "give a window whose end is after its start")
        return {"from": float(window["from"]), "to": float(window["to"])}

    def _grant(self, urn: str, environment: str, principal: str,
               declared_use: str) -> Dict[str, Any]:
        """The standing entitlement the descriptor was minted from.

        The register accepts a fitted set only against a warrant MAYA issued,
        and what MAYA persists is the grant -- a resolved descriptor is minted
        per request and never stored. So this is the id the parameter set has to
        carry if "did this come from us" is to have an answer later.

        Deliberately not guarded. resolve_fit has already run and goes through
        the same entitlement check, so a refusal here would mean the two
        disagreed; recording the set with no warrant instead would fail further
        down as `warrant_required`, which describes the caller's request rather
        than the platform's inconsistency.
        """
        return self.warrants.entitlement(urn, environment, principal,
                                         declared_use)
