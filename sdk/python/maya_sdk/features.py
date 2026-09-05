"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Features, featuresets, and getting the rows out.

Two things this module will not do for you, both deliberate.

It will not **fill in a missing clock**. Every row needs `event_ts` (when the
fact was true) and `ingest_ts` (when it became known), and an SDK that helpfully
defaulted the second to the first would make every restatement invisible — which
is the single most common way a model is quietly wrong. The refusal happens at
the upload, where it is still fixable, rather than two layers later during
assembly.

It will not **materialise a dataset in memory to be helpful**. Feature values are
not small. `data()` streams to a file and hands back the path, because an SDK
that returns a list of dicts turns a few million rows into punctuation and then
into an out-of-memory error inside somebody's notebook.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

#: What a bulk read may ask for. `arrow` for an engine (zero-copy, incremental),
#: `parquet` for disk, `ndjson` for anything at all, `csv` for a person.
#: The formats the platform will *read back*, from `core/features/transfer.py`.
#:
#: This said `csv` and omitted `json`, which is the **upload** set — so the SDK
#: refused `json`, which works, and passed `csv`, which the platform then
#: refuses. A client-side list that disagrees with the server is worse than no
#: list: it turns a clear server refusal into a confusing local one, and lets
#: through the case it was meant to catch.
FORMATS = ("arrow", "parquet", "ndjson", "json")

#: Media types the upload endpoint reads a file as. The extension is a hint, and
#: a hint the caller may override — a `.txt` holding CSV is somebody's Tuesday.
MEDIA = {".csv": "text/csv", ".jsonl": "application/x-ndjson",
         ".ndjson": "application/x-ndjson", ".parquet": "application/vnd.apache.parquet",
         ".arrow": "application/vnd.apache.arrow.stream"}


class Features:
    """Governed signals, their values, and their lineage."""

    def __init__(self, maya):
        self._maya = maya

    def define(self, *, name: str, entity: str, dtype: str, description: str,
               owner: str, business_definition: str = "",
               source_system: str = "", sensitivity: str = "internal",
               pii: bool = False, protected_basis: bool = False,
               shape: Any = None,
               components: Optional[List[str]] = None) -> Dict[str, Any]:
        """A feature is an object with an owner and a lineage, not a column."""
        return self._maya.call("POST", "/features", json={
            "name": name, "entity": entity, "dtype": dtype,
            "description": description, "owner": owner,
            "business_definition": business_definition,
            "source_system": source_system, "sensitivity": sensitivity,
            "pii": pii, "protected_basis": protected_basis,
            "shape": shape, "components": components})

    def derive(self, *, name: str, expression: str, dtype: str,
               description: str, owner: str) -> Dict[str, Any]:
        """`Z = f(X, Y)`, computed rather than supplied.

        Two things happen without asking. Its ingest clock is the **maximum**
        over its inputs, which is arithmetic and therefore cannot be forgotten;
        and its lineage is walked whenever it is used, so a feature derived from
        the label is refused with the derivation chain named rather than with a
        bare no.
        """
        return self._maya.call("POST", "/derived-features", json={
            "name": name, "expression": expression, "dtype": dtype,
            "description": description, "owner": owner})

    def lineage(self, name: str) -> Dict[str, Any]:
        return self._maya.call("GET", f"/derived-features/{name}/lineage")

    def create_view(self, *, name: str, entity: str, owner: str,
                    features: List[str], description: str = "") -> Dict[str, Any]:
        """A view is where values live. One upload becomes one view version."""
        return self._maya.call("POST", "/feature-views", json={
            "name": name, "entity": entity, "owner": owner,
            "features": features, "description": description})

    def load(self, view: str, path: Union[str, Path], *,
             media_type: Optional[str] = None) -> Dict[str, Any]:
        """Upload a file of values. CSV, JSONL, Parquet or Arrow.

        The file must carry `entity_id`, `event_ts` and `ingest_ts`. A file with
        one clock is refused here rather than accepted and discovered later: with
        one clock you cannot answer *what did we know when the decision was
        made*, and a restatement silently rewrites history.

        Streamed from disk rather than read into memory, because the whole reason
        this endpoint exists is that these files are large.
        """
        path = Path(path)
        media = media_type or MEDIA.get(path.suffix.lower())
        if media is None:
            raise ValueError(
                f"cannot tell what {path.name} holds from its extension; pass "
                f"media_type explicitly — one of {sorted(set(MEDIA.values()))}")
        return self._maya.call("POST", f"/feature-views/{view}/data",
                               content=path.read_bytes(),
                               headers={"Content-Type": media})


