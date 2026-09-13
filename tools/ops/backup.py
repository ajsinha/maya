#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Back up a MAYA instance, and refuse to call a broken chain a backup.

    python -m tools.ops.backup --config application.yaml --out /backups/2026-09-12

See `tools/ops/common.py` for what a governance backup is over and above a file
copy, and which five stores an instance actually lives in.

## The one decision in this file

**The evidence chain is verified BEFORE anything is copied, and a chain that
does not verify refuses the backup.**

The tempting alternative is to copy first and report afterwards, which produces
a backup of a broken chain. Restored six months later it is indistinguishable
from a chain that broke during the restore, and the investigation starts on the
wrong day. Worse, it is a backup somebody will *use*: the alternative to
restoring it is having nothing, so it gets restored, and the break enters the
record as though it had always been there.

`--even-if-broken` exists for the case where a broken chain is exactly what you
need to preserve — a forensic copy before repair. It writes `"verifies": false`
into the manifest and prints what broke, so the copy is honest about what it is.

## What a backup consistent enough to restore actually needs

SQLite is copied with **`VACUUM INTO`**, which takes a transactionally
consistent snapshot of a live database. A `cp` of a file being written produces
a torn page and an unreadable database, and it produces one *occasionally* —
which is the worst possible failure rate for a thing nobody tests until they
need it.

The other four stores are append-mostly, and the ordering is deliberate: they
are copied **before** the database, so anything the register refers to is
already captured when the chain head is recorded. The reverse order can produce
a manifest naming an artifact digest the backup does not contain.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

from tools.ops.common import (MANIFEST_VERSION, STORES, chain_state,
                              dialect_of, digest_of, load_config,
                              open_database,
                              paths_from, say, stamp, tree_digest,
                              write_manifest)


def run(config: str, out: str, even_if_broken: bool = False) -> dict:
    cfg = load_config(config)
    target = pathlib.Path(out)
    if target.exists() and any(target.iterdir()):
        raise SystemExit(
            f"{target} is not empty. A backup writes into a fresh directory so "
            f"that a partial copy can never be mistaken for a complete one — "
            f"there is no merging here, deliberately.")
    target.mkdir(parents=True, exist_ok=True)

    dialect = dialect_of(cfg)
    if not dialect.startswith("sqlite"):
        # The remediation names an endpoint rather than a tool, because the
        # tool it used to name was never written. `tools.ops.verify` appeared
        # in this message and in `restore.py`'s, and neither has ever existed
        # in this tree: an operator on PostgreSQL — the one reader who reaches
        # this line — was told to run a command that answers
        # `No module named tools.ops.verify`. A remediation pointing at a
        # phantom is worse than none, because it reads as though somebody
        # checked. `tests/test_backup_restore.py` now sweeps every `python -m`
        # in `tools/` and refuses one that will not import.
        raise SystemExit(
            f"this instance is on {dialect}, and these tools do not back up "
            f"PostgreSQL. `pg_dump` and `pg_basebackup` exist, are better than "
            f"anything here, and are what you already have.\n\n"
            f"Take the dump, then copy the four stores it does not cover — "
            f"artifacts, attachments, delta and worm — and record the chain "
            f"head beside them: `GET /api/v1/evidence/chain` returns the head "
            f"this manifest would have carried, which is what a restore is "
            f"then checked against.")

    db = open_database(cfg)
    started = stamp()
    say("verifying the evidence chain before copying anything")
    chain = chain_state(db)
    if not chain["verifies"]:
        detail = (f"broken at seq {chain['broken_at']}: {chain['reason']}"
                  if chain.get("reason") else "the verifier reported no reason")
        if not even_if_broken:
            raise SystemExit(
                f"refusing to take this backup: the evidence chain does not "
                f"verify.\n\n  {detail}\n\n"
                f"A backup of a broken chain is restored months later and is "
                f"indistinguishable from a chain that broke during the "
                f"restore, so the investigation starts on the wrong day. Fix "
                f"the chain, or pass --even-if-broken to take a forensic copy "
                f"that says so in its manifest.")
        say(f"! the chain does NOT verify, and --even-if-broken was given: "
            f"{detail}")
    else:
        say(f"chain verifies to seq {chain['seq']}")

    stores = {}
    sources = paths_from(cfg)
    for name, _key in STORES:
        source = sources[name]
        if not source.exists():
            say(f"{name}: absent at {source} — recorded as absent, not skipped")
            stores[name] = {"present": False, "files": 0, "bytes": 0,
                            "digest": None, "source": str(source)}
            continue
        shutil.copytree(source, target / name, dirs_exist_ok=False)
        stores[name] = {**tree_digest(target / name), "source": str(source)}
        say(f"{name}: {stores[name]['files']} file(s), "
            f"{stores[name]['bytes'] / 1e6:.1f} MB")

    # Last, and consistently. See the module docstring.
    database = target / "maya.db"
    db.execute("VACUUM INTO :path", {"path": str(database)})
    say(f"database: {database.stat().st_size / 1e6:.1f} MB, "
        f"consistent snapshot via VACUUM INTO")

    payload = {
        "manifest_version": MANIFEST_VERSION,
        "taken_at": started, "took_seconds": round(stamp() - started, 2),
        "source_url": db.url, "dialect": db.dialect,
        "chain": {k: v for k, v in chain.items() if k != "verification"},
        "chain_reason": chain.get("reason", ""),
        "database": {"file": database.name, "digest": digest_of(database),
                     "bytes": database.stat().st_size},
        "stores": stores,
        "covers": [name for name, _ in STORES] + ["database"],
        "does_not_cover": NOT_COVERED,
    }
    write_manifest(target, payload)
    # Let go of the source. A backup tool that leaves a connection open holds a
    # lock on the database it just copied, and the next thing an operator runs
    # is usually a restore.
    db.engine.dispose()
    say(f"manifest written; {payload['took_seconds']}s total")
    return payload


#: Carried in every manifest, because a backup is read by somebody who did not
#: take it and a list of what it holds is not a list of what an instance needs.
NOT_COVERED = [
    "the configuration file. It names paths, a database URL, a signing key and "
    "a session secret, and a backup that carried it would be a backup that "
    "carries credentials",
    "the warrant signing key and the session secret. Restoring an instance "
    "with different ones invalidates live descriptors and signed-in sessions, "
    "which is the correct behaviour and has to be planned for",
    "anything outside this MAYA instance — the systems of record its attested "
    "facts came from, and the engines that ran its models",
    "encryption and transport. Where this goes and who may read it are "
    "decisions with a retention schedule and a legal basis attached",
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.ops.backup",
        description="Back up a MAYA instance, chain verified first.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--even-if-broken", action="store_true",
                        help="take a forensic copy of a chain that does not "
                             "verify, and say so in the manifest")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    payload = run(args.config, args.out, args.even_if_broken)
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":                       # pragma: no cover
    sys.exit(main())
