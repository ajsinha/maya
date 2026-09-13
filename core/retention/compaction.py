"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Reclaiming what a deletion left on disk — and being honest that it is a second,
later, differently-dangerous act.

## Deleting a model frees almost nothing

`model_version` blocks deletion. A model cannot go while any version of it
exists, so by the time the deleter runs there are no versions left, and the
artifacts those versions named were orphaned earlier, by whatever removed them.
The bytes on disk are not the deleted model's bytes. They are **whatever
nothing references any more**, accumulated over the life of the install, and
nothing has ever reclaimed them.

That is the honest framing, and it changes the design. This is not "clean up
after a deletion". It is a **refcount sweep over two content-addressed stores**
that a deletion happens to be one cause of.

## Why a sweep cannot delete what it finds

Both stores address by digest, so two models sharing a checkpoint share one
file, and a per-model delete would take the surviving model's bytes with it.
Reclamation therefore asks the register, not the deletion: *does any surviving
row name this digest?*

But "no row names it" is a fact about **one moment**, and the moment is racy in
the worst direction. An upload writes the bytes and then writes the row that
references them. A sweeper walking past in between sees a file nothing points
at, which is exactly what a real orphan looks like — and deletes the artifact
of a model somebody is registering.

So a sweep **marks**, and a later sweep reclaims what is still unreferenced.
`SIGHTINGS_BEFORE_SWEEP` passes with a reference appearing in none of them is a
much stronger statement than one pass, and a blob that acquires a reference in
between has its mark cleared and is never touched again. The quarantine is the
gap between passes, which makes it an interval something has to survive rather
than a timestamp somebody trusts.

## What this does not reach

The `data.delta` root holds one directory per view version, and this does not
touch it. Delta keeps its own transaction log, a directory is not addressed by
content, and removing files under a table Delta believes in is how a reader
gets a manifest naming a part file that is not there. Compacting Delta is
Delta's operation, not this one's, and doing it badly from outside would
corrupt a table rather than shrink it.

Reported, not silently skipped: `plan()` returns the Delta root's size under
`not_reclaimable`, so an operator looking at disk usage sees the number and
sees that this tool is not the thing that will move it.

## VACUUM is the half that actually is about the deletion

A cascade removes rows from up to eight tables. SQLite keeps the pages, so the
file does not shrink and the space is reused only by later inserts. `VACUUM`
rewrites it. It needs free space equal to the database and it takes a write
lock for the duration, which is why it is asked for rather than automatic.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from core.log import get_logger
from core.retention.common import RetentionError

logger = get_logger(__name__)

#: Consecutive sweeps that must find a blob unreferenced before it goes.
#:
#: Two, not one, because one is a race. Not more, because each pass costs a
#: full walk of both stores and the marginal safety after the second is small
#: next to the cost of never reclaiming anything.
SIGHTINGS_BEFORE_SWEEP = 2

#: Columns that hold a content address, and the tables they are on.
#:
#: This is the refcount. A digest missing from here is a digest this sweep
#: believes nothing references — so a new column holding an artifact address
#: and not listed here means a live artifact gets marked, then deleted.
#: `tests/test_compaction.py` walks the schema for `digest`-shaped columns and
#: fails if one is not accounted for.
REFERENCED_BY: Dict[str, Sequence[tuple]] = {
    "artifact": (("model_version", "artifact_digest"),),
    "attachment": (("attachment", "digest"),),
}

STORES = tuple(REFERENCED_BY)


