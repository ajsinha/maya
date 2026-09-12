# Operating a MAYA instance

Two tools, and the reason they exist is one sentence:

> A filesystem snapshot copies the bytes correctly and cannot tell you whether
> the **evidence chain** survived.

That matters more here than in most systems. Every governance decision in MAYA
is read off the chain — who approved what, who may act next, whether a developer
approved their own version — and a broken chain **does not fail closed**. It
reads as *no evidence*, which is indistinguishable from *nothing happened*.

```bash
python -m tools.ops.backup  --config application.yaml --out /backups/2026-09-12
python -m tools.ops.restore --from /backups/2026-09-12 --config application.yaml
```

## The five stores

An instance is not one thing on disk. Miss any of these and the restore starts,
serves pages, and is wrong:

| | What is in it | Losing it means |
|---|---|---|
| the control database | the register, and the evidence chain | everything |
| `data/artifacts/` | content-addressed model artifacts | digests in the register that resolve to nothing |
| `data/attachments/` | uploaded documents | holes in the documentation graph, and search that finds less |
| `data/delta/` | features, snapshots, telemetry, monitoring | training sets that cannot be reproduced, and `L-19` unanswerable |
| `data/worm/` | the chain anchors | the only check an attacker with the database cannot defeat |

The last is the one a hand-written backup script forgets, and its absence is the
least visible: the chain still verifies **against itself** without it.

## What they refuse

**A backup of a chain that does not verify.** Copying first and reporting
afterwards produces a backup that, restored six months later, is
indistinguishable from a chain that broke during the restore — so the
investigation starts on the wrong day. Worse, it is a backup somebody will
*use*, because the alternative is having nothing. `--even-if-broken` takes a
forensic copy and writes `"verifies": false` into the manifest.

**A restore over a database that holds evidence.** Two chains do not interleave,
so there is no merge, and the act is irreversible. Restore into an empty
location and move the configuration.

**PostgreSQL.** `pg_dump` and `pg_basebackup` exist, are better than anything
here, and are what an operator already has. The tool refuses and names them —
without needing the driver installed to do so.

## What a restore actually checks

Three things, in order, and the second is the one no other tool does:

1. Every store's digest against the manifest.
2. **The chain head against the head the backup recorded.** A chain verifying
   against *itself* at a different head is a restore of a different backup, or
   of a database somebody wrote to in between. The bytes are fine and the
   history is not the one you asked for.
3. The anchors, which a database cannot forge.

It exits **non-zero** when the chain is wrong, because this runs inside a
recovery script whose next step is usually *start serving*.

## And it measures

`NFR-AVAIL-003` asks for RTO 4 hours and RPO 15 minutes. A restore reports its
own wall clock for the estate it restored, which is a **measured** RTO on that
hardware rather than a target. The RPO half is a property of how often you run
`backup.py`, and is not this tool's to claim.

## What is not covered, and is in every manifest

The configuration file (it carries credentials), the warrant signing key and
session secret (restoring with different ones invalidates live descriptors and
sessions — correct, and something to plan for), anything outside this instance,
and encryption or transport. A backup contains personal data from the feature
store; where it goes and who may read it are decisions with a retention schedule
and a legal basis attached, and a tool that quietly wrote them somewhere would be
making them.
