"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

What a backup of a governance register has to be, over and above a file copy.

`docs/10 §2.3` lists backup and restore under *the operating* — the things that
belong to whoever runs the platform. That is right about **storage** and wrong
about **verification**, and the difference is the whole reason these tools exist.

A filesystem snapshot or a `pg_basebackup` copies bytes correctly. What neither
can tell you is the thing a model risk function needs to know:

> **Did the evidence chain survive?**

A register whose chain does not verify after a restore has lost its audit trail
while appearing to be back. Every governance decision in it — who approved what,
who may act next, whether a developer approved their own version — is read off
that chain, and a broken one does not fail closed. It reads as *no evidence*,
which is indistinguishable from *nothing happened*.

## The five stores

A MAYA instance is not one thing on disk. Missing any of these produces a
restore that starts, serves pages, and is wrong:

| | What is in it | Losing it means |
|---|---|---|
| the control database | the register, and the evidence chain | everything |
| `data/artifacts/` | content-addressed model artifacts | digests in the register that resolve to nothing |
| `data/attachments/` | uploaded documents | a documentation graph with holes, and search that finds less |
| `data/delta/` | features, snapshots, telemetry, monitoring | training sets that cannot be reproduced, and `L-19` unanswerable |
| `data/worm/` | the chain anchors | the only check an attacker with the database cannot defeat |

The last is the one most likely to be left out of a backup script somebody
writes in a hurry, and it is the one whose absence is least visible: the chain
still verifies **against itself** without it.

## What these tools refuse to do

**They do not back up PostgreSQL.** `pg_dump` and `pg_basebackup` exist, are
better than anything here, and are what an operator already has. Reimplementing
them badly inside a governance platform would be the platform doing a job it is
not the right tool for — the same argument it makes about not running models.
What `backup.py` does on PostgreSQL is refuse, name the command, and offer to
verify and manifest the result once the operator has taken it.

**They do not encrypt, and they do not ship anything anywhere.** A backup
contains personal data from the feature store. Where it goes, who may read it
and how long it is kept are decisions with a retention schedule and a legal
basis attached, and a tool that quietly wrote them to a path would be making
them.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time
from typing import Any, Dict, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: What the manifest is, and the version of its shape. A restore reads a
#: manifest written by a possibly older backup, so the shape is versioned from
#: the first release rather than from the first time it changes.
MANIFEST = "maya-backup.json"
MANIFEST_VERSION = 1

#: The stores, in the order they are copied. The database goes LAST on the way
#: out and FIRST on the way in, for a reason worth keeping: the chain head
#: recorded in the manifest must not be newer than the artifacts it refers to.
STORES: Tuple[Tuple[str, str], ...] = (
    ("artifacts", "data.artifacts"),
    ("attachments", "data.attachments"),
    ("delta", "data.delta.dir"),
    ("worm", "data.worm"),
)


def load_config(path: str):
    """The platform's own configurator, so a backup reads what the app reads."""
    sys.path.insert(0, str(ROOT))
    from core.config import PropertiesConfigurator
    PropertiesConfigurator.reset()
    return PropertiesConfigurator(path, reload_interval=0)


def dialect_of(cfg) -> str:
    """The dialect from the URL string, without connecting.

    Read before opening anything, because the PostgreSQL answer here is "use
    `pg_dump`" — and being told that must not require the PostgreSQL driver to
    be installed. The first version constructed a `Database` first and died on
    a missing `psycopg2` while trying to explain that it was not going to use
    it.
    """
    url = str(cfg.get("database.url", "sqlite:///data/sqlite/maya.db"))
    return url.split(":", 1)[0].split("+", 1)[0].lower()


def open_database(cfg):
    sys.path.insert(0, str(ROOT))
    from db.database import Database
    return Database(cfg.get("database.url", "sqlite:///data/sqlite/maya.db"))


def evidence_for(db):
    sys.path.insert(0, str(ROOT))
    from core.evidence import EvidenceEngine
    from db import EvidenceRepository
    return EvidenceEngine(EvidenceRepository(db))


