"""
Retention: cold pins and archived ones (§7.3, §29.3).

§7.3 says pins are never deleted automatically, that cold pins move to an
infrequent-access tier after a configurable age, and that a retired pin can be archived to
a compressed bundle with its manifest. None of it was built. What is here, and what is not:

* **Cold** is a **statement, not a move.** MAYA marks which pins have gone unread past
  ``retention.cold_after_days`` and reports how many bytes they hold, so an operator can
  act on it. Moving bytes to an infrequent-access class is an object-store operation, and
  MAYA's lake is a directory: without the object-store backend of §25 there is nothing to
  move them to, and pretending otherwise would be the worst kind of green tick.
* **Archive** is real: a retired pin's rows, its manifest and its fragment list are packed
  into one compressed bundle, stored as a blob, and the pin records the blob and its hash.
  The bundle re-reads: ``restore`` returns the table and refuses if it does not hash to
  what was sealed, so an archive that rotted is caught rather than served.

Archiving does **not** delete the pin's fragments. They are content-addressed and shared
with every other pin that holds the same rows, and MAYA's lake layer has no delete, so
removing them safely is the §29.3 collector — not built, and named in the runbook.

Copyright (c) 2026 Ashutosh Sinha.  All rights reserved.
"""

from __future__ import annotations

import datetime as dt
import gzip
import io
import json
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from maya.core import canonical, djson
from maya.core.clock import utcnow
from maya.core.errors import NotApproved, PermissionDenied, ValidationFailed

FORMAT = "maya-pin-archive-1"
DEFAULT_COLD_AFTER_DAYS = 180


