"""
Object handles and typed records (§18.2.4).

The SDK spoke in dictionaries: correct, and tiring to use. §18.2.4 writes the API as
objects — `feat.version(4).pin(...)`, `job.wait(progress=print)`, `pin.to_arrow()`,
`with warrant.data() as ds` — and that shape is most of what makes an SDK pleasant.

Every record here **is** a dict, so nothing that consumed the old return values breaks and
nothing has to be kept in step with the server's fields: a record wraps whatever came back
and gives it attribute access, one level at a time. What the handles add on top is the verb
that belongs to the thing: a feature knows how to pin, a pin knows how to become a table,
a job knows how to be waited on.

Handles carry the client, so they only exist where a client made them. `maya.offline(...)`
returns the same records, and the ones whose verbs need a server say so when called.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from maya.core.errors import MayaError, ValidationFailed


class Record(dict):
    """A server object: a dict, plus attribute access for the fields it happens to have.

    ``feature.latest_version`` is the same as ``feature["latest_version"]``; a nested dict
    comes back as a Record and a list of dicts as a list of Records, so
    ``fs.pins[0].content_hash`` reads the way §18.2.4 writes it. An unknown name raises
    ``AttributeError`` naming what is there, which is a better error than ``None``.
    """

    __slots__ = ()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return wrap(self[name])
        except KeyError:
            raise AttributeError(
                f"no field '{name}' on this {self.get('object_type') or 'record'}; "
                f"it carries: {', '.join(sorted(self)) or '(nothing)'}"
            ) from None

    def __dir__(self) -> list[str]:
        return sorted({*super().__dir__(), *(k for k in self if isinstance(k, str))})


def _iso(value: Any) -> Any:
    """A date or datetime as ISO text; anything else unchanged."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def wrap(value: Any) -> Any:
    """``value`` as records, one level at a time (dicts and lists of dicts)."""
    if isinstance(value, Record):
        return value
    if isinstance(value, dict):
        return Record(value)
    if isinstance(value, list):
        return [wrap(v) for v in value]
    return value


class Handle(Record):
    """A record that knows where it came from, so it can carry verbs.

    The client and the little context a verb needs (which reference this came from, which
    resource namespace owns it) live in slots, not in the dict: a handle still compares,
    prints and serialises as exactly the payload the server sent.
    """

    __slots__ = ("_attached", "_context")

    @classmethod
    def of(cls, client: Any, payload: dict[str, Any], **extra: Any) -> Any:
        handle = cls(payload)
        handle._attached = client
        handle._context = dict(extra)
        return handle

    @property
    def _client(self) -> Any:
        client = getattr(self, "_attached", None)
        if client is None:
            raise MayaError(
                "This record came from a bundle or a plain call, so it has no client to "
                "act through; use the resource methods on your client instead"
            )
        return client

    @property
    def _extra(self) -> dict[str, Any]:
        """The verb's context. Reading it asserts there is a client, so a record that came
        from a bundle says that plainly instead of raising KeyError on a field it never
        had."""
        context = getattr(self, "_context", None)
        if context is None:
            self._client  # raises, with the reason  # noqa: B018
        return context or {}


class JobHandle(Handle):
    """Slow work: ``job.wait(progress=print)``, ``job.cancel()``, ``job.progress()``."""

    __slots__ = ()

    def refresh(self) -> JobHandle:
        return JobHandle.of(self._client, self._client.jobs.get(self["id"]))

    def progress(self) -> tuple[int, str]:
        row = self._client.jobs.get(self["id"])
        return int(row["progress"]), str(row["message"] or "")

    def wait(self, *, timeout: float = 600.0, progress: Any = None) -> Record:
        """Poll to a terminal state, raising on failure and never blocking forever."""
        return wrap(self._client.wait(self["id"], timeout=timeout, progress=progress))

    def cancel(self) -> Record:
        return wrap(self._client.jobs.cancel(self["id"]))

    def events(self, timeout: float = 120.0) -> Any:
        return self._client.jobs.events(self["id"], timeout=timeout)


