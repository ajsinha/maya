"""
``maya.sdk`` clients (§18.2): the only client library of MAYA.

``Client`` is synchronous and ``AsyncClient`` asynchronous; both expose the
same resource namespaces (``catalog``, ``features``, ``featuresets``,
``models``, ``training``, ``execution``, ``workflow``, ``jobs``, ``admin``,
``access``, ``namespaces``, ``auth``). The web UI uses ``AsyncClient`` with the
``inproc`` transport and the logged-in user's session token — no privileged
path, no shared key.

Credential resolution, first match wins: explicit ``api_key=`` → the
``MAYA_API_KEY`` environment variable → the named profile in
``~/.maya/config.toml`` → anonymous (health endpoints only).

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""

from __future__ import annotations

import io
import os
import time
import tomllib
from pathlib import Path
from typing import Any

import httpx

from maya.core.errors import MayaError, ValidationFailed
from maya.sdk.cache import PinCache
from maya.sdk.resources import (
    Access,
    Admin,
    Assistant,
    Auth,
    Catalog,
    Custody,
    Events,
    ExecutionWarrants,
    Features,
    FeatureSets,
    Jobs,
    Models,
    Namespaces,
    Sources,
    TrainingWarrants,
    Workflow,
    Workspaces,
)
from maya.sdk.transport import AsyncTransport, SyncTransport

API_PREFIX = "/api/v1"
TERMINAL = ("succeeded", "failed", "cancelled", "dead_letter")


class _Namespaces:
    def _bind(self, transport: Any) -> None:
        self._transport = transport
        self.auth = Auth(transport)
        self.admin = Admin(transport)
        self.namespaces = Namespaces(transport)
        self.access = Access(transport)
        self.catalog = Catalog(transport)
        self.features = Features(transport)
        self.featuresets = FeatureSets(transport)
        self.models = Models(transport)
        self.training = TrainingWarrants(transport)
        self.execution = ExecutionWarrants(transport)
        self.workflow = Workflow(transport)
        self.jobs = Jobs(transport)
        self.workspaces = Workspaces(transport)
        self.sources = Sources(transport)
        self.events = Events(transport)
        self.custody = Custody(transport)
        self.assistant = Assistant(transport)
        self.cache = PinCache()

    @property
    def reads(self) -> Any:
        """The ETag-revalidated read cache the transport holds — ``None`` on a cassette,
        which has no server to revalidate against (§18.1)."""
        return getattr(self._transport, "reads", None)


class Client(_Namespaces):
    """Synchronous client over HTTP (default) or in-process ASGI."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8600",
        *,
        api_key: str | None = None,
        token: str | None = None,
        app: Any = None,
        timeout: float = 120.0,
        channel: str = "sdk",
        verify: bool | str = True,
    ) -> None:
        credential = token or api_key
        _refuse_plain_http(base_url, credential, app)
        if app is not None:
            from starlette.testclient import TestClient

            http: httpx.Client = TestClient(app, base_url="http://inproc" + API_PREFIX)
            http.timeout = httpx.Timeout(timeout)
            self.mode = "inproc"
        else:
            http = httpx.Client(
                base_url=base_url.rstrip("/") + API_PREFIX,
                verify=verify,
                timeout=httpx.Timeout(timeout, connect=10.0),
            )
            self.mode = "http"
        self._http = http
        self._bind(SyncTransport(http, credential, channel))

    # -- record / replay (§18.2.7) -----------------------------------------------------
    @classmethod
    def record(
        cls, cassette: str | Path, base_url: str = "http://127.0.0.1:8600", **kw: Any
    ) -> "Client":
        """A live client that also writes every call and response to ``cassette``."""
        from maya.sdk.replay import RecordingTransport

        client = cls(base_url, **kw)
        client._bind(RecordingTransport(client._transport, cassette))
        client.mode = f"record ({client.mode})"
        return client

    @classmethod
    def replay(cls, cassette: str | Path) -> "Client":
        """A client served entirely from a recorded cassette: no server, no network."""
        from maya.sdk.replay import ReplayTransport

        client = cls.__new__(cls)
        client._http = None
        client.mode = "replay"
        client._bind(ReplayTransport(cassette))
        return client

    def close(self) -> None:
        if self._http is not None:
            self._http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- ergonomic layer ---------------------------------------------------------
    def wait(
        self, job: dict[str, Any] | str, *, timeout: float = 600.0, progress: Any = None
    ) -> dict[str, Any]:
        """Poll a job to a terminal state; never blocks forever (§18.2.5)."""
        job_id = job["id"] if isinstance(job, dict) else job
        deadline = time.monotonic() + timeout
        last = None
        while True:
            row = self.jobs.get(job_id)
            if progress and (row["progress"], row["message"]) != last:
                last = (row["progress"], row["message"])
                progress(row)
            if row["state"] in TERMINAL:
                if row["state"] != "succeeded":
                    raise MayaError(
                        f"Job {row['job_type']} {row['state']}: {row['error']}", job=job_id
                    )
                return row
            if time.monotonic() > deadline:
                raise MayaError(f"Timed out waiting for job {job_id}", job=job_id)
            time.sleep(0.3)

    # -- handles: §18.2.4's object shape over the same calls ----------------------
    def feature(self, ref: str) -> Any:
        """A feature as an object: ``feature(ref).version(4).pin("q1", as_of=...)``."""
        from maya.sdk.handles import FeatureHandle

        return FeatureHandle.of(
            self, self.features.get(ref), ref=ref, kind="feature", resource="features"
        )

    def featureset(self, ref: str) -> Any:
        """A feature set as an object, including a cascade pin over its members."""
        from maya.sdk.handles import FeatureSetHandle

        return FeatureSetHandle.of(
            self, self.featuresets.get(ref), ref=ref, kind="featureset", resource="featuresets"
        )

    def model(self, ref: str) -> Any:
        from maya.sdk.handles import ModelHandle

        return ModelHandle.of(self, self.models.get(ref), ref=ref, kind="model", resource="models")

    def warrant(self, warrant_id: str) -> Any:
        """A training warrant as an object: ``with warrant(id).data() as ds: …``."""
        from maya.sdk.handles import TrainingWarrantHandle

        return TrainingWarrantHandle.of(self, self.training.get(warrant_id))

    def job(self, job: dict[str, Any] | str) -> Any:
        """A job as an object: ``job(row).wait(progress=print)``."""
        from maya.sdk.handles import JobHandle

        row = job if isinstance(job, dict) else self.jobs.get(job)
        return JobHandle.of(self, row.get("job") or row)

    def training_data(self, warrant_id: str) -> tuple[Any, dict[str, Any]]:
        """Download, verify the checksum MAYA issued, and yield an Arrow table."""
        import pyarrow.parquet as pq
        from maya.sdk.io import table_checksum

        result = self.training.data(warrant_id)
        table = pq.read_table(io.BytesIO(result["data"]))
        checksum = table_checksum(table)
        if checksum != result["manifest"].get("checksum"):
            raise ValidationFailed(
                "Downloaded training data failed checksum verification",
                expected=result["manifest"].get("checksum"),
                actual=checksum,
            )
        return table, result["manifest"]