class Featuresets:
    """A schema of named slots, and the versions that fill it."""

    def __init__(self, maya):
        self._maya = maya

    def define(self, *, name: str, entity: str, slots: Dict[str, Any],
               label_slot: Optional[str] = None, outcome_window_days: int = 0,
               grain: str = "", description: str = "",
               composes: Optional[List[Any]] = None,
               operations: Optional[List[Dict[str, Any]]] = None,
               defaults: Optional[Dict[str, Any]] = None,
               ephemeral: bool = False,
               ttl_days: Optional[float] = None) -> Dict[str, Any]:
        """Declare the schema. Constituents come later, with a version.

        `composes` and `operations` build one set from others by a left-to-right
        fold in which the **rightmost wins**. Each operation is total: an `add`
        of a slot that exists, a `drop` of one that does not, and an `override`
        that changes nothing are each refused, because an operation that silently
        did nothing is one somebody believes happened.
        """
        return self._maya.call("POST", "/featuresets", json={
            "name": name, "entity": entity, "slots": slots,
            "label_slot": label_slot, "outcome_window_days": outcome_window_days,
            "grain": grain, "description": description, "composes": composes,
            "operations": operations, "defaults": defaults,
            "ephemeral": ephemeral, "ttl_days": ttl_days})

    def preview(self, *, composes: Optional[List[Any]] = None,
                operations: Optional[List[Dict[str, Any]]] = None,
                slots: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """What would this resolve to? Runs the same fold without declaring it.

        Refuses exactly what declaring would, so an author can find out without
        filling the register with attempts.
        """
        return self._maya.call("POST", "/featuresets/preview", json={
            "composes": composes, "operations": operations, "slots": slots or {}})

    def get(self, name: str) -> Dict[str, Any]:
        return self._maya.call("GET", f"/featuresets/{name}")

    def resolved(self, name: str) -> Dict[str, Any]:
        """The schema after the fold, which is what a model is defined over."""
        return self._maya.call("GET", f"/featuresets/{name}/resolved")

    def fill(self, name: str, *, bindings: Dict[str, Any],
             label: Optional[Dict[str, Any]] = None,
             note: str = "") -> Dict[str, Any]:
        """Bind each slot to a feature and to the exact view version supplying it.

        The pin is the point: a filled version always resolves to the same bytes,
        because every binding names a Delta version rather than a path.
        """
        return self._maya.call("POST", f"/featuresets/{name}/versions", json={
            "bindings": bindings, "label": label, "note": note})

    def seal(self, name: str, *, note: str = "") -> Dict[str, Any]:
        """Freeze the schema. A sealed set can still be composed from, which is
        what sealing is for: a parent that cannot move is worth building on."""
        return self._maya.call("POST", f"/featuresets/{name}/seal",
                               json={"note": note})

    def training_set(self, name: str, *, version: int, spine: List[Dict[str, Any]],
                     as_of: float,
                     snapshot_name: Optional[str] = None) -> Dict[str, Any]:
        """Assemble a point-in-time-correct training set from a pinned version.

        The set supplies the columns; you supply the spine and the `as_of`. The
        snapshot it produces names the featureset version, so a fit warrant can
        pin the snapshot and recompute nothing.
        """
        return self._maya.call("POST", f"/featuresets/{name}/training-sets", json={
            "version": version, "spine": spine, "as_of": as_of,
            "name": snapshot_name})

    def data(self, name: str, *, version: int, into: Union[str, Path],
             as_of: Optional[float] = None,
             format: str = "parquet") -> Path:
        """Stream a featureset version's rows to a file. Returns the path.

        A path rather than a list of dictionaries, and that is the whole design
        of this method: these are not small, and an SDK that materialised them to
        be convenient would be convenient until the first real dataset.

        The read uses the **pinned** Delta version, so what comes out is what the
        version *is* rather than what its path has since become.
        """
        if format not in FORMATS:
            raise ValueError(f"format must be one of {', '.join(FORMATS)}")
        body = self._maya.call(
            "GET", f"/featuresets/{name}/versions/{version}/data",
            params={"as_of": as_of, "format": format}, raw=True)
        destination = Path(into)
        destination.write_bytes(body)
        return destination

    def parts(self, name: str, *, version: int) -> Dict[str, Any]:
        """Each namespace beneath a version and its pin, so a large set can be
        pulled in parallel rather than waiting on one join."""
        return self._maya.call(
            "GET", f"/featuresets/{name}/versions/{version}/parts")
