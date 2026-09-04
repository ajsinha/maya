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

from core.features.transfer import MEDIA_TYPE, describe as describe_transfer
from core.features.transfer import normalise
from routes.base import Routes


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
                            format: Optional[str] = None,
                            limit: Optional[int] = None):
            """Copy a whole featureset version out, joined on the entity key.

            A featureset spans several namespaces, so this is a join. A client
            wanting parallelism should read the parts instead — `/parts` says
            what they are.
            """
            self.authorise(request, "feature:read")
            chosen = self.guard(
                lambda: normalise(format, request.headers.get("accept")))
            if chosen == "json":
                rows = self.guard(lambda: [
                    r for batch in transfer.featureset_batches(
                        name, version, min(limit or 1000, 10_000))
                    for r in batch.to_pylist()])
                return {"featureset": name, "version": version,
                        "returned": len(rows), "rows": rows,
                        "detail": "json is capped; ask for arrow or parquet to "
                                  "take the whole thing"}
            return self._stream(
                transfer.featureset_stream(name, version, chosen, limit),
                chosen, f"{name}-v{version}")

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
