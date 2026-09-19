"""
Object references (§4): ``maya://<kind>/<namespace>/<name>[@vN | #series[/YYYY-MM-DD]]``.

``@`` addresses a version and ``#`` a pin series; a date after the series
selects one pin within it (D-2). A bare name — no ``@`` and no ``#`` — means
the latest approved version, and the resolution is recorded, so "latest"
never hides in an audit trail. The namespace may be omitted when the name is
unique across namespaces.

Copyright (c) 2026 Ashutosh Sinha. All rights reserved.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from maya.core.errors import ValidationFailed

KINDS = ("feature", "featureset", "model", "warrant/train", "warrant/exec", "job", "namespace")
_RE = re.compile(
    r"^maya://(?P<kind>feature|featureset|model|warrant/train|warrant/exec)/"
    r"(?P<path>[A-Za-z0-9_.\-/]+?)"
    r"(?:@v(?P<version>\d+)|#(?P<series>[A-Za-z0-9_.\-]+)(?:/(?P<asof>\d{4}-\d{2}-\d{2}))?)?$")


@dataclass(frozen=True)
class Ref:
    kind: str
    namespace: str | None
    name: str
    version: int | None = None
    series: str | None = None
    as_of: dt.date | None = None

    @property
    def is_pin(self) -> bool:
        return self.series is not None

    @property
    def is_bare(self) -> bool:
        return self.version is None and self.series is None

    def __str__(self) -> str:
        base = f"maya://{self.kind}/" + (f"{self.namespace}/" if self.namespace else "") + self.name
        if self.version is not None:
            return f"{base}@v{self.version}"
        if self.series is not None:
            return f"{base}#{self.series}" + (f"/{self.as_of.isoformat()}" if self.as_of else "")
        return base


def parse(text: str, default_kind: str | None = None) -> Ref:
    """Parse a reference; ``feature/x@v2`` and ``x@v2`` are accepted with a default kind."""
    text = text.strip()
    if not text.startswith("maya://"):
        if default_kind and not text.startswith(tuple(k + "/" for k in KINDS)):
            text = f"{default_kind}/{text}"
        text = "maya://" + text
    m = _RE.match(text)
    if not m:
        raise ValidationFailed(f"'{text}' is not a MAYA reference "
                               "(maya://kind/[namespace/]name[@vN|#series[/date]])", ref=text)
    path = m["path"].split("/")
    namespace, name = (path[0], path[1]) if len(path) == 2 else (None, path[-1])
    if len(path) > 2:
        raise ValidationFailed(f"'{text}': namespaces nest one level only", ref=text)
    as_of = dt.date.fromisoformat(m["asof"]) if m["asof"] else None
    return Ref(m["kind"], namespace, name,
               int(m["version"]) if m["version"] else None, m["series"], as_of)


def version_ref(kind: str, namespace: str, name: str, version_no: int) -> str:
    return str(Ref(kind, namespace, name, version=version_no))


def pin_ref(kind: str, namespace: str, name: str, series: str, as_of: dt.date) -> str:
    return str(Ref(kind, namespace, name, series=series, as_of=as_of))


def object_ref(kind: str, namespace: str, name: str) -> str:
    return str(Ref(kind, namespace, name))