class PinHandle(Handle):
    """A sealed pin: immutable, so its bytes are cached by content hash and verified."""

    __slots__ = ()

    def to_arrow(self, *, shape: str = "tabular", **kw: Any) -> Any:
        """The pin's rows as an Arrow table, checksum-verified (and cached, §18.2.5)."""
        ref = self._extra["ref"]
        data = self._client.cache.pin_bytes(self._client, ref, self, shape=shape, **kw)
        import pyarrow.parquet as pq

        return pq.read_table(io.BytesIO(data))

    def to_pandas(self, **kw: Any) -> Any:
        return self.to_arrow(**kw).to_pandas()

    def to_polars(self, **kw: Any) -> Any:
        from maya.core.backends import has_module

        if not has_module("polars"):
            raise MayaError("to_polars() needs polars (pip install polars)")
        import polars as pl

        return pl.from_arrow(self.to_arrow(**kw))

    def to_file(self, path: str | Path, *, shape: str = "tabular", **kw: Any) -> Path:
        out = Path(path)
        ref = self._extra["ref"]
        out.write_bytes(self._client.cache.pin_bytes(self._client, ref, self, shape=shape, **kw))
        return out


class VersionHandle(Handle):
    """One version of a feature or feature set: what you pin, submit or approve."""

    __slots__ = ()

    def pin(self, pin_name: str, *, as_of: Any, **kw: Any) -> JobHandle:
        # §18.2.4 writes `as_of="2026-03-31"` and a date object is the natural thing to
        # pass; the wire is JSON, so dates become ISO text here rather than in the caller
        as_of = _iso(as_of)
        for key in ("as_of_known", "start", "end"):
            if key in kw:
                kw[key] = _iso(kw[key])
        extra = self._extra
        kind, ref = extra["kind"], extra["ref"]
        resource = getattr(self._client, "features" if kind == "feature" else "featuresets")
        out = resource.pin(ref, version_no=self["version_no"], pin_name=pin_name, as_of=as_of, **kw)
        return JobHandle.of(self._client, out.get("job") or out, ref=ref)

    def transition(self, name: str, **kw: Any) -> Record:
        extra = self._extra
        resource = getattr(
            self._client, "features" if extra["kind"] == "feature" else "featuresets"
        )
        return wrap(resource.transition(extra["ref"], self["version_no"], name, **kw))

    def submit(self, note: str = "") -> Record:
        return self.transition("submit", rationale=note or None)


class CatalogHandle(Handle):
    """Shared shape of a feature, feature set or model handle."""

    __slots__ = ()

    @property
    def ref(self) -> str:
        return str(self._extra["ref"])

    def version(self, version_no: int | None = None) -> VersionHandle:
        """One version, by number; the latest version by default."""
        versions = self.get("versions") or []
        # different payloads name it differently: a feature carries `latest_version`, a set
        # carries its versions and nothing else. The newest version is the default either way.
        wanted = (
            version_no
            or self.get("latest_version")
            or max((v.get("version_no") or 0 for v in versions), default=None)
        )
        rows = [v for v in versions if v.get("version_no") == wanted]
        if not rows:
            raise ValidationFailed(
                f"{self.ref} has no version {wanted}",
                available=[v.get("version_no") for v in self.get("versions") or []],
            )
        return VersionHandle.of(self._client, rows[0], ref=self.ref, kind=self._extra["kind"])

    def refresh(self) -> Any:
        resource = getattr(self._client, self._extra["resource"])
        return resource.get(self.ref)

    def preview(self, **kw: Any) -> Record:
        resource = getattr(self._client, self._extra["resource"])
        return wrap(resource.preview(self.ref, **kw))