def digest_of(path: pathlib.Path) -> str:
    """SHA-256 of one file, read in blocks so a large Delta part does not
    have to fit in memory."""
    out = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            out.update(block)
    return "sha256:" + out.hexdigest()


def tree_digest(root: pathlib.Path) -> Dict[str, Any]:
    """A digest over a directory, and the count and bytes behind it.

    Path-sensitive on purpose: two files with the same content at different
    paths are not the same store, and a restore that silently moved one would
    leave a digest that still matched.
    """
    if not root.exists():
        return {"present": False, "files": 0, "bytes": 0, "digest": None}
    rolling = hashlib.sha256()
    files = size = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rolling.update(str(path.relative_to(root)).encode())
        rolling.update(digest_of(path).encode())
        files += 1
        size += path.stat().st_size
    return {"present": True, "files": files, "bytes": size,
            "digest": "sha256:" + rolling.hexdigest()}


def chain_state(db) -> Dict[str, Any]:
    """Where the chain is, and whether it verifies. Both, always.

    The head alone would let a backup record a position in a chain that was
    already broken when it was taken — and the restore would then report a
    break that predated it, sending somebody to investigate the wrong day.
    """
    evidence = evidence_for(db)
    seq, chain_hash = evidence.head()
    verified = evidence.verify_chain()
    anchors = {}
    try:
        anchors = evidence.verify_against_anchors()
    except Exception as exc:                     # pragma: no cover - defensive
        anchors = {"available": False, "detail": str(exc)}
    return {"seq": seq, "chain_hash": chain_hash,
            "verifies": bool(verified.get("valid")),
            # `reason` and `broken_at` rather than a `detail` the verifier does
            # not emit. The first version read a key that is never there, so a
            # refusal printed a blank line where the reason belonged — a
            # refusal nobody can act on is most of the way to no refusal.
            "broken_at": verified.get("broken_at"),
            "reason": verified.get("reason", ""),
            "verification": verified, "anchors": anchors}


def write_manifest(target: pathlib.Path, payload: Dict[str, Any]) -> pathlib.Path:
    path = target / MANIFEST
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def read_manifest(source: pathlib.Path) -> Dict[str, Any]:
    path = source / MANIFEST
    if not path.is_file():
        raise SystemExit(
            f"{source} has no {MANIFEST}, so this is not a MAYA backup — or it "
            f"is one taken by copying files, which is the case these tools "
            f"exist to distinguish. Without the manifest there is no recorded "
            f"chain head to verify the restore against.")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as unreadable:
        raise SystemExit(
            f"{path} is not readable JSON ({unreadable}). A manifest that "
            f"cannot be parsed is a backup that cannot be verified, and a "
            f"restore that proceeded would be copying bytes with nothing to "
            f"check them against.") from unreadable

    # Every section the restore reads, checked HERE rather than found missing
    # halfway through.
    #
    # A truncated manifest raised a bare `KeyError('chain')` from the middle of
    # the restore — after the stores had already been copied over the target.
    # An operator in the middle of a recovery was handed a dictionary key and
    # nothing else: not which file was wrong, not what to do, and not the fact
    # that the target had already been partly overwritten.
    missing = [section for section in
               ("manifest_version", "chain", "database", "stores")
               if section not in manifest]
    if missing:
        raise SystemExit(
            f"{path} is missing {', '.join(missing)}, so it cannot describe "
            f"the backup it sits in. Nothing has been restored. Use the "
            f"manifest written with this backup, or take a fresh one — a "
            f"manifest assembled by hand cannot record the chain head the "
            f"restore is verified against.")
    return manifest


def paths_from(cfg) -> Dict[str, pathlib.Path]:
    out: Dict[str, pathlib.Path] = {}
    for name, key in STORES:
        configured = cfg.get(key, None)
        if configured:
            out[name] = pathlib.Path(configured)
        else:
            out[name] = pathlib.Path(cfg.get("data.dir", "./data")) / name
    return out


def say(message: str) -> None:
    print(f"  {message}", flush=True)


def stamp() -> float:
    return time.time()