class AsyncClient(_Namespaces):
    """Asynchronous client — what the web tier uses so a render never blocks."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8600",
        *,
        api_key: str | None = None,
        token: str | None = None,
        app: Any = None,
        timeout: float = 120.0,
        channel: str = "sdk",
    ) -> None:
        credential = token or api_key
        if app is not None:
            transport = httpx.ASGITransport(app=app)
            http = httpx.AsyncClient(
                transport=transport, base_url="http://inproc" + API_PREFIX, timeout=timeout
            )
            self.mode = "inproc"
        else:
            _refuse_plain_http(base_url, credential, None)
            http = httpx.AsyncClient(base_url=base_url.rstrip("/") + API_PREFIX, timeout=timeout)
            self.mode = "http"
        self._http = http
        self._bind(AsyncTransport(http, credential, channel))

    # -- record / replay (§18.2.7) -----------------------------------------------------
    @classmethod
    def record(
        cls, cassette: str | Path, base_url: str = "http://127.0.0.1:8600", **kw: Any
    ) -> "AsyncClient":
        """A live asynchronous client that also writes every call to ``cassette``."""
        from maya.sdk.replay import AsyncRecordingTransport

        client = cls(base_url, **kw)
        client._bind(AsyncRecordingTransport(client._transport, cassette))
        client.mode = f"record ({client.mode})"
        return client

    @classmethod
    def replay(cls, cassette: str | Path) -> "AsyncClient":
        """An asynchronous client served entirely from a cassette (either client's)."""
        from maya.sdk.replay import AsyncReplayTransport

        client = cls.__new__(cls)
        client._http = None
        client.mode = "replay"
        client._bind(AsyncReplayTransport(cassette))
        return client

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()


def _refuse_plain_http(base_url: str, credential: str | None, app: Any) -> None:
    """A key is a bearer credential: never over plain HTTP beyond localhost (§18.2.2)."""
    if app is not None or not credential or base_url.startswith("https://"):
        return
    host = httpx.URL(base_url).host
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise ValidationFailed(
            f"Refusing to send a credential over plain HTTP to '{host}'. Use https://."
        )


def connect(
    profile: str | None = None, *, base_url: str | None = None, api_key: str | None = None
) -> Client:
    """Build a client from arguments, the environment, or ``~/.maya/config.toml``."""
    cfg: dict[str, Any] = {}
    if profile:
        path = Path(os.environ.get("MAYA_CONFIG", Path.home() / ".maya" / "config.toml"))
        if path.exists():
            cfg = tomllib.loads(path.read_text()).get("profiles", {}).get(profile, {})
        else:
            raise ValidationFailed(f"No SDK profile file at {path}")
    key = (
        api_key
        or os.environ.get("MAYA_API_KEY")
        or (os.environ.get(cfg["api_key_env"]) if cfg.get("api_key_env") else None)
    )
    url = base_url or os.environ.get("MAYA_URL") or cfg.get("base_url") or "http://127.0.0.1:8600"
    if os.environ.get("MAYA_DEBUG_AUTH"):
        source = (
            "argument"
            if api_key
            else "MAYA_API_KEY"
            if os.environ.get("MAYA_API_KEY")
            else f"profile {profile}"
            if key
            else "anonymous"
        )
        print(f"maya.sdk: credential from {source}")
    return Client(url, api_key=key)
