# Integrity drift

For the administrator or `techops` engineer told that a sealed pin no longer matches its
seal. A pin is MAYA's promise that the same reference returns the same bytes forever; drift
means that promise is broken for the pins listed, and it is an incident — not a warning to be
cleared. Every model trained on, and every warrant sealed over, a drifted pin now rests on
bytes nobody can vouch for.

## Symptoms

- `python -m maya.cli admin verify-integrity` exits 1:

  ```text
  <n> pin(s) checked; drift: <k>; audit chain ok: True
  ```

- Every administrator has an inbox notification *"<k> pin(s) failed integrity verification"*
  (kind `integrity_drift`), and the run is audited — and emitted as an event — as
  `integrity.verified` with `{"pins": <n>, "drift": <k>}`.
- `/admin/storage`, after *Verify integrity now*, flashes
  *"Integrity verified: <n> pin(s), <k> with drift."*
- Reading a feature-set pin that is not stored fails with `integrity_error`:

  ```text
  Replaying this pin from its member pins did not reproduce its sealed content (sealed <12 hex>,
  replayed <12 hex>); it is not served
  ```

## Diagnosis

```bash
python -m maya.cli --json admin verify-integrity > integrity.json
python -c "import json; r=json.load(open('integrity.json')); [print(d) for d in r['drift']]"
```

Each drifted entry is one of three shapes, and they mean different things:

| Entry | What it means | Usual cause |
|---|---|---|
| `{"pin": "<ns>/<name>#<series>/<date>", "ok": false, "expected": "<hash>", "actual": "<hash>", "rows": <n>}` | The stored bytes were read and hash differently | A file under `lake/` was changed in place, or `storage.root` was restored from a different moment than the database |
| `{"pin": …, "ok": false, "error": "<message>"}` | The pin could not be read at all | Files under `lake/` missing or unreadable; a table another tool upgraded (see the [`maya_delta` runbook](maya-delta-backend-fallback.md)) |
| `{"pin": …, "ok": false, "expected": …, "actual": …, "replayed": true}` | A feature-set pin sealed under `materialize_policy` `on_demand` or `never` was replayed from its member pins and did not reproduce | A member pin drifted (it will be in the list too), or **this version of MAYA resolves the same inputs differently** — typically just after an upgrade |

Then establish when it started:

```bash
# Earlier verification runs, and what changed the lake since the last clean one
curl -s "$MAYA_URL/api/v1/audit?action=integrity.verified" -H "Authorization: Bearer $MAYA_API_KEY"
curl -s "$MAYA_URL/api/v1/audit?action=lake.maintained"    -H "Authorization: Bearer $MAYA_API_KEY"
# Who depends on a drifted pin
curl -s "$MAYA_URL/api/v1/lineage?root=maya://feature/<ns>/<name>%23<series>/<date>&direction=down&depth=8" \
  -H "Authorization: Bearer $MAYA_API_KEY"
```

On disk, a feature pin lives in the Delta table `<storage.root>/lake/pins/<namespace>/<name>/`,
one `_fragment=<hash>` partition per fragment it lists; a feature-set pin in
`<storage.root>/lake/fspins/<namespace>/<name>/`.

## Steps

1. **Do not paper over it.** Do not re-pin under the same name and date (it is refused anyway),
   and do not retire the pin to make the count go to zero: retirement hides the evidence and
   leaves every consumer where it was. Tell the owners of the objects the lineage query named.
2. **Stored bytes changed or missing.** Restore the pin's table directory — the whole
   `lake/pins/<namespace>/<name>/`, `_delta_log` included, never loose Parquet files — from the
   most recent backup in which it verifies. Prove that first on a scratch copy, as in the
   [restore drill](restore-drill.md). Fragments are content-addressed and never rewritten in
   place, so a good backup holds exactly the right bytes; but a table directory older than the
   newest pin sealed into it loses that pin's fragments, so choose a backup newer than it.
3. **A replayed pin after an upgrade.** The new version resolves those inputs differently, so
   it will never serve that pin. Nothing re-seals it — that would be rewriting a sealed record.
   Either go back to the previous version (restore the database and code, per the
   [restore drill](restore-drill.md)) or accept that the pin is unavailable under this version
   and record why. Report the resolver change as a defect: it changed a published result.
4. **A replayed pin whose member drifted.** Fix the member first (step 2); the set pin
   replays again once its member verifies.
5. Whatever the cause, find out how bytes under `storage.root` changed. MAYA never rewrites a
   sealed fragment; something else did.

## Verification

- `python -m maya.cli admin verify-integrity` exits 0: `drift: 0`.
- The consumers you notified have been told which of their results rested on the drifted
  pin, and for how long.

## What this does not reach

- **Only sealed pins are checked.** Retired pins, raw ingested data (`lake/raw/`), blobs
  (artifacts, PDFs, bundles, estates) and the keys are not re-hashed by this command.
- **It does not check custody anchors.** A consistent rewrite of the audit log — history changed
  and every later hash recomputed — passes `verify-integrity` with `audit chain ok: True`. Only
  `GET /api/v1/custody/verify` catches that; see the
  [audit chain and custody runbook](audit-chain-and-custody.md).
- The check runs synchronously in the request and reads every sealed pin. How long it takes on
  a large estate has not been measured.
