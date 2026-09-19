# Audit chain break and custody anchor verification

For the administrator or `techops` engineer when the audit log stops verifying, when custody
verification says `TAMPERING`, or when anchoring is refused. The audit log is hash-chained and
append-only: each entry's hash covers the previous entry's, and a database trigger refuses
updates and deletes. Custody anchors pin the chain's head outside the database — signed,
appended to a file, sent to webhook subscribers, optionally timestamped by an RFC 3161
authority — because a consistent rewrite, with every later hash recomputed, still verifies as
a chain. The chain catches clumsy tampering; only the anchors catch careful tampering.

**Treat both as a security incident until shown otherwise.** The procedures below preserve
evidence first and restore service second. Nothing in MAYA "repairs" a chain: rewriting it is
exactly what the anchors exist to detect.

## Symptoms

- The chain does not verify — `GET /api/v1/audit/verify`, the health page's `audit_chain`, and
  `admin verify-integrity` (which then exits 1 with `audit chain ok: False`):

  ```json
  {"ok": false, "checked": <n>, "broken_at": <seq>}
  ```

- Custody verification (`GET /api/v1/custody/verify`, or *Verify chain and anchors* on
  `/admin/custody`) reports a verdict other than `chain and anchors agree`:
  - `TAMPERING: the chain is broken` — the chain itself fails, as above;
  - `TAMPERING: <k> anchor(s) contradict the chain` — the chain verifies, but anchors disagree
    with it. Each entry in `broken` lists its `problems`:
    - *"the live chain no longer has this head at this position: history before it was
      rewritten"*
    - *"the anchor's signature does not verify"*
    - *"the anchor is missing from the append-only file"*
    - *"timestamp token: <detail>"*, for instance *"the TSA's signature does not verify: …"*
- Anchoring is refused, on demand and every hour by the scheduler (which logs *scheduled task
  custody.anchor failed*):

  ```json
  {"type": "validation_failed", "title": "ValidationFailed", "status": 422,
   "detail": "The audit chain is broken; anchoring it would certify tampering",
   "context": {"ok": false, "checked": <n>, "broken_at": <seq>}}
  ```

- An estate import ends with `maya: ValidationFailed: The imported audit chain does not
  verify` — and has nonetheless committed every row ([schema rebuild](schema-rebuild.md)).
- Startup refuses a custody configuration:
  *"custody.anchor.methods names rfc3161 but custody.anchor.tsa_url is not set"*, or
  *"custody.anchor.tsa_ca_file needs the CA file to exist and openssl to be installed"*.

## Diagnosis

```bash
curl -s "$MAYA_URL/api/v1/audit/verify"   -H "Authorization: Bearer $MAYA_API_KEY"
curl -s "$MAYA_URL/api/v1/custody/verify" -H "Authorization: Bearer $MAYA_API_KEY"
curl -s "$MAYA_URL/api/v1/custody/anchors" -H "Authorization: Bearer $MAYA_API_KEY"
# anchors (newest first), the configured methods, anchor file, TSA URL and CA file,
# and the public key and key id anchors are signed with
```

Then, **read-only**, against the database itself:

```bash
# Is the append-only trigger still there? Missing means someone with DDL rights removed it.
python -c "import sqlite3,sys; c=sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True); print(c.execute(\"SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='audit_events'\").fetchall())" "$MAYA_HOME/maya.db"
# expected: [('audit_events_no_update',), ('audit_events_no_delete',)]
# PostgreSQL: SELECT tgname FROM pg_trigger WHERE tgrelid = 'audit_events'::regclass AND NOT tgisinternal;
#             expected: audit_events_no_update (it covers UPDATE and DELETE)

# The entries around the break
python -c "import sqlite3,sys; c=sqlite3.connect(f'file:{sys.argv[1]}?mode=ro', uri=True); [print(r) for r in c.execute('SELECT seq, at, actor, action, object_ref FROM audit_events WHERE seq BETWEEN ? AND ?', (int(sys.argv[2])-2, int(sys.argv[2])+2))]" "$MAYA_HOME/maya.db" <broken_at>
```

Compare the entries with a backup of the database taken before the break, and each
contradicted anchor with its line in the anchor file (`custody.anchor.file`, default
`<storage.root>/anchors.jsonl`; one JSON object per line, keys `at`, `head`, `seq`,
`signature`) and with any copy your webhook subscribers hold of the `audit.anchored` event.
Three independent witnesses that agree with each other and not with the database are the
answer.