class FeatureHandle(CatalogHandle):
    """§18.2.4's feature: clone it, extend it, override a rule, submit the draft."""

    __slots__ = ()

    def pins(self, **kw: Any) -> list[PinHandle]:
        rows = self._client.features.pins(self.ref, **kw)
        items = rows["items"] if isinstance(rows, dict) else rows
        return [PinHandle.of(self._client, r, ref=self.ref, kind="feature") for r in items]

    def pin(self, pin_name: str, *, as_of: Any, version_no: int | None = None, **kw: Any) -> Any:
        return self.version(version_no).pin(pin_name, as_of=as_of, **kw)

    def clone(self, name: str, *, namespace: str | None = None) -> FeatureHandle:
        """A new feature that inherits this one (§5.8's `extends`, binding `pinned`)."""
        ns, _, own = self.ref.partition("/")
        del own
        definition = {
            "extends": {
                "parent": f"{self.ref}@v{self.get('latest_version') or 1}",
                "binding": "pinned",
            }
        }
        out = self._client.features.create(namespace or ns, name, definition)
        return FeatureHandle.of(
            self._client, out, ref=f"{namespace or ns}/{name}", kind="feature", resource="features"
        )

    def override(self, **changes: Any) -> Record:
        """Change this feature's open draft — a resolution rule, a filter, a schema."""
        return wrap(self._client.features.update_draft(self.ref, **changes))

    def submit(self, note: str = "") -> Record:
        return self.version().submit(note)


class FeatureSetHandle(CatalogHandle):
    """A feature set, including a cascade pin over its members (§6.6)."""

    __slots__ = ()

    def pin(
        self,
        pin_name: str,
        *,
        as_of: Any,
        cascade: bool = False,
        version_no: int | None = None,
        **kw: Any,
    ) -> JobHandle:
        return self.version(version_no).pin(pin_name, as_of=as_of, cascade=cascade, **kw)


class ModelHandle(CatalogHandle):
    """A model: its draft, its specification, its conformance."""

    __slots__ = ()

    def conformance(self, version_no: int | None = None) -> Record:
        return wrap(
            self._client.models.conformance(self.ref, version_no or self.get("latest_version") or 1)
        )


class TrainingData:
    """What `with warrant.data() as ds:` yields: the frame, and X and y ready to fit.

    The context manager exists for the reason §9.1 gives: the download's checksum is the
    one a parameter upload must quote, so holding the data open and handing back the
    checksum with it is what keeps a fit attached to the rows it was fitted on. Leaving the
    block drops the frame; the checksum stays on the warrant handle.
    """

    def __init__(self, table: Any, manifest: dict[str, Any], target: str | None) -> None:
        self.table = table
        self.manifest = Record(manifest)
        self.checksum = manifest.get("checksum")
        self.target = target

    @property
    def frame(self) -> Any:
        return self.table.to_pandas()

    @property
    def y(self) -> Any:
        if not self.target:
            raise ValidationFailed("This warrant declares no target, so there is no y")
        return self.frame[self.target]

    @property
    def X(self) -> Any:  # noqa: N802 - the name every fitting library uses
        drop = [
            c
            for c in (self.target, "_split", "_knowledge_time")
            if c and c in self.table.column_names
        ]
        return self.frame.drop(columns=drop)

    def __enter__(self) -> TrainingData:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.table = None


class TrainingWarrantHandle(Handle):
    """§18.2.4's warrant: open its data, upload parameters, score the holdout, seal."""

    __slots__ = ()

    def data(self, *, shape: str = "tabular") -> TrainingData:
        table, manifest = self._client.training_data(self["id"])
        del shape  # the warrant's own shape governs; kept for the §18.2.4 signature
        return TrainingData(table, manifest, (self.get("spec") or {}).get("target"))

    def upload_parameters(self, values: dict[str, Any], **kw: Any) -> Record:
        return wrap(self._client.training.upload_parameters(self["id"], values, **kw))

    def score_holdout(self, **kw: Any) -> Record:
        return wrap(self._client.training.score_holdout(self["id"], **kw))

    def seal(self) -> Record:
        return wrap(self._client.training.seal(self["id"]))

    def bundle(self) -> Record:
        return wrap(self._client.training.export_bundle(self["id"]))

    def refresh(self) -> TrainingWarrantHandle:
        return TrainingWarrantHandle.of(self._client, self._client.training.get(self["id"]))


__all__ = [
    "CatalogHandle",
    "FeatureHandle",
    "FeatureSetHandle",
    "Handle",
    "JobHandle",
    "ModelHandle",
    "PinHandle",
    "Record",
    "TrainingData",
    "TrainingWarrantHandle",
    "VersionHandle",
    "wrap",
]
