"""
MAYA — bulk transfer of feature values.
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Every other surface here moves small documents. Feature values are not small, so
these endpoints stream: reads iterate Arrow batches straight off the Delta files,
and writes parse a batch at a time. Peak memory is one batch rather than one
dataset, whether that dataset is a thousand rows or a hundred million.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from fastapi.responses import StreamingResponse

from typing import Any, Dict, List


from core.features.alignment import align
from core.features.preparation import prepare
from core.features.transfer import MEDIA_TYPE, describe as describe_transfer
from core.features.transfer import normalise
from routes.base import Body, Routes


class PrepareIn(Body):
    """What a caller asks MAYA to do to the values on the way out."""
    as_of: Any = None
    fill: Dict[str, Any] = {}
    normalise: Dict[str, str] = {}
    align: Dict[str, Any] = {}
    limit: Any = None

    def policy(self) -> Dict[str, Any]:
        return {k: v for k, v in
                {"fill": self.fill, "normalise": self.normalise,
                 "align": self.align}.items() if v}


def _prepare(rows: List[Dict[str, Any]], policy: Dict[str, Any],
             body: "PrepareIn") -> Dict[str, Any]:
    """Align, then fill, then normalise — and say what each step did."""
    report: Dict[str, Any] = {"rows_in": len(rows)}
    spec = policy.get("align") or {}
    if spec:
        columns = sorted({k for r in rows for k in r} -
                         {"entity_id", "event_ts", "ingest_ts"})
        aligned = align(rows, columns, spec.get("axis", "event_ts"),
                        spec.get("rule", "flat_forward"),
                        spec.get("grid"), limit=spec.get("carry_limit"))
        rows = aligned["rows"]
        report["aligned"] = {k: v for k, v in aligned.items() if k != "rows"}
    out = prepare(rows, policy.get("fill"), policy.get("normalise"), body.as_of)
    report.update({k: v for k, v in out.items() if k != "rows"})
    return {"rows": out["rows"], "count": len(out["rows"]),
            "policy_applied": policy, "report": report}


class TransferRoutes(Routes):
    def register(self) -> None:
        features, api = self.ctx["features"], self.api
        transfer = features.transfer

        @self.app.get(f"{api}/transfer", tags=["features"])
        def formats(request: Request):
            """What this surface offers, so a client need not guess."""
            self.principal(request)
            return describe_transfer()

        # ------------------------------------------------------------- read
        @self.app.get(f"{api}/feature-views/{{name}}/versions/{{version}}/data",
                      tags=["features"])
        def view_data(request: Request, name: str, version: int,
                      format: Optional[str] = None, columns: Optional[str] = None,
                      limit: Optional[int] = None):
            """Copy a feature view version out, at the version it was pinned at.

            The read uses the pinned Delta version rather than whatever the
            namespace currently holds, so what comes out is what that version
            is, not what the path has since become.
            """
            self.authorise(request, "feature:read")
            pin = self.guard(lambda: features.pinned(name, version))
            wanted = [c.strip() for c in columns.split(",")] if columns else None
            chosen = self.guard(
                lambda: normalise(format, request.headers.get("accept")))
            # Checked before the response starts: a generator raises on its
            # first pull, by which time the status line has already gone out.
            self.guard(lambda: transfer.check_columns(
                pin["namespace"], wanted, pin["delta_version"]))
            if chosen == "json":
                return self.guard(lambda: {
                    "view": name, "version": version,
                    "namespace": pin["namespace"],
                    "delta_version": pin["delta_version"],
                    **transfer.rows(pin["namespace"], pin["delta_version"],
                                    wanted, limit or 1000)})
            return self._stream(
                transfer.stream(pin["namespace"], chosen, pin["delta_version"],
                                wanted, limit),
                chosen, f"{name}-v{version}")

        @self.app.get(f"{api}/featuresets/{{name}}/versions/{{version}}/data",
                      tags=["features"])
        def featureset_data(request: Request, name: str, version: int,
                            as_of: Optional[float] = None,
                            format: Optional[str] = None,
                            limit: Optional[int] = None):
            """Copy a whole featureset version out **as at a stated moment**.

            A featureset spans several namespaces, so this is a join — and each
            part is reduced to what was true and known at `as_of` before the
            join happens. Without that the join pairs each feature's whole
            history against every other feature's, which is what it used to do.

            `as_of` is required. An export is a claim about what was known at a
            moment, and defaulting it would make that moment whatever the clock
            said when somebody happened to call.

            A client wanting parallelism should read the parts instead — `/parts`
            says what they are.
            """
            self.authorise(request, "feature:read")
            chosen = self.guard(
                lambda: normalise(format, request.headers.get("accept")))
            if chosen == "json":
                rows = self.guard(lambda: [
                    r for batch in transfer.featureset_batches(
                        name, version, as_of, min(limit or 1000, 10_000))
                    for r in batch.to_pylist()])
                return {"featureset": name, "version": version,
                        "returned": len(rows), "rows": rows,
                        "detail": "json is capped; ask for arrow or parquet to "
                                  "take the whole thing"}
            return self._stream(
                transfer.featureset_stream(name, version, chosen, as_of, limit),
                chosen, f"{name}-v{version}")

        @self.app.post(f"{api}/featuresets/{{name}}/versions/{{version}}/prepared",
                       tags=["features"])
        def prepared(request: Request, name: str, version: int,
                     body: PrepareIn):
            """The featureset with MAYA's preparation applied.

            Aligned onto an axis if asked, gaps filled, and normalised — with the
            statistics fitted from what was knowable at the stated moment, and
            returned alongside the rows so the same transform can be applied to
            one row tomorrow.

            The policy is the featureset's own default, overridden column by
            column by anything in the request.
            """
            self.authorise(request, "feature:read")
            resolved = self.guard(
                lambda: features.sets.resolved(name, body.policy()))
            effective = resolved["policy"]["policy"]
            rows = self.guard(lambda: [
                r for batch in transfer.featureset_batches(
                    name, version, body.as_of, body.limit or 50_000)
                for r in batch.to_pylist()])
            return self.guard(lambda: _prepare(rows, effective, body))

        @self.app.get(f"{api}/featuresets/{{name}}/versions/{{version}}/parts",
                      tags=["features"])
        def parts(request: Request, name: str, version: int):
            """The namespaces this version's data lives in, and their pins.

            An engine that wants to pull a large set in parallel reads this and
            fetches each part itself, rather than waiting on a join here.
            """
            self.authorise(request, "feature:read")
            return self.guard(lambda: transfer.featureset_table(name, version))

        # ------------------------------------------------------------ write
        @self.app.post(f"{api}/feature-views/{{name}}/data", status_code=201,
                       tags=["features"])
        async def load(request: Request, name: str):
            """Load feature values in. The body is Arrow, Parquet or NDJSON.

            The whole upload becomes one feature view version, because a version
            is what a featureset pins and half a version is not something
            anybody can pin.
            """
            who = self.authorise(request, "feature:materialise")
            body = await request.body()
            media = request.headers.get("content-type", "")
            return self.guard(lambda: transfer.load(name, body, media,
                                                    actor=self.actor(who)))

    # ------------------------------------------------------------------ util
    def _stream(self, chunks, fmt: str, stem: str) -> StreamingResponse:
        """A streaming response that names what it is and what it is called."""
        return StreamingResponse(
            chunks, media_type=MEDIA_TYPE[fmt],
            headers={"Content-Disposition":
                     f'attachment; filename="{stem}.{fmt}"',
                     "X-MAYA-Format": fmt})