### Checking a timestamp token by hand

With `custody.anchor.tsa_ca_file` set, MAYA checks the authority's signature itself, at anchor
time and at every verification ([ADR-028](../adr/ADR-028-tsa-signature-checked-against-its-ca.md)).
Without it, check it yourself. The token's imprint is the head hash itself, so pass it as a
digest:

```bash
# Extract the token of the anchor at sequence <seq>, and print its head
curl -s "$MAYA_URL/api/v1/custody/anchors" -H "Authorization: Bearer $MAYA_API_KEY" \
  | python -c "import base64,json,sys; a=[x for x in json.load(sys.stdin)['anchors'] if x['seq']==int(sys.argv[1])][0]; open('token.tsr','wb').write(base64.b64decode(a['tsa_token'])); print(a['head_hash'])" <seq>
openssl ts -verify -digest <head_hash> -in token.tsr -CAfile tsa-ca.pem
# Verification: OK
```

**Do not use the command MAYA suggests.** The anchor's recorded detail says *"Verify the TSA's
signature with 'openssl ts -verify -data <head> -in <token> -CAfile <tsa>'"*. `-data` hashes
the file it is given, so it fails with `message imprint mismatch` whether the file holds the
head as hex or as bytes — a genuine token looks forged. That hint is a defect.

## Steps

1. **Preserve the evidence before anything else.** Copy the database (see the
   [restore drill](restore-drill.md) for an online SQLite backup), the anchor file, and the
   application logs, and keep them apart from the running system.
2. **Restore the trigger if it is missing** — only after the copy. The DDL is in the shipped
   schema file (`maya/persistence/schema/<dialect>.sql`, the `CREATE TRIGGER` statements at
   the end). Whoever removed it had rights they should not have; find out who.
3. **Decide what the record of truth is.** A backup from before the break, whose chain verifies
   and whose head matches an anchor, is a verifiable earlier state. Restoring it loses
   everything recorded since, and that loss has to be reconciled from the logs and the
   webhook subscribers' copies of events. A tampered database is never "fixed" by recomputing
   hashes — that is the attack, not the remedy.
4. **Anchoring stays refused while the chain is broken**, deliberately. It resumes on its own
   once MAYA runs on a database whose chain verifies.
5. **An anchor contradiction with an intact chain** is the case anchors exist for: the history
   before that anchor was rewritten and every later hash recomputed. Proceed as in 3, taking
   the anchor file and subscribers' events as the reference.
6. **A signature that does not verify**: the anchor row — its sequence, head or time — was
   altered after it was signed. The check uses the public key stored in the anchor itself, so
   also compare every anchor's `signature.key_id` with the `key_id` the anchors list reports
   for MAYA's current key. An anchor signed by a key MAYA does not hold verifies, and proves
   nothing. (A restore that lost `keys/` gives later anchors a new `key_id` legitimately; know
   when that happened.)
7. **An anchor missing from the file**: the file was truncated, replaced, or `custody.anchor.file`
   now points somewhere else. Put the file on WORM or off-host storage; on the database's disk it
   only raises the bar.

## Verification

- `GET /api/v1/audit/verify` returns `"ok": true`, and `checked` equals the number of entries.
- `GET /api/v1/custody/verify` returns `"verdict": "chain and anchors agree"`.
- `POST /api/v1/custody/anchor` (or *Anchor now* on `/admin/custody`) succeeds.

## What this does not reach

- **`admin verify-integrity` does not check anchors.** A careful rewrite passes it with `audit
  chain ok: True`; only custody verification catches it. Run both.
- **Anchors are only as external as you make them.** With the default methods
  (`signature,file,event`), the anchor file on the same disk as the database, and no webhook
  subscriber, one person with root on that host can rewrite the database, the anchors table
  and the file together. An off-host file, subscribers outside that person's control, or an
  RFC 3161 authority are what make the anchors independent.
- **The signature is not pinned to MAYA's key.** Custody verification checks each anchor's
  signature against the public key recorded in that anchor, so an anchors table rewritten and
  re-signed with any key passes that check. It is compared with nothing. Until it is, the
  `signature` method adds little that the file and the event do not; compare `key_id`s by hand
  as in step 6.
- **The chain is checked from its start.** Verification walks every entry; on the health page it
  is cached for `health.audit_verify_seconds` (60) because the walk grows with the log. How long
  it takes on a large log has not been measured.
- **The PostgreSQL commands here were not run** when this runbook was written.