class Compaction:
    """Marks unreferenced blobs, sweeps ones that stayed unreferenced."""

    def __init__(self, db, repo, *, artifacts=None, attachments=None,
                 delta_root: Optional[Path] = None, holds=None,
                 tombstones=None, evidence=None):
        self.db, self.repo = db, repo
        self.stores = {"artifact": artifacts, "attachment": attachments}
        self.delta_root = Path(delta_root) if delta_root else None
        self.holds, self.tombstones, self.evidence = holds, tombstones, evidence

    # ------------------------------------------------------------------- plan
    def plan(self) -> Dict[str, Any]:
        """What a sweep would reclaim, without reclaiming it.

        The default answer to "should I compact?", because the destructive
        version of this is not reversible and the plan is cheap.
        """
        marks = {(m["store"], m["digest"]): m for m in self.repo.many()}
        out: Dict[str, Any] = {"stores": [], "would_reclaim_bytes": 0,
                               "would_mark": 0, "would_sweep": 0}
        for store in STORES:
            unref = self._unreferenced(store)
            ready: List[Tuple[str, int]] = []
            marked: List[Tuple[str, int]] = []
            fresh: List[Tuple[str, int]] = []
            for digest, size in unref.items():
                mark = marks.get((store, digest))
                seen = (mark["sightings"] + 1) if mark else 1
                (ready if seen >= SIGHTINGS_BEFORE_SWEEP
                 else (marked if mark else fresh)).append((digest, size))
            out["stores"].append({
                "store": store,
                "unreferenced": len(unref),
                "ready_to_sweep": len(ready),
                "awaiting_another_pass": len(marked) + len(fresh),
                "bytes_ready": sum(s for _, s in ready),
            })
            out["would_reclaim_bytes"] += sum(s for _, s in ready)
            out["would_sweep"] += len(ready)
            out["would_mark"] += len(marked) + len(fresh)
        out["not_reclaimable"] = self._delta_size()
        out["database_free_pages"] = self._free_pages()
        return out

    # ------------------------------------------------------------------ sweep
    def sweep(self, *, actor: str = "system",
              dry_run: bool = False) -> Dict[str, Any]:
        """Mark what nothing references; reclaim what stayed that way.

        Refused entirely while any estate-wide legal hold is active. A hold is
        the instruction not to destroy, and a sweep is destruction with a
        refcount in front of it — the refcount answers *is this needed*, not
        *am I allowed*.
        """
        self._refuse_under_estate_hold()
        result: Dict[str, Any] = {"dry_run": dry_run, "marked": 0,
                                  "cleared": 0, "swept": 0,
                                  "reclaimed_bytes": 0, "by_store": {}}
        for store in STORES:
            handle = self.stores.get(store)
            if handle is None:
                continue
            unref = self._unreferenced(store)
            swept, freed, marked, cleared = 0, 0, 0, 0

            # A mark on something that now has a reference is cleared. Not
            # left to expire: the next sweep would see a two-pass-old mark on
            # a live blob and reclaim it.
            for mark in self.repo.many(store=store):
                if mark["digest"] not in unref:
                    if not dry_run:
                        self.repo.remove(id=mark["id"])
                    cleared += 1

            for digest, size in unref.items():
                mark = self.repo.one(store=store, digest=digest)
                seen = (mark["sightings"] + 1) if mark else 1
                if seen < SIGHTINGS_BEFORE_SWEEP:
                    if not dry_run:
                        if mark:
                            self.repo.set({"sightings": seen,
                                           "last_seen_at": time.time()},
                                          id=mark["id"])
                        else:
                            self.repo.add({"store": store, "digest": digest,
                                           "bytes": size,
                                           "first_seen_at": time.time(),
                                           "last_seen_at": time.time(),
                                           "sightings": 1})
                    marked += 1
                    continue
                if not dry_run:
                    self._remove(store, digest)
                    if mark:
                        self.repo.remove(id=mark["id"])
                swept += 1
                freed += size
            result["by_store"][store] = {"marked": marked, "cleared": cleared,
                                         "swept": swept, "bytes": freed}
            result["marked"] += marked
            result["cleared"] += cleared
            result["swept"] += swept
            result["reclaimed_bytes"] += freed

        if not dry_run and result["swept"]:
            logger.warning("compaction swept %d blob(s), %d bytes, by %s",
                           result["swept"], result["reclaimed_bytes"], actor)
            if self.evidence is not None:
                self.evidence.append(
                    "storage_compacted", "platform", "compaction",
                    {"swept": result["swept"],
                     "reclaimed_bytes": result["reclaimed_bytes"],
                     "by_store": result["by_store"]}, actor=actor)
        return result

    # ----------------------------------------------------------------- vacuum
    def vacuum(self, *, actor: str = "system") -> Dict[str, Any]:
        """Rewrite the database so removed rows stop occupying the file.

        Only worth asking for after a cascade. Takes a write lock for its
        duration and needs free space equal to the database, so it is an act
        somebody chooses at a quiet moment rather than something a deletion
        does on its way out.
        """
        self._refuse_under_estate_hold()
        before = self._file_bytes()
        self.db.execute("VACUUM")
        after = self._file_bytes()
        logger.warning("vacuum by %s: %s -> %s bytes", actor, before, after)
        return {"before_bytes": before, "after_bytes": after,
                "reclaimed_bytes": max(0, (before or 0) - (after or 0)),
                "measured": before is not None}

    # ----------------------------------------------------------- tombstones
    def mark_compacted(self, urn: str, *, actor: str,
                       reclaimed: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Record on the tombstone that the storage behind it is gone."""
        if self.tombstones is None:
            raise RetentionError(
                "no_tombstones",
                "this deployment has no tombstone register wired",
                "construct Compaction with tombstones=")
        stone = self.tombstones.of(urn)
        if not stone:
            raise RetentionError(
                "no_tombstone",
                f"there is no tombstone for {urn}",
                "only a deleted model has storage to reclaim; a model still "
                "registered is compacted by deleting it first")
        if stone.get("compacted_at"):
            raise RetentionError(
                "already_compacted",
                f"{urn} was compacted on {_when(stone['compacted_at'])} by "
                f"{stone.get('compacted_by') or 'somebody'}",
                "there is nothing further to reclaim; the tombstone stays "
                "either way, because it is the identity, not the storage")
        self.tombstones.repo.set(
            {"compacted_at": time.time(), "compacted_by": actor,
             "reclaimed": dict(reclaimed or {})}, id=stone["id"])
        return self.tombstones.of(urn)

    # --------------------------------------------------------------- internal
    def _unreferenced(self, store: str) -> Dict[str, int]:
        """Digests present on disk that no surviving row names."""
        handle = self.stores.get(store)
        if handle is None or not getattr(handle, "root", None):
            return {}
        root = Path(handle.root)
        if not root.is_dir():
            return {}
        held: Set[str] = set()
        for table, column in REFERENCED_BY[store]:
            for row in self.db.query(
                    f"SELECT DISTINCT {column} AS d FROM {table} "
                    f"WHERE {column} IS NOT NULL AND {column} != ''"):
                held.add(str(row["d"]))
        out: Dict[str, int] = {}
        for path in root.rglob("*"):
            if not path.is_file() or path.name.endswith(".partial"):
                continue
            digest = f"sha256:{path.name}"
            if digest in held or path.name in held:
                continue
            try:
                out[digest] = path.stat().st_size
            except OSError as exc:
                # Vanished, or unreadable, between the walk and the stat. Not
                # an orphan this pass can speak for, so it is skipped — and
                # logged, because a store the sweeper cannot read looks
                # exactly like a store with nothing in it.
                logger.warning("cannot size %s in the %s store, skipping: %s",
                               path.name[:16], store, exc)
                continue
        return out

    def _remove(self, store: str, digest: str) -> None:
        handle = self.stores.get(store)
        if handle is None:
            return
        # The store owns its own layout; asking it where a digest lives is
        # better than a second copy of the fan-out rule in this file.
        path = handle._path(digest)
        try:
            path.unlink()
        except FileNotFoundError:
            # Already gone. Two passes marked it and something else removed it
            # in between; the outcome is the one intended, so this is not an
            # error, but it means somebody else is writing to this store.
            logger.info("blob %s was already gone from the %s store",
                        digest[:23], store)
            return
        # Tidy the fan-out directories, outward until one still holds
        # something. Asked rather than attempted-and-caught: a non-empty
        # directory is the *normal* outcome here, and a handler for it would
        # log noise on every sweep or say nothing on every sweep, which are
        # the only two things a handler for an expected case can do.
        for parent in (path.parent, path.parent.parent):
            if parent == Path(self.stores[store].root) or any(parent.iterdir()):
                break
            parent.rmdir()

    def _refuse_under_estate_hold(self) -> None:
        if self.holds is None:
            return
        covering = [h for h in self.holds.active()
                    if h.get("scope_kind") == "estate"]
        if not covering:
            return
        matters = ", ".join(sorted(h.get("reference", "?") for h in covering))
        raise RetentionError(
            "under_legal_hold",
            f"{len(covering)} estate-wide legal hold(s) are active: {matters}",
            "lift the hold first. A refcount says whether bytes are needed by "
            "the register; a hold says whether anyone is permitted to destroy "
            "them, and the first is not an answer to the second")

    def _delta_size(self) -> Dict[str, Any]:
        if not self.delta_root or not self.delta_root.is_dir():
            return {"delta_bytes": 0, "why": "no delta root configured"}
        total = sum(p.stat().st_size for p in self.delta_root.rglob("*")
                    if p.is_file())
        return {"delta_bytes": total,
                "why": "Delta keeps its own transaction log; removing part "
                       "files from outside it produces a manifest naming a "
                       "file that is not there. Compacting a Delta table is "
                       "Delta's operation, not this one's"}

    def _free_pages(self) -> int:
        try:
            row = self.db.query_one("PRAGMA freelist_count")
        except Exception as exc:
            # PostgreSQL has no freelist pragma. Reported as zero, and said
            # out loud, because a plan showing no reclaimable pages on a
            # dialect that cannot answer is a plan making a claim it has not
            # checked.
            logger.info("free pages not measurable on this dialect: %s", exc)
            return 0
        if not row:
            return 0
        return int(next(iter(row.values())) or 0)

    def _file_bytes(self) -> Optional[int]:
        url = str(getattr(self.db, "url", "") or "")
        if not url.startswith("sqlite:///") or ":memory:" in url:
            return None
        path = Path(url[len("sqlite:///"):])
        return path.stat().st_size if path.is_file() else None

    @staticmethod
    def describe() -> List[Dict[str, str]]:
        return [{"store": s,
                 "referenced_by": ", ".join(f"{t}.{c}"
                                            for t, c in REFERENCED_BY[s])}
                for s in STORES]


def _when(at: Optional[float]) -> str:
    if not at:
        return "an unrecorded date"
    return time.strftime("%Y-%m-%d", time.gmtime(float(at)))
