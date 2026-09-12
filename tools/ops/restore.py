#!/usr/bin/env python3
"""
MAYA — Model & AI Lifecycle Assurance
Copyright © 2026 Ashutosh Sinha <ajsinha@gmail.com>. All rights reserved.
Proprietary and confidential. See LICENSE and NOTICE at the repository root.

Restore a MAYA instance, and prove the audit trail came back.

    python -m tools.ops.restore --from /backups/2026-09-12 --config application.yaml

## Why a restore tool exists at all, when `cp -r` would move the bytes

Because moving the bytes is not the hard part, and it is not the part anybody is
worried about at three in the morning. The question is:

> **Is the evidence chain the one we backed up, and does it still verify?**

Two different questions, and this answers both. The manifest recorded the chain
head at backup time — a sequence number and a hash — so after the copy this
walks the restored chain and compares. A restore that produces a chain
verifying *against itself* but sitting at a different head is a restore of a
**different backup**, or of a database somebody wrote to in between, and
nothing about the filesystem would have told you.

Then it checks the **anchors**, which is the only verification an attacker with
the database cannot defeat — and the one most likely to be missing, because the
WORM store is the store a hand-written backup script forgets.

## What it refuses

**It will not restore over a database that has rows.** The act is
irreversible and the alternative — a merge — is not a thing a register can
meaningfully do: two chains do not interleave. Restore into an empty location
and move the configuration, which is a step somebody performs deliberately.

## And it measures

`NFR-AVAIL-003` asks for RTO 4 hours and RPO 15 minutes, RPO **0** for the
evidence chain, and `docs/03` has said *not demonstrated* since the first
release. A restore reports its own wall clock and the estate it restored, which
is a measured RTO for that estate on that hardware rather than a target — the
first half of that row becoming a result. The RPO half is a property of how
often you run `backup.py`, which is not this tool's to claim.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys

from tools.ops.common import (STORES, chain_state, dialect_of, digest_of,
                              load_config, open_database, paths_from,
                              read_manifest, say, stamp, tree_digest)


def run(source: str, config: str, force: bool = False) -> dict:
    origin = pathlib.Path(source)
    manifest = read_manifest(origin)
    cfg = load_config(config)
    started = stamp()

    if not manifest["chain"].get("verifies"):
        say("! this backup records a chain that did NOT verify when it was "
            "taken. Restoring it restores the break, which is what it is for "
            "— but nothing below should be read as the chain being sound")

    dialect = dialect_of(cfg)
    if not dialect.startswith("sqlite"):
        raise SystemExit(
            f"this configuration points at {dialect}. Restore the dump with "
            f"`pg_restore`, then run `python -m tools.ops.verify` to check the "
            f"chain head against this backup's manifest — which is the half "
            f"`pg_restore` does not do.")

    db = open_database(cfg)
    existing = db.query_one("SELECT COUNT(*) AS n FROM evidence_node") \
        if _has_table(db, "evidence_node") else {"n": 0}
    if (existing or {}).get("n") and not force:
        raise SystemExit(
            f"refusing to restore over a database holding "
            f"{existing['n']} evidence node(s). Two chains do not interleave, "
            f"so there is no merge here and the act is irreversible.\n\n"
            f"Restore into an empty location and move the configuration, or "
            f"pass --force if destroying this instance is what you mean.")

    say(f"restoring the four stores from {origin}")
    targets = paths_from(cfg)
    restored = {}
    for name, _key in STORES:
        held = manifest["stores"].get(name) or {}
        if not held.get("present"):
            say(f"{name}: absent from the backup, so absent here")
            restored[name] = {"present": False}
            continue
        destination = targets[name]
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(origin / name, destination)
        seen = tree_digest(destination)
        restored[name] = {**seen, "expected": held.get("digest"),
                          "matches": seen["digest"] == held.get("digest")}
        say(f"{name}: {seen['files']} file(s), "
            f"{'digest matches' if restored[name]['matches'] else 'DIGEST DIFFERS'}")

    database = pathlib.Path(str(db.url).replace("sqlite:///", ""))

    # Let go of the target BEFORE writing over it, and take its write-ahead log
    # with it. Both halves of that were learned by this tool catching itself on
    # its first round trip.
    #
    # The emptiness check above opens a connection, which creates the file and
    # its `-wal`/`-shm` siblings. Replacing `maya.db` underneath a live handle
    # and then reading through a NEW one gave a chain at seq 0 — every byte of
    # the restore correct, the digest matching, and the audit trail apparently
    # empty. A stale write-ahead log replayed over a restored database is the
    # quietest way to lose a chain there is, and a restore that reported
    # success while doing it is exactly what this file exists to prevent.
    db.engine.dispose()
    for sidecar in (f"{database}-wal", f"{database}-shm"):
        pathlib.Path(sidecar).unlink(missing_ok=True)

    database.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origin / manifest["database"]["file"], database)
    same = digest_of(database) == manifest["database"]["digest"]
    say(f"database: {'digest matches' if same else 'DIGEST DIFFERS'}")

    # Re-open: the file underneath the old handle has been replaced.
    db = open_database(cfg)
    after = chain_state(db)
    expected = manifest["chain"]
    agrees = (after["seq"] == expected["seq"]
              and after["chain_hash"] == expected["chain_hash"])

    out = {
        "restored_from": str(origin), "took_seconds": round(stamp() - started, 2),
        "stores": restored,
        "database_digest_matches": same,
        "chain": {
            "expected_seq": expected["seq"], "seq": after["seq"],
            "expected_hash": expected["chain_hash"],
            "chain_hash": after["chain_hash"],
            "head_agrees": agrees, "verifies": after["verifies"],
        },
        "anchors": after["anchors"],
        "detail": _detail(agrees, after, restored, same),
    }
    say(out["detail"])
    return out


def _detail(agrees, after, restored, database_matches) -> str:
    if not after["verifies"]:
        return ("the restored chain DOES NOT VERIFY. Do not put this instance "
                "in front of anybody: every governance decision here is read "
                "off that chain, and a broken one does not fail closed — it "
                "reads as no evidence, which is indistinguishable from nothing "
                "having happened")
    if not agrees:
        return ("the restored chain verifies against ITSELF but sits at a "
                "different head from the one this backup recorded. That is a "
                "restore of a different backup, or of a database somebody "
                "wrote to in between — the bytes are fine and the history is "
                "not the one you asked for")
    if not database_matches or any(
            s.get("present") and not s.get("matches") for s in restored.values()):
        return ("the chain is intact and at the recorded head, and at least "
                "one store's digest differs from the manifest. Something was "
                "changed between the backup and here; the register is sound "
                "and its artifacts may not be")
    anchors = after["anchors"] or {}
    if anchors.get("agrees") == 0 and anchors.get("anchors"):
        return ("the chain verifies and is at the recorded head, and it does "
                "NOT agree with the anchors. The anchors are the one check a "
                "database cannot forge, so this disagreement is the one to "
                "act on")
    return ("restored: the chain verifies, sits at the head this backup "
            "recorded, and every store's digest matches. The audit trail is "
            "the one that was backed up")


def _has_table(db, name: str) -> bool:
    try:
        db.query_one(f"SELECT 1 FROM {name} LIMIT 1")
        return True
    except Exception:
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.ops.restore",
        description="Restore a MAYA instance and verify the audit trail.")
    parser.add_argument("--from", required=True, dest="source")
    parser.add_argument("--config", required=True)
    parser.add_argument("--force", action="store_true",
                        help="restore over an instance that holds evidence")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    out = run(args.source, args.config, args.force)
    if args.as_json:
        print(json.dumps(out, indent=2, sort_keys=True))
    # A restore whose chain is wrong must not exit 0: this runs in a recovery
    # script, and the script's next step is usually "start serving".
    return 0 if out["chain"]["verifies"] and out["chain"]["head_agrees"] else 1


if __name__ == "__main__":                       # pragma: no cover
    sys.exit(main())
