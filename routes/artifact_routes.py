"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Uploading and retrieving the serialised model itself.

A version could always NAME an artifact and the engine verified its digest
before loading — but the bytes had to arrive on disk out of band, so the one
thing the whole chain of custody rests on came by a route the platform had no
view of.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Request
from fastapi.responses import StreamingResponse

from core.artifacts import FORMAT_MEANING, FORMATS
from routes.base import Routes


class ArtifactRoutes(Routes):
    def register(self) -> None:
        api, store = self.api, self.ctx["artifacts"]

        @self.app.get(f"{api}/artifact-formats", tags=["artifacts"])
        def formats(request: Request):
            """What may be stored, and which formats run code when they load."""
            self.principal(request)
            from core.artifacts import EXECUTES_ON_LOAD
            return {"formats": [{"format": f, "means": FORMAT_MEANING[f],
                                 "executes_on_load": f in EXECUTES_ON_LOAD}
                                for f in FORMATS]}

        @self.app.post(f"{api}/artifacts", status_code=201, tags=["artifacts"])
        async def upload(request: Request, format: str,
                         digest: Optional[str] = None):
            """Store a serialised model. The body is the file.

            **The digest is the address.** Storing the same weights twice stores
            them once, an artifact cannot be edited in place because edited
            bytes are a different address, and "these are the bytes the warrant
            names" is true by construction rather than by a check somebody
            remembered to write.

            Pass `digest` if you know what you are uploading: it is CHECKED
            rather than trusted, so a truncated upload is refused instead of
            being stored under the address of whatever arrived.
            """
            who = self.authorise(request, "version:create")
            body = await request.body()
            import io
            result = self.guard(lambda: store.put(io.BytesIO(body), format, digest))
            self.ctx["evidence"].append(
                "artifact_stored", "artifact", result["digest"],
                {"format": format, "size": result["size"],
                 "already_held": not result["stored"]}, actor=self.actor(who))
            return result

        @self.app.get(f"{api}/artifacts/{{digest}}", tags=["artifacts"])
        def download(request: Request, digest: str):
            """The bytes back, streamed."""
            self.authorise(request, "model:read")
            self.guard(lambda: store.require(digest))
            return StreamingResponse(
                store.stream(digest), media_type="application/octet-stream",
                headers={"Content-Disposition":
                         f'attachment; filename="{digest.split(":")[1][:16]}.bin"'})

        @self.app.get(f"{api}/artifacts/{{digest}}/verify", tags=["artifacts"])
        def verify(request: Request, digest: str):
            """Re-derive the digest from the bytes on disk.

            Content addressing makes tampering hard rather than impossible — the
            filesystem is still a filesystem. This is how you find out, and it is
            a separate call because re-hashing a multi-gigabyte file is not
            something a read should do every time.
            """
            self.authorise(request, "evidence:read")
            return self.guard(lambda: store.verify(digest))

        @self.app.get(f"{api}/artifact-usage", tags=["artifacts"])
        def usage(request: Request):
            """What the store is holding. Somebody has to be able to ask."""
            self.authorise(request, "evidence:read")
            return store.usage()