class RetentionService:
    def __init__(self, platform: Any) -> None:
        self.p = platform

    # -- cold -------------------------------------------------------------------
    def cold_after_days(self) -> int:
        return self.p.settings.int("retention.cold_after_days", DEFAULT_COLD_AFTER_DAYS)

    def cold_report(self, p: Any = None, days: int | None = None) -> dict[str, Any]:
        """Which sealed pins have gone unread long enough to be called cold, and what they
        hold. A report, not a move: see this module's own note."""
        cutoff = utcnow() - dt.timedelta(days=days if days is not None else self.cold_after_days())
        cold, warm, cold_bytes, warm_bytes = [], 0, 0, 0
        with self.p.uow() as uow:
            for table in ("feature_pins", "feature_set_pins"):
                for pin in uow.repo(table).list(state="sealed"):
                    last = pin.get("last_read_at") or pin["created_at"]
                    size = int(pin.get("bytes_total") or 0)
                    if last <= cutoff:
                        cold.append(
                            {
                                "table": table,
                                "id": pin["id"],
                                "pin_name": pin["pin_name"],
                                "as_of_date": pin["as_of_date"],
                                "last_touched": last,
                                "bytes_total": size,
                            }
                        )
                        cold_bytes += size
                    else:
                        warm += 1
                        warm_bytes += size
        return {
            "cold_after_days": days if days is not None else self.cold_after_days(),
            "cold_pins": len(cold),
            "cold_bytes": cold_bytes,
            "warm_pins": warm,
            "warm_bytes": warm_bytes,
            "pins": sorted(cold, key=lambda r: r["last_touched"])[:200],
            "note": "MAYA names cold pins; moving their bytes to an infrequent-access "
            "class needs an object-store backend, which is not built (§25).",
        }

    # -- archive ----------------------------------------------------------------
    def archive(self, p: Any, pin_id: str, *, table: str = "feature_pins") -> dict[str, Any]:
        """Pack a retired pin into one compressed bundle and record where it went."""
        if not p.is_admin:
            raise PermissionDenied("Archiving a pin is for administrators")
        with self.p.uow() as uow:
            pin = uow.repo(table).require(pin_id)
            if pin["state"] != "retired":
                raise NotApproved(
                    f"Only a retired pin is archived; this one is '{pin['state']}'. "
                    "Retire it first, with a reason.",
                    state=pin["state"],
                )
            if pin.get("archive_blob"):
                return {"pin_id": pin_id, "blob": pin["archive_blob"], "already": True}
            kind, namespace, name = self._where(uow, table, pin)
        written = self.p.featuresets.stored(pin) if table == "feature_set_pins" else True
        rows = None
        if written and pin["fragments"]:
            rows = self.p.lake.read_pin(kind, namespace, name, pin["fragments"])
        body = self._bundle(pin, rows, namespace, name, kind)
        digest = self.p.blobs.put(body)
        with self.p.uow(p.username) as uow:
            row = uow.repo(table).update(
                pin_id,
                {"archive_blob": digest, "archived_at": utcnow()},
            )
            uow.audit(
                "pin.archived",
                object_type="feature_pin" if table == "feature_pins" else "feature_set_pin",
                object_ref=pin_id,
                detail={"blob": digest, "bytes": len(body), "rows": rows.num_rows if rows else 0},
            )
        return {
            "pin_id": pin_id,
            "blob": digest,
            "bytes": len(body),
            "rows": rows.num_rows if rows else 0,
            "content_hash": pin["content_hash"],
            "note": "the pin's fragments are shared with other pins and are not deleted; "
            "collecting them is the §29.3 collector, which is not built",
            "row_version": row["row_version"],
        }

    def restore(self, p: Any, pin_id: str, *, table: str = "feature_pins") -> dict[str, Any]:
        """Read an archived pin back, refusing an archive that no longer hashes true."""
        if not p.is_admin:
            raise PermissionDenied("Reading a pin archive is for administrators")
        with self.p.uow() as uow:
            pin = uow.repo(table).require(pin_id)
        if not pin.get("archive_blob"):
            raise ValidationFailed("This pin has not been archived")
        raw = gzip.decompress(self.p.blobs.get(pin["archive_blob"]))
        with io.BytesIO(raw) as buf:
            payload = json.loads(buf.readline().decode("utf-8"))
            data = buf.read()
        rows = pq.read_table(io.BytesIO(data)) if data else None
        if rows is not None:
            schema_hex, runs = self.p.lake.plan_fragments(rows)
            actual = canonical.content_hash(schema_hex, [d for d, _, _ in runs])
            if actual != pin["content_hash"]:
                raise ValidationFailed(
                    "This archive no longer hashes to the pin it was made from: it has "
                    "been altered or damaged",
                    expected=pin["content_hash"],
                    actual=actual,
                )
        return {"manifest": payload, "table": rows, "verified": rows is not None}

    # -- the collector (§29.3) ---------------------------------------------------
    def collect(
        self, p: Any, *, dry_run: bool = True, keep_hours: float | None = None
    ) -> dict[str, Any]:
        """Remove fragments no pin references — provably, and reversibly for a while.

        §29.3 asks for a collector that is *provably safe*. What makes it provable here is
        the order of the checks, all inside one pass:

        1. a fragment is a candidate only if **no pin row of any state** names it — not
           sealed, not materializing, not failed, not retired, not archived;
        2. a candidate is skipped if any pin was created since the pass began, because a pin
           in flight may be about to claim it (the writer records fragments before it seals);
        3. what remains is removed with a Delta **remove** commit, so the bytes stay on disk
           until a vacuum past the retention window takes them, and time travel still
           answers in between.

        Nothing is removed by a schedule: this runs when an administrator asks. ``dry_run``
        is the default, because an operator should see the list before it goes.
        """
        if not p.is_admin:
            raise PermissionDenied("Collecting fragments is for administrators")
        started = utcnow()
        with self.p.uow() as uow:
            claimed: set[str] = set()
            recent = False
            for table in ("feature_pins", "feature_set_pins"):
                for pin in uow.repo(table).list():
                    claimed.update(pin["fragments"] or [])
                    if pin["created_at"] and pin["created_at"] >= started:
                        recent = True
            fragments = uow.repo("fragments").list()
        orphans = [f for f in fragments if f["hash"] not in claimed]
        if recent:
            return {
                "collected": 0,
                "orphans": len(orphans),
                "refused": "a pin was created while this pass was reading; nothing was "
                "removed. A pin records its fragments before it seals, so a pass that "
                "overlaps one cannot prove what is unreferenced. Run it again.",
            }
        by_table: dict[str, list[str]] = {}
        for fragment in orphans:
            by_table.setdefault(fragment["lake_table"], []).append(fragment["hash"])
        plan = [
            {
                "lake_table": table,
                "fragments": len(digests),
                "bytes": sum(f["bytes"] for f in orphans if f["lake_table"] == table),
            }
            for table, digests in sorted(by_table.items())
        ]
        if dry_run:
            return {
                "dry_run": True,
                "orphans": len(orphans),
                "bytes": sum(f["bytes"] for f in orphans),
                "plan": plan,
                "note": "nothing was removed; run with dry_run=False to remove these",
            }
        removed, freed = 0, 0
        for table, digests in sorted(by_table.items()):
            out = self.p.lake.delete_fragments(table, digests)
            removed += out["filesRemoved"]
            freed += out["bytesRemoved"]
        with self.p.uow(p.username) as uow:
            for fragment in orphans:
                uow.repo("fragments").delete_where(
                    hash=fragment["hash"], lake_table=fragment["lake_table"]
                )
            uow.audit(
                "fragments.collected",
                detail={"fragments": len(orphans), "files": removed, "bytes": freed},
            )
        return {
            "dry_run": False,
            "collected": len(orphans),
            "files_removed": removed,
            "bytes_removed": freed,
            "note": "the files are removed from the table's current version; a vacuum past "
            "the retention window frees the disk, and until then time travel still answers",
        }

    def _bundle(
        self, pin: dict[str, Any], rows: pa.Table | None, namespace: str, name: str, kind: str
    ) -> bytes:
        """One line of JSON — what this pin was — then the rows as parquet, all gzipped."""
        header = {
            "format": FORMAT,
            "pin_id": pin["id"],
            "kind": kind,
            "namespace": namespace,
            "name": name,
            "pin_name": pin["pin_name"],
            "as_of_date": pin["as_of_date"],
            "as_of_known": pin["as_of_known"],
            "content_hash": pin["content_hash"],
            "row_count": pin["row_count"],
            "bytes_total": pin["bytes_total"],
            "fragments": pin["fragments"],
            "manifest": pin.get("manifest") or {},
            "retired_at": pin.get("retired_at"),
            "retire_reason": pin.get("retire_reason"),
            "archived_at": utcnow(),
        }
        buf = io.BytesIO()
        buf.write(djson.dumps(header).encode("utf-8") + b"\n")
        if rows is not None:
            table_buf = io.BytesIO()
            pq.write_table(rows, table_buf, compression="zstd")
            buf.write(table_buf.getvalue())
        return gzip.compress(buf.getvalue())

    def _where(self, uow: Any, table: str, pin: dict[str, Any]) -> tuple[str, str, str]:
        if table == "feature_pins":
            feature = uow.repo("features").require(pin["feature_id"])
            ns = uow.repo("namespaces").require(feature["namespace_id"])
            return "pins", ns["name"], feature["name"]
        fs = uow.repo("feature_sets").require(pin["feature_set_id"])
        ns = uow.repo("namespaces").require(fs["namespace_id"])
        return "fspins", ns["name"], fs["name"]


__all__ = ["DEFAULT_COLD_AFTER_DAYS", "FORMAT", "RetentionService"]
